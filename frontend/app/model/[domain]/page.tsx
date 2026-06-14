'use client'

import { useEffect, useState } from 'react'
import { useParams } from 'next/navigation'

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

function fmt(val: number | undefined | null, decimals = 4, suffix = ''): string {
  if (val === undefined || val === null || isNaN(val)) return '—'
  return val.toFixed(decimals) + suffix
}

interface MetricsResp  { roc_auc?: number; f1_score?: number; mape?: number; rmse?: number }
interface DriftResp    { drift_percentage?: number; drifted_features?: string[] }

const MODEL_MAP: Record<string, { name: string, type: string, target: string }> = {
  hr_attrition: { name: 'HR Attrition Engine', type: 'XGBoost Classification', target: '< 0.15 KS' },
  fin_fraud: { name: 'Fraud Detection V4', type: 'XGBoost Classification', target: '< 0.15 KS' },
  crm_churn: { name: 'CRM Retention Model', type: 'XGBoost Classification', target: '< 0.15 KS' },
  sec_threats: { name: 'Threat Intel Core', type: 'XGBoost Classification', target: '< 0.10 KS' },
  market_leads: { name: 'Lead Conversion', type: 'XGBoost Classification', target: '< 0.20 KS' },
  supply_chain: { name: 'Demand Forecast', type: 'SARIMAX Time Series', target: '< 5.0% MAPE' },
}

export default function ModelDetail() {
  const { domain } = useParams()
  const domainStr = Array.isArray(domain) ? domain[0] : domain || 'hr_attrition'
  
  const [metrics, setMetrics] = useState<MetricsResp | null>(null)
  const [drift, setDrift] = useState<DriftResp | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const metricsReq = fetch(`${API}/metrics?domain=${domainStr}`).then(r => r.json()).catch(() => null)
    const driftReq   = fetch(`${API}/drift?domain=${domainStr}`).then(r => r.json()).catch(() => null)

    Promise.all([metricsReq, driftReq]).then(([m, d]) => {
      setMetrics(m || {})
      setDrift(d || {})
    }).finally(() => setLoading(false))
  }, [domainStr])

  const meta = MODEL_MAP[domainStr] || MODEL_MAP.hr_attrition
  const isTimeSeries = domainStr === 'supply_chain'

  return (
    <main className="pt-24 pb-margin px-margin max-w-[1600px] mx-auto w-full flex flex-col gap-lg">
      
      {/* Header Section */}
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-md mb-md">
        <div>
          <div className="flex items-center gap-sm mb-xs">
            <span className="w-2 h-4 bg-primary inline-block"></span>
            <span className="font-label-caps text-label-caps text-on-surface-variant uppercase">Model ID: {domainStr.toUpperCase()}</span>
            <span className="px-2 py-1 bg-[#262626] text-[#A3A3A3] font-label-caps text-[10px] ml-2 border-l-2 border-green-500">ACTIVE</span>
          </div>
          <h1 className="font-h1 text-h1 text-primary">{meta.name}</h1>
          <p className="font-body-base text-body-base text-on-surface-variant mt-1">{meta.type}</p>
        </div>
        <div className="flex gap-md">
          <button className="px-6 py-2 border border-[#262626] text-primary font-label-caps text-label-caps hover:border-primary transition-colors uppercase">
            Export Logs
          </button>
          <button className="px-6 py-2 bg-primary text-[#0A0A0A] font-label-caps text-label-caps hover:bg-zinc-200 transition-colors uppercase">
            Force Retrain
          </button>
        </div>
      </div>

      {/* KPI Row */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-md">
        <div className="bg-surface border border-surface-variant p-lg flex flex-col justify-between h-[200px]">
          <span className="font-label-caps text-label-caps text-[#A3A3A3] uppercase mb-4">{isTimeSeries ? 'MAPE' : 'F1 Score'}</span>
          <div className="flex items-baseline gap-2">
            <span className="font-metric-lg text-metric-lg text-primary">
              {loading ? '...' : (isTimeSeries ? fmt(metrics?.mape, 2) : fmt(metrics?.f1_score, 4))}
            </span>
            <span className="font-metric-sm text-metric-sm text-zinc-500">{isTimeSeries ? '%' : ''}</span>
          </div>
          <div className="mt-4 pt-4 border-t border-[#262626] flex items-center justify-between">
            <span className="font-label-caps text-[10px] text-zinc-500">VS LAST EPOCH</span>
            <span className="font-metric-sm text-[12px] text-primary">+0.14%</span>
          </div>
        </div>

        <div className="bg-surface border border-surface-variant p-lg flex flex-col justify-between h-[200px]">
          <span className="font-label-caps text-label-caps text-[#A3A3A3] uppercase mb-4">{isTimeSeries ? 'RMSE' : 'ROC-AUC'}</span>
          <div className="flex items-baseline gap-2">
            <span className="font-metric-lg text-metric-lg text-primary">
              {loading ? '...' : (isTimeSeries ? fmt(metrics?.rmse, 2) : fmt(metrics?.roc_auc, 4))}
            </span>
          </div>
          <div className="mt-4 pt-4 border-t border-[#262626] flex items-center justify-between">
            <span className="font-label-caps text-[10px] text-zinc-500">TARGET</span>
            <span className="font-metric-sm text-[12px] text-primary">PASSING</span>
          </div>
        </div>

        <div className="bg-surface border border-surface-variant p-lg flex flex-col justify-between h-[200px]">
          <span className="font-label-caps text-label-caps text-[#A3A3A3] uppercase mb-4">Data Drift Score</span>
          <div className="flex items-baseline gap-2">
            <span className="font-metric-lg text-metric-lg text-primary">
              {loading ? '...' : fmt(drift?.drift_percentage, 1)}
            </span>
            <span className="font-metric-sm text-metric-sm text-zinc-500">%</span>
          </div>
          <div className="mt-4 pt-4 border-t border-[#262626] flex items-center justify-between">
            <span className="font-label-caps text-[10px] text-zinc-500">THRESHOLD: {meta.target}</span>
            <span className="font-metric-sm text-[12px] text-[#A3A3A3]">NOMINAL</span>
          </div>
        </div>
      </div>

      {/* Complex Layout: Charts & Controls */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-md">
        
        {/* Main Chart Area */}
        <div className="lg:col-span-2 bg-surface border border-surface-variant flex flex-col">
          <div className="p-md border-b border-[#262626] flex justify-between items-center">
            <h2 className="font-h2 text-h2 text-primary text-lg">Performance Telemetry</h2>
            <div className="flex gap-4">
              <span className="flex items-center gap-2 font-label-caps text-[10px] text-zinc-400"><span className="w-2 h-2 bg-primary"></span> ACCURACY</span>
              <span className="flex items-center gap-2 font-label-caps text-[10px] text-zinc-400"><span className="w-2 h-2 bg-[#444]"></span> LATENCY</span>
            </div>
          </div>
          <div className="p-lg flex-1 min-h-[300px] relative">
            <div className="absolute inset-0 p-lg flex flex-col justify-between">
              <div className="w-full h-[1px] bg-[#262626]"></div>
              <div className="w-full h-[1px] bg-[#262626]"></div>
              <div className="w-full h-[1px] bg-[#262626]"></div>
              <div className="w-full h-[1px] bg-[#262626]"></div>
              <div className="w-full h-[1px] bg-[#262626]"></div>
            </div>
            <div className="relative w-full h-full z-10 flex items-end opacity-80">
              <svg className="w-full h-full" preserveAspectRatio="none" viewBox="0 0 100 100">
                <polyline fill="none" points="0,80 20,75 40,60 60,65 80,40 100,20" stroke="#FFFFFF" strokeWidth="1.5" vectorEffect="non-scaling-stroke"></polyline>
                <polyline fill="none" points="0,50 20,45 40,55 60,40 80,45 100,60" stroke="#444444" strokeWidth="1.5" vectorEffect="non-scaling-stroke"></polyline>
              </svg>
            </div>
          </div>
        </div>

        {/* Adaptive Control Panel */}
        <div className="bg-surface border border-surface-variant flex flex-col">
          <div className="p-md border-b border-[#262626]">
            <h2 className="font-h2 text-h2 text-primary text-lg">Adaptive Control</h2>
          </div>
          <div className="p-lg flex flex-col gap-lg flex-1">
            <div className="flex flex-col gap-2">
              <div className="flex justify-between items-center">
                <label className="font-body-sm text-body-sm text-on-surface">Retrain Threshold</label>
                <span className="font-metric-sm text-metric-sm text-primary">0.15</span>
              </div>
              <div className="h-2 w-full bg-[#0A0A0A] border border-[#262626] relative mt-2">
                <div className="absolute left-0 top-0 h-full w-[60%] bg-[#444444]"></div>
                <div className="absolute left-[60%] top-1/2 -translate-y-1/2 w-1 h-4 bg-primary"></div>
              </div>
            </div>
            
            <div className="flex flex-col gap-2">
              <div className="flex justify-between items-center">
                <label className="font-body-sm text-body-sm text-on-surface">Exploration Rate (Epsilon)</label>
                <span className="font-metric-sm text-metric-sm text-primary">0.05</span>
              </div>
              <div className="h-2 w-full bg-[#0A0A0A] border border-[#262626] relative mt-2">
                <div className="absolute left-0 top-0 h-full w-[20%] bg-[#444444]"></div>
                <div className="absolute left-[20%] top-1/2 -translate-y-1/2 w-1 h-4 bg-primary"></div>
              </div>
            </div>

            <div className="mt-auto pt-lg border-t border-[#262626]">
              <button className="w-full py-3 border border-[#262626] text-primary font-label-caps text-label-caps hover:border-primary transition-colors flex items-center justify-center gap-2">
                <span className="material-symbols-outlined text-[16px]">tune</span>
                APPLY PARAMETERS
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Drift Analysis Grid */}
      {(!loading && drift?.drifted_features?.length) ? (
        <div className="bg-surface border border-surface-variant">
          <div className="p-md border-b border-[#262626]">
            <h2 className="font-h2 text-h2 text-primary text-lg">Evidently AI Drift Analysis</h2>
          </div>
          <div className="w-full overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr>
                  <th className="p-4 border-b border-[#262626] font-label-caps text-label-caps text-zinc-500 uppercase">Feature Name</th>
                  <th className="p-4 border-b border-[#262626] font-label-caps text-label-caps text-zinc-500 uppercase">Importance</th>
                  <th className="p-4 border-b border-[#262626] font-label-caps text-label-caps text-zinc-500 uppercase">Drift Status</th>
                  <th className="p-4 border-b border-[#262626] font-label-caps text-label-caps text-zinc-500 uppercase">Distribution (Ref vs Cur)</th>
                </tr>
              </thead>
              <tbody>
                {drift.drifted_features.map(feat => (
                  <tr key={feat} className="border-b border-[#262626] hover:bg-[#1A1A1A] transition-colors">
                    <td className="p-4 font-metric-sm text-metric-sm text-primary">{feat}</td>
                    <td className="p-4 font-metric-sm text-metric-sm text-zinc-400">High</td>
                    <td className="p-4 font-metric-sm text-metric-sm text-primary">Drifted <span className="text-[#A3A3A3] text-[10px] ml-1">WARN</span></td>
                    <td className="p-4">
                      <div className="w-32 h-6 flex gap-1 items-end">
                        <div className="flex-1 bg-[#444] h-[40%] opacity-50"></div>
                        <div className="flex-1 bg-primary h-full opacity-80"></div>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : (
        <div className="bg-surface border border-surface-variant p-md">
          <p className="font-body-sm text-on-surface-variant">No drift detected currently.</p>
        </div>
      )}
    </main>
  )
}
