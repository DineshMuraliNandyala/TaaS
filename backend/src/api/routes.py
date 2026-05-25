"""
FastAPI route definitions.
Three route groups:
  /ws          — WebSocket endpoint for live dashboard
  /api/v1      — REST endpoints for dashboard data queries
  /health      — System health check
"""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from sqlalchemy import text

from backend.src.api.websocket_manager import ws_manager
from backend.src.db.postgres import get_session
from backend.src.logger import get_logger
from backend.src.models.api import (
    HealthStatus,
    PatientSummary,
    RecentTriageResponse,
    TriageEventSummary,
    WebSocketEvent,
)

log = get_logger(__name__)

# ── Routers ──────────────────────────────────────────────────────────────────

ws_router    = APIRouter(tags=["WebSocket"])
api_router   = APIRouter(prefix="/api/v1", tags=["REST API"])
health_router = APIRouter(tags=["Health"])


# ── WebSocket ─────────────────────────────────────────────────────────────────

@ws_router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """
    Live event stream for the dashboard.
    Clients connect and receive:
      - 'alert_received'         when CEP fires a CriticalAlert
      - 'triage_recommendation'  when the agent completes
      - 'ping'                   every 30s to keep connection alive

    The client should reconnect on disconnect — this is a
    stateless broadcast channel, not a session.
    """
    await ws_manager.connect(websocket)

    # Send a welcome ping so the client knows it's connected
    await ws_manager.send_to(
        websocket,
        WebSocketEvent(
            event_type="ping",
            payload={"message": "Connected to TaaS live feed"},
            timestamp=datetime.now(timezone.utc),
        ).model_dump(mode="json"),
    )

    try:
        while True:
            # Keep the connection open — we only send server→client
            # but we must await something to detect disconnection
            data = await websocket.receive_text()
            # Handle client-side ping/pong to keep connection alive
            if data == "ping":
                await ws_manager.send_to(
                    websocket,
                    WebSocketEvent(
                        event_type="ping",
                        payload={"message": "pong"},
                        timestamp=datetime.now(timezone.utc),
                    ).model_dump(mode="json"),
                )
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)


# ── REST: Patients ────────────────────────────────────────────────────────────

@api_router.get("/patients", response_model=list[PatientSummary])
async def list_patients(
    hospital_id: Optional[str] = Query(None),
    ward: Optional[str] = Query(None),
) -> list[PatientSummary]:
    """
    Returns all patients, optionally filtered by hospital or ward.
    Includes recent alert count (last 24h) per patient.
    """
    filters = "WHERE 1=1"
    params: dict = {}

    if hospital_id:
        filters += " AND p.hospital_id = :hospital_id"
        params["hospital_id"] = hospital_id
    if ward:
        filters += " AND p.ward = :ward"
        params["ward"] = ward

    async with get_session() as session:
        result = await session.execute(
            text(f"""
                SELECT
                    p.patient_id,
                    p.full_name,
                    DATE_PART('year', AGE(p.date_of_birth))::int AS age_years,
                    p.gender,
                    p.ward,
                    p.bed_number,
                    p.chronic_conditions,
                    p.active_medications,
                    COUNT(t.id) AS recent_alert_count
                FROM patients p
                LEFT JOIN triage_events t
                    ON t.patient_id = p.patient_id
                    AND t.created_at > NOW() - INTERVAL '24 hours'
                {filters}
                GROUP BY p.patient_id
                ORDER BY p.ward, p.bed_number
            """),
            params,
        )
        rows = result.mappings().fetchall()

    return [
        PatientSummary(
            patient_id=row["patient_id"],
            full_name=row["full_name"],
            age_years=row["age_years"],
            gender=row["gender"],
            ward=row["ward"],
            bed_number=row["bed_number"],
            chronic_conditions=list(row["chronic_conditions"] or []),
            active_medications=list(row["active_medications"] or []),
            recent_alert_count=row["recent_alert_count"] or 0,
        )
        for row in rows
    ]


@api_router.get(
    "/patients/{patient_id}/history",
    response_model=list[TriageEventSummary],
)
async def get_patient_triage_history(
    patient_id: str,
    limit: int = Query(10, ge=1, le=100),
) -> list[TriageEventSummary]:
    """Returns the most recent triage events for a specific patient."""
    async with get_session() as session:
        result = await session.execute(
            text("""
                SELECT
                    id, alert_id, patient_id, severity,
                    recommendation_text, confidence_score,
                    processing_ms, created_at
                FROM triage_events
                WHERE patient_id = :pid
                ORDER BY created_at DESC
                LIMIT :lim
            """),
            {"pid": patient_id.upper(), "lim": limit},
        )
        rows = result.mappings().fetchall()

    return [
        TriageEventSummary(
            id=row["id"],
            alert_id=row["alert_id"],
            patient_id=row["patient_id"],
            severity=row["severity"],
            urgency_level=None,
            recommendation_text=row["recommendation_text"],
            confidence_score=float(row["confidence_score"])
                if row["confidence_score"] else None,
            processing_ms=row["processing_ms"],
            created_at=row["created_at"],
        )
        for row in rows
    ]


# ── REST: Triage Feed ─────────────────────────────────────────────────────────

@api_router.get("/triage/recent", response_model=RecentTriageResponse)
async def get_recent_triage_events(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    severity: Optional[str] = Query(None),
) -> RecentTriageResponse:
    """
    Paginated feed of recent triage events across all patients.
    Used by the dashboard's main alert feed view.
    """
    offset = (page - 1) * page_size
    severity_filter = ""
    params: dict = {"limit": page_size, "offset": offset}

    if severity:
        severity_filter = "AND severity = :severity"
        params["severity"] = severity.upper()

    async with get_session() as session:
        # Total count for pagination
        count_result = await session.execute(
            text(f"""
                SELECT COUNT(*) FROM triage_events
                WHERE 1=1 {severity_filter}
            """),
            params,
        )
        total = count_result.scalar() or 0

        # Paginated results
        result = await session.execute(
            text(f"""
                SELECT
                    id, alert_id, patient_id, severity,
                    recommendation_text, confidence_score,
                    processing_ms, created_at
                FROM triage_events
                WHERE 1=1 {severity_filter}
                ORDER BY created_at DESC
                LIMIT :limit OFFSET :offset
            """),
            params,
        )
        rows = result.mappings().fetchall()

    return RecentTriageResponse(
        items=[
            TriageEventSummary(
                id=row["id"],
                alert_id=row["alert_id"],
                patient_id=row["patient_id"],
                severity=row["severity"],
                urgency_level=None,
                recommendation_text=row["recommendation_text"],
                confidence_score=float(row["confidence_score"])
                    if row["confidence_score"] else None,
                processing_ms=row["processing_ms"],
                created_at=row["created_at"],
            )
            for row in rows
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


# ── REST: Stats ───────────────────────────────────────────────────────────────

@api_router.get("/stats")
async def get_dashboard_stats() -> dict:
    """
    Aggregate stats for the dashboard header cards.
    Returns counts and averages for the last 24 hours.
    """
    async with get_session() as session:
        result = await session.execute(text("""
            SELECT
                COUNT(*)                                        AS total_events_24h,
                COUNT(*) FILTER (WHERE severity = 'CRITICAL')  AS critical_count,
                COUNT(*) FILTER (WHERE severity = 'HIGH')      AS high_count,
                COUNT(*) FILTER (WHERE severity = 'MEDIUM')    AS medium_count,
                ROUND(AVG(confidence_score)::numeric, 3)       AS avg_confidence,
                ROUND(AVG(processing_ms)::numeric, 0)          AS avg_processing_ms,
                COUNT(DISTINCT patient_id)                     AS patients_triaged
            FROM triage_events
            WHERE created_at > NOW() - INTERVAL '24 hours'
        """))
        row = result.mappings().fetchone()

    return {
        "period":            "last_24_hours",
        "total_events":      row["total_events_24h"] or 0,
        "critical_count":    row["critical_count"] or 0,
        "high_count":        row["high_count"] or 0,
        "medium_count":      row["medium_count"] or 0,
        "avg_confidence":    float(row["avg_confidence"] or 0),
        "avg_processing_ms": int(row["avg_processing_ms"] or 0),
        "patients_triaged":  row["patients_triaged"] or 0,
        "ws_connections":    ws_manager.connection_count,
    }


# ── Health Check ──────────────────────────────────────────────────────────────

@health_router.get("/health", response_model=HealthStatus)
async def health_check() -> HealthStatus:
    """
    Checks connectivity of all downstream services.
    Returns 200 if all healthy, 503 if any service is down.
    """
    import time
    from backend.src.config import settings

    start = time.time()
    services: dict[str, str] = {}
    all_healthy = True

    # ── Neon Postgres ─────────────────────────────────────────────────────
    try:
        async with get_session() as session:
            await session.execute(text("SELECT 1"))
        services["neon_postgres"] = "ok"
    except Exception as exc:
        services["neon_postgres"] = f"error: {str(exc)[:80]}"
        all_healthy = False

    # ── Gemini API ────────────────────────────────────────────────────────
    try:
        from google import genai
        client = genai.Client(api_key=settings.gemini_api_key)
        # Lightweight check — list models without generating content
        models = client.models.list()
        services["gemini_api"] = "ok"
    except Exception as exc:
        services["gemini_api"] = f"error: {str(exc)[:80]}"
        all_healthy = False

    # ── Kafka / Aiven ─────────────────────────────────────────────────────
    try:
        from confluent_kafka.admin import AdminClient
        admin = AdminClient({
            "bootstrap.servers":        settings.kafka_brokers,
            "security.protocol":        "SSL",
            "ssl.ca.location":          settings.kafka_ca_cert_path,
            "ssl.certificate.location": settings.kafka_ssl_cert_path,
            "ssl.key.location":         settings.kafka_ssl_key_path,
            "socket.timeout.ms":        5000,
        })
        meta = admin.list_topics(timeout=5)
        services["aiven_kafka"] = (
            "ok" if settings.topic_alerts in meta.topics
            else "error: topic not found"
        )
    except Exception as exc:
        services["aiven_kafka"] = f"error: {str(exc)[:80]}"
        all_healthy = False

    # ── WebSocket ─────────────────────────────────────────────────────────
    services["websocket"] = f"ok ({ws_manager.connection_count} clients)"

    return HealthStatus(
        status="healthy" if all_healthy else "degraded",
        services=services,
        uptime_s=round(time.time() - start, 3),
    )

# ── Dev Endpoint(Debug) ────────────────────────────────────────────────────────────

@api_router.post("/debug/fire-test-alert")
async def fire_test_alert() -> dict:
    """
    DEV ONLY — bypasses Kafka and fires a synthetic alert directly
    through the agent and WebSocket pipeline. Remove before production.
    """
    from datetime import datetime, timezone
    from backend.src.agent.triage_agent import run_triage_agent
    from backend.src.models.telemetry import (
        AlertSeverity, CriticalAlert, VitalSigns,
    )

    alert = CriticalAlert(
        source_event_id="debug-test-001",
        patient_id="PT-005",
        hospital_id="HOSP-001",
        ward="ICU",
        bed_number="2C",
        timestamp_utc=datetime.now(timezone.utc),
        severity=AlertSeverity.CRITICAL,
        triggered_rules=[
            "R8 SHOCK PATTERN: HR=128 bpm, SBP=86 mmHg, SpO2=90.0%",
            "R9 SIRS (3/3 criteria): Temp=38.9°C, HR=128 bpm, RR=27 rpm",
        ],
        vitals_snapshot=VitalSigns(
            heart_rate_bpm=128,
            systolic_bp_mmhg=86,
            diastolic_bp_mmhg=54,
            spo2_percent=90.0,
            respiratory_rate_rpm=27,
            temperature_celsius=38.9,
        ),
        nursing_notes="Debug test — verifying WebSocket pipeline end-to-end.",
    )

    await ws_manager.broadcast(
        WebSocketEvent(
            event_type="alert_received",
            payload=alert.model_dump(mode="json"),
            timestamp=datetime.now(timezone.utc),
        ).model_dump(mode="json")
    )

    recommendation = await run_triage_agent(alert)

    if recommendation:
        await ws_manager.broadcast(
            WebSocketEvent(
                event_type="triage_recommendation",
                payload=recommendation.model_dump(mode="json"),
                timestamp=datetime.now(timezone.utc),
            ).model_dump(mode="json")
        )
        return {
            "status": "fired",
            "urgency": recommendation.urgency_level.value,
            "confidence": recommendation.confidence_score,
        }

    return {"status": "agent_failed"}