import { notFound } from 'next/navigation'

import { api, type AuditEntry, type ObservationRow } from '@/lib/api'
import {
  ActionTag,
  EmptyState,
  ErrorNote,
  PageHeader,
  RiskPill,
  Stat,
  formatWhen,
} from '@/components/ui'

import { EvaluateNow, MonitoringControls, PushObservation } from './Controls'

const DOMAIN_PATTERN = /^[a-z0-9][a-z0-9_-]*$/

export default async function DomainPage({
  params,
}: {
  params: Promise<{ domain: string }>
}) {
  const { domain } = await params
  if (!DOMAIN_PATTERN.test(domain)) notFound()

  const [observations, activity] = await Promise.all([
    api.runtime<ObservationRow[]>(`/v1/domains/${domain}/observations?limit=12`),
    api.runtime<AuditEntry[]>('/v1/audit-logs?limit=50'),
  ])

  const readings = observations.ok ? observations.data : []
  const latest = readings[0]
  const domainActivity = activity.ok
    ? activity.data.filter((e) => e.domain === domain).slice(0, 8)
    : []

  return (
    <>
      <PageHeader
        title={domain}
        subtitle="Telemetry, monitoring schedule, and what the agent decided."
        right={<EvaluateNow domain={domain} />}
      />

      {!observations.ok ? (
        <div style={{ marginBottom: 24 }}>
          <ErrorNote message={observations.message} />
        </div>
      ) : null}

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
          gap: 16,
          marginBottom: 32,
        }}
      >
        <Stat
          label="Latest drift"
          value={latest ? `${Math.round(latest.drift_fraction * 100)}%` : '—'}
          hint={latest ? `source: ${latest.source}` : 'no readings yet'}
          tone={latest && latest.drift_fraction > 0.5 ? 'high' : 'plain'}
        />
        <Stat
          label="Latest performance"
          value={latest ? `${Math.round(latest.performance * 100)}%` : '—'}
          hint={latest ? formatWhen(latest.observed_at) : 'no readings yet'}
          tone={latest && latest.performance < 0.7 ? 'high' : 'plain'}
        />
        <Stat label="Readings stored" value={String(readings.length)} hint="most recent 12" />
      </div>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))',
          gap: 16,
          marginBottom: 32,
        }}
      >
        <MonitoringControls domain={domain} />
        <PushObservation domain={domain} />
      </div>

      <section style={{ marginBottom: 32 }}>
        <h2 className="label" style={{ marginBottom: 12 }}>
          Telemetry history
        </h2>
        {readings.length === 0 ? (
          <EmptyState
            title="No readings yet"
            body="Send one above, or POST to this domain's observations endpoint from your own systems."
          />
        ) : (
          <div className="card" style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr>
                  {['Observed at', 'Drift', 'Performance', 'Source'].map((h) => (
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
                  ))}
                </tr>
              </thead>
              <tbody>
                {readings.map((row) => (
                  <tr key={row.id}>
                    <td
                      className="mono"
                      style={{
                        padding: '10px 16px',
                        borderBottom: '1px solid var(--color-line)',
                        color: 'var(--color-ink-muted)',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {formatWhen(row.observed_at)}
                    </td>
                    <td
                      className="mono"
                      style={{
                        padding: '10px 16px',
                        borderBottom: '1px solid var(--color-line)',
                        color:
                          row.drift_fraction > 0.5
                            ? 'var(--color-risk-high)'
                            : 'var(--color-ink)',
                      }}
                    >
                      {row.drift_fraction.toFixed(2)}
                    </td>
                    <td
                      className="mono"
                      style={{
                        padding: '10px 16px',
                        borderBottom: '1px solid var(--color-line)',
                        color:
                          row.performance < 0.7 ? 'var(--color-risk-high)' : 'var(--color-ink)',
                      }}
                    >
                      {row.performance.toFixed(2)}
                    </td>
                    <td
                      className="mono"
                      style={{
                        padding: '10px 16px',
                        borderBottom: '1px solid var(--color-line)',
                        color: 'var(--color-ink-faint)',
                        fontSize: 12,
                      }}
                    >
                      {row.source}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section>
        <h2 className="label" style={{ marginBottom: 12 }}>
          Decisions for this domain
        </h2>
        {domainActivity.length === 0 ? (
          <EmptyState
            title="No decisions recorded"
            body="Decisions appear once the agent evaluates this domain, either on its schedule or via Evaluate now."
          />
        ) : (
          <div className="card">
            {domainActivity.map((entry, index) => (
              <div
                key={entry.id}
                style={{
                  padding: '12px 16px',
                  borderBottom:
                    index === domainActivity.length - 1
                      ? 'none'
                      : '1px solid var(--color-line)',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 14,
                  flexWrap: 'wrap',
                }}
              >
                <span
                  className="mono"
                  style={{
                    fontSize: 12,
                    color: 'var(--color-ink-faint)',
                    minWidth: 150,
                  }}
                >
                  {formatWhen(entry.created_at)}
                </span>
                <ActionTag action={entry.action} />
                <RiskPill level={entry.risk_level} />
                <span
                  className="mono"
                  style={{ fontSize: 11, color: 'var(--color-ink-faint)' }}
                >
                  {entry.status}
                </span>
              </div>
            ))}
          </div>
        )}
      </section>
    </>
  )
}
