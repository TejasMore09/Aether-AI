'use client'

import { useEffect, useState } from 'react'

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

const DOMAINS = ['hr_attrition', 'fin_fraud', 'crm_churn', 'sec_threats', 'market_leads', 'supply_chain']
const METRICS = ['drift_pct', 'expected_loss_usd', 'f1_score']
const CHANNELS = ['email', 'slack', 'webhook']
const SEVERITIES = ['LOW', 'MEDIUM', 'HIGH']

interface AlertRule { id: number; domain: string; metric: string; threshold: number; channel: string; severity: string; enabled: boolean; created_at: string }
interface Health { avg_latency_ms: number; p99_latency_ms: number; total_evaluations: number; retrain_rate_pct: number; avg_drift_pct: number; domains_monitored: number }

const SEV_COLORS: Record<string, string> = { HIGH: '#EF4444', MEDIUM: '#EAB308', LOW: '#22C55E' }
const CHAN_ICONS: Record<string, string> = { email: 'mail', slack: 'chat', webhook: 'webhook' }

const MOCK_INTEGRATIONS = [
  { name: 'Slack', icon: 'chat', status: 'configured', channel: '#mlops-alerts', color: '#22C55E' },
  { name: 'Email', icon: 'mail', status: 'configured', channel: 'ops@company.com', color: '#22C55E' },
  { name: 'Microsoft Teams', icon: 'groups', status: 'not configured', channel: '—', color: '#525252' },
  { name: 'Webhook', icon: 'webhook', status: 'configured', channel: 'https://hooks.example.com/aether', color: '#22C55E' },
  { name: 'PagerDuty', icon: 'notifications_active', status: 'not configured', channel: '—', color: '#525252' },
  { name: 'MLflow', icon: 'science', status: 'configured', channel: 'http://localhost:5000', color: '#22C55E' },
]

export default function IntegrationsPage() {
  const [rules, setRules] = useState<AlertRule[]>([])
  const [health, setHealth] = useState<Health | null>(null)
  const [loading, setLoading] = useState(true)
  const [newDomain, setNewDomain] = useState('hr_attrition')
  const [newMetric, setNewMetric] = useState('drift_pct')
  const [newThreshold, setNewThreshold] = useState(30)
  const [newChannel, setNewChannel] = useState('email')
  const [newSeverity, setNewSeverity] = useState('HIGH')
  const [creating, setCreating] = useState(false)
  const [testResult, setTestResult] = useState<string | null>(null)

  const fetchAll = async () => {
    setLoading(true)
    const [r, h] = await Promise.all([
      fetch(`${API}/alerts`).then(r => r.json()).catch(() => []),
      fetch(`${API}/health`).then(r => r.json()).catch(() => null)
    ])
    setRules(r)
    setHealth(h)
    setLoading(false)
  }

  useEffect(() => { fetchAll() }, [])

  const createRule = async () => {
    setCreating(true)
    await fetch(`${API}/alerts?domain=${newDomain}&metric=${newMetric}&threshold=${newThreshold}&channel=${newChannel}&severity=${newSeverity}`, { method: 'POST' })
    await fetchAll()
    setCreating(false)
  }

  const toggleRule = async (id: number, enabled: boolean) => {
    await fetch(`${API}/alerts/${id}/toggle?enabled=${!enabled}`, { method: 'POST' })
    await fetchAll()
  }

  const simulateWebhook = async () => {
    setTestResult('⏳ Sending test alert via SMTP...')
    try {
      const r = await fetch(`${API}/send-test-alert`, { method: 'POST' })
      const data = await r.json()
      if (data.sent) {
        setTestResult(`🟢 Alert successfully fired to ${data.recipient}! Check your inbox.`)
      } else {
        setTestResult(`🔴 Failed to send: ${data.reason}\nDid you update the .env file with your GMAIL_SENDER and GMAIL_APP_PASSWORD?`)
      }
    } catch (e: any) {
      setTestResult(`🔴 Error: ${e.message}`)
    }
    setTimeout(() => setTestResult(null), 8000)
  }

  return (
    <main className="pt-24 pb-margin px-margin max-w-[1600px] mx-auto w-full flex flex-col gap-lg">
      {/* Header */}
      <div>
        <h1 className="font-h1 text-h1 text-primary flex items-center gap-3">
          <span className="material-symbols-outlined text-[32px] text-zinc-400">hub</span>
          Integrations & Alerts
        </h1>
        <p className="text-on-surface-variant mt-1">Configure alert rules, notification channels, and external integrations.</p>
      </div>

      {/* System Health KPIs */}
      <div className="bg-surface border border-surface-variant">
        <div className="p-md border-b border-[#262626] flex items-center gap-3">
          <span className="material-symbols-outlined text-[#22C55E] text-[18px]">monitor_heart</span>
          <h2 className="font-semibold text-primary text-lg">System Health Overview</h2>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-[1px] bg-[#262626]">
          {[
            { label: 'Avg Latency', value: health ? `${health.avg_latency_ms}ms` : '—', icon: 'speed' },
            { label: 'P99 Latency', value: health ? `${health.p99_latency_ms}ms` : '—', icon: 'timer' },
            { label: 'Total Evaluations', value: health ? health.total_evaluations : '—', icon: 'analytics' },
            { label: 'Retrain Rate', value: health ? `${health.retrain_rate_pct}%` : '—', icon: 'refresh' },
            { label: 'Avg Drift', value: health ? `${health.avg_drift_pct}%` : '—', icon: 'trending_up' },
            { label: 'Domains Active', value: health ? health.domains_monitored : '—', icon: 'grid_view' },
          ].map(k => (
            <div key={k.label} className="bg-surface p-lg flex flex-col gap-2">
              <div className="flex items-center gap-2">
                <span className="material-symbols-outlined text-zinc-500 text-[16px]">{k.icon}</span>
                <span className="font-label-caps text-[10px] text-zinc-500 uppercase">{k.label}</span>
              </div>
              <div className="font-mono text-xl text-primary">{loading ? '…' : k.value}</div>
            </div>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-md">
        {/* Alert Rule Builder */}
        <div className="bg-surface border border-surface-variant flex flex-col">
          <div className="p-md border-b border-[#262626] flex items-center gap-3">
            <span className="material-symbols-outlined text-[#EAB308] text-[18px]">add_alert</span>
            <h2 className="font-semibold text-primary text-lg">Create Alert Rule</h2>
          </div>
          <div className="p-lg flex flex-col gap-4">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="font-label-caps text-[10px] text-zinc-500 uppercase mb-1 block">Domain</label>
                <select value={newDomain} onChange={e => setNewDomain(e.target.value)}
                  className="w-full bg-[#0A0A0A] border border-[#262626] text-primary font-label-caps text-label-caps px-3 py-2 uppercase outline-none">
                  {DOMAINS.map(d => <option key={d} value={d}>{d.replace(/_/g, ' ')}</option>)}
                </select>
              </div>
              <div>
                <label className="font-label-caps text-[10px] text-zinc-500 uppercase mb-1 block">Metric</label>
                <select value={newMetric} onChange={e => setNewMetric(e.target.value)}
                  className="w-full bg-[#0A0A0A] border border-[#262626] text-primary font-label-caps text-label-caps px-3 py-2 uppercase outline-none">
                  {METRICS.map(m => <option key={m} value={m}>{m.replace(/_/g, ' ')}</option>)}
                </select>
              </div>
              <div>
                <label className="font-label-caps text-[10px] text-zinc-500 uppercase mb-1 block">Threshold</label>
                <input type="number" value={newThreshold} onChange={e => setNewThreshold(Number(e.target.value))}
                  className="w-full bg-[#0A0A0A] border border-[#262626] text-primary px-3 py-2 outline-none focus:border-zinc-500 transition-colors" />
              </div>
              <div>
                <label className="font-label-caps text-[10px] text-zinc-500 uppercase mb-1 block">Channel</label>
                <select value={newChannel} onChange={e => setNewChannel(e.target.value)}
                  className="w-full bg-[#0A0A0A] border border-[#262626] text-primary font-label-caps text-label-caps px-3 py-2 uppercase outline-none">
                  {CHANNELS.map(c => <option key={c} value={c}>{c}</option>)}
                </select>
              </div>
              <div>
                <label className="font-label-caps text-[10px] text-zinc-500 uppercase mb-1 block">Severity</label>
                <select value={newSeverity} onChange={e => setNewSeverity(e.target.value)}
                  className="w-full bg-[#0A0A0A] border border-[#262626] text-primary font-label-caps text-label-caps px-3 py-2 uppercase outline-none">
                  {SEVERITIES.map(s => <option key={s} value={s}>{s}</option>)}
                </select>
              </div>
            </div>
            <div className="flex gap-3 mt-2">
              <button onClick={createRule} disabled={creating}
                className="flex-1 py-3 bg-primary text-[#0A0A0A] font-label-caps text-label-caps hover:bg-zinc-200 transition-colors uppercase flex items-center justify-center gap-2 disabled:opacity-50">
                <span className="material-symbols-outlined text-[16px]">add</span>
                {creating ? 'Creating...' : 'Create Rule'}
              </button>
              <button onClick={simulateWebhook}
                className="px-4 py-3 border border-surface-variant text-zinc-400 font-label-caps text-label-caps hover:border-zinc-500 hover:text-white transition-colors uppercase flex items-center gap-2">
                <span className="material-symbols-outlined text-[16px]">send</span>
                Test Fire
              </button>
            </div>
            {testResult && (
              <div className="bg-[#0A0F0A] border border-[#22C55E]/30 p-3 font-mono text-[11px] text-[#22C55E] whitespace-pre-wrap">{testResult}</div>
            )}
          </div>
        </div>

        {/* Active Rules */}
        <div className="bg-surface border border-surface-variant flex flex-col">
          <div className="p-md border-b border-[#262626] flex items-center gap-3">
            <span className="material-symbols-outlined text-zinc-400 text-[18px]">rule</span>
            <h2 className="font-semibold text-primary text-lg">Active Rules ({rules.length})</h2>
            <button onClick={fetchAll} className="ml-auto text-zinc-500 hover:text-white transition-colors">
              <span className="material-symbols-outlined text-[16px]">refresh</span>
            </button>
          </div>
          <div className="flex-1 overflow-y-auto max-h-[400px]">
            {loading ? (
              <div className="p-8 text-center text-zinc-500 font-label-caps">Loading rules...</div>
            ) : rules.length === 0 ? (
              <div className="p-8 text-center text-zinc-600 font-label-caps">No alert rules yet. Create one to the left.</div>
            ) : (
              rules.map(r => (
                <div key={r.id} className={`flex items-center gap-3 p-4 border-b border-[#262626] hover:bg-[#1A1A1A] transition-colors ${!r.enabled ? 'opacity-50' : ''}`}>
                  <span className="material-symbols-outlined text-zinc-400 text-[18px]">{CHAN_ICONS[r.channel] || 'notifications'}</span>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-0.5">
                      <span className="font-label-caps text-[11px] text-zinc-200 uppercase">{r.domain.replace(/_/g, ' ')}</span>
                      <span className="font-label-caps text-[10px]" style={{ color: SEV_COLORS[r.severity] }}>· {r.severity}</span>
                    </div>
                    <div className="font-mono text-[11px] text-zinc-400">{r.metric} &gt; {r.threshold} → {r.channel}</div>
                  </div>
                  <button onClick={() => toggleRule(r.id, r.enabled)}
                    className={`px-2 py-1 text-[10px] font-bold uppercase transition-colors ${r.enabled ? 'text-[#22C55E] hover:text-red-400' : 'text-zinc-600 hover:text-[#22C55E]'}`}>
                    {r.enabled ? 'ON' : 'OFF'}
                  </button>
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      {/* Integration Hub */}
      <div className="bg-surface border border-surface-variant">
        <div className="p-md border-b border-[#262626] flex items-center gap-3">
          <span className="material-symbols-outlined text-zinc-400 text-[18px]">hub</span>
          <h2 className="font-semibold text-primary text-lg">Integration Hub</h2>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-[1px] bg-[#262626]">
          {MOCK_INTEGRATIONS.map(i => (
            <div key={i.name} className="bg-surface p-lg flex items-start gap-4">
              <div className="w-10 h-10 bg-[#1A1A1A] border border-[#262626] flex items-center justify-center flex-shrink-0">
                <span className="material-symbols-outlined text-[20px] text-zinc-400">{i.icon}</span>
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <span className="font-semibold text-primary text-sm">{i.name}</span>
                  <span className="text-[10px] font-bold uppercase" style={{ color: i.color }}>{i.status}</span>
                </div>
                <div className="font-mono text-[11px] text-zinc-500 truncate">{i.channel}</div>
              </div>
              <button className="px-3 py-1 border border-[#262626] text-zinc-400 text-[10px] font-label-caps uppercase hover:border-zinc-500 hover:text-white transition-colors flex-shrink-0">
                {i.status === 'configured' ? 'Edit' : 'Connect'}
              </button>
            </div>
          ))}
        </div>
      </div>
    </main>
  )
}
