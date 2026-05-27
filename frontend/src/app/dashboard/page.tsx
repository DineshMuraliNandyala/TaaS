'use client'

import { useState } from 'react'
import { StatsBar } from '@/components/dashboard/StatsBar'
import { PatientSidebar } from '@/components/dashboard/PatientSidebar'
import { AlertFeed } from '@/components/dashboard/AlertFeed'

export default function DashboardPage() {
    const [selectedPatientId, setSelectedPatientId] = useState<string | null>(null)

    return (
        <div className="flex-1 flex flex-col overflow-hidden">
            <StatsBar />
            <div className="flex-1 flex overflow-hidden">
                <PatientSidebar
                    selectedPatientId={selectedPatientId}
                    onSelect={(id) =>
                        setSelectedPatientId((prev) => (prev === id ? null : id))
                    }
                />
                <main className="flex-1 flex flex-col overflow-hidden">
                    <AlertFeed filterPatientId={selectedPatientId} />
                </main>
            </div>
        </div>
    )
}