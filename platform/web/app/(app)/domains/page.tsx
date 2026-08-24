import Link from 'next/link'

import { api } from '@/lib/api'
import { EmptyState, ErrorNote, PageHeader, formatWhen } from '@/components/ui'

type DomainSummary = {
  domain: string
  last_seen: string | null
  observation_count: number
  has_policy: boolean
  latest_drift_fraction: number | null
  latest_performance: number | null
}

function pct(value: number | null): string {
  return value === null ? '—' : `${Math.round(value * 100)}%`
}

export default async function DomainsPage() {
  const domains = await api.runtime<DomainSummary[]>('/v1/domains')

  if (!domains.ok) {
    return (
      <>
        <PageHeader title="Domains" />
        <ErrorNote message={domains.message} />
      </>
    )
  }

  return (
    <>
      <PageHeader
        title="Domains"
        subtitle="Each area of your operation the agent watches — finance, HR, sales, whatever you feed it."
      />

      {domains.data.length === 0 ? (
        <EmptyState
          title="No domains yet"
          body="A domain appears as soon as it has telemetry. Push your first reading from a domain page, or point a connector at the observations endpoint."
        />
      ) : (
        <div className="card" style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr>
                {['Domain', 'Latest drift', 'Latest performance', 'Readings', 'Last seen'].map(
                  (h) => (
                    <th
                      key={h}
                      className="label"
                      style={{
                        textAlign: 'left',
                        padding: '11px 16px',
                        borderBottom: '1px solid var(--color-line)',
                        background: 'var(--color-surface-raised)',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {h}
                    </th>
                  ),
                )}
              </tr>
            </thead>
            <tbody>
              {domains.data.map((d) => (
                <tr key={d.domain}>
                  <td style={{ padding: '12px 16px', borderBottom: '1px solid var(--color-line)' }}>
                    <Link
                      href={`/domains/${d.domain}`}
                      className="mono"
                      style={{ color: 'var(--color-accent)' }}
                    >
                      {d.domain}
                    </Link>
                  </td>
                  <td
                    className="mono"
                    style={{
                      padding: '12px 16px',
                      borderBottom: '1px solid var(--color-line)',
                      color:
                        (d.latest_drift_fraction ?? 0) > 0.5
                          ? 'var(--color-risk-high)'
                          : 'var(--color-ink)',
                    }}
                  >
                    {pct(d.latest_drift_fraction)}
                  </td>
                  <td
                    className="mono"
                    style={{
                      padding: '12px 16px',
                      borderBottom: '1px solid var(--color-line)',
                      color:
                        (d.latest_performance ?? 1) < 0.7
                          ? 'var(--color-risk-high)'
                          : 'var(--color-ink)',
                    }}
                  >
                    {pct(d.latest_performance)}
                  </td>
                  <td
                    className="mono"
                    style={{
                      padding: '12px 16px',
                      borderBottom: '1px solid var(--color-line)',
                      color: 'var(--color-ink-muted)',
                    }}
                  >
                    {d.observation_count}
                  </td>
                  <td
                    className="mono"
                    style={{
                      padding: '12px 16px',
                      borderBottom: '1px solid var(--color-line)',
                      color: 'var(--color-ink-faint)',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {d.last_seen ? formatWhen(d.last_seen) : 'never'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div style={{ marginTop: 28 }}>
        <NewDomainHint />
      </div>
    </>
  )
}

function NewDomainHint() {
  return (
    <div className="card" style={{ padding: 20 }}>
      <div className="label">Adding a domain</div>
      <p style={{ fontSize: 13, color: 'var(--color-ink-muted)', marginTop: 8, maxWidth: '68ch' }}>
        Domains are created by sending telemetry — no setup step. Visit{' '}
        <span className="mono" style={{ color: 'var(--color-ink)' }}>
          /domains/&lt;name&gt;
        </span>{' '}
        for any lowercase name to push its first reading and enable monitoring.
      </p>
    </div>
  )
}
