"""
TaaS Platform — FastAPI Application Entry Point
────────────────────────────────────────────────
Wires together:
  - FastAPI lifespan (startup/shutdown hooks)
  - Kafka alert consumer background task
  - WebSocket manager
  - All route groups

Run:
    uvicorn backend.main:app --reload --port 8000
"""
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.src.api.routes import api_router, health_router, ws_router
from backend.src.api.websocket_manager import ws_manager
from backend.src.db.postgres import check_db_connection
from backend.src.logger import get_logger
from backend.src.streaming.alert_consumer import alert_consumer

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI lifespan context manager.
    Code before `yield` runs on startup.
    Code after `yield` runs on shutdown.
    This replaces the deprecated @app.on_event pattern.
    """
    # ── Startup ───────────────────────────────────────────────────────────
    log.info("taas_api_starting")

    # Verify database connectivity before accepting traffic
    db_ok = await check_db_connection()
    if not db_ok:
        log.error("startup_aborted", reason="database_unreachable")
        raise RuntimeError("Cannot connect to Neon Postgres on startup")

    # Start the Kafka alert consumer as a background asyncio task
    # It runs concurrently with request handling — never blocks the API
    consumer_task = asyncio.create_task(
        alert_consumer.start(),
        name="kafka-alert-consumer",
    )
    log.info("kafka_alert_consumer_task_started")

    log.info(
        "taas_api_ready",
        docs_url="http://localhost:8000/docs",
        websocket_url="ws://localhost:8000/ws",
        health_url="http://localhost:8000/health",
    )

    yield  # ← Application is running and serving requests

    # ── Shutdown ──────────────────────────────────────────────────────────
    log.info("taas_api_shutting_down")

    alert_consumer.stop()
    consumer_task.cancel()

    try:
        await asyncio.wait_for(consumer_task, timeout=5.0)
    except (asyncio.CancelledError, asyncio.TimeoutError):
        pass

    log.info("taas_api_shutdown_complete")


# ── Application factory ───────────────────────────────────────────────────────

def create_app() -> FastAPI:
    app = FastAPI(
        title="Triage-as-a-Service (TaaS) API",
        description=(
            "Real-time hospital telemetry triage platform. "
            "Ingests CEP alerts and generates AI-powered clinical recommendations."
        ),
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # CORS — allow Next.js dev server and Vercel preview URLs
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",     # Next.js dev
            "https://*.vercel.app",      # Vercel previews
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register route groups
    app.include_router(health_router)
    app.include_router(ws_router)
    app.include_router(api_router)

    return app


app = create_app()