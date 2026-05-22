"""
TaaS LangGraph Triage Agent
────────────────────────────
Stateful 4-node agent that processes a CriticalAlert into a
TriageRecommendation using patient context, hybrid RAG, and Gemini reasoning.

Graph topology:
  fetch_patient_context
          │
          ▼
    hybrid_rag_lookup
          │
          ▼
    gemini_reasoning
          │
          ▼
    persist_audit
"""
import json
import time
import asyncio
from typing import Any

from google import genai
from google.genai import types
import stripe
from sqlalchemy import text

from backend.src.config import settings
from backend.src.db.postgres import get_session
from backend.src.logger import get_logger
from backend.src.models.agent import (
    PatientContext,
    RecommendedAction,
    SOPDocument,
    TriageAgentState,
    TriageRecommendation,
    UrgencyLevel,
)
from backend.src.models.telemetry import CriticalAlert

log = get_logger(__name__)

# ── SDK Configuration ────────────────────────────────────────────────────────

gemini_client = genai.Client(api_key=settings.gemini_api_key)
stripe.api_key = settings.stripe_secret_key


# ── Node 1: Fetch Patient Context ────────────────────────────────────────────

async def fetch_patient_context(state: TriageAgentState) -> TriageAgentState:
    """
    Fetches patient demographics, conditions, medications, and recent
    triage history from Neon Postgres.
    Gracefully degrades if patient not found — agent continues with
    partial context rather than failing the entire pipeline.
    """
    alert = CriticalAlert.model_validate(state.alert_dict)
    log.info(
        "node1_fetch_patient_context_start",
        patient_id=alert.patient_id,
        alert_id=alert.alert_id,
    )

    try:
        async with get_session() as session:
            # Fetch patient record
            result = await session.execute(
                text("""
                    SELECT
                        patient_id, full_name, date_of_birth, gender,
                        blood_type, weight_kg, allergies,
                        chronic_conditions, active_medications
                    FROM patients
                    WHERE patient_id = :pid
                """),
                {"pid": alert.patient_id},
            )
            row = result.mappings().fetchone()

            if row is None:
                log.warning(
                    "patient_not_found",
                    patient_id=alert.patient_id,
                )
                state.context_fetch_error = (
                    f"Patient {alert.patient_id} not found in database"
                )
                return state

            # Calculate age from date of birth
            from datetime import date
            today = date.today()
            dob = row["date_of_birth"]
            age = today.year - dob.year - (
                (today.month, today.day) < (dob.month, dob.day)
            )

            # Count recent triage events (last 24h)
            count_result = await session.execute(
                text("""
                    SELECT COUNT(*) FROM triage_events
                    WHERE patient_id = :pid
                    AND created_at > NOW() - INTERVAL '24 hours'
                """),
                {"pid": alert.patient_id},
            )
            recent_count = count_result.scalar() or 0

            state.patient_context = PatientContext(
                patient_id=row["patient_id"],
                full_name=row["full_name"],
                age_years=age,
                gender=row["gender"],
                blood_type=row["blood_type"],
                weight_kg=float(row["weight_kg"]) if row["weight_kg"] else None,
                allergies=list(row["allergies"] or []),
                chronic_conditions=list(row["chronic_conditions"] or []),
                active_medications=list(row["active_medications"] or []),
                recent_triage_count=recent_count,
            )

            log.info(
                "node1_patient_context_fetched",
                patient_id=alert.patient_id,
                age=age,
                conditions=state.patient_context.chronic_conditions,
                recent_alerts=recent_count,
            )

    except Exception as exc:
        log.error(
            "node1_fetch_error",
            patient_id=alert.patient_id,
            error=str(exc),
            exc_info=True,
        )
        state.context_fetch_error = str(exc)

    return state


# ── Node 2: Hybrid RAG Lookup ─────────────────────────────────────────────────

async def hybrid_rag_lookup(state: TriageAgentState) -> TriageAgentState:
    """
    Hybrid search against clinical_sops table:
      1. Vector search: semantic similarity via pgvector cosine distance
      2. Keyword search: PostgreSQL full-text search (tsvector/tsquery)
      3. Reciprocal Rank Fusion: merge and re-rank results from both methods

    This two-signal approach ensures both semantic relevance (captures
    meaning) and keyword precision (captures exact clinical terms like
    'SIRS', 'SpO2', 'cardiogenic shock').
    """
    alert = CriticalAlert.model_validate(state.alert_dict)

    # Build a rich query from the alert's triggered rules + vitals
    vitals = alert.vitals_snapshot
    rules_text = ". ".join(alert.triggered_rules)
    rag_query = (
        f"Clinical protocol for: {rules_text}. "
        f"Patient presenting with HR {vitals.heart_rate_bpm} bpm, "
        f"BP {vitals.systolic_bp_mmhg}/{vitals.diastolic_bp_mmhg} mmHg, "
        f"SpO2 {vitals.spo2_percent}%, "
        f"RR {vitals.respiratory_rate_rpm} rpm, "
        f"Temp {vitals.temperature_celsius}°C. "
        f"Severity: {alert.severity.value}."
    )
    state.rag_query_used = rag_query

    log.info(
        "node2_hybrid_rag_start",
        patient_id=alert.patient_id,
        query_preview=rag_query[:120],
    )

    try:
        # Generate query embedding
        embed_result = gemini_client.models.embed_content(
            model=settings.gemini_embedding_model,
            contents=rag_query,
            config=types.EmbedContentConfig(
                task_type="RETRIEVAL_QUERY",
                output_dimensionality=768,
            ),
        )
        query_embedding = embed_result.embeddings[0].values

        async with get_session() as session:
            # ── Vector search (top 5 by cosine similarity) ───────────────────
            vector_results = await session.execute(
                text("""
                    SELECT
                        id, title, category, content,
                        1 - (embedding <=> CAST(:embedding AS vector)) AS score
                    FROM clinical_sops
                    ORDER BY embedding <=> CAST(:embedding AS vector)
                    LIMIT 5
                """),
                {"embedding": str(query_embedding)},
            )
            vector_rows = vector_results.mappings().fetchall()

            # ── Keyword search (full-text, top 5) ────────────────────────────
            # Extract key clinical terms from triggered rules for tsquery
            keyword_terms = " | ".join([
                word for rule in alert.triggered_rules
                for word in rule.split()
                if len(word) > 4  # filter short words
            ])

            keyword_results = await session.execute(
                text("""
                    SELECT
                        id, title, category, content,
                        ts_rank(
                            to_tsvector('english', title || ' ' || content),
                            plainto_tsquery('english', :query)
                        ) AS score
                    FROM clinical_sops
                    WHERE to_tsvector('english', title || ' ' || content)
                          @@ plainto_tsquery('english', :query)
                    ORDER BY score DESC
                    LIMIT 5
                """),
                {"query": rag_query},
            )
            keyword_rows = keyword_results.mappings().fetchall()

        # ── Reciprocal Rank Fusion (RRF) ─────────────────────────────────────
        # RRF score = 1/(k + rank) where k=60 is a standard smoothing constant
        # Merges rankings from both retrieval signals without needing score normalisation
        k = 60
        rrf_scores: dict[int, float] = {}
        doc_data: dict[int, dict] = {}

        for rank, row in enumerate(vector_rows):
            doc_id = row["id"]
            rrf_scores[doc_id] = rrf_scores.get(doc_id, 0) + 1 / (k + rank + 1)
            doc_data[doc_id] = {
                **dict(row), "retrieval_method": "vector"
            }

        for rank, row in enumerate(keyword_rows):
            doc_id = row["id"]
            rrf_scores[doc_id] = rrf_scores.get(doc_id, 0) + 1 / (k + rank + 1)
            if doc_id in doc_data:
                doc_data[doc_id]["retrieval_method"] = "hybrid"
            else:
                doc_data[doc_id] = {
                    **dict(row), "retrieval_method": "keyword"
                }

        # Sort by RRF score, take top 3
        top_ids = sorted(rrf_scores, key=lambda x: rrf_scores[x], reverse=True)[:3]

        state.retrieved_sops = [
            SOPDocument(
                title=doc_data[doc_id]["title"],
                category=doc_data[doc_id]["category"],
                content=doc_data[doc_id]["content"],
                relevance_score=round(rrf_scores[doc_id], 6),
                retrieval_method=doc_data[doc_id]["retrieval_method"],
            )
            for doc_id in top_ids
        ]

        log.info(
            "node2_rag_complete",
            patient_id=alert.patient_id,
            sops_retrieved=len(state.retrieved_sops),
            titles=[s.title for s in state.retrieved_sops],
            methods=[s.retrieval_method for s in state.retrieved_sops],
        )

    except Exception as exc:
        log.error(
            "node2_rag_error",
            patient_id=alert.patient_id,
            error=str(exc),
            exc_info=True,
        )
        # Continue with empty SOPs — agent degrades gracefully

    return state


# ── Node 3: Gemini Reasoning ──────────────────────────────────────────────────

async def gemini_reasoning(state: TriageAgentState) -> TriageAgentState:
    """
    Synthesises alert vitals, patient context, and retrieved SOPs into
    a structured TriageRecommendation via Gemini 2.5 Flash.

    Uses structured JSON output mode to guarantee a parseable response
    that maps directly to the TriageRecommendation Pydantic schema.
    """
    alert = CriticalAlert.model_validate(state.alert_dict)
    log.info(
        "node3_gemini_reasoning_start",
        patient_id=alert.patient_id,
        alert_id=alert.alert_id,
        sops_available=len(state.retrieved_sops),
        has_patient_context=state.patient_context is not None,
    )

    # ── Build context blocks ──────────────────────────────────────────────────

    # Patient context block
    if state.patient_context:
        ctx = state.patient_context
        meds = ", ".join(
            f"{m.get('name','?')} {m.get('dose','')}" 
            for m in ctx.active_medications
        )
        patient_block = f"""
PATIENT CONTEXT:
- Name: {ctx.full_name}, Age: {ctx.age_years}y, Gender: {ctx.gender}
- Blood Type: {ctx.blood_type or 'Unknown'}, Weight: {ctx.weight_kg or 'Unknown'} kg
- Known Allergies: {', '.join(ctx.allergies) or 'None documented'}
- Chronic Conditions: {', '.join(ctx.chronic_conditions) or 'None documented'}
- Active Medications: {meds or 'None documented'}
- Triage alerts in last 24h: {ctx.recent_triage_count}
"""
    else:
        patient_block = "PATIENT CONTEXT: Not available (database lookup failed).\n"

    # SOP context block
    sop_block = "\nRELEVANT CLINICAL SOPs:\n"
    for i, sop in enumerate(state.retrieved_sops, 1):
        sop_block += f"\n[SOP {i}: {sop.title} — {sop.category}]\n{sop.content}\n"

    if not state.retrieved_sops:
        sop_block += "No SOPs retrieved — apply general clinical judgment.\n"

    # Alert block
    v = alert.vitals_snapshot
    alert_block = f"""
CRITICAL ALERT:
- Patient ID: {alert.patient_id} | Ward: {alert.ward} | Bed: {alert.bed_number}
- Alert Severity: {alert.severity.value}
- Triggered Rules: {'; '.join(alert.triggered_rules)}
- Vitals Snapshot:
    Heart Rate:        {v.heart_rate_bpm} bpm
    Blood Pressure:    {v.systolic_bp_mmhg}/{v.diastolic_bp_mmhg} mmHg
    SpO2:              {v.spo2_percent}%
    Respiratory Rate:  {v.respiratory_rate_rpm} rpm
    Temperature:       {v.temperature_celsius}°C
- Nursing Notes: {alert.nursing_notes or 'None recorded'}
"""

    # ── Structured output prompt ──────────────────────────────────────────────
    prompt = f"""You are a senior clinical decision support AI embedded in a hospital 
triage system. Your role is to synthesise real-time patient vitals, patient history, 
and clinical protocols into an actionable triage recommendation for the clinical team.

{alert_block}
{patient_block}
{sop_block}

Based on the above, produce a clinical triage recommendation. You MUST respond with 
ONLY valid JSON matching this exact schema — no preamble, no markdown, no explanation:

{{
  "urgency_level": "IMMEDIATE | URGENT | SEMI_URGENT | NON_URGENT",
  "clinical_summary": "<2-3 sentence synthesis of current patient status and primary concern>",
  "primary_concern": "<single most critical issue>",
  "recommended_actions": [
    {{
      "priority": <1-5, 1=highest>,
      "action": "<specific clinical action>",
      "rationale": "<why this action, referencing patient history or SOP>",
      "time_window": "<when, e.g. 'within 15 minutes'>"
    }}
  ],
  "contraindications": ["<medication or intervention to avoid and why>"],
  "sops_referenced": ["<SOP title>"],
  "confidence_score": <0.0 to 1.0>
}}

Rules:
- Provide 3-5 recommended_actions ordered by priority (1 = most urgent).
- Reference specific patient allergies, conditions, and medications in rationale.
- List any contraindications based on known allergies or drug interactions.
- Confidence score reflects data completeness (1.0 = full context available).
- CRITICAL severity must always produce urgency_level of IMMEDIATE or URGENT.
"""

    try:
        response = gemini_client.models.generate_content(
            model=settings.gemini_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.1,        # low temperature for clinical determinism
                max_output_tokens=4096,
                response_mime_type="application/json",
            ),
        )
        raw_json = response.text.strip()

        # Parse and validate the response
        parsed = json.loads(raw_json)

        state.recommendation = TriageRecommendation(
            alert_id=alert.alert_id,
            patient_id=alert.patient_id,
            hospital_id=alert.hospital_id,
            urgency_level=UrgencyLevel(parsed["urgency_level"]),
            clinical_summary=parsed["clinical_summary"],
            primary_concern=parsed["primary_concern"],
            recommended_actions=[
                RecommendedAction(**a) for a in parsed["recommended_actions"]
            ],
            contraindications=parsed.get("contraindications", []),
            sops_referenced=parsed.get("sops_referenced", []),
            confidence_score=float(parsed["confidence_score"]),
            llm_model_used=settings.gemini_model,
            processing_ms=int(
                (time.time() * 1000) - state.start_time_ms
            ),
        )

        log.info(
            "node3_recommendation_generated",
            patient_id=alert.patient_id,
            urgency=state.recommendation.urgency_level.value,
            confidence=state.recommendation.confidence_score,
            actions_count=len(state.recommendation.recommended_actions),
            processing_ms=state.recommendation.processing_ms,
        )

    except json.JSONDecodeError as exc:
        log.error(
            "node3_json_parse_error",
            patient_id=alert.patient_id,
            error=str(exc),
            raw_response=raw_json[:500] if 'raw_json' in dir() else "no response",
        )
        state.llm_error = f"JSON parse error: {exc}"

    except Exception as exc:
        log.error(
            "node3_gemini_error",
            patient_id=alert.patient_id,
            error=str(exc),
            exc_info=True,
        )
        state.llm_error = str(exc)

    return state


# ── Node 4: Persist Audit ─────────────────────────────────────────────────────

async def persist_audit(state: TriageAgentState) -> TriageAgentState:
    """
    Persists the TriageRecommendation to Neon triage_events table.
    Records a Stripe metered billing event ($0.05 per triage).
    Both operations are attempted independently — a Stripe failure
    does not prevent the audit log from being written, and vice versa.
    """
    alert = CriticalAlert.model_validate(state.alert_dict)

    if state.recommendation is None:
        log.warning(
            "node4_skipped_no_recommendation",
            patient_id=alert.patient_id,
            llm_error=state.llm_error,
        )
        return state

    rec = state.recommendation

    # ── Persist to Neon ───────────────────────────────────────────────────────
    try:
        async with get_session() as session:
            await session.execute(
                text("""
                    INSERT INTO triage_events (
                        alert_id, patient_id, hospital_id, severity,
                        triggered_rules, vitals_snapshot,
                        recommendation_text, recommended_actions,
                        confidence_score, sops_referenced,
                        llm_model_used, processing_ms, stripe_event_id
                    ) VALUES (
                        :alert_id, :patient_id, :hospital_id, :severity,
                        :triggered_rules, CAST(:vitals_snapshot AS jsonb),
                        :recommendation_text, CAST(:recommended_actions AS jsonb),
                        :confidence_score, :sops_referenced,
                        :llm_model_used, :processing_ms, :stripe_event_id
                    )
                    ON CONFLICT (alert_id) DO NOTHING
                """),
                {
                    "alert_id":            alert.alert_id,
                    "patient_id":          alert.patient_id,
                    "hospital_id":         alert.hospital_id,
                    "severity":            alert.severity.value,
                    "triggered_rules":     alert.triggered_rules,
                    "vitals_snapshot":     alert.vitals_snapshot.model_dump_json(),
                    "recommendation_text": rec.clinical_summary,
                    "recommended_actions": json.dumps(
                        [a.model_dump() for a in rec.recommended_actions]
                    ),
                    "confidence_score":    rec.confidence_score,
                    "sops_referenced":     rec.sops_referenced,
                    "llm_model_used":      rec.llm_model_used,
                    "processing_ms":       rec.processing_ms,
                    "stripe_event_id":     state.stripe_event_id,
                },
            )
        state.audit_persisted = True
        log.info(
            "node4_audit_persisted",
            alert_id=alert.alert_id,
            patient_id=alert.patient_id,
        )

    except Exception as exc:
        log.error(
            "node4_persist_error",
            alert_id=alert.alert_id,
            error=str(exc),
            exc_info=True,
        )

    # ── Stripe metered billing event ──────────────────────────────────────────
    if settings.stripe_secret_key:
        try:
            event = stripe.billing.MeterEvent.create(
                event_name=settings.stripe_meter_event_name,
                payload={
                    "value": "1",
                    "stripe_customer_id": alert.hospital_id,
                },
            )
            state.stripe_event_id = event.identifier
            log.info(
                "node4_stripe_meter_event_recorded",
                alert_id=alert.alert_id,
                stripe_event_id=event.identifier,
            )
        except Exception as exc:
            # Billing failure must never block clinical data flow
            log.warning(
                "node4_stripe_error_non_fatal",
                alert_id=alert.alert_id,
                error=str(exc),
            )
    else:
        log.debug("node4_stripe_skipped", reason="no_stripe_key_configured")

    return state


# ── LangGraph StateGraph Assembly ────────────────────────────────────────────

def build_triage_graph():
    """
    Assemble the LangGraph StateGraph.
    Returns a compiled graph ready for async invocation.

    Node execution is sequential — each node receives the full state
    and returns the mutated state for the next node.
    """
    from langgraph.graph import StateGraph, END

    # LangGraph requires a TypedDict or dataclass for state, not Pydantic.
    # We use a plain dict wrapper and convert to/from TriageAgentState
    # at the graph boundary.
    from typing import TypedDict

    class GraphState(TypedDict, total=False):
        state: TriageAgentState

    async def node1(data: dict) -> dict:
        data["state"] = await fetch_patient_context(data["state"])
        return data

    async def node2(data: dict) -> dict:
        data["state"] = await hybrid_rag_lookup(data["state"])
        return data

    async def node3(data: dict) -> dict:
        data["state"] = await gemini_reasoning(data["state"])
        return data

    async def node4(data: dict) -> dict:
        data["state"] = await persist_audit(data["state"])
        return data

    graph = StateGraph(GraphState)
    graph.add_node("fetch_patient_context", node1)
    graph.add_node("hybrid_rag_lookup",     node2)
    graph.add_node("gemini_reasoning",      node3)
    graph.add_node("persist_audit",         node4)

    graph.set_entry_point("fetch_patient_context")
    graph.add_edge("fetch_patient_context", "hybrid_rag_lookup")
    graph.add_edge("hybrid_rag_lookup",     "gemini_reasoning")
    graph.add_edge("gemini_reasoning",      "persist_audit")
    graph.add_edge("persist_audit",         END)

    return graph.compile()


# Module-level compiled graph — import this in FastAPI
triage_graph = build_triage_graph()


# ── Public Entry Point ────────────────────────────────────────────────────────

async def run_triage_agent(alert: CriticalAlert) -> TriageRecommendation | None:
    """
    Public API for the triage agent.
    Called by FastAPI when a CriticalAlert arrives via the CEP pipeline.

    Returns TriageRecommendation on success, None if the LLM node failed.
    """
    start_ms = time.time() * 1000
    log.info(
        "triage_agent_invoked",
        alert_id=alert.alert_id,
        patient_id=alert.patient_id,
        severity=alert.severity.value,
    )

    initial_state = TriageAgentState(
        alert_dict=alert.model_dump(mode="json"),
        start_time_ms=start_ms,
    )

    result = await triage_graph.ainvoke({"state": initial_state})
    final_state: TriageAgentState = result["state"]

    if final_state.recommendation:
        log.info(
            "triage_agent_complete",
            alert_id=alert.alert_id,
            patient_id=alert.patient_id,
            urgency=final_state.recommendation.urgency_level.value,
            confidence=final_state.recommendation.confidence_score,
            audit_persisted=final_state.audit_persisted,
            total_ms=int(time.time() * 1000 - start_ms),
        )
        return final_state.recommendation

    log.error(
        "triage_agent_failed",
        alert_id=alert.alert_id,
        llm_error=final_state.llm_error,
        context_error=final_state.context_fetch_error,
    )
    return None