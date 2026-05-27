'use client'

import Link from 'next/link'
import { SignInButton, useAuth } from '@clerk/nextjs'
import { Activity, Brain, Zap, Shield } from 'lucide-react'

export default function LandingPage() {
  const { isSignedIn } = useAuth()

  return (
    <div className="min-h-screen bg-gray-950 flex flex-col">
      {/* Nav */}
      <nav className="border-b border-gray-800 px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Activity className="text-red-500" size={24} />
          <span className="text-lg font-semibold tracking-tight">TaaS</span>
          <span className="text-xs text-gray-500 ml-1">Triage-as-a-Service</span>
        </div>
        <div>
          {!isSignedIn ? (
            <SignInButton mode="modal">
              <button className="px-4 py-2 bg-red-600 hover:bg-red-500 rounded-lg text-sm font-medium transition-colors">
                Sign In
              </button>
            </SignInButton>
          ) : (
            <Link
              href="/dashboard"
              className="px-4 py-2 bg-red-600 hover:bg-red-500 rounded-lg text-sm font-medium transition-colors"
            >
              Go to Dashboard →
            </Link>
          )}
        </div>
      </nav>

      {/* Hero */}
      <main className="flex-1 flex flex-col items-center justify-center px-6 text-center">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-red-950 border border-red-800 text-red-400 text-xs mb-8">
          <span className="w-2 h-2 rounded-full bg-red-500 animate-pulse" />
          Live pipeline active — real-time telemetry ingestion
        </div>

        <h1 className="text-5xl font-bold tracking-tight mb-4 max-w-3xl">
          AI-Powered Clinical Triage{' '}
          <span className="text-red-500">in Real Time</span>
        </h1>
        <p className="text-gray-400 text-lg max-w-xl mb-10">
          Ingests hospital telemetry streams, detects critical anomalies via CEP,
          and generates actionable clinical recommendations using LangGraph +
          Gemini 2.5 Flash — in under 30 seconds per event.
        </p>

        {!isSignedIn ? (
          <SignInButton mode="modal">
            <button className="px-8 py-3 bg-red-600 hover:bg-red-500 rounded-xl text-base font-semibold transition-colors shadow-lg shadow-red-900/30">
              Access Live Dashboard →
            </button>
          </SignInButton>
        ) : (
          <Link
            href="/dashboard"
            className="px-8 py-3 bg-red-600 hover:bg-red-500 rounded-xl text-base font-semibold transition-colors shadow-lg shadow-red-900/30"
          >
            Access Live Dashboard →
          </Link>
        )}

        {/* Feature pills */}
        <div className="mt-16 grid grid-cols-2 md:grid-cols-4 gap-4 max-w-3xl w-full">
          {[
            { icon: Zap, label: 'Redpanda + Quix CEP', sub: 'Sub-second anomaly detection' },
            { icon: Brain, label: 'LangGraph Agent', sub: 'Stateful 4-node reasoning' },
            { icon: Shield, label: 'Hybrid RAG', sub: 'pgvector + full-text SOPs' },
            { icon: Activity, label: 'Live WebSocket', sub: 'Zero-latency broadcast' },
          ].map(({ icon: Icon, label, sub }) => (
            <div
              key={label}
              className="p-4 rounded-xl bg-gray-900 border border-gray-800 text-left"
            >
              <Icon size={18} className="text-red-400 mb-2" />
              <div className="text-sm font-medium">{label}</div>
              <div className="text-xs text-gray-500 mt-1">{sub}</div>
            </div>
          ))}
        </div>
      </main>
    </div>
  )
}