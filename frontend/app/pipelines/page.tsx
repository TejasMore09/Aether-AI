'use client'

import { useEffect, useState } from 'react'

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

const DOMAINS = ['hr_attrition', 'fin_fraud', 'crm_churn', 'sec_threats', 'market_leads', 'supply_chain']
const DOMAIN_LABELS: Record<string, string> = {
  hr_attrition: 'HR Attrition', fin_fraud: 'Fraud Detection',
  crm_churn: 'CRM Churn', sec_threats: 'Security Threats',
  market_leads: 'Market Leads', supply_chain: 'Supply Chain'
}

interface AuditEntry {
  id: number; timestamp: string; domain: string; action: string;
  triggered_by: string; risk_level: string; drift_pct: number;
  f1_before: number; expected_loss_usd: number; status: string;
}
interface Approval {
  id: number; timestamp: string; domain: string; action: string;
  reason: string; risk_level: string; expected_loss_usd: number; status: string;
}
interface Decision {
  action: string; risk_level: string; risk_score_raw: number;
  expected_daily_loss_usd: number; retraining_cost_usd: number;
  reason: string; approval_required?: boolean; approval_id?: number;
}

const ACTION_COLORS: Record<string, string> = {
  RETRAIN: '#EF4444', MONITOR: '#EAB308', FLAG_ANOMALY: '#F97316', NO_ACTION: '#22C55E'
}
const RISK_COLORS: Record<string, string> = { HIGH: '#EF4444', MEDIUM: '#EAB308', LOW: '#22C55E' }

export default function PipelinesPage() {
  const [logs, setLogs] = useState<AuditEntry[]>([])
  const [approvals, setApprovals] = useState<Approval[]>([])
  const [decisions, setDecisions] = useState<Record<string, Decision>>({})
  const [loading, setLoading] = useState(true)
  const [running, setRunning] = useState<string | null>(null)

  const fetchAll = async () => {
    setLoading(true)
    const [logsData, approvalsData] = await Promise.all([
      fetch(`${API}/audit-logs?limit=30`).then(r => r.json()).catch(() => []),
      fetch(`${API}/approvals`).then(r => r.json()).catch(() => [])
    ])
    setLogs(logsData)
    setApprovals(approvalsData)
    setLoading(false)
  }

  useEffect(() => { fetchAll() }, [])

  const runDecision = async (domain: string) => {
    setRunning(domain)
    const d = await fetch(`${API}/decision?domain=${domain}`).then(r => r.json()).catch(() => null)
    if (d) setDecisions(prev => ({ ...prev, [domain]: d }))
    await fetchAll()
    setRunning(null)
  }

  const resolveApproval = async (id: number, decision: string) => {
    await fetch(`${API}/approvals/${id}/resolve?decision=${decision}`, { method: 'POST' })
    await fetchAll()
  }

  return (
    <main className="pt-24 pb-margin px-margin max-w-[1600px] mx-auto w-full flex flex-col gap-lg">
      {/* Header */}
      <div className="flex justify-between items-start mb-2">
        <div>
          <h1 className="font-h1 text-h1 text-primary flex items-center gap-3">
            <span className="material-symbols-outlined text-[32px] text-zinc-400">account_tree</span>
            Adaptive Pipelines
          </h1>
          <p className="text-on-surface-variant mt-1">Run the Multi-Signal Decision Engine across all domains. Review audit trail and pending governance approvals.</p>
        </div>
        <button onClick={fetchAll} className="px-5 py-2 border border-surface-variant text-primary font-label-caps text-label-caps hover:border-primary transition-colors uppercase flex items-center gap-2">
          <span className="material-symbols-outlined text-[16px]">refresh</span> Refresh
        </button>
      </div>

      {/* Pending Approvals - Governance */}
      {approvals.length > 0 && (
        <div className="bg-[#1A0A0A] border border-[#EF4444]/40 p-lg">
          <div className="flex items-center gap-3 mb-4 pb-4 border-b border-[#262626]">
            <span className="material-symbols-outlined text-[#EF4444]">gavel</span>
            <h2 className="text-lg font-semibold text-primary">Pending Governance Approvals ({approvals.length})</h2>
          </div>
          <div className="flex flex-col gap-3">
            {approvals.map(a => (
              <div key={a.id} className="bg-surface border border-surface-variant p-4 flex flex-col md:flex-row justify-between gap-4">
                <div>
                  <div className="flex items-center gap-3 mb-2">
                    <span className="px-2 py-0.5 text-[10px] font-bold tracking-widest uppercase" style={{ background: '#EF444422', color: '#EF4444', border: '1px solid #EF4444' }}>{a.action}</span>
                    <span className="font-label-caps text-zinc-400">{DOMAIN_LABELS[a.domain] || a.domain}</span>
                  </div>
                  <p className="text-sm text-zinc-300 mb-1">{a.reason}</p>
                  <p className="text-xs text-zinc-500">Expected Loss: <span className="text-[#EF4444] font-semibold">${a.expected_loss_usd?.toLocaleString('en-US', { maximumFractionDigits: 0 })}/day</span></p>
                </div>
                <div className="flex gap-3 items-start">
                  <button onClick={() => resolveApproval(a.id, 'approved')} className="px-5 py-2 bg-[#22C55E] text-[#0A0A0A] font-label-caps text-label-caps hover:opacity-90 transition-opacity uppercase">Approve</button>
                  <button onClick={() => resolveApproval(a.id, 'rejected')} className="px-5 py-2 border border-[#EF4444] text-[#EF4444] font-label-caps text-label-caps hover:bg-[#EF444415] transition-colors uppercase">Reject</button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Decision Engine Runner */}
      <div className="bg-surface border border-surface-variant">
        <div className="p-md border-b border-[#262626] flex items-center gap-3">
          <span className="material-symbols-outlined text-zinc-400 text-[18px]">play_circle</span>
          <h2 className="font-h2 text-h2 text-primary text-lg">Decision Engine — Per Domain</h2>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-[1px] bg-[#262626]">
          {DOMAINS.map(domain => {
            const d = decisions[domain]
            const isRunning = running === domain
            return (
              <div key={domain} className="bg-surface p-lg flex flex-col gap-4">
                <div className="flex justify-between items-center">
                  <span className="font-label-caps text-label-caps text-zinc-400 uppercase">{DOMAIN_LABELS[domain]}</span>
                  {d && <span className="w-2 h-2 rounded-full" style={{ backgroundColor: ACTION_COLORS[d.action] || '#525252' }}></span>}
                </div>

                {d ? (
                  <div className="flex flex-col gap-2">
                    <div className="flex items-baseline gap-2">
                      <span className="font-metric-lg text-metric-lg text-primary" style={{ color: ACTION_COLORS[d.action] }}>{d.action.replace('_', ' ')}</span>
                    </div>
                    <div className="text-xs text-zinc-400 space-y-1">
                      <div>Risk: <span style={{ color: RISK_COLORS[d.risk_level] }}>{d.risk_level}</span></div>
                      <div>Daily Loss: <span className="text-zinc-200">${d.expected_daily_loss_usd?.toLocaleString('en-US', { maximumFractionDigits: 0 })}</span></div>
                      <div>Approval Required: <span className={d.approval_required ? 'text-[#EF4444]' : 'text-[#22C55E]'}>{d.approval_required ? 'YES' : 'No'}</span></div>
                    </div>
                    <p className="text-[11px] text-zinc-500 leading-relaxed">{d.reason}</p>
                  </div>
                ) : (
                  <div className="text-zinc-600 text-sm">Not evaluated yet</div>
                )}

                <button
                  onClick={() => runDecision(domain)}
                  disabled={isRunning}
                  className="mt-auto py-2 border border-surface-variant text-primary font-label-caps text-label-caps hover:border-primary transition-colors uppercase flex items-center justify-center gap-2 disabled:opacity-50"
                >
                  {isRunning ? <span className="material-symbols-outlined text-[16px] animate-spin">sync</span> : <span className="material-symbols-outlined text-[16px]">play_arrow</span>}
                  {isRunning ? 'Evaluating...' : 'Run Engine'}
                </button>
              </div>
            )
          })}
        </div>
      </div>

      {/* Audit Log Table */}
      <div className="bg-surface border border-surface-variant">
        <div className="p-md border-b border-[#262626] flex items-center gap-3">
          <span className="material-symbols-outlined text-zinc-400 text-[18px]">receipt_long</span>
          <h2 className="font-h2 text-h2 text-primary text-lg">Immutable Audit Log</h2>
          <span className="ml-auto font-label-caps text-label-caps text-zinc-500">{logs.length} entries</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr>
                {['Timestamp', 'Domain', 'Action', 'Triggered By', 'Risk', 'Drift %', 'Expected Loss', 'Status'].map(h => (
                  <th key={h} className="p-3 border-b border-[#262626] font-label-caps text-label-caps text-zinc-500 text-[10px] uppercase">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={8} className="p-8 text-center text-zinc-500 font-label-caps">Loading audit trail...</td></tr>
              ) : logs.length === 0 ? (
                <tr><td colSpan={8} className="p-8 text-center text-zinc-500 font-label-caps">No audit entries yet. Run a Decision Engine cycle above.</td></tr>
              ) : logs.map(l => (
                <tr key={l.id} className="border-b border-[#262626] hover:bg-[#1A1A1A] transition-colors">
                  <td className="p-3 font-mono text-[11px] text-zinc-400">{l.timestamp ? new Date(l.timestamp).toLocaleString() : '—'}</td>
                  <td className="p-3 font-label-caps text-[11px] text-zinc-300 uppercase">{DOMAIN_LABELS[l.domain] || l.domain}</td>
                  <td className="p-3">
                    <span className="px-2 py-0.5 text-[10px] font-bold tracking-widest uppercase" style={{ color: ACTION_COLORS[l.action] || '#A3A3A3', border: `1px solid ${ACTION_COLORS[l.action] || '#262626'}` }}>
                      {l.action.replace('_', ' ')}
                    </span>
                  </td>
                  <td className="p-3 text-[11px] text-zinc-400 uppercase">{l.triggered_by}</td>
                  <td className="p-3 text-[11px]" style={{ color: RISK_COLORS[l.risk_level] || '#A3A3A3' }}>{l.risk_level}</td>
                  <td className="p-3 font-mono text-[11px] text-zinc-300">{l.drift_pct?.toFixed(1)}%</td>
                  <td className="p-3 font-mono text-[11px] text-zinc-300">${l.expected_loss_usd?.toLocaleString('en-US', { maximumFractionDigits: 0 })}</td>
                  <td className="p-3">
                    <span className="text-[10px] font-bold uppercase" style={{ color: l.status === 'completed' ? '#22C55E' : l.status === 'pending' ? '#EAB308' : '#EF4444' }}>{l.status}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </main>
  )
}
