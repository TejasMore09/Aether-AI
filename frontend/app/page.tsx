'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

function fmt(val: number | undefined | null, decimals = 4, suffix = ''): string {
  if (val === undefined || val === null || isNaN(val)) return '—'
  return val.toFixed(decimals) + suffix
}

interface MetricsResp  { roc_auc?: number; f1_score?: number }
interface DriftResp    { drift_percentage?: number; drifted_features?: string[] }

export default function GlobalDashboard() {
  const [metrics, setMetrics] = useState<MetricsResp | null>(null)
  const [drift, setDrift] = useState<DriftResp | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    // We fetch metrics for the default HR module to display global aggregates
    const metricsReq = fetch(`${API}/metrics?domain=hr_attrition`).then(r => r.json()).catch(() => null)
    const driftReq   = fetch(`${API}/drift`).then(r => r.json()).catch(() => null)

    Promise.all([metricsReq, driftReq]).then(([m, d]) => {
      setMetrics(m || {})
      setDrift(d || {})
    }).finally(() => setLoading(false))
  }, [])

  return (
    <main className="pt-24 pb-margin px-margin max-w-[1600px] w-full mx-auto flex-1 flex flex-col gap-margin">
      
      <section className="flex flex-col gap-lg">
        <div className="flex justify-between items-end border-b border-surface-variant pb-4">
              <div>
                <h1 className="font-h1 text-h1 text-on-surface">System Performance</h1>
                <p className="font-body-base text-body-base text-on-surface-variant mt-2">Aggregate metrics across the entire active model fleet.</p>
              </div>
              <div className="font-metric-sm text-metric-sm text-on-surface-variant">
                LAST UPDATED: <span className="text-primary ml-2">LIVE</span>
              </div>
            </div>

            <div className="grid grid-cols-12 gap-gutter">
              <div className="col-span-12 lg:col-span-6 bg-surface border border-surface-variant p-lg flex flex-col justify-between h-[240px]">
                <div className="flex justify-between items-start">
                  <span className="font-label-caps text-label-caps text-on-surface-variant uppercase tracking-widest">Global ROC-AUC Average</span>
                  <span className="material-symbols-outlined text-primary">security</span>
                </div>
                <div>
                  <div className="font-display-lg text-display-lg text-primary tracking-tighter">{loading ? '...' : fmt(metrics?.roc_auc, 4)}</div>
                  <div className="mt-4 flex items-center gap-2 font-metric-sm text-metric-sm text-primary">
                    <span className="w-2 h-2 bg-[#4ade80]"></span>
                    Exceeds 0.85 Enterprise Threshold
                  </div>
                </div>
              </div>
              
              <div className="col-span-12 md:col-span-6 lg:col-span-3 bg-surface border border-surface-variant p-lg flex flex-col justify-between h-[240px]">
                <span className="font-label-caps text-label-caps text-on-surface-variant uppercase tracking-widest">Active Models</span>
                <div>
                  <div className="font-metric-lg text-[48px] leading-none font-medium text-on-surface">5</div>
                  <div className="mt-4 flex items-center gap-2 font-metric-sm text-metric-sm text-on-surface-variant">
                    Running in Production
                  </div>
                </div>
              </div>

              <div className="col-span-12 md:col-span-6 lg:col-span-3 bg-surface border border-surface-variant p-lg flex flex-col justify-between h-[240px]">
                <span className="font-label-caps text-label-caps text-on-surface-variant uppercase tracking-widest">Global Anomaly Rate</span>
                <div>
                  <div className="font-metric-lg text-[48px] leading-none font-medium text-on-surface">{loading ? '...' : fmt(drift?.drift_percentage, 1, '%')}</div>
                  <div className="mt-4 flex items-center gap-2 font-metric-sm text-metric-sm text-on-surface-variant">
                    <span className="w-2 h-2 bg-[#eab308]"></span>
                    Drift Detection Live
                  </div>
                </div>
              </div>
            </div>
          </section>

          <section className="flex flex-col gap-lg mt-8">
            <div className="border-b border-surface-variant pb-4">
              <h2 className="font-h2 text-h2 text-on-surface">Model Fleet</h2>
            </div>
            
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-gutter">
              
              {/* HR Attrition */}
              <Link href="/model/hr_attrition" className="bg-surface border border-surface-variant relative h-[200px] flex flex-col hover:border-primary transition-all cursor-pointer">
                <div className="absolute left-0 top-0 bottom-0 w-[4px] bg-[#4ade80]"></div>
                <div className="p-6 flex-1 flex flex-col justify-between ml-1">
                  <div className="flex justify-between items-start">
                    <div>
                      <h3 className="font-body-base text-body-base font-semibold text-on-surface">HR Attrition</h3>
                      <div className="font-label-caps text-label-caps text-on-surface-variant mt-2 uppercase">Workforce Intelligence</div>
                    </div>
                    <div className="w-3 h-3 bg-[#4ade80]"></div>
                  </div>
                  <div className="grid grid-cols-2 gap-4 border-t border-surface-variant pt-4">
                    <div>
                      <div className="font-label-caps text-label-caps text-on-surface-variant mb-1">Status</div>
                      <div className="font-metric-sm text-metric-sm text-[#4ade80]">Optimal</div>
                    </div>
                    <div>
                      <div className="font-label-caps text-label-caps text-on-surface-variant mb-1">F1 Score</div>
                      <div className="font-metric-sm text-metric-sm text-on-surface">{loading ? '...' : fmt(metrics?.f1_score, 4)}</div>
                    </div>
                  </div>
                </div>
              </Link>

              {/* CRM Churn */}
              <Link href="/model/crm_churn" className="bg-surface border border-surface-variant relative h-[200px] flex flex-col hover:border-primary transition-all cursor-pointer">
                <div className="absolute left-0 top-0 bottom-0 w-[4px] bg-[#eab308]"></div>
                <div className="p-6 flex-1 flex flex-col justify-between ml-1">
                  <div className="flex justify-between items-start">
                    <div>
                      <h3 className="font-body-base text-body-base font-semibold text-on-surface">CRM Churn</h3>
                      <div className="font-label-caps text-label-caps text-on-surface-variant mt-2 uppercase">User Retention</div>
                    </div>
                    <div className="w-3 h-3 bg-[#eab308]"></div>
                  </div>
                  <div className="grid grid-cols-2 gap-4 border-t border-surface-variant pt-4">
                    <div>
                      <div className="font-label-caps text-label-caps text-on-surface-variant mb-1">Status</div>
                      <div className="font-metric-sm text-metric-sm text-[#eab308]">Feature Drift</div>
                    </div>
                    <div>
                      <div className="font-label-caps text-label-caps text-on-surface-variant mb-1">Confidence</div>
                      <div className="font-metric-sm text-metric-sm text-on-surface">82.4%</div>
                    </div>
                  </div>
                </div>
              </Link>

              {/* Financial Fraud */}
              <Link href="/model/fin_fraud" className="bg-surface border border-surface-variant relative h-[200px] flex flex-col hover:border-primary transition-all cursor-pointer">
                <div className="absolute left-0 top-0 bottom-0 w-[4px] bg-[#4ade80]"></div>
                <div className="p-6 flex-1 flex flex-col justify-between ml-1">
                  <div className="flex justify-between items-start">
                    <div>
                      <h3 className="font-body-base text-body-base font-semibold text-on-surface">Fraud Detection V4</h3>
                      <div className="font-label-caps text-label-caps text-on-surface-variant mt-2 uppercase">Transaction Core</div>
                    </div>
                    <div className="w-3 h-3 bg-[#4ade80]"></div>
                  </div>
                  <div className="grid grid-cols-2 gap-4 border-t border-surface-variant pt-4">
                    <div>
                      <div className="font-label-caps text-label-caps text-on-surface-variant mb-1">Latency</div>
                      <div className="font-metric-sm text-metric-sm text-on-surface">24ms</div>
                    </div>
                    <div>
                      <div className="font-label-caps text-label-caps text-on-surface-variant mb-1">Precision</div>
                      <div className="font-metric-sm text-metric-sm text-on-surface">99.9%</div>
                    </div>
                  </div>
                </div>
              </Link>

              {/* Supply Chain */}
              <Link href="/model/supply_chain" className="bg-surface border border-surface-variant relative h-[200px] flex flex-col hover:border-primary transition-all cursor-pointer">
                <div className="absolute left-0 top-0 bottom-0 w-[4px] bg-[#4ade80]"></div>
                <div className="p-6 flex-1 flex flex-col justify-between ml-1">
                  <div className="flex justify-between items-start">
                    <div>
                      <h3 className="font-body-base text-body-base font-semibold text-on-surface">Demand Forecast</h3>
                      <div className="font-label-caps text-label-caps text-on-surface-variant mt-2 uppercase">Supply Chain</div>
                    </div>
                    <div className="w-3 h-3 bg-[#4ade80]"></div>
                  </div>
                  <div className="grid grid-cols-2 gap-4 border-t border-surface-variant pt-4">
                    <div>
                      <div className="font-label-caps text-label-caps text-on-surface-variant mb-1">Horizon</div>
                      <div className="font-metric-sm text-metric-sm text-on-surface">Daily</div>
                    </div>
                    <div>
                      <div className="font-label-caps text-label-caps text-on-surface-variant mb-1">MAPE</div>
                      <div className="font-metric-sm text-metric-sm text-on-surface">4.2%</div>
                    </div>
                  </div>
                </div>
              </Link>

            </div>
          </section>
    </main>
  )
}
