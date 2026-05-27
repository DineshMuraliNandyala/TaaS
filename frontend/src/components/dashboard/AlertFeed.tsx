'use client'

import { useEffect, useRef, useState } from 'react'
import { useWebSocket } from '@/components/providers/WebSocketProvider'
import type { CriticalAlert, TriageRecommendation } from '@/types/taas'
import { SeverityBadge } from '@/components/ui/SeverityBadge'
import { TriagePanel } from './TriagePanel'
import { Brain, ChevronRight, Radio } from 'lucide-react'

interface FeedItem {
    id: string
    alert: CriticalAlert
    recommendation: TriageRecommendation | null
    receivedAt: Date
    processing: boolean
}

interface Props {
    filterPatientId: string | null
}

export function AlertFeed({ filterPatientId }: Props) {
    const [items, setItems] = useState<FeedItem[]>([])
    const [selected, setSelected] = useState<TriageRecommendation | null>(null)
    const { onAlert, onRecommendation } = useWebSocket()
    const feedRef = useRef<HTMLDivElement>(null)

    // New alert arrives — add to feed immediately
    useEffect(() => {
        return onAlert((alert: CriticalAlert) => {
            setItems((prev) => [
                {
                    id: alert.alert_id,
                    alert,
                    recommendation: null,
                    receivedAt: new Date(),
                    processing: true,
                },
                ...prev.slice(0, 49), // keep max 50 items
            ])
        })
    }, [onAlert])

    // Recommendation arrives — attach to existing alert item
    useEffect(() => {
        return onRecommendation((rec: TriageRecommendation) => {
            setItems((prev) =>
                prev.map((item) =>
                    item.alert.alert_id === rec.alert_id
                        ? { ...item, recommendation: rec, processing: false }
                        : item
                )
            )
        })
    }, [onRecommendation])

    const filtered = filterPatientId
        ? items.filter((i) => i.alert.patient_id === filterPatientId)
        : items

    return (
        <>
            <div className="flex-1 flex flex-col overflow-hidden">
                {/* Feed header */}
                <div className="px-4 py-3 border-b border-gray-800 flex items-center gap-2">
                    <Radio size={14} className="text-red-400 animate-pulse" />
                    <span className="text-sm font-medium text-gray-300">Live Alert Feed</span>
                    {filtered.length > 0 && (
                        <span className="ml-auto text-xs text-gray-500">
                            {filtered.length} event{filtered.length !== 1 ? 's' : ''}
                            {filterPatientId ? ` for ${filterPatientId}` : ''}
                        </span>
                    )}
                </div>

                {/* Feed items */}
                <div
                    ref={feedRef}
                    className="flex-1 overflow-y-auto p-4 space-y-3"
                >
                    {filtered.length === 0 && (
                        <div className="flex flex-col items-center justify-center h-64 text-gray-600">
                            <Radio size={32} className="mb-3 opacity-40" />
                            <p className="text-sm">Waiting for alerts...</p>
                            <p className="text-xs mt-1 opacity-60">
                                PT-005 deteriorates every ~60 seconds
                            </p>
                        </div>
                    )}

                    {filtered.map((item) => (
                        <div
                            key={item.id}
                            className={`rounded-xl border transition-all ${item.alert.severity === 'CRITICAL'
                                    ? 'border-red-900/70 bg-red-950/20'
                                    : item.alert.severity === 'HIGH'
                                        ? 'border-orange-900/70 bg-orange-950/20'
                                        : 'border-gray-800 bg-gray-900'
                                }`}
                        >
                            {/* Alert header row */}
                            <div className="px-4 py-3 flex items-center gap-3">
                                <SeverityBadge severity={item.alert.severity} />
                                <span className="text-sm font-semibold text-gray-200">
                                    {item.alert.patient_id}
                                </span>
                                <span className="text-xs text-gray-500">
                                    {item.alert.ward} / {item.alert.bed_number}
                                </span>
                                <span className="ml-auto text-xs text-gray-600">
                                    {item.receivedAt.toLocaleTimeString()}
                                </span>
                            </div>

                            {/* Triggered rules */}
                            <div className="px-4 pb-3">
                                <div className="flex flex-wrap gap-1.5">
                                    {item.alert.triggered_rules.map((rule, i) => (
                                        <span
                                            key={i}
                                            className="text-xs px-2 py-0.5 rounded-md bg-gray-800 text-gray-400 border border-gray-700"
                                        >
                                            {rule.split(':')[0]}
                                        </span>
                                    ))}
                                </div>
                            </div>

                            {/* Recommendation row */}
                            <div className="px-4 pb-3 border-t border-gray-800/50 pt-3">
                                {item.processing ? (
                                    <div className="flex items-center gap-2 text-xs text-gray-500">
                                        <Brain size={12} className="animate-pulse text-purple-400" />
                                        <span>LangGraph agent reasoning...</span>
                                    </div>
                                ) : item.recommendation ? (
                                    <button
                                        onClick={() => setSelected(item.recommendation)}
                                        className="flex items-center gap-2 text-xs text-purple-400 hover:text-purple-300 transition-colors group"
                                    >
                                        <Brain size={12} />
                                        <span className="font-medium">
                                            {item.recommendation.urgency_level} —{' '}
                                            {item.recommendation.primary_concern.slice(0, 60)}...
                                        </span>
                                        <ChevronRight
                                            size={12}
                                            className="group-hover:translate-x-0.5 transition-transform"
                                        />
                                    </button>
                                ) : null}
                            </div>
                        </div>
                    ))}
                </div>
            </div>

            {/* Triage detail panel — slides in from right */}
            {selected && (
                <TriagePanel
                    recommendation={selected}
                    onClose={() => setSelected(null)}
                />
            )}
        </>
    )
}