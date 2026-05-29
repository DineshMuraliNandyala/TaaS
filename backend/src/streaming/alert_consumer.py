"""
FastAPI Background Kafka Consumer
───────────────────────────────────
Runs as an asyncio task within the FastAPI lifespan context.
Reads CriticalAlert messages from the `critical_alerts` topic,
invokes the LangGraph triage agent, and broadcasts the
TriageRecommendation to all connected WebSocket clients.

Design notes:
  - Uses confluent-kafka's Consumer directly (not Quix Streams)
    because we need a non-blocking poll loop compatible with asyncio.
  - poll() is called with timeout=0 for non-blocking reads, then
    yields to the event loop via asyncio.sleep(0.1) to prevent
    CPU spinning.
  - Agent invocation is awaited directly — LangGraph ainvoke is
    a native coroutine.
"""
import asyncio
import json
import time
from datetime import datetime, timezone
from typing import Optional

from confluent_kafka import Consumer, KafkaException, Message

from backend.src.config import settings
from backend.src.logger import get_logger
from backend.src.models.telemetry import CriticalAlert
from backend.src.models.api import WebSocketEvent

log = get_logger(__name__)


def _build_consumer() -> Consumer:
    """
    Confluent-kafka Consumer with Aiven mTLS SSL configuration.
    Separate consumer group from the CEP engine to ensure this
    consumer independently reads every alert from offset 0
    without interfering with the CEP engine's offsets.
    """
    config = {
        # ── Connection (mTLS) ────────────────────────────────────────────
        "bootstrap.servers":        settings.kafka_brokers,
        "security.protocol":        "SSL",
        "ssl.ca.location":          settings.kafka_ca_cert_path,
        "ssl.certificate.location": settings.kafka_ssl_cert_path,
        "ssl.key.location":         settings.kafka_ssl_key_path,

        # ── Consumer config ──────────────────────────────────────────────
        "group.id":                 "taas-fastapi-alert-consumer-v1",
        "auto.offset.reset":        "latest",
        "enable.auto.commit":       True,
        "auto.commit.interval.ms":  1000,
        "session.timeout.ms":       30000,
        "heartbeat.interval.ms":    10000,
    }
    return Consumer(config)


# ── Alert Throttling ──────────────────────────────────────────────────────────
# The CEP engine fires alerts every ~2s during a deterioration cycle.
# Without throttling, this burns through the Gemini free-tier quota
# (20 req/day) in seconds. We allow at most 1 triage per patient
# per ALERT_COOLDOWN_SECONDS.
ALERT_COOLDOWN_SECONDS = 60


class AlertConsumer:
    """
    Manages the Kafka consumer lifecycle inside FastAPI.
    Designed to run as a long-lived asyncio background task.
    """

    def __init__(self) -> None:
        self._consumer: Optional[Consumer] = None
        self._running = False
        self._processed = 0
        self._errors = 0
        self._skipped = 0
        # Tracks last triage timestamp per patient_id for throttling
        self._last_triage: dict[str, float] = {}

    async def start(self) -> None:
        """
        Entry point called from FastAPI lifespan.
        Initialises the consumer and starts the poll loop.
        """
        # Import here to avoid circular imports at module load time
        from backend.src.agent.triage_agent import run_triage_agent
        from backend.src.api.websocket_manager import ws_manager

        self._consumer = _build_consumer()
        self._consumer.subscribe([settings.topic_alerts])
        self._running = True

        log.info(
            "alert_consumer_started",
            topic=settings.topic_alerts,
            group="taas-fastapi-alert-consumer-v1",
        )

        loop = asyncio.get_event_loop()

        while self._running:
            try:
                # poll() is a C-extension — runs in thread pool to avoid
                # blocking the asyncio event loop. timeout=1.0 means it
                # waits up to 1 second for a message before returning None,
                # which is far more efficient than spinning with timeout=0.0
                msg = await loop.run_in_executor(
                    None,
                    lambda: self._consumer.poll(timeout=1.0),
                )

                if msg is None:
                    continue

                if msg.error():
                    self._errors += 1
                    log.error(
                        "kafka_consumer_error",
                        error=str(msg.error()),
                        error_count=self._errors,
                    )
                    continue

                # ── Process message ──────────────────────────────────────
                await self._handle_message(msg, run_triage_agent, ws_manager)


            except asyncio.CancelledError:
                log.info("alert_consumer_task_cancelled")
                break

            except KafkaException as exc:
                self._errors += 1
                log.error("kafka_exception", error=str(exc))
                await asyncio.sleep(2.0)

            except Exception as exc:
                self._errors += 1
                log.error(
                    "alert_consumer_unexpected_error",
                    error=str(exc),
                    exc_info=True,
                )
                await asyncio.sleep(2.0)

    async def _handle_message(
        self,
        msg: Message,
        run_triage_agent,
        ws_manager,
    ) -> None:
        """
        Process a single Kafka message:
        1. Deserialise and validate as CriticalAlert
        2. Broadcast raw alert to dashboard immediately
           (so the UI shows the alert before the agent finishes)
        3. Invoke the triage agent
        4. Broadcast the completed recommendation
        """
        raw = msg.value()
        if raw is None:
            return

        try:
            payload = json.loads(raw.decode("utf-8"))
            alert = CriticalAlert.model_validate(payload)
        except Exception as exc:
            self._errors += 1
            log.error(
                "alert_deserialisation_failed",
                error=str(exc),
                raw_preview=str(raw)[:200],
            )
            return

        # ── Per-patient throttle ──────────────────────────────────────────
        # Skip if we've already triaged this patient within the cooldown
        now = time.monotonic()
        last = self._last_triage.get(alert.patient_id, 0)
        if now - last < ALERT_COOLDOWN_SECONDS:
            self._skipped += 1
            log.debug(
                "alert_throttled",
                patient_id=alert.patient_id,
                seconds_since_last=round(now - last, 1),
                cooldown=ALERT_COOLDOWN_SECONDS,
                total_skipped=self._skipped,
            )
            return

        log.info(
            "alert_received_by_fastapi",
            alert_id=alert.alert_id,
            patient_id=alert.patient_id,
            severity=alert.severity.value,
        )

        # ── Step 1: Broadcast raw alert immediately ───────────────────────
        # Dashboard shows alert card before agent completes (~30s)
        await ws_manager.broadcast(
            WebSocketEvent(
                event_type="alert_received",
                payload=alert.model_dump(mode="json"),
                timestamp=datetime.now(timezone.utc),
            ).model_dump(mode="json")
        )

        # ── Step 2: Run triage agent ──────────────────────────────────────
        # Record triage timestamp BEFORE the agent call to prevent
        # concurrent alerts from also triggering during the ~30s agent run
        self._last_triage[alert.patient_id] = time.monotonic()
        recommendation = await run_triage_agent(alert)
        self._processed += 1

        if recommendation is None:
            log.error(
                "agent_returned_no_recommendation",
                alert_id=alert.alert_id,
                patient_id=alert.patient_id,
            )
            return

        # ── Step 3: Broadcast completed recommendation ────────────────────
        await ws_manager.broadcast(
            WebSocketEvent(
                event_type="triage_recommendation",
                payload=recommendation.model_dump(mode="json"),
                timestamp=datetime.now(timezone.utc),
            ).model_dump(mode="json")
        )

        log.info(
            "triage_recommendation_broadcast",
            alert_id=alert.alert_id,
            patient_id=alert.patient_id,
            urgency=recommendation.urgency_level.value,
            ws_clients=ws_manager.connection_count,
            total_processed=self._processed,
        )

    def stop(self) -> None:
        """Graceful shutdown — called from FastAPI lifespan on exit."""
        self._running = False
        if self._consumer:
            self._consumer.close()
        log.info(
            "alert_consumer_stopped",
            total_processed=self._processed,
            total_errors=self._errors,
        )


# Module-level singleton
alert_consumer = AlertConsumer()