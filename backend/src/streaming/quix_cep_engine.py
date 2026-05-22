#!/usr/bin/env python3
"""
Complex Event Processing Engine — Quix Streams on Aiven Kafka
──────────────────────────────────────────────────────────────
Consumes from `clinical_telemetry`, applies multi-rule anomaly detection,
and publishes CriticalAlert payloads to `critical_alerts`.

Connects to Aiven via SASL_SSL + SCRAM-SHA-512 + CA certificate.

CEP Rules:
  Simple   →  R1 Tachycardia, R2 Bradycardia, R3 Hypoxia,
              R4 Hypotension, R5 Hypertensive Crisis,
              R6 Tachypnea, R7 Fever
  Compound →  R8 Shock Pattern (→ CRITICAL), R9 SIRS (→ HIGH)

Severity escalation:
  1 simple rule fired       → MEDIUM
  2+ simple rules fired     → HIGH
  R9 SIRS compound fires    → HIGH  (overrides simple count)
  R8 Shock compound fires   → CRITICAL (overrides everything)

Run from project root:
    python -m backend.src.streaming.quix_cep_engine
"""
import signal
import sys
from typing import Optional

from quixstreams import Application
from quixstreams.kafka.configuration import ConnectionConfig
from pydantic import ValidationError

sys.path.insert(0, ".")

from backend.src.config import settings
from backend.src.logger import get_logger
from backend.src.models.telemetry import (
    AlertSeverity,
    CriticalAlert,
    TelemetryEvent,
    VitalSigns,
)

log = get_logger(__name__)


# ── CEP Rule Definitions ─────────────────────────────────────────────────────
#
# Design principle: each rule is a pure function.
# Simple rules:   (VitalSigns) -> Optional[str]
#                 Returns a description string if the rule fires, else None.
# Compound rules: (VitalSigns) -> Optional[tuple[str, AlertSeverity]]
#                 Returns (description, severity) if fires, else None.
# This separation allows severity escalation logic to be centralised.


# ── Simple Rules ─────────────────────────────────────────────────────────────

def rule_tachycardia(v: VitalSigns) -> Optional[str]:
    if v.heart_rate_bpm > 110:
        return f"R1 Tachycardia: HR={v.heart_rate_bpm} bpm (threshold >110)"
    return None


def rule_bradycardia(v: VitalSigns) -> Optional[str]:
    if v.heart_rate_bpm < 45:
        return f"R2 Bradycardia: HR={v.heart_rate_bpm} bpm (threshold <45)"
    return None


def rule_hypoxia(v: VitalSigns) -> Optional[str]:
    if v.spo2_percent < 94.0:
        return f"R3 Hypoxia: SpO2={v.spo2_percent}% (threshold <94%)"
    return None


def rule_hypotension(v: VitalSigns) -> Optional[str]:
    if v.systolic_bp_mmhg < 90:
        return f"R4 Hypotension: SBP={v.systolic_bp_mmhg} mmHg (threshold <90)"
    return None


def rule_hypertensive_crisis(v: VitalSigns) -> Optional[str]:
    if v.systolic_bp_mmhg > 180:
        return (
            f"R5 Hypertensive Crisis: SBP={v.systolic_bp_mmhg} mmHg "
            f"(threshold >180)"
        )
    return None


def rule_tachypnea(v: VitalSigns) -> Optional[str]:
    if v.respiratory_rate_rpm > 22:
        return (
            f"R6 Tachypnea: RR={v.respiratory_rate_rpm} rpm (threshold >22)"
        )
    return None


def rule_fever(v: VitalSigns) -> Optional[str]:
    if v.temperature_celsius > 38.3:
        return (
            f"R7 Fever: Temp={v.temperature_celsius}°C (threshold >38.3)"
        )
    return None


SIMPLE_RULES = [
    rule_tachycardia,
    rule_bradycardia,
    rule_hypoxia,
    rule_hypotension,
    rule_hypertensive_crisis,
    rule_tachypnea,
    rule_fever,
]


# ── Compound Rules ───────────────────────────────────────────────────────────

def rule_shock_pattern(
    v: VitalSigns,
) -> Optional[tuple[str, AlertSeverity]]:
    """
    R8 — Distributive Shock Pattern.
    Criteria: HR > 100 AND SBP < 100 AND SpO2 < 95%
    Clinical rationale: concurrent tachycardia, hypotension, and hypoxia
    indicate haemodynamic compromise — immediate intervention required.
    """
    if (
        v.heart_rate_bpm > 100
        and v.systolic_bp_mmhg < 100
        and v.spo2_percent < 95.0
    ):
        desc = (
            f"R8 SHOCK PATTERN: HR={v.heart_rate_bpm} bpm, "
            f"SBP={v.systolic_bp_mmhg} mmHg, "
            f"SpO2={v.spo2_percent}%"
        )
        return desc, AlertSeverity.CRITICAL
    return None


def rule_sirs(
    v: VitalSigns,
) -> Optional[tuple[str, AlertSeverity]]:
    """
    R9 — Systemic Inflammatory Response Syndrome (SIRS).
    Criteria: 2 or more of:
      - Temperature > 38.0°C OR < 36.0°C
      - Heart rate > 90 bpm
      - Respiratory rate > 20 rpm
    Clinical rationale: SIRS is an early indicator of sepsis.
    """
    criteria_met = []
    if v.temperature_celsius > 38.0 or v.temperature_celsius < 36.0:
        criteria_met.append(f"Temp={v.temperature_celsius}°C")
    if v.heart_rate_bpm > 90:
        criteria_met.append(f"HR={v.heart_rate_bpm} bpm")
    if v.respiratory_rate_rpm > 20:
        criteria_met.append(f"RR={v.respiratory_rate_rpm} rpm")

    if len(criteria_met) >= 2:
        desc = (
            f"R9 SIRS ({len(criteria_met)}/3 criteria): "
            f"{', '.join(criteria_met)}"
        )
        return desc, AlertSeverity.HIGH
    return None


COMPOUND_RULES = [
    rule_shock_pattern,
    rule_sirs,
]

# Severity ordering for escalation logic
_SEVERITY_RANK = {
    AlertSeverity.LOW:      0,
    AlertSeverity.MEDIUM:   1,
    AlertSeverity.HIGH:     2,
    AlertSeverity.CRITICAL: 3,
}


# ── Core CEP Evaluation ──────────────────────────────────────────────────────

def evaluate_event(event: TelemetryEvent) -> Optional[CriticalAlert]:
    """
    Apply all CEP rules to a single TelemetryEvent.
    Returns a CriticalAlert if any rule fires, else None.

    Severity escalation logic:
      - Start at None
      - Each compound rule that fires sets a minimum severity
      - CRITICAL always wins regardless of evaluation order
      - If no compound rule fires: 1 simple → MEDIUM, 2+ simple → HIGH
    """
    v = event.vitals
    fired_rules: list[str] = []
    compound_severity: Optional[AlertSeverity] = None

    # Evaluate compound rules first — they carry explicit severity
    for rule_fn in COMPOUND_RULES:
        result = rule_fn(v)
        if result is not None:
            description, severity = result
            fired_rules.append(description)
            if compound_severity is None or (
                _SEVERITY_RANK[severity] > _SEVERITY_RANK[compound_severity]
            ):
                compound_severity = severity

    # Evaluate simple rules
    for rule_fn in SIMPLE_RULES:
        result = rule_fn(v)
        if result is not None:
            fired_rules.append(result)

    # Nothing fired — normal reading, do not produce alert
    if not fired_rules:
        return None

    # Determine final severity
    if compound_severity == AlertSeverity.CRITICAL:
        final_severity = AlertSeverity.CRITICAL
    elif compound_severity == AlertSeverity.HIGH:
        final_severity = AlertSeverity.HIGH
    elif len(fired_rules) >= 2:
        final_severity = AlertSeverity.HIGH
    else:
        final_severity = AlertSeverity.MEDIUM

    return CriticalAlert(
        source_event_id=event.event_id,
        patient_id=event.patient_id,
        hospital_id=event.hospital_id,
        ward=event.ward,
        bed_number=event.bed_number,
        timestamp_utc=event.timestamp_utc,
        severity=final_severity,
        triggered_rules=fired_rules,
        vitals_snapshot=v,
        nursing_notes=event.nursing_notes,
    )


# ── Quix Streams Transform ───────────────────────────────────────────────────

def process_message(raw_value: dict) -> Optional[dict]:
    """
    Quix Streams transformation function applied to every message.

    1. Deserialise raw dict → TelemetryEvent (Pydantic validation)
    2. Run CEP evaluation
    3. Return alert dict for downstream sink, or None to suppress message
    """
    try:
        event = TelemetryEvent.model_validate(raw_value)
    except ValidationError as exc:
        log.error(
            "telemetry_deserialization_failed",
            errors=exc.errors(),
            raw_keys=list(raw_value.keys()),
        )
        return None  # Drop malformed messages — do not crash the pipeline

    alert = evaluate_event(event)

    if alert is None:
        log.debug(
            "telemetry_normal",
            patient_id=event.patient_id,
            hr=event.vitals.heart_rate_bpm,
            spo2=event.vitals.spo2_percent,
            sbp=event.vitals.systolic_bp_mmhg,
        )
        return None

    log.warning(
        "cep_alert_generated",
        alert_id=alert.alert_id,
        patient_id=alert.patient_id,
        severity=alert.severity.value,
        rules_fired=len(alert.triggered_rules),
        triggered_rules=alert.triggered_rules,
        summary=alert.summary,
    )
    return alert.model_dump(mode="json")


# ── Quix Application ─────────────────────────────────────────────────────────

def build_application() -> Application:
    """
    Construct Quix Streams Application with Aiven SSL (mTLS) configuration.

    Aiven Kafka is configured for certificate-based auth (mTLS), not SASL.
    All three internal clients (consumer, producer, admin) need the client
    cert + key; passing a ConnectionConfig as broker_address is the only way
    to ensure the admin client also receives them.
    """
    connection = ConnectionConfig(
        bootstrap_servers=settings.kafka_brokers,
        security_protocol="ssl",
        ssl_ca_location=settings.kafka_ca_cert_path,
        ssl_certificate_location=settings.kafka_ssl_cert_path,
        ssl_key_location=settings.kafka_ssl_key_path,
    )

    return Application(
        broker_address=connection,
        consumer_group="taas-cep-engine-v1",
        auto_offset_reset="latest",
    )


def run_cep_engine() -> None:
    """
    Wire up the Quix Streams pipeline and start the blocking consume loop.

    Pipeline:
      input_topic → apply(process_message) → filter(not None) → output_topic
    """
    app = build_application()

    input_topic = app.topic(
        name=settings.topic_telemetry,
        value_deserializer="json",
    )
    output_topic = app.topic(
        name=settings.topic_alerts,
        value_serializer="json",
    )

    log.info(
        "cep_engine_starting",
        input_topic=settings.topic_telemetry,
        output_topic=settings.topic_alerts,
        consumer_group="taas-cep-engine-v1",
        broker=settings.kafka_brokers,
        rules_loaded=len(SIMPLE_RULES) + len(COMPOUND_RULES),
    )

    sdf = app.dataframe(input_topic)
    sdf = sdf.apply(process_message, expand=False)
    sdf = sdf.filter(lambda x: x is not None)
    sdf.to_topic(output_topic)

    def _handle_signal(sig, _frame):
        log.info("cep_engine_shutdown_signal", signal=sig)
        app.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    app.run(sdf)


if __name__ == "__main__":
    run_cep_engine()