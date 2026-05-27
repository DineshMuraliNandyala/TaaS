'use client'

import { useWebSocket } from '@/components/providers/WebSocketProvider'
import { StatusDot } from '@/components/ui/StatusDot'

export function WSIndicatorClient() {
    const { isConnected } = useWebSocket()
    return (
        <div className="flex items-center gap-1.5 text-xs text-gray-500">
            <StatusDot status={isConnected ? 'green' : 'red'} pulse={isConnected} />
            <span>{isConnected ? 'Live' : 'Reconnecting...'}</span>
        </div>
    )
}