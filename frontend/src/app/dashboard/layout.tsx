import { auth } from '@clerk/nextjs/server'
import { redirect } from 'next/navigation'
import { WebSocketProvider } from '@/components/providers/WebSocketProvider'
import { UserButton } from '@clerk/nextjs'
import { Activity } from 'lucide-react'
import { WSIndicatorClient } from '@/components/dashboard/WSIndicatorClient'

export default async function DashboardLayout({
    children,
}: {
    children: React.ReactNode
}) {
    const { userId } = await auth()
    if (!userId) redirect('/sign-in')

    return (
        <WebSocketProvider>
            <div className="min-h-screen flex flex-col bg-gray-950">
                {/* Top nav */}
                <header className="h-12 border-b border-gray-800 bg-gray-900 flex items-center px-4 gap-3 flex-shrink-0">
                    <Activity size={16} className="text-red-500" />
                    <span className="text-sm font-semibold">TaaS Platform</span>
                    <span className="text-xs text-gray-600 ml-1">
                        Triage-as-a-Service
                    </span>
                    <div className="ml-auto flex items-center gap-3">
                        <WSIndicatorClient />
                        <UserButton />
                    </div>
                </header>
                {children}
            </div>
        </WebSocketProvider>
    )
}