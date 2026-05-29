"""
Central application configuration.
Single source of truth for all environment variables.
Import the `settings` singleton everywhere — never instantiate Settings directly.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Kafka / Aiven ────────────────────────────────────────────────────────
    kafka_brokers: str
    kafka_security_protocol: str = "SSL"
    # SASL (only used when security_protocol is SASL_SSL)
    kafka_sasl_mechanism: str = "SCRAM-SHA-512"
    kafka_sasl_username: str = ""
    kafka_sasl_password: str = ""
    # mTLS client certificate (required for Aiven SSL auth)
    kafka_ca_cert_path: str = "certs/ca.pem"
    kafka_ssl_cert_path: str = "certs/service.cert"
    kafka_ssl_key_path: str = "certs/service.key"

    # ── Neon Postgres ────────────────────────────────────────────────────────
    database_url: str

    # ── Gemini ───────────────────────────────────────────────────────────────
    gemini_api_key: str
    gemini_model: str = "gemini-2.5-flash"
    gemini_embedding_model: str = "models/gemini-embedding-001"

    # ── Stripe ───────────────────────────────────────────────────────────────
    stripe_secret_key: str = ""
    stripe_meter_event_name: str = "triage_event"

    # ── Observability ────────────────────────────────────────────────────────
    otlp_endpoint: str = ""
    otlp_headers: str = ""
    otel_service_name: str = "taas-backend"
    otel_environment: str = "development"
    grafana_enabled: bool = False

    # ── Rate limiting ────────────────────────────────────────────────────────
    rate_limit_per_minute: int = 60

    # ── Topics ───────────────────────────────────────────────────────────────
    topic_telemetry: str = "clinical_telemetry"
    topic_alerts: str = "critical_alerts"

    # ── App ──────────────────────────────────────────────────────────────────
    log_level: str = "INFO"
    hospital_id: str = "HOSP-001"
    environment: str = "development"

    def validate_required_secrets(self) -> None:
        """
        Called on startup — fails fast if critical secrets are missing
        rather than allowing the app to start and fail mid-request.
        """
        missing = []
        if not self.kafka_brokers:
            missing.append("KAFKA_BROKERS")
        if not self.database_url:
            missing.append("DATABASE_URL")
        if not self.gemini_api_key:
            missing.append("GEMINI_API_KEY")
        if missing:
            raise RuntimeError(
                f"Missing required environment variables: {', '.join(missing)}"
            )


# Module-level singleton — import this everywhere
settings = Settings()