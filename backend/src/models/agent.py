"""
Data contracts for the LangGraph agent layer.
These models are the typed interface between:
  - CEP engine output  →  Agent input  (CriticalAlert, already defined)
  - Agent internal state  (TriageAgentState)
  - Agent output  →  FastAPI/WebSocket  (TriageRecommendation)
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class UrgencyLevel(str, Enum):
    IMMEDIATE = "IMMEDIATE"       # Act within minutes
    URGENT = "URGENT"             # Act within 30 minutes
    SEMI_URGENT = "SEMI_URGENT"   # Act within 2 hours
    NON_URGENT = "NON_URGENT"     # Routine management


class RecommendedAction(BaseModel):
    """A single discrete clinical action."""
    priority:    int = Field(..., ge=1, le=5, description="1 = highest priority")
    action:      str = Field(..., description="The specific action to take")
    rationale:   str = Field(..., description="Clinical reasoning behind this action")
    time_window: str = Field(..., description="When this should be done, e.g. 'within 15 minutes'")


class PatientContext(BaseModel):
    """Fetched from Neon Postgres by Node 1."""
    patient_id:         str
    full_name:          str
    age_years:          int
    gender:             str
    blood_type:         Optional[str]
    weight_kg:          Optional[float]
    allergies:          list[str]
    chronic_conditions: list[str]
    active_medications: list[dict[str, Any]]
    recent_triage_count: int = 0        # number of alerts in last 24h


class SOPDocument(BaseModel):
    """A retrieved clinical SOP from pgvector hybrid search."""
    title:            str
    category:         str
    content:          str
    relevance_score:  float = Field(..., ge=0.0, le=1.0)
    retrieval_method: str   # 'vector', 'keyword', or 'hybrid'


class TriageRecommendation(BaseModel):
    """
    Final output of the LangGraph agent.
    This is the contract consumed by FastAPI → WebSocket → Next.js dashboard.
    Also persisted to Neon triage_events table.
    """
    recommendation_id:   str = Field(
        default_factory=lambda: str(uuid.uuid4())
    )
    alert_id:            str
    patient_id:          str
    hospital_id:         str
    urgency_level:       UrgencyLevel
    clinical_summary:    str = Field(
        ..., description="2-3 sentence synthesis of the patient's current status"
    )
    primary_concern:     str = Field(
        ..., description="Single most critical issue identified"
    )
    recommended_actions: list[RecommendedAction] = Field(
        ..., description="Ordered list of discrete actions, highest priority first"
    )
    contraindications:   list[str] = Field(
        default_factory=list,
        description="Medications or interventions to avoid given patient history"
    )
    sops_referenced:     list[str] = Field(
        default_factory=list,
        description="Titles of clinical SOPs used to generate this recommendation"
    )
    confidence_score:    float = Field(
        ..., ge=0.0, le=1.0,
        description="Model's self-assessed confidence in the recommendation"
    )
    llm_model_used:      str
    processing_ms:       int = 0
    generated_at:        datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class TriageAgentState(BaseModel):
    """
    Typed state dictionary for the LangGraph StateGraph.
    Every node reads from and writes to this object.
    Fields are Optional because nodes populate them incrementally.
    """
    # ── Input ────────────────────────────────────────────────────────────────
    alert_dict: dict[str, Any]          # raw CriticalAlert as dict

    # ── Node 1 output ────────────────────────────────────────────────────────
    patient_context: Optional[PatientContext] = None
    context_fetch_error: Optional[str] = None

    # ── Node 2 output ────────────────────────────────────────────────────────
    retrieved_sops: list[SOPDocument] = Field(default_factory=list)
    rag_query_used: Optional[str] = None

    # ── Node 3 output ────────────────────────────────────────────────────────
    recommendation: Optional[TriageRecommendation] = None
    llm_error: Optional[str] = None

    # ── Node 4 output ────────────────────────────────────────────────────────
    audit_persisted: bool = False
    stripe_event_id: Optional[str] = None

    # ── Metadata ─────────────────────────────────────────────────────────────
    start_time_ms: float = 0.0