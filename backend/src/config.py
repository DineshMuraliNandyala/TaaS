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

    # ── Topics ───────────────────────────────────────────────────────────────
    topic_telemetry: str = "clinical_telemetry"
    topic_alerts: str = "critical_alerts"

    # ── App ──────────────────────────────────────────────────────────────────
    log_level: str = "INFO"
    hospital_id: str = "HOSP-001"
    environment: str = "development"


# Module-level singleton — import this everywhere
settings = Settings()