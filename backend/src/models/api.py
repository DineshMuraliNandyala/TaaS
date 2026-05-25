"""
API response contracts for FastAPI endpoints.
These are the schemas the Next.js frontend consumes.
Separate from internal agent models — API contracts should
evolve independently of internal data structures.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel


class PatientSummary(BaseModel):
    """Lightweight patient record for dashboard list view."""
    patient_id:         str
    full_name:          str
    age_years:          int
    gender:             str
    ward:               str
    bed_number:         str
    chronic_conditions: list[str]
    active_medications: list[dict[str, Any]]
    recent_alert_count: int = 0


class TriageEventSummary(BaseModel):
    """Single triage event for history/feed views."""
    id:                  int
    alert_id:            str
    patient_id:          str
    severity:            str
    urgency_level:       Optional[str]
    recommendation_text: Optional[str]
    confidence_score:    Optional[float]
    processing_ms:       Optional[int]
    created_at:          datetime


class RecentTriageResponse(BaseModel):
    """Paginated triage event feed."""
    items:       list[TriageEventSummary]
    total:       int
    page:        int
    page_size:   int


class HealthStatus(BaseModel):
    """System health check response."""
    status:   str                   # 'healthy' | 'degraded' | 'unhealthy'
    services: dict[str, str]        # service_name → 'ok' | 'error: ...'
    version:  str = "1.0.0"
    uptime_s: float = 0.0


class WebSocketEvent(BaseModel):
    """
    Envelope for all WebSocket messages sent to the dashboard.
    The frontend switches on `event_type` to route the payload.
    """
    event_type: str     # 'triage_recommendation' | 'alert_received' | 'ping'
    payload:    Any
    timestamp:  datetime