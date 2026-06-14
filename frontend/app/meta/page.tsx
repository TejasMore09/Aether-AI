'use client'

import { useEffect, useState } from 'react'

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

interface FeedbackItem {
  audit_id: number; domain: string; timestamp: string;
  f1_before: number; f1_after: number; f1_improvement: number;
  was_worth_it: boolean; expected_loss_prevented: number;
}

interface MetaLearningData {
  status: string; message?: string; total_evaluated: number;
  hit_rate_pct: number; wasted_compute_usd: number; engine_grade: string;
  cross_model_patterns: string; feedback_history: FeedbackItem[];
}

const GRADE_COLORS: Record<string, string> = { A: '#22C55E', B: '#EAB308', C: '#EF4444' }

export default function MetaLearningPage() {
  const [data, setData] = useState<MetaLearningData | null>(null)
  const [loading, setLoading] = useState(true)

  const fetchData = async () => {
    setLoading(true)
    try {
      const res = await fetch(`${API}/meta-learning`)
      const json = await res.json()
      setData(json)
    } catch (e) {
      console.error(e)
    }
    setLoading(false)
  }

  useEffect(() => { fetchData() }, [])

  return (
    <main className="pt-24 pb-margin px-margin max-w-[1600px] mx-auto w-full flex flex-col gap-lg">
      <div className="flex justify-between items-start">
        <div>
          <h1 className="font-h1 text-h1 text-primary flex items-center gap-3">
            <span className="material-symbols-outlined text-[32px] text-[#A855F7]">psychology_alt</span>
            Meta-Learning & Intelligence
          </h1>
          <p className="text-on-surface-variant mt-1">
            Sections 10.1, 10.3, 10.4: The system grades its own past decisions to learn if retraining was financially worth it.
          </p>
        </div>
        <button onClick={fetchData} className="px-5 py-2 border border-surface-variant text-primary font-label-caps text-label-caps hover:border-primary transition-colors uppercase flex items-center gap-2">
          <span className="material-symbols-outlined text-[16px]">refresh</span> Refresh
        </button>
      </div>

      {loading ? (
        <div className="p-12 text-center text-zinc-500 font-label-caps tracking-widest animate-pulse">Running Meta-Learning analysis...</div>
      ) : data?.status === 'insufficient_data' ? (
        <div className="bg-[#1A1A1A] border border-[#262626] p-lg text-center text-zinc-400">
          <span className="material-symbols-outlined text-4xl mb-4 text-zinc-500">hourglass_empty</span>
          <p>{data.message}</p>
          <p className="text-sm mt-2">Run the Decision Engine in the Pipelines page, then trigger some RETRAIN actions.</p>
        </div>
      ) : data && (
        <div className="flex flex-col gap-lg">
          {/* Top KPI Row */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-[1px] bg-[#262626]">
            <div className="bg-surface p-lg flex flex-col items-center justify-center text-center">
              <span className="font-label-caps text-[10px] text-zinc-500 uppercase tracking-widest mb-2">Engine Meta-Grade</span>
              <div className="text-6xl font-black" style={{ color: GRADE_COLORS[data.engine_grade] || '#A3A3A3' }}>{data.engine_grade}</div>
            </div>
            
            <div className="bg-surface p-lg flex flex-col justify-center">
              <span className="font-label-caps text-[10px] text-zinc-500 uppercase tracking-widest mb-1">Decision Hit Rate</span>
              <div className="font-mono text-3xl" style={{ color: data.hit_rate_pct > 75 ? '#22C55E' : '#EAB308' }}>
                {data.hit_rate_pct}%
              </div>
              <p className="text-xs text-zinc-400 mt-2">of Retrain decisions resulted in positive financial ROI.</p>
            </div>

            <div className="bg-surface p-lg flex flex-col justify-center">
              <span className="font-label-caps text-[10px] text-zinc-500 uppercase tracking-widest mb-1">Wasted Compute Cost</span>
              <div className="font-mono text-3xl" style={{ color: data.wasted_compute_usd > 500 ? '#EF4444' : '#22C55E' }}>
                ${data.wasted_compute_usd.toLocaleString('en-US')}
              </div>
              <p className="text-xs text-zinc-400 mt-2">spent on retraining models that did not meaningfully improve.</p>
            </div>

            <div className="bg-surface p-lg flex flex-col justify-center">
              <span className="font-label-caps text-[10px] text-zinc-500 uppercase tracking-widest mb-1">Total Decisions Evaluated</span>
              <div className="font-mono text-3xl text-zinc-200">{data.total_evaluated}</div>
            </div>
          </div>

          {/* Cross-Model Intelligence */}
          <div className="bg-[#1A0A1A] border border-[#A855F7]/30 p-lg flex items-start gap-4">
            <span className="material-symbols-outlined text-[#A855F7] text-3xl">hub</span>
            <div>
              <h2 className="text-lg font-semibold text-primary mb-1">Cross-Model Intelligence (Section 10.3)</h2>
              <p className="text-[#A855F7] font-mono text-sm">{data.cross_model_patterns}</p>
            </div>
          </div>

          {/* Feedback Loop Log */}
          <div className="bg-surface border border-surface-variant">
            <div className="p-md border-b border-[#262626] flex items-center gap-3">
              <span className="material-symbols-outlined text-zinc-400 text-[18px]">history</span>
              <h2 className="font-semibold text-primary text-lg">Feedback Learning Loop (Section 10.1)</h2>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr>
                    {['Date', 'Domain', 'F1 Before', 'F1 After', 'Improvement', 'Loss Prevented', 'ROI Positive?'].map(h => (
                      <th key={h} className="p-3 border-b border-[#262626] font-label-caps text-label-caps text-zinc-500 text-[10px] uppercase">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {data.feedback_history.map(item => (
                    <tr key={item.audit_id} className="border-b border-[#262626] hover:bg-[#1A1A1A]">
                      <td className="p-3 font-mono text-[11px] text-zinc-400">{new Date(item.timestamp).toLocaleString()}</td>
                      <td className="p-3 font-label-caps text-[11px] text-zinc-300 uppercase">{item.domain}</td>
                      <td className="p-3 font-mono text-[11px] text-zinc-400">{item.f1_before.toFixed(4)}</td>
                      <td className="p-3 font-mono text-[11px] text-zinc-200">{item.f1_after.toFixed(4)}</td>
                      <td className="p-3 font-mono text-[11px]" style={{ color: item.f1_improvement > 0 ? '#22C55E' : '#EF4444' }}>
                        {item.f1_improvement > 0 ? '+' : ''}{item.f1_improvement.toFixed(4)}
                      </td>
                      <td className="p-3 font-mono text-[11px] text-[#22C55E]">${item.expected_loss_prevented.toLocaleString('en-US', { maximumFractionDigits: 0 })}</td>
                      <td className="p-3">
                        <span className="px-2 py-0.5 text-[10px] font-bold uppercase" style={{
                          background: item.was_worth_it ? '#22C55E20' : '#EF444420',
                          color: item.was_worth_it ? '#22C55E' : '#EF4444',
                          border: `1px solid ${item.was_worth_it ? '#22C55E' : '#EF4444'}`
                        }}>
                          {item.was_worth_it ? 'YES' : 'NO'}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

        </div>
      )}
    </main>
  )
}
