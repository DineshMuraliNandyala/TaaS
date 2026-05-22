#!/usr/bin/env python3
"""
Standalone test for the triage agent.
Fires a synthetic CRITICAL alert for PT-005 and prints the recommendation.
Run: python -m backend.src.agent.test_agent
"""
import asyncio
import sys
from datetime import datetime, timezone

sys.path.insert(0, ".")

from backend.src.agent.triage_agent import run_triage_agent
from backend.src.db.postgres import check_db_connection
from backend.src.logger import get_logger
from backend.src.models.telemetry import AlertSeverity, CriticalAlert, VitalSigns

log = get_logger(__name__)


async def main():
    # Verify DB connection first
    db_ok = await check_db_connection()
    if not db_ok:
        log.error("test_aborted", reason="database_unreachable")
        sys.exit(1)

    # Synthetic CRITICAL alert matching PT-005's deterioration pattern
    test_alert = CriticalAlert(
        source_event_id="test-event-001",
        patient_id="PT-005",
        hospital_id="HOSP-001",
        ward="ICU",
        bed_number="2C",
        timestamp_utc=datetime.now(timezone.utc),
        severity=AlertSeverity.CRITICAL,
        triggered_rules=[
            "R8 SHOCK PATTERN: HR=132 bpm, SBP=84 mmHg, SpO2=89.0%",
            "R9 SIRS (3/3 criteria): Temp=39.1°C, HR=132 bpm, RR=28 rpm",
            "R1 Tachycardia: HR=132 bpm (threshold >110)",
            "R3 Hypoxia: SpO2=89.0% (threshold <94%)",
            "R4 Hypotension: SBP=84 mmHg (threshold <90)",
        ],
        vitals_snapshot=VitalSigns(
            heart_rate_bpm=132,
            systolic_bp_mmhg=84,
            diastolic_bp_mmhg=52,
            spo2_percent=89.0,
            respiratory_rate_rpm=28,
            temperature_celsius=39.1,
        ),
        nursing_notes="Patient increasingly confused, not responding to voice. "
                      "Urine output <10mL last 2 hours.",
    )

    log.info("test_alert_dispatched", patient_id="PT-005", severity="CRITICAL")
    recommendation = await run_triage_agent(test_alert)

    if recommendation:
        print("\n" + "═" * 70)
        print("  TRIAGE RECOMMENDATION")
        print("═" * 70)
        print(f"  Patient:    {recommendation.patient_id}")
        print(f"  Urgency:    {recommendation.urgency_level.value}")
        print(f"  Confidence: {recommendation.confidence_score:.0%}")
        print(f"  Summary:    {recommendation.clinical_summary}")
        print(f"\n  Primary Concern: {recommendation.primary_concern}")
        print(f"\n  Recommended Actions:")
        for action in recommendation.recommended_actions:
            print(f"    [{action.priority}] {action.action}")
            print(f"        Why: {action.rationale}")
            print(f"        When: {action.time_window}")
        if recommendation.contraindications:
            print(f"\n  Contraindications:")
            for c in recommendation.contraindications:
                print(f"    ⚠ {c}")
        print(f"\n  SOPs Referenced: {', '.join(recommendation.sops_referenced)}")
        print(f"  Processing Time: {recommendation.processing_ms}ms")
        print("═" * 70 + "\n")
    else:
        print("\n  Agent returned no recommendation — check logs above.\n")


if __name__ == "__main__":
    asyncio.run(main())