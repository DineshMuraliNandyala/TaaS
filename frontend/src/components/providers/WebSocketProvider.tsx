/**
 * WebSocketProvider
 * ──────────────────
 * Manages a single persistent WebSocket connection for the entire app.
 * Distributes events to subscribers via a React context + EventEmitter pattern.
 *
 * Features:
 *   - Auto-reconnect with exponential backoff (max 30s)
 *   - Heartbeat ping every 25s to keep connection alive through proxies
 *   - Connection state exposed via context for UI indicators
 *   - All components subscribe via useWebSocket() hook — zero prop drilling
 */
'use client'

import React, {
    createContext,
    useCallback,
    useContext,
    useEffect,
    useRef,
    useState,
} from 'react'
import type { CriticalAlert, TriageRecommendation, WebSocketEvent } from '@/types/taas'

// ── Event bus types ──────────────────────────────────────────────────────────

type AlertHandler = (alert: CriticalAlert) => void
type RecommendationHandler = (rec: TriageRecommendation) => void

interface WSContextValue {
    isConnected: boolean
    lastPing: Date | null
    onAlert: (handler: AlertHandler) => () => void
    onRecommendation: (handler: RecommendationHandler) => () => void
}

const WSContext = createContext<WSContextValue | null>(null)

// ── Provider ─────────────────────────────────────────────────────────────────

const PING_INTERVAL_MS = 25_000
const MAX_BACKOFF_MS = 30_000

/**
 * Construct the WebSocket URL.
 * Next.js rewrites do NOT proxy WebSocket upgrade requests, so the
 * browser must connect directly to the backend for WebSocket.
 * 
 * In local dev, the backend runs on port 8000 on the same host.
 * NEXT_PUBLIC_WS_URL can be set for production deployments.
 */
function getWsUrl(): string {
    if (typeof window === 'undefined') return 'ws://localhost:8000/ws'
    // If explicitly configured, use that
    const envUrl = process.env.NEXT_PUBLIC_WS_URL
    if (envUrl) return envUrl
    // Default: same hostname as the page but on port 8000
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    return `${proto}//${window.location.hostname}:8000/ws`
}

export function WebSocketProvider({ children }: { children: React.ReactNode }) {
    const [isConnected, setIsConnected] = useState(false)
    const [lastPing, setLastPing] = useState<Date | null>(null)

    const wsRef = useRef<WebSocket | null>(null)
    const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
    const pingIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
    const backoffRef = useRef(1000) // start at 1s, double each attempt

    // Subscriber registries
    const alertHandlers = useRef<Set<AlertHandler>>(new Set())
    const recommendationHandlers = useRef<Set<RecommendationHandler>>(new Set())

    const connect = useCallback(() => {
        if (wsRef.current?.readyState === WebSocket.OPEN) return

        const ws = new WebSocket(getWsUrl())
        wsRef.current = ws

        ws.onopen = () => {
            setIsConnected(true)
            backoffRef.current = 1000 // reset backoff on successful connect

            // Heartbeat — send ping every 25s to keep connection alive
            pingIntervalRef.current = setInterval(() => {
                if (ws.readyState === WebSocket.OPEN) {
                    ws.send('ping')
                }
            }, PING_INTERVAL_MS)
        }

        ws.onmessage = (event) => {
            try {
                const wsEvent = JSON.parse(event.data) as WebSocketEvent

                switch (wsEvent.event_type) {
                    case 'ping':
                        setLastPing(new Date())
                        break

                    case 'alert_received':
                        alertHandlers.current.forEach((h) =>
                            h(wsEvent.payload as CriticalAlert)
                        )
                        break

                    case 'triage_recommendation':
                        recommendationHandlers.current.forEach((h) =>
                            h(wsEvent.payload as TriageRecommendation)
                        )
                        break
                }
            } catch {
                // Malformed message — ignore silently
            }
        }

        ws.onclose = () => {
            setIsConnected(false)
            if (pingIntervalRef.current) clearInterval(pingIntervalRef.current)

            // Exponential backoff reconnect
            const delay = Math.min(backoffRef.current, MAX_BACKOFF_MS)
            backoffRef.current = Math.min(backoffRef.current * 2, MAX_BACKOFF_MS)
            reconnectTimeoutRef.current = setTimeout(connect, delay)
        }

        ws.onerror = () => {
            ws.close()
        }
    }, [])

    useEffect(() => {
        connect()
        return () => {
            wsRef.current?.close()
            if (reconnectTimeoutRef.current)
                clearTimeout(reconnectTimeoutRef.current)
            if (pingIntervalRef.current)
                clearInterval(pingIntervalRef.current)
        }
    }, [connect])

    // Subscription helpers — return unsubscribe function
    const onAlert = useCallback((handler: AlertHandler) => {
        alertHandlers.current.add(handler)
        return () => alertHandlers.current.delete(handler)
    }, [])

    const onRecommendation = useCallback((handler: RecommendationHandler) => {
        recommendationHandlers.current.add(handler)
        return () => recommendationHandlers.current.delete(handler)
    }, [])

    return (
        <WSContext.Provider value={{ isConnected, lastPing, onAlert, onRecommendation }}>
            {children}
        </WSContext.Provider>
    )
}

// ── Hook ─────────────────────────────────────────────────────────────────────

export function useWebSocket(): WSContextValue {
    const ctx = useContext(WSContext)
    if (!ctx) throw new Error('useWebSocket must be used inside WebSocketProvider')
    return ctx
}