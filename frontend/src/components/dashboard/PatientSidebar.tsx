'use client'

import { useEffect, useState } from 'react'
import { useWebSocket } from '@/components/providers/WebSocketProvider'
import { api } from '@/lib/api'
import type { CriticalAlert, PatientSummary } from '@/types/taas'
import { StatusDot } from '@/components/ui/StatusDot'
import { User } from 'lucide-react'

interface Props {
    selectedPatientId: string | null
    onSelect: (id: string) => void
}

export function PatientSidebar({ selectedPatientId, onSelect }: Props) {
    const [patients, setPatients] = useState<PatientSummary[]>([])
    const [alertCounts, setAlertCounts] = useState<Record<string, number>>({})
    const { onAlert } = useWebSocket()

    useEffect(() => {
        api.getPatients().then(setPatients).catch(console.error)
    }, [])

    // Increment badge count on live alerts
    useEffect(() => {
        return onAlert((alert: CriticalAlert) => {
            setAlertCounts((prev) => ({
                ...prev,
                [alert.patient_id]: (prev[alert.patient_id] ?? 0) + 1,
            }))
        })
    }, [onAlert])

    const wardGroups = patients.reduce<Record<string, PatientSummary[]>>(
        (acc, p) => {
            acc[p.ward] = acc[p.ward] ?? []
            acc[p.ward].push(p)
            return acc
        },
        {}
    )

    return (
        <aside className="w-64 border-r border-gray-800 bg-gray-900 flex flex-col overflow-y-auto">
            <div className="p-4 border-b border-gray-800">
                <div className="flex items-center gap-2">
                    <User size={14} className="text-gray-400" />
                    <span className="text-xs font-medium text-gray-400 uppercase tracking-wide">
                        Patients
                    </span>
                </div>
            </div>

            {Object.entries(wardGroups).map(([ward, pts]) => (
                <div key={ward}>
                    <div className="px-4 py-2 text-xs font-semibold text-gray-500 uppercase tracking-wider bg-gray-950">
                        {ward}
                    </div>
                    {pts.map((p) => {
                        const liveAlerts = alertCounts[p.patient_id] ?? 0
                        const isCritical = liveAlerts > 0
                        const isSelected = p.patient_id === selectedPatientId

                        return (
                            <button
                                key={p.patient_id}
                                onClick={() => {
                                    onSelect(p.patient_id)
                                    // Clear badge on select
                                    setAlertCounts((prev) => ({ ...prev, [p.patient_id]: 0 }))
                                }}
                                className={`w-full px-4 py-3 flex items-center gap-3 text-left transition-colors hover:bg-gray-800 ${isSelected ? 'bg-gray-800 border-r-2 border-red-500' : ''
                                    }`}
                            >
                                <StatusDot
                                    status={isCritical ? 'red' : 'green'}
                                    pulse={isCritical}
                                />
                                <div className="flex-1 min-w-0">
                                    <div className="text-sm font-medium text-gray-200 truncate">
                                        {p.full_name}
                                    </div>
                                    <div className="text-xs text-gray-500">
                                        {p.patient_id} · Bed {p.bed_number}
                                    </div>
                                </div>
                                {liveAlerts > 0 && (
                                    <span className="flex-shrink-0 w-5 h-5 rounded-full bg-red-600 text-white text-xs flex items-center justify-center font-bold">
                                        {liveAlerts}
                                    </span>
                                )}
                            </button>
                        )
                    })}
                </div>
            ))}
        </aside>
    )
}