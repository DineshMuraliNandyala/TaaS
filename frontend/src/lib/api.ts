/**
 * Typed fetch wrappers for all TaaS REST endpoints.
 * All functions throw on non-2xx responses — handle errors at call site.
 *
 * Requests are routed through the Next.js proxy (/api/backend)
 * so the browser never makes cross-origin calls to localhost:8000.
 * The rewrite rule in next.config.ts maps:
 *   /api/backend/:path* → http://localhost:8000/:path*
 */

import type {
    DashboardStats,
    PatientSummary,
    TriageEventSummary,
} from '@/types/taas'

// Use the Next.js proxy prefix — all requests stay same-origin
const BASE = '/api/backend'

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
    const res = await fetch(`${BASE}${path}`, {
        ...init,
        headers: { 'Content-Type': 'application/json', ...init?.headers },
    })
    if (!res.ok) {
        throw new Error(`API error ${res.status} on ${path}`)
    }
    return res.json() as Promise<T>
}

export const api = {
    getPatients: (hospitalId?: string, ward?: string) => {
        const params = new URLSearchParams()
        if (hospitalId) params.set('hospital_id', hospitalId)
        if (ward) params.set('ward', ward)
        const qs = params.toString()
        return apiFetch<PatientSummary[]>(`/api/v1/patients${qs ? `?${qs}` : ''}`)
    },

    getPatientHistory: (patientId: string, limit = 10) =>
        apiFetch<TriageEventSummary[]>(
            `/api/v1/patients/${patientId}/history?limit=${limit}`
        ),

    getRecentTriage: (page = 1, pageSize = 20, severity?: string) => {
        const params = new URLSearchParams({
            page: String(page),
            page_size: String(pageSize),
        })
        if (severity) params.set('severity', severity)
        return apiFetch<{ items: TriageEventSummary[]; total: number }>(
            `/api/v1/triage/recent?${params}`
        )
    },

    getStats: () => apiFetch<DashboardStats>('/api/v1/stats'),

    fireTestAlert: () =>
        apiFetch<{ status: string; urgency?: string; confidence?: number }>(
            '/api/v1/debug/fire-test-alert',
            { method: 'POST' }
        ),
}