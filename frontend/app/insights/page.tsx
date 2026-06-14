'use client'

import { useState } from 'react'

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

const DOMAINS = [
  { id: 'hr_attrition', name: 'HR Attrition', features: ['age', 'monthly_income', 'workload', 'distance_from_home', 'performance_rating'] },
  { id: 'fin_fraud', name: 'Financial Fraud', features: ['amount', 'ip_distance'] },
  { id: 'crm_churn', name: 'CRM Churn', features: ['tenure', 'monthly_charges', 'total_charges', 'support_tickets'] },
  { id: 'sec_threats', name: 'Security Threats', features: ['session_duration', 'login_attempts', 'failed_logins', 'ip_reputation_score', 'bandwidth_spikes'] },
  { id: 'market_leads', name: 'Market Leads', features: ['session_duration', 'pages_visited', 'cart_value', 'engagement_score'] },
]

const ACTION_COLORS: Record<string, string> = {
  RETRAIN: '#EF4444', MONITOR: '#EAB308', FLAG_ANOMALY: '#F97316', NO_ACTION: '#22C55E'
}
const RISK_COLORS: Record<string, string> = { HIGH: '#EF4444', MEDIUM: '#EAB308', LOW: '#22C55E' }

interface ScenarioResult {
  feature_shifted: string; shift_pct: number;
  baseline: { drift_percentage: number; action: string; risk_level: string; expected_daily_loss_usd: number; drifted_features: string[] }
  scenario: { drift_percentage: number; action: string; risk_level: string; expected_daily_loss_usd: number; drifted_features: string[] }
  delta_loss_usd: number; decision_changed: boolean; available_features: string[];
}

export default function ScenarioPage() {
  const [domain, setDomain] = useState('hr_attrition')
  const [feature, setFeature] = useState('monthly_income')
  const [shift, setShift] = useState(-20)
  const [result, setResult] = useState<ScenarioResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const currentDomain = DOMAINS.find(d => d.id === domain) || DOMAINS[0]

  const runSim = async () => {
    setLoading(true); setError(''); setResult(null)
    try {
      const r = await fetch(`${API}/scenario?domain=${domain}&feature=${feature}&shift_pct=${shift}`)
      const data = await r.json()
      if (data.error) { setError(data.error) } else { setResult(data) }
    } catch (e: any) { setError(e.message) }
    setLoading(false)
  }

  return (
    <main className="pt-24 pb-margin px-margin max-w-[1400px] mx-auto w-full flex flex-col gap-lg">
      {/* Header */}
      <div>
        <h1 className="font-h1 text-h1 text-primary flex items-center gap-3">
          <span className="material-symbols-outlined text-[32px] text-[#EAB308]">science</span>
          Scenario Simulator
        </h1>
        <p className="text-on-surface-variant mt-1">
          Simulate real-world distribution shifts and observe how the Multi-Signal Decision Engine reacts — without touching production data.
        </p>
      </div>

      {/* Controls */}
      <div className="bg-surface border border-surface-variant p-lg">
        <div className="flex items-center gap-3 mb-6 pb-4 border-b border-[#262626]">
          <span className="material-symbols-outlined text-zinc-400 text-[18px]">tune</span>
          <h2 className="font-semibold text-primary">Simulation Controls</h2>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-lg">
          {/* Domain */}
          <div className="flex flex-col gap-2">
            <label className="font-label-caps text-[10px] text-zinc-500 uppercase tracking-widest">Domain Model</label>
            <select
              value={domain}
              onChange={e => { setDomain(e.target.value); setFeature(DOMAINS.find(d => d.id === e.target.value)?.features[0] || '') }}
              className="bg-[#0A0A0A] border border-[#262626] text-primary font-label-caps text-label-caps px-4 py-3 uppercase outline-none hover:border-zinc-500 transition-colors"
            >
              {DOMAINS.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}
            </select>
          </div>

          {/* Feature */}
          <div className="flex flex-col gap-2">
            <label className="font-label-caps text-[10px] text-zinc-500 uppercase tracking-widest">Feature to Shift</label>
            <select
              value={feature}
              onChange={e => setFeature(e.target.value)}
              className="bg-[#0A0A0A] border border-[#262626] text-primary font-label-caps text-label-caps px-4 py-3 uppercase outline-none hover:border-zinc-500 transition-colors"
            >
              {currentDomain.features.map(f => <option key={f} value={f}>{f.replace(/_/g, ' ').toUpperCase()}</option>)}
            </select>
          </div>

          {/* Shift Amount */}
          <div className="flex flex-col gap-2">
            <label className="font-label-caps text-[10px] text-zinc-500 uppercase tracking-widest">
              Distribution Shift: <span className={shift < 0 ? 'text-[#EF4444]' : 'text-[#22C55E]'}>{shift > 0 ? '+' : ''}{shift}%</span>
            </label>
            <input
              type="range" min={-80} max={80} step={5} value={shift}
              onChange={e => setShift(Number(e.target.value))}
              className="w-full accent-white mt-1"
            />
            <div className="flex justify-between font-mono text-[10px] text-zinc-600">
              <span>-80% (Collapse)</span><span>0</span><span>+80% (Surge)</span>
            </div>
          </div>
        </div>

        <button
          onClick={runSim}
          disabled={loading}
          className="mt-6 px-8 py-3 bg-primary text-[#0A0A0A] font-label-caps text-label-caps hover:bg-zinc-200 transition-colors uppercase flex items-center gap-2 disabled:opacity-50"
        >
          {loading
            ? <><span className="material-symbols-outlined text-[16px] animate-spin">sync</span> Simulating...</>
            : <><span className="material-symbols-outlined text-[16px]">play_arrow</span> Run Simulation</>
          }
        </button>
      </div>

      {/* Error */}
      {error && <div className="bg-[#1A0A0A] border border-[#EF4444]/40 p-4 text-[#EF4444] font-mono text-sm">{error}</div>}

      {/* Results */}
      {result && (
        <div className="flex flex-col gap-md">
          {/* Decision Changed Banner */}
          {result.decision_changed && (
            <div className="bg-[#1A0A00] border border-[#EAB308]/40 p-4 flex items-center gap-3">
              <span className="material-symbols-outlined text-[#EAB308]">warning</span>
              <span className="font-label-caps text-[#EAB308]">
                DECISION CHANGED: {result.baseline.action} → {result.scenario.action} · Shifting <strong>{result.feature_shifted.replace(/_/g, ' ').toUpperCase()}</strong> by {result.shift_pct > 0 ? '+' : ''}{result.shift_pct}% triggered a system response change.
              </span>
            </div>
          )}

          {/* Before / After Comparison */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-[1px] bg-[#262626]">
            {/* Baseline */}
            <div className="bg-surface p-lg">
              <div className="flex items-center gap-3 mb-4 pb-3 border-b border-[#262626]">
                <div className="w-2 h-2 bg-[#22C55E]"></div>
                <span className="font-label-caps text-[10px] text-zinc-400 uppercase tracking-widest">Baseline (Current State)</span>
              </div>
              <div className="space-y-4">
                <div>
                  <div className="font-label-caps text-[10px] text-zinc-500 mb-1">ENGINE DECISION</div>
                  <div className="text-2xl font-bold" style={{ color: ACTION_COLORS[result.baseline.action] }}>{result.baseline.action.replace('_', ' ')}</div>
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <div className="font-label-caps text-[10px] text-zinc-500 mb-1">RISK LEVEL</div>
                    <div className="font-mono text-sm" style={{ color: RISK_COLORS[result.baseline.risk_level] }}>{result.baseline.risk_level}</div>
                  </div>
                  <div>
                    <div className="font-label-caps text-[10px] text-zinc-500 mb-1">DRIFT SCORE</div>
                    <div className="font-mono text-sm text-zinc-200">{result.baseline.drift_percentage.toFixed(1)}%</div>
                  </div>
                  <div>
                    <div className="font-label-caps text-[10px] text-zinc-500 mb-1">DAILY LOSS</div>
                    <div className="font-mono text-sm text-zinc-200">${result.baseline.expected_daily_loss_usd.toLocaleString('en-US', { maximumFractionDigits: 0 })}</div>
                  </div>
                  <div>
                    <div className="font-label-caps text-[10px] text-zinc-500 mb-1">DRIFTED FEATURES</div>
                    <div className="font-mono text-sm text-zinc-200">{result.baseline.drifted_features.length}</div>
                  </div>
                </div>
              </div>
            </div>

            {/* Scenario */}
            <div className="bg-[#0F0F00] p-lg border border-[#EAB308]/20">
              <div className="flex items-center gap-3 mb-4 pb-3 border-b border-[#262626]">
                <div className="w-2 h-2 bg-[#EAB308]"></div>
                <span className="font-label-caps text-[10px] text-zinc-400 uppercase tracking-widest">Scenario ({result.shift_pct > 0 ? '+' : ''}{result.shift_pct}% on {result.feature_shifted.replace(/_/g, ' ')})</span>
              </div>
              <div className="space-y-4">
                <div>
                  <div className="font-label-caps text-[10px] text-zinc-500 mb-1">ENGINE DECISION</div>
                  <div className="text-2xl font-bold" style={{ color: ACTION_COLORS[result.scenario.action] }}>{result.scenario.action.replace('_', ' ')}</div>
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <div className="font-label-caps text-[10px] text-zinc-500 mb-1">RISK LEVEL</div>
                    <div className="font-mono text-sm" style={{ color: RISK_COLORS[result.scenario.risk_level] }}>{result.scenario.risk_level}</div>
                  </div>
                  <div>
                    <div className="font-label-caps text-[10px] text-zinc-500 mb-1">DRIFT SCORE</div>
                    <div className="font-mono text-sm" style={{ color: result.scenario.drift_percentage > result.baseline.drift_percentage ? '#EF4444' : '#22C55E' }}>
                      {result.scenario.drift_percentage.toFixed(1)}%
                    </div>
                  </div>
                  <div>
                    <div className="font-label-caps text-[10px] text-zinc-500 mb-1">DAILY LOSS</div>
                    <div className="font-mono text-sm" style={{ color: result.delta_loss_usd > 0 ? '#EF4444' : '#22C55E' }}>
                      ${result.scenario.expected_daily_loss_usd.toLocaleString('en-US', { maximumFractionDigits: 0 })}
                      {result.delta_loss_usd !== 0 && (
                        <span className="text-[10px] ml-2">({result.delta_loss_usd > 0 ? '+' : ''}${result.delta_loss_usd.toLocaleString('en-US', { maximumFractionDigits: 0 })})</span>
                      )}
                    </div>
                  </div>
                  <div>
                    <div className="font-label-caps text-[10px] text-zinc-500 mb-1">DRIFTED FEATURES</div>
                    <div className="font-mono text-sm" style={{ color: result.scenario.drifted_features.length > result.baseline.drifted_features.length ? '#EF4444' : '#22C55E' }}>
                      {result.scenario.drifted_features.length}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Drifted Features Delta */}
          {result.scenario.drifted_features.length > 0 && (
            <div className="bg-surface border border-surface-variant p-lg">
              <div className="font-label-caps text-[10px] text-zinc-500 mb-3 uppercase tracking-widest">Features Now Drifted in Scenario</div>
              <div className="flex flex-wrap gap-2">
                {result.scenario.drifted_features.map(f => (
                  <span key={f} className="px-3 py-1 text-[11px] font-mono" style={{
                    background: result.baseline.drifted_features.includes(f) ? '#1A1A1A' : '#1A0A00',
                    border: `1px solid ${result.baseline.drifted_features.includes(f) ? '#262626' : '#EAB30840'}`,
                    color: result.baseline.drifted_features.includes(f) ? '#A3A3A3' : '#EAB308'
                  }}>
                    {result.baseline.drifted_features.includes(f) ? '' : '⚠ NEW: '}{f.replace(/_/g, ' ')}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </main>
  )
}
