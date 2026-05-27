'use client'

import type { TriageRecommendation } from '@/types/taas'
import { UrgencyBadge } from '@/components/ui/SeverityBadge'
import { CheckCircle, AlertTriangle, BookOpen, Clock, X } from 'lucide-react'

interface Props {
    recommendation: TriageRecommendation
    onClose: () => void
}

export function TriagePanel({ recommendation: rec, onClose }: Props) {
    return (
        <div className="fixed inset-y-0 right-0 w-[480px] bg-gray-900 border-l border-gray-800 flex flex-col shadow-2xl z-50 overflow-y-auto">
            {/* Header */}
            <div className="sticky top-0 bg-gray-900 border-b border-gray-800 px-6 py-4 flex items-center justify-between">
                <div>
                    <div className="flex items-center gap-3">
                        <UrgencyBadge urgency={rec.urgency_level} />
                        <span className="text-sm font-semibold text-gray-200">
                            {rec.patient_id}
                        </span>
                    </div>
                    <div className="text-xs text-gray-500 mt-1">
                        Confidence {(rec.confidence_score * 100).toFixed(0)}% ·{' '}
                        {(rec.processing_ms / 1000).toFixed(1)}s ·{' '}
                        {rec.llm_model_used}
                    </div>
                </div>
                <button
                    onClick={onClose}
                    className="p-1.5 rounded-lg hover:bg-gray-800 text-gray-400 hover:text-gray-200 transition-colors"
                >
                    <X size={16} />
                </button>
            </div>

            <div className="flex-1 px-6 py-4 space-y-6">
                {/* Primary concern */}
                <div className="p-4 rounded-xl bg-red-950/40 border border-red-900/50">
                    <div className="text-xs font-semibold text-red-400 uppercase tracking-wide mb-1">
                        Primary Concern
                    </div>
                    <div className="text-sm text-gray-200 font-medium">{rec.primary_concern}</div>
                </div>

                {/* Clinical summary */}
                <div>
                    <div className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
                        Clinical Summary
                    </div>
                    <p className="text-sm text-gray-300 leading-relaxed">{rec.clinical_summary}</p>
                </div>

                {/* Recommended actions */}
                <div>
                    <div className="flex items-center gap-2 mb-3">
                        <CheckCircle size={14} className="text-green-400" />
                        <span className="text-xs font-semibold text-gray-400 uppercase tracking-wide">
                            Recommended Actions
                        </span>
                    </div>
                    <div className="space-y-3">
                        {rec.recommended_actions.map((action) => (
                            <div
                                key={action.priority}
                                className="p-3 rounded-lg bg-gray-800 border border-gray-700"
                            >
                                <div className="flex items-start gap-3">
                                    <span className="flex-shrink-0 w-6 h-6 rounded-full bg-gray-700 text-xs font-bold text-gray-300 flex items-center justify-center">
                                        {action.priority}
                                    </span>
                                    <div className="flex-1 min-w-0">
                                        <div className="text-sm font-medium text-gray-200">
                                            {action.action}
                                        </div>
                                        <div className="text-xs text-gray-400 mt-1 leading-relaxed">
                                            {action.rationale}
                                        </div>
                                        <div className="flex items-center gap-1 mt-2 text-xs text-amber-400">
                                            <Clock size={11} />
                                            {action.time_window}
                                        </div>
                                    </div>
                                </div>
                            </div>
                        ))}
                    </div>
                </div>

                {/* Contraindications */}
                {rec.contraindications.length > 0 && (
                    <div>
                        <div className="flex items-center gap-2 mb-3">
                            <AlertTriangle size={14} className="text-amber-400" />
                            <span className="text-xs font-semibold text-gray-400 uppercase tracking-wide">
                                Contraindications
                            </span>
                        </div>
                        <div className="space-y-2">
                            {rec.contraindications.map((c, i) => (
                                <div
                                    key={i}
                                    className="flex items-start gap-2 p-3 rounded-lg bg-amber-950/30 border border-amber-900/40"
                                >
                                    <AlertTriangle size={12} className="text-amber-400 flex-shrink-0 mt-0.5" />
                                    <span className="text-xs text-amber-200 leading-relaxed">{c}</span>
                                </div>
                            ))}
                        </div>
                    </div>
                )}

                {/* SOPs referenced */}
                {rec.sops_referenced.length > 0 && (
                    <div>
                        <div className="flex items-center gap-2 mb-3">
                            <BookOpen size={14} className="text-blue-400" />
                            <span className="text-xs font-semibold text-gray-400 uppercase tracking-wide">
                                Clinical SOPs Referenced
                            </span>
                        </div>
                        <div className="space-y-1">
                            {rec.sops_referenced.map((sop, i) => (
                                <div
                                    key={i}
                                    className="text-xs text-blue-300 bg-blue-950/30 border border-blue-900/40 rounded-lg px-3 py-2"
                                >
                                    {sop}
                                </div>
                            ))}
                        </div>
                    </div>
                )}
            </div>
        </div>
    )
}