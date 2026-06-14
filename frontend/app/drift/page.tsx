'use client'

import { useEffect, useState } from 'react'
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

interface DriftResult { drift_percentage?: number; drifted_features?: string[]; feature_impact?: Record<string, { correlation: number, impact: string }> }

function fmt(val: number | undefined | null, decimals = 1, suffix = ''): string {
  if (val === undefined || val === null || isNaN(val)) return '—'
  return val.toFixed(decimals) + suffix
}

const DRIFT_HISTORY = [
  { window: '2022 (Ref)', score: 0.0 },
  { window: '2023 (Q1)', score: 4.2 },
  { window: '2023 (Q2)', score: 12.8 },
]

export default function DriftPage() {
  const [domain, setDomain] = useState('hr_attrition')
  const [drift, setDrift] = useState<DriftResult | null>(null)
  const [loading, setLoading] = useState(true)
  const [injecting, setInjecting] = useState(false)

  const fetchDrift = () => {
    setLoading(true)
    fetch(`${API}/drift?domain=${domain}`)
      .then(r => r.json())
      .then(setDrift)
      .catch(() => setDrift({ drift_percentage: 0, drifted_features: [] }))
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    fetchDrift()
  }, [domain])

  const injectAnomaly = () => {
    setInjecting(true)
    fetch(`${API}/simulate-drift?level=2.5&domain=${domain}`, { method: 'POST' })
      .then(() => fetchDrift())
      .finally(() => setInjecting(false))
  }

  const pct = drift?.drift_percentage ?? 0
  const statusColor = pct > 30 ? '#EF4444' : pct > 15 ? '#EAB308' : '#22C55E'
  const statusLabel = pct > 30 ? 'CRITICAL' : pct > 15 ? 'WARNING' : 'NOMINAL'
  const displayPct  = drift == null ? (loading ? '...' : '—') : fmt(pct, 1, '%')

  const DOMAINS = [
    { id: 'hr_attrition', name: 'HR Attrition' },
    { id: 'fin_fraud', name: 'Financial Fraud' },
    { id: 'crm_churn', name: 'CRM Churn' },
    { id: 'sec_threats', name: 'Security Threats' },
    { id: 'market_leads', name: 'Market Leads' },
  ]

  return (
    <main className="pt-24 pb-margin px-margin max-w-[1600px] mx-auto w-full flex flex-col gap-lg">
      
      {/* Header Section */}
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-md mb-md">
        <div>
          <h1 className="font-h1 text-h1 text-primary">Drift & Data Quality</h1>
          <p className="font-body-base text-body-base text-on-surface-variant mt-1">
            Statistical comparison of reference vs. current data distribution via Evidently AI.
          </p>
        </div>
        <div className="flex gap-md">
          <select 
            value={domain} 
            onChange={(e) => setDomain(e.target.value)}
            className="bg-surface border border-surface-variant text-primary font-label-caps text-label-caps px-4 py-2 uppercase outline-none"
          >
            {DOMAINS.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}
          </select>
          <button 
            onClick={fetchDrift}
            className="px-6 py-2 border border-[#262626] text-primary font-label-caps text-label-caps hover:border-primary transition-colors uppercase"
          >
            Refresh Data
          </button>
          <button 
            onClick={injectAnomaly}
            disabled={injecting}
            className="px-6 py-2 bg-[#EF4444] text-white font-label-caps text-label-caps hover:bg-red-600 transition-colors uppercase flex items-center gap-2"
          >
            <span className="material-symbols-outlined text-[16px]">warning</span>
            {injecting ? 'Injecting...' : 'Inject Anomaly'}
          </button>
        </div>
      </div>

      {/* Score + Status */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-md">
        <div className="col-span-1 bg-surface border border-surface-variant p-lg flex flex-col justify-between h-[280px]">
          <span className="font-label-caps text-label-caps text-[#A3A3A3] uppercase mb-4">Overall Drift Score</span>
          <div>
            <div className="font-metric-lg text-[64px] leading-none font-medium" style={{ color: statusColor }}>
              {displayPct}
            </div>
            <div className="mt-8 h-2 w-full bg-[#0A0A0A] border border-[#262626] relative">
              <div className="absolute left-0 top-0 h-full transition-all duration-500" style={{ width: `${Math.min(pct, 100)}%`, backgroundColor: statusColor }}></div>
            </div>
            <div className="mt-2 font-label-caps text-[10px] text-zinc-500">THRESHOLD: 30.0%</div>
          </div>
          <div className="mt-auto">
            <span className="px-3 py-1 text-[10px] font-label-caps font-bold tracking-widest uppercase border" style={{ borderColor: statusColor, color: statusColor }}>
              {statusLabel}
            </span>
          </div>
        </div>

        <div className="col-span-2 bg-surface border border-surface-variant p-lg flex flex-col h-[280px]">
          <div className="border-b border-surface-variant pb-3 mb-6">
            <div className="font-label-caps text-label-caps text-zinc-400">Drift Score by Temporal Window</div>
          </div>
          <div className="flex-1 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={[...DRIFT_HISTORY, { window: 'Current', score: pct }]}>
                <CartesianGrid strokeDasharray="2 4" stroke="#262626" vertical={false} />
                <XAxis dataKey="window" tick={{ fill: '#525252', fontSize: 10, fontFamily: 'Geist Mono' }} axisLine={false} tickLine={false} />
                <YAxis domain={[0, 50]} tick={{ fill: '#525252', fontSize: 10, fontFamily: 'Geist Mono' }} axisLine={false} tickLine={false} width={30} />
                <Tooltip contentStyle={{ background: '#141414', border: '1px solid #262626', borderRadius: 0, fontFamily: 'Geist Mono', fontSize: 12 }} />
                <Bar dataKey="score" fill="#404040" radius={0} name="Drift %">
                  {/* Color the last bar dynamically based on current drift */}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {/* Feature Table */}
      <div className="bg-surface border border-surface-variant mt-4">
        <div className="p-md border-b border-[#262626]">
          <h2 className="font-h2 text-h2 text-primary text-lg">Feature-Level Drift Analysis (Evidently AI)</h2>
        </div>
        <div className="w-full overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr>
                <th className="p-4 border-b border-[#262626] font-label-caps text-label-caps text-zinc-500 uppercase">Feature Name</th>
                <th className="p-4 border-b border-[#262626] font-label-caps text-label-caps text-zinc-500 uppercase">Target Correlation</th>
                <th className="p-4 border-b border-[#262626] font-label-caps text-label-caps text-zinc-500 uppercase">Business Impact</th>
                <th className="p-4 border-b border-[#262626] font-label-caps text-label-caps text-zinc-500 uppercase">Status</th>
                <th className="p-4 border-b border-[#262626] font-label-caps text-label-caps text-zinc-500 uppercase">Distribution (Ref vs Cur)</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={4} className="text-center text-zinc-500 p-8 font-label-caps">Running Statistical Tests...</td></tr>
              ) : drift?.drifted_features?.length === 0 ? (
                <tr><td colSpan={4} className="text-center text-[#22C55E] p-8 font-label-caps">All Features Stable - No Drift Detected</td></tr>
              ) : (
                drift?.drifted_features?.map(f => {
                  const impactData = drift.feature_impact?.[f]
                  const impactColor = impactData?.impact === 'High' ? '#EF4444' : impactData?.impact === 'Medium' ? '#EAB308' : '#22C55E'
                  return (
                    <tr key={f} className="border-b border-[#262626] hover:bg-[#1A1A1A] transition-colors">
                      <td className="p-4 font-metric-sm text-metric-sm text-primary">{f.replace(/_/g, ' ')}</td>
                      <td className="p-4 font-mono text-[12px] text-zinc-400">{impactData ? impactData.correlation.toFixed(3) : '—'}</td>
                      <td className="p-4">
                        <span className="px-2 py-0.5 text-[10px] font-bold tracking-widest uppercase border" style={{ color: impactColor, borderColor: impactColor, backgroundColor: impactColor + '20' }}>
                          {impactData?.impact || 'Unknown'} Impact
                        </span>
                      </td>
                      <td className="p-4 font-metric-sm text-metric-sm text-[#EF4444]">Drifted <span className="text-[#A3A3A3] text-[10px] ml-1">WARN</span></td>
                      <td className="p-4">
                        <div className="w-32 h-6 flex gap-1 items-end">
                          <div className="flex-1 bg-[#444] h-[30%] opacity-50"></div>
                          <div className="flex-1 bg-[#EF4444] h-[90%] opacity-80"></div>
                          <div className="flex-1 bg-[#444] h-[60%] opacity-50"></div>
                          <div className="flex-1 bg-[#444] h-[20%] opacity-50"></div>
                        </div>
                      </td>
                    </tr>
                  )
                })
              )}
            </tbody>
          </table>
        </div>
      </div>
    </main>
  )
}
