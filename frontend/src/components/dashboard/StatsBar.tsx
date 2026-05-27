'use client'

import { useEffect, useState } from 'react'
import { api } from '@/lib/api'
import type { DashboardStats } from '@/types/taas'
import { Activity, AlertTriangle, Clock, Users } from 'lucide-react'

export function StatsBar() {
    const [stats, setStats] = useState<DashboardStats | null>(null)

    useEffect(() => {
        const load = () => api.getStats().then(setStats).catch(console.error)
        load()
        // Refresh stats every 30s
        const interval = setInterval(load, 30_000)
        return () => clearInterval(interval)
    }, [])

    const cards = [
        {
            icon: Activity,
            label: 'Events (24h)',
            value: stats?.total_events ?? '—',
            sub: 'total triage events',
            colour: 'text-blue-400',
        },
        {
            icon: AlertTriangle,
            label: 'Critical',
            value: stats?.critical_count ?? '—',
            sub: `${stats?.high_count ?? 0} high severity`,
            colour: 'text-red-400',
        },
        {
            icon: Users,
            label: 'Patients Triaged',
            value: stats?.patients_triaged ?? '—',
            sub: 'unique patients',
            colour: 'text-green-400',
        },
        {
            icon: Clock,
            label: 'Avg Response',
            value: stats ? `${(stats.avg_processing_ms / 1000).toFixed(1)}s` : '—',
            sub: 'agent processing time',
            colour: 'text-purple-400',
        },
    ]

    return (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 p-4 border-b border-gray-800">
            {cards.map(({ icon: Icon, label, value, sub, colour }) => (
                <div key={label} className="bg-gray-900 rounded-xl p-4 border border-gray-800">
                    <div className="flex items-center gap-2 mb-2">
                        <Icon size={14} className={colour} />
                        <span className="text-xs text-gray-500 uppercase tracking-wide">{label}</span>
                    </div>
                    <div className="text-2xl font-bold text-gray-100">{value}</div>
                    <div className="text-xs text-gray-500 mt-0.5">{sub}</div>
                </div>
            ))}
        </div>
    )
}