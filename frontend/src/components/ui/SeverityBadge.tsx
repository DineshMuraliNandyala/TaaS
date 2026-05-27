import type { AlertSeverity, UrgencyLevel } from '@/types/taas'

const severityConfig: Record<AlertSeverity, { label: string; classes: string }> = {
    CRITICAL: { label: 'CRITICAL', classes: 'bg-red-950 text-red-400 border-red-800' },
    HIGH: { label: 'HIGH', classes: 'bg-orange-950 text-orange-400 border-orange-800' },
    MEDIUM: { label: 'MEDIUM', classes: 'bg-yellow-950 text-yellow-400 border-yellow-800' },
    LOW: { label: 'LOW', classes: 'bg-gray-800 text-gray-400 border-gray-700' },
}

const urgencyConfig: Record<UrgencyLevel, { label: string; classes: string }> = {
    IMMEDIATE: { label: 'IMMEDIATE', classes: 'bg-red-950 text-red-300 border-red-700' },
    URGENT: { label: 'URGENT', classes: 'bg-orange-950 text-orange-300 border-orange-700' },
    SEMI_URGENT: { label: 'SEMI-URGENT', classes: 'bg-yellow-950 text-yellow-300 border-yellow-700' },
    NON_URGENT: { label: 'NON-URGENT', classes: 'bg-gray-800 text-gray-300 border-gray-700' },
}

export function SeverityBadge({ severity }: { severity: AlertSeverity }) {
    const cfg = severityConfig[severity]
    return (
        <span className={`inline-flex items-center px-2 py-0.5 rounded-md text-xs font-semibold border ${cfg.classes}`}>
            {cfg.label}
        </span>
    )
}

export function UrgencyBadge({ urgency }: { urgency: UrgencyLevel }) {
    const cfg = urgencyConfig[urgency]
    return (
        <span className={`inline-flex items-center px-2 py-0.5 rounded-md text-xs font-semibold border ${cfg.classes}`}>
            {cfg.label}
        </span>
    )
}