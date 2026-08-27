import Link from 'next/link'

import {
  EmptyState,
  ErrorNote,
  Eyebrow,
  Gauge,
  PageTitle,
  Panel,
  whenUTC,
} from '@/components/forge'
import { api } from '@/lib/api'

type DomainSummary = {
  domain: string
  last_seen: string | null
  observation_count: number
  has_policy: boolean
  latest_drift_fraction: number | null
  latest_performance: number | null
}

export default async function DomainsPage() {
  const domains = await api.runtime<DomainSummary[]>('/v1/domains')

  if (!domains.ok) {
    return (
      <>
        <PageTitle title="Domains" />
        <ErrorNote message={domains.message} />
      </>
    )
  }

  return (
    <>
      <div className="mb-5">
        <Eyebrow>What your agent watches</Eyebrow>
      </div>

      <PageTitle
        title="Domains"
        lede="Each area of the business your agent tracks. A domain exists as soon as it has readings — there is nothing to register."
      />

      {domains.data.length === 0 ? (
        <EmptyState
          title="No domains yet"
          body="Send a first reading from any domain page, or point a connector at its readings endpoint. Visit /domains/receivables to start with cash collection."
        />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {domains.data.map((d) => {
            const health = d.latest_performance
            const unhealthy = health !== null && health < 0.6
            return (
              <Link key={d.domain} href={`/domains/${d.domain}`} className="group block">
                <Panel className="h-full !p-[22px] transition-transform duration-[240ms] ease-[var(--ease-forge)] group-hover:-translate-y-[2px]">
                  <div className="flex items-start justify-between gap-3">
                    <span className="text-[15px] font-semibold tracking-[-0.015em]">
                      {d.domain}
                    </span>
                    <span
                      className="text-[11px] transition-colors duration-200 group-hover:text-[var(--color-copper)]"
                      style={{ color: 'var(--color-ink-faint)' }}
                      aria-hidden="true"
                    >
                      →
                    </span>
                  </div>

                  <div className="mt-5 flex items-baseline gap-2">
                    <span
                      data-figure
                      className="text-[30px] font-bold leading-none tracking-[-0.03em]"
                      style={{ color: unhealthy ? 'var(--color-risk)' : 'var(--color-ink)' }}
                    >
                      {health === null ? '—' : `${Math.round(health * 100)}%`}
                    </span>
                    <span className="text-[12.5px]" style={{ color: 'var(--color-ink-faint)' }}>
                      health
                    </span>
                  </div>

                  <div className="mt-3">
                    <Gauge
                      pct={health === null ? 0 : health * 100}
                      tone={unhealthy ? 'risk' : 'good'}
                    />
                  </div>

                  <p className="mt-4 text-[12px]" style={{ color: 'var(--color-ink-faint)' }}>
                    {d.observation_count} reading{d.observation_count === 1 ? '' : 's'} ·{' '}
                    {d.last_seen ? whenUTC(d.last_seen).slice(0, 10) : 'never reported'}
                  </p>
                </Panel>
              </Link>
            )
          })}
        </div>
      )}
    </>
  )
}
