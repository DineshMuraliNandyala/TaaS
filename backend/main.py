"""
TaaS Platform — FastAPI Application Entry Point (Phase 5)
──────────────────────────────────────────────────────────
Adds:
  - OpenTelemetry auto-instrumentation (FastAPI + SQLAlchemy)
  - Rate limiting via slowapi
  - Request logging middleware
  - Startup secret validation (fail-fast)
  - Graceful OTEL flush on shutdown
"""
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from backend.src.api.middleware import (
    limiter,
    log_requests_middleware,
    rate_limit_exceeded_handler,
)
from backend.src.api.routes import api_router, health_router, ws_router
from backend.src.config import settings
from backend.src.db.postgres import check_db_connection, engine
from backend.src.logger import get_logger
from backend.src.observability.telemetry import setup_telemetry, shutdown_telemetry
from backend.src.streaming.alert_consumer import alert_consumer

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ───────────────────────────────────────────────────────────
    log.info("taas_api_starting", environment=settings.environment)

    # Fail fast if required secrets are missing
    settings.validate_required_secrets()

    # Instrument SQLAlchemy before any DB calls
    SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)

    db_ok = await check_db_connection()
    if not db_ok:
        raise RuntimeError("Cannot connect to Neon Postgres on startup")

    consumer_task = asyncio.create_task(
        alert_consumer.start(),
        name="kafka-alert-consumer",
    )

    log.info(
        "taas_api_ready",
        docs_url="http://localhost:8000/docs",
        websocket_url="ws://localhost:8000/ws",
        health_url="http://localhost:8000/health",
        grafana_enabled=settings.grafana_enabled,
    )

    yield

    # ── Shutdown ──────────────────────────────────────────────────────────
    log.info("taas_api_shutting_down")
    alert_consumer.stop()
    consumer_task.cancel()
    try:
        await asyncio.wait_for(consumer_task, timeout=5.0)
    except (asyncio.CancelledError, asyncio.TimeoutError):
        pass

    shutdown_telemetry()
    log.info("taas_api_shutdown_complete")


def create_app() -> FastAPI:
    # Initialise telemetry BEFORE creating the FastAPI app
    # so FastAPIInstrumentor can patch the app on creation
    setup_telemetry()

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

    # ── Middleware stack (order matters) ──────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "https://*.vercel.app",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(SlowAPIMiddleware)
    app.middleware("http")(log_requests_middleware)

    # ── Rate limiter ──────────────────────────────────────────────────────
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

    # ── Auto-instrument FastAPI spans ─────────────────────────────────────
    FastAPIInstrumentor.instrument_app(
        app,
        excluded_urls="health",  # skip health check — too noisy
    )

    # ── Routes ────────────────────────────────────────────────────────────
    app.include_router(health_router)
    app.include_router(ws_router)
    app.include_router(api_router)

    return app


app = create_app()