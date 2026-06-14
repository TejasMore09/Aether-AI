'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

const DOMAINS = [
  { id: 'hr_attrition', name: 'HR Attrition Engine', type: 'XGBoost', domain: 'Workforce' },
  { id: 'fin_fraud', name: 'Fraud Detection V4', type: 'XGBoost', domain: 'Financial' },
  { id: 'crm_churn', name: 'CRM Retention Model', type: 'XGBoost', domain: 'Customer' },
  { id: 'sec_threats', name: 'Threat Intel Core', type: 'XGBoost', domain: 'Security' },
  { id: 'market_leads', name: 'Lead Conversion', type: 'XGBoost', domain: 'Marketing' },
  { id: 'supply_chain', name: 'Demand Forecast', type: 'SARIMAX', domain: 'Operations' },
]

interface Reliability {
  reliability_score: number; grade: string; perf_score: number; drift_penalty_pct: number;
}
interface Metrics {
  f1_score?: number; roc_auc?: number; mape?: number; rmse?: number; drift_percentage?: number;
}

const GRADE_COLOR: Record<string, string> = { A: '#22C55E', B: '#4ade80', C: '#EAB308', D: '#EF4444' }

export default function RegistryPage() {
  const [reliability, setReliability] = useState<Record<string, Reliability>>({})
  const [metrics, setMetrics] = useState<Record<string, Metrics>>({})
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all(
      DOMAINS.flatMap(d => [
        fetch(`${API}/reliability?domain=${d.id}`).then(r => r.json()).then(data => ({ type: 'rel', id: d.id, data })).catch(() => null),
        fetch(`${API}/metrics?domain=${d.id}`).then(r => r.json()).then(data => ({ type: 'met', id: d.id, data })).catch(() => null),
      ])
    ).then(results => {
      const rel: Record<string, Reliability> = {}
      const met: Record<string, Metrics> = {}
      results.filter(Boolean).forEach((r: any) => {
        if (r.type === 'rel') rel[r.id] = r.data
        else met[r.id] = r.data
      })
      setReliability(rel)
      setMetrics(met)
    }).finally(() => setLoading(false))
  }, [])

  return (
    <main className="pt-24 pb-margin px-margin max-w-[1600px] mx-auto w-full flex flex-col gap-lg">
      <div className="flex justify-between items-start mb-2">
        <div>
          <h1 className="font-h1 text-h1 text-primary flex items-center gap-3">
            <span className="material-symbols-outlined text-[32px] text-zinc-400">inventory_2</span>
            Model Registry
          </h1>
          <p className="text-on-surface-variant mt-1">Live model fleet with Reliability Scores, performance metrics, and drift status.</p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-md">
        {DOMAINS.map(d => {
          const rel = reliability[d.id]
          const met = metrics[d.id]
          const score = rel?.reliability_score ?? null
          const grade = rel?.grade ?? '—'
          const gradeColor = GRADE_COLOR[grade] || '#525252'
          const isTs = d.id === 'supply_chain'

          return (
            <Link key={d.id} href={`/model/${d.id}`} className="bg-surface border border-surface-variant relative flex flex-col hover:border-zinc-600 transition-all group">
              {/* Top accent bar colored by grade */}
              <div className="absolute top-0 left-0 right-0 h-[2px]" style={{ backgroundColor: gradeColor, opacity: loading ? 0.2 : 1 }}></div>

              <div className="p-lg flex flex-col gap-md flex-1 pt-8">
                {/* Header */}
                <div className="flex justify-between items-start">
                  <div>
                    <div className="font-label-caps text-label-caps text-zinc-500 uppercase mb-1">{d.domain} · {d.type}</div>
                    <h2 className="font-semibold text-primary text-base leading-tight">{d.name}</h2>
                  </div>
                  {/* Reliability Grade */}
                  <div className="flex flex-col items-center">
                    <div className="text-3xl font-black leading-none" style={{ color: gradeColor }}>
                      {loading ? '…' : grade}
                    </div>
                    <div className="font-label-caps text-[9px] text-zinc-500 mt-1">GRADE</div>
                  </div>
                </div>

                {/* Reliability Score Bar */}
                <div>
                  <div className="flex justify-between mb-2">
                    <span className="font-label-caps text-[10px] text-zinc-500">RELIABILITY</span>
                    <span className="font-mono text-[12px]" style={{ color: gradeColor }}>{loading ? '—' : `${score}%`}</span>
                  </div>
                  <div className="h-1.5 w-full bg-[#262626]">
                    <div className="h-full transition-all duration-700" style={{ width: loading ? '0%' : `${score || 0}%`, backgroundColor: gradeColor }}></div>
                  </div>
                </div>

                {/* Metrics Grid */}
                <div className="grid grid-cols-2 gap-3 pt-2 border-t border-[#262626]">
                  {isTs ? (
                    <>
                      <div>
                        <div className="font-label-caps text-[10px] text-zinc-500 mb-1">MAPE</div>
                        <div className="font-mono text-sm text-zinc-200">{loading ? '—' : `${met?.mape?.toFixed(2) ?? '—'}%`}</div>
                      </div>
                      <div>
                        <div className="font-label-caps text-[10px] text-zinc-500 mb-1">RMSE</div>
                        <div className="font-mono text-sm text-zinc-200">{loading ? '—' : `${met?.rmse?.toFixed(1) ?? '—'}`}</div>
                      </div>
                    </>
                  ) : (
                    <>
                      <div>
                        <div className="font-label-caps text-[10px] text-zinc-500 mb-1">F1 SCORE</div>
                        <div className="font-mono text-sm text-zinc-200">{loading ? '—' : `${met?.f1_score?.toFixed(4) ?? '—'}`}</div>
                      </div>
                      <div>
                        <div className="font-label-caps text-[10px] text-zinc-500 mb-1">ROC-AUC</div>
                        <div className="font-mono text-sm text-zinc-200">{loading ? '—' : `${met?.roc_auc?.toFixed(4) ?? '—'}`}</div>
                      </div>
                    </>
                  )}
                  <div>
                    <div className="font-label-caps text-[10px] text-zinc-500 mb-1">DRIFT</div>
                    <div className="font-mono text-sm" style={{ color: (met?.drift_percentage || 0) > 15 ? '#EF4444' : '#22C55E' }}>
                      {loading ? '—' : `${met?.drift_percentage?.toFixed(1) ?? '0.0'}%`}
                    </div>
                  </div>
                  <div>
                    <div className="font-label-caps text-[10px] text-zinc-500 mb-1">PERF SCORE</div>
                    <div className="font-mono text-sm text-zinc-200">{loading ? '—' : `${rel?.perf_score ?? '—'}%`}</div>
                  </div>
                </div>

                {/* View Detail Link */}
                <div className="mt-auto pt-3 border-t border-[#262626] flex items-center gap-2 text-zinc-500 group-hover:text-white transition-colors">
                  <span className="material-symbols-outlined text-[14px]">open_in_full</span>
                  <span className="font-label-caps text-[10px] uppercase">View Full Telemetry</span>
                </div>
              </div>
            </Link>
          )
        })}
      </div>
    </main>
  )
}
