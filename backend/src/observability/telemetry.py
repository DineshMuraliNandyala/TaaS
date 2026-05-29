"""
OpenTelemetry instrumentation for TaaS backend.
Exports traces to Grafana Cloud via OTLP HTTP.

Architecture:
  - TracerProvider configured with OTLP exporter → Grafana Cloud
  - BatchSpanProcessor for efficient export (not blocking)
  - Resource attributes identify the service in Grafana
  - Auto-instrumentation patches FastAPI, SQLAlchemy, and httpx
  - Manual spans wrap LangGraph nodes for agent-level visibility

Usage:
    # In main.py, before app creation:
    from backend.src.observability.telemetry import setup_telemetry
    setup_telemetry()

    # In any module for custom spans:
    from backend.src.observability.telemetry import get_tracer
    tracer = get_tracer(__name__)
    with tracer.start_as_current_span("my_operation") as span:
        span.set_attribute("key", "value")
"""
import base64
from typing import Optional

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource, SERVICE_NAME, SERVICE_VERSION
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.trace import Tracer

from backend.src.config import settings
from backend.src.logger import get_logger

log = get_logger(__name__)

_tracer_provider: Optional[TracerProvider] = None


def setup_telemetry() -> None:
    """
    Initialise OpenTelemetry SDK with Grafana Cloud OTLP exporter.
    Call once at application startup before the FastAPI app is created.
    Safe to call multiple times — subsequent calls are no-ops.
    """
    global _tracer_provider
    if _tracer_provider is not None:
        return  # Already initialised

    resource = Resource.create({
        SERVICE_NAME:    settings.otel_service_name,
        SERVICE_VERSION: "1.0.0",
        "deployment.environment": settings.otel_environment,
        "service.namespace": "taas-platform",
    })

    provider = TracerProvider(resource=resource)

    if settings.grafana_enabled and settings.otlp_endpoint:
        # Parse headers from "Key=Value,Key2=Value2" format
        # URL-decode values since env vars often contain %20 etc.
        from urllib.parse import unquote
        headers = {}
        if settings.otlp_headers:
            for pair in settings.otlp_headers.split(","):
                if "=" in pair:
                    k, v = pair.split("=", 1)
                    headers[k.strip()] = unquote(v.strip())

        otlp_exporter = OTLPSpanExporter(
            endpoint=f"{settings.otlp_endpoint}/v1/traces",
            headers=headers,
        )
        provider.add_span_processor(
            BatchSpanProcessor(
                otlp_exporter,
                max_export_batch_size=512,
                export_timeout_millis=30_000,
            )
        )
        log.info(
            "otel_grafana_exporter_configured",
            endpoint=settings.otlp_endpoint,
            service=settings.otel_service_name,
        )
    else:
        # Development fallback — print spans to console at DEBUG level
        # Only active if LOG_LEVEL=DEBUG to avoid noise
        if settings.log_level.upper() == "DEBUG":
            provider.add_span_processor(
                BatchSpanProcessor(ConsoleSpanExporter())
            )
        log.info(
            "otel_console_exporter_configured",
            reason="grafana_disabled_or_no_endpoint",
        )

    trace.set_tracer_provider(provider)
    _tracer_provider = provider
    log.info("otel_telemetry_initialised", service=settings.otel_service_name)


def get_tracer(name: str) -> Tracer:
    """
    Returns a named tracer. Call setup_telemetry() before using this.
    Falls back gracefully if telemetry was never initialised.
    """
    return trace.get_tracer(name)


def shutdown_telemetry() -> None:
    """Flush pending spans on shutdown — call from FastAPI lifespan."""
    global _tracer_provider
    if _tracer_provider:
        _tracer_provider.shutdown()
        log.info("otel_telemetry_shutdown")