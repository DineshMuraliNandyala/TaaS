/**
 * TypeScript types mirroring the backend Pydantic models exactly.
 * Single source of truth for all API response shapes on the frontend.
 * Update these whenever backend models change.
 */

export type AlertSeverity = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL'
export type UrgencyLevel = 'IMMEDIATE' | 'URGENT' | 'SEMI_URGENT' | 'NON_URGENT'
export type WebSocketEventType = 'ping' | 'alert_received' | 'triage_recommendation'

export interface VitalSigns {
    heart_rate_bpm: number
    systolic_bp_mmhg: number
    diastolic_bp_mmhg: number
    spo2_percent: number
    respiratory_rate_rpm: number
    temperature_celsius: number
}

export interface CriticalAlert {
    alert_id: string
    source_event_id: string
    patient_id: string
    hospital_id: string
    ward: string
    bed_number: string
    timestamp_utc: string
    severity: AlertSeverity
    triggered_rules: string[]
    vitals_snapshot: VitalSigns
    nursing_notes: string | null
}

export interface RecommendedAction {
    priority: number
    action: string
    rationale: string
    time_window: string
}

export interface TriageRecommendation {
    recommendation_id: string
    alert_id: string
    patient_id: string
    hospital_id: string
    urgency_level: UrgencyLevel
    clinical_summary: string
    primary_concern: string
    recommended_actions: RecommendedAction[]
    contraindications: string[]
    sops_referenced: string[]
    confidence_score: number
    llm_model_used: string
    processing_ms: number
    generated_at: string
}

export interface WebSocketEvent {
    event_type: WebSocketEventType
    payload: CriticalAlert | TriageRecommendation | { message: string }
    timestamp: string
}

export interface PatientSummary {
    patient_id: string
    full_name: string
    age_years: number
    gender: string
    ward: string
    bed_number: string
    chronic_conditions: string[]
    active_medications: Array<{ name: string; dose: string; frequency: string }>
    recent_alert_count: number
}

export interface TriageEventSummary {
    id: number
    alert_id: string
    patient_id: string
    severity: AlertSeverity
    urgency_level: UrgencyLevel | null
    recommendation_text: string | null
    confidence_score: number | null
    processing_ms: number | null
    created_at: string
}

export interface DashboardStats {
    period: string
    total_events: number
    critical_count: number
    high_count: number
    medium_count: number
    avg_confidence: number
    avg_processing_ms: number
    patients_triaged: number
    ws_connections: number
}