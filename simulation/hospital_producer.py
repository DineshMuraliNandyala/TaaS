#!/usr/bin/env python3
"""
Hospital IoT Telemetry Simulator
─────────────────────────────────
Streams synthetic patient vitals to Aiven Kafka `clinical_telemetry` topic.
Connects via SASL_SSL + SCRAM-SHA-512 with Aiven CA certificate.

Patient roster:
  PT-001  Cardiology/1A  normal baseline
  PT-002  Cardiology/1B  normal baseline
  PT-003  ICU/2A         elevated baseline
  PT-004  ICU/2B         normal baseline
  PT-005  ICU/2C         critical baseline — enters shock deterioration
                         every ~30 cycles to reliably trigger CEP alerts

Run from project root:
    python simulation/hospital_producer.py
"""
import json
import random
import signal
import sys
import time
from datetime import datetime, timezone
from typing import Optional

from confluent_kafka import Producer, KafkaException
from pydantic import ValidationError

sys.path.insert(0, ".")

from backend.src.config import settings
from backend.src.logger import get_logger
from backend.src.models.telemetry import TelemetryEvent, VitalSigns

log = get_logger(__name__)

# ── Patient Roster ───────────────────────────────────────────────────────────

PATIENTS = [
    {
        "patient_id": "PT-001",
        "ward": "Cardiology",
        "bed": "1A",
        "baseline": "normal",
    },
    {
        "patient_id": "PT-002",
        "ward": "Cardiology",
        "bed": "1B",
        "baseline": "normal",
    },
    {
        "patient_id": "PT-003",
        "ward": "ICU",
        "bed": "2A",
        "baseline": "elevated",
    },
    {
        "patient_id": "PT-004",
        "ward": "ICU",
        "bed": "2B",
        "baseline": "normal",
    },
    {
        "patient_id": "PT-005",
        "ward": "ICU",
        "bed": "2C",
        "baseline": "critical",  # periodic deterioration episodes
    },
]

NURSING_NOTES_POOL = [
    "Patient resting comfortably, no complaints.",
    "Patient reports chest tightness since morning.",
    "Post-op day 2, wound site clean and dry.",
    "Increased agitation noted, sedation reviewed.",
    "Family present at bedside, patient appears anxious.",
    "Urine output reduced over last 2 hours, monitoring.",
    "Patient desaturating on exertion, repositioned.",
    None, None, None, None,  # majority of readings have no note
]


# ── Vital Sign Generation ────────────────────────────────────────────────────

def _build_vitals(baseline: str, deteriorating: bool = False) -> dict:
    """
    Generate plausible vital signs based on patient baseline and state.
    Deteriorating vitals are calibrated to trigger the Shock Pattern CEP rule:
      HR > 100 AND SBP < 100 AND SpO2 < 95%  →  CRITICAL alert
    """
    if deteriorating:
        return {
            "heart_rate_bpm":       random.randint(118, 145),
            "systolic_bp_mmhg":     random.randint(72, 92),
            "diastolic_bp_mmhg":    random.randint(45, 60),
            "spo2_percent":         round(random.uniform(87.0, 93.0), 1),
            "respiratory_rate_rpm": random.randint(26, 36),
            "temperature_celsius":  round(random.uniform(38.6, 39.9), 1),
        }

    profiles = {
        "critical": {
            "heart_rate_bpm":       random.randint(98, 118),
            "systolic_bp_mmhg":     random.randint(88, 108),
            "diastolic_bp_mmhg":    random.randint(56, 70),
            "spo2_percent":         round(random.uniform(90.0, 94.5), 1),
            "respiratory_rate_rpm": random.randint(19, 25),
            "temperature_celsius":  round(random.uniform(37.6, 38.4), 1),
        },
        "elevated": {
            "heart_rate_bpm":       random.randint(82, 102),
            "systolic_bp_mmhg":     random.randint(132, 158),
            "diastolic_bp_mmhg":    random.randint(86, 98),
            "spo2_percent":         round(random.uniform(94.5, 98.0), 1),
            "respiratory_rate_rpm": random.randint(15, 21),
            "temperature_celsius":  round(random.uniform(36.5, 37.4), 1),
        },
        "normal": {
            "heart_rate_bpm":       random.randint(60, 88),
            "systolic_bp_mmhg":     random.randint(112, 132),
            "diastolic_bp_mmhg":    random.randint(70, 84),
            "spo2_percent":         round(random.uniform(96.5, 99.5), 1),
            "respiratory_rate_rpm": random.randint(12, 18),
            "temperature_celsius":  round(random.uniform(36.2, 37.1), 1),
        },
    }
    return profiles.get(baseline, profiles["normal"])


# ── Kafka Producer Factory ───────────────────────────────────────────────────

def _build_producer() -> Producer:
    """
    Construct confluent-kafka Producer with Aiven SSL (mTLS) configuration.

    Aiven Kafka uses certificate-based mutual TLS auth.  Three cert files are
    required (all downloadable from the Aiven console):
      - ssl.ca.location:          CA cert — verifies the broker's certificate
      - ssl.certificate.location: client cert — proves our identity to broker
      - ssl.key.location:         client private key — signs the TLS handshake
    """
    config = {
        # ── Connection ───────────────────────────────────────────────────
        "bootstrap.servers":          settings.kafka_brokers,
        "security.protocol":          "SSL",
        "ssl.ca.location":            settings.kafka_ca_cert_path,
        "ssl.certificate.location":   settings.kafka_ssl_cert_path,
        "ssl.key.location":           settings.kafka_ssl_key_path,

        # ── Reliability ──────────────────────────────────────────────────
        "acks":                 "all",       # wait for all in-sync replicas
        "enable.idempotence":   True,        # exactly-once per partition
        "retries":              5,
        "retry.backoff.ms":     500,

        # ── Throughput (dev: low-latency mode) ───────────────────────────
        "linger.ms":            10,
        "batch.size":           16384,
        "compression.type":     "lz4",
    }
    return Producer(config)


def _delivery_callback(err, msg) -> None:
    """
    Invoked asynchronously by librdkafka for every produced message.
    Logs failures as errors and successful deliveries at debug level.
    """
    if err:
        log.error(
            "kafka_delivery_failed",
            topic=msg.topic(),
            partition=msg.partition(),
            error=str(err),
        )
    else:
        log.debug(
            "kafka_delivery_confirmed",
            topic=msg.topic(),
            partition=msg.partition(),
            offset=msg.offset(),
            key=msg.key().decode("utf-8") if msg.key() else None,
        )


# ── Producer Class ───────────────────────────────────────────────────────────

class HospitalProducer:
    """
    Manages Kafka producer lifecycle and the patient simulation loop.
    Designed for clean startup, graceful shutdown, and observable operation.
    """

    def __init__(self) -> None:
        self._producer = _build_producer()
        self._running = False
        self._stats = {"published": 0, "validation_errors": 0, "kafka_errors": 0}
        log.info(
            "producer_initialised",
            broker=settings.kafka_brokers,
            topic=settings.topic_telemetry,
            hospital_id=settings.hospital_id,
            patient_count=len(PATIENTS),
        )

    def _publish_event(self, event: TelemetryEvent) -> None:
        """Serialise a TelemetryEvent and produce it to Kafka."""
        try:
            self._producer.produce(
                topic=settings.topic_telemetry,
                key=event.patient_id.encode("utf-8"),
                value=event.model_dump_json().encode("utf-8"),
                on_delivery=_delivery_callback,
            )
            # Non-blocking poll — triggers delivery callbacks without waiting
            self._producer.poll(0)
            self._stats["published"] += 1

        except KafkaException as exc:
            self._stats["kafka_errors"] += 1
            log.error(
                "kafka_produce_error",
                patient_id=event.patient_id,
                error=str(exc),
            )
        except BufferError:
            # Producer queue full — poll briefly to drain, then retry
            log.warning(
                "producer_queue_full_backpressure",
                patient_id=event.patient_id,
            )
            self._producer.poll(1)

    def run(self, interval_seconds: float = 2.0) -> None:
        """
        Main simulation loop.
        Publishes one TelemetryEvent per patient on each cycle.
        PT-005 enters a deterioration window every 30 cycles for 5 readings,
        guaranteeing CRITICAL CEP alerts for end-to-end testing.
        """
        self._running = True
        cycle = 0
        log.info(
            "simulation_loop_started",
            interval_s=interval_seconds,
            patients=[p["patient_id"] for p in PATIENTS],
        )

        while self._running:
            cycle += 1
            # PT-005 deteriorates during cycles 1-5 of every 30-cycle window
            in_deterioration = (cycle % 30) < 5

            for patient in PATIENTS:
                is_deteriorating = (
                    patient["patient_id"] == "PT-005" and in_deterioration
                )
                raw_vitals = _build_vitals(
                    patient["baseline"],
                    deteriorating=is_deteriorating,
                )

                try:
                    event = TelemetryEvent(
                        patient_id=patient["patient_id"],
                        hospital_id=settings.hospital_id,
                        ward=patient["ward"],
                        bed_number=patient["bed"],
                        vitals=VitalSigns(**raw_vitals),
                        nursing_notes=random.choice(NURSING_NOTES_POOL),
                        is_simulated=True,
                    )
                    self._publish_event(event)
                    log.info(
                        "telemetry_published",
                        patient_id=event.patient_id,
                        hr=event.vitals.heart_rate_bpm,
                        spo2=event.vitals.spo2_percent,
                        sbp=event.vitals.systolic_bp_mmhg,
                        deteriorating=is_deteriorating,
                        cycle=cycle,
                    )

                except ValidationError as exc:
                    self._stats["validation_errors"] += 1
                    log.error(
                        "telemetry_validation_failed",
                        patient_id=patient["patient_id"],
                        errors=exc.errors(),
                    )

            # Log stats every 10 cycles
            if cycle % 10 == 0:
                log.info("producer_stats", cycle=cycle, **self._stats)

            time.sleep(interval_seconds)

    def shutdown(self) -> None:
        """Flush in-flight messages and close the producer cleanly."""
        self._running = False
        log.info("producer_shutdown_initiated", pending_flush=True)
        remaining = self._producer.flush(timeout=15)
        if remaining > 0:
            log.warning(
                "producer_flush_incomplete",
                undelivered_count=remaining,
            )
        else:
            log.info("producer_flushed_cleanly", **self._stats)


# ── Entry Point ──────────────────────────────────────────────────────────────

def main() -> None:
    producer = HospitalProducer()

    def _handle_signal(sig, _frame):
        log.info("shutdown_signal_received", signal=sig)
        producer.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    producer.run(interval_seconds=2.0)


if __name__ == "__main__":
    main()