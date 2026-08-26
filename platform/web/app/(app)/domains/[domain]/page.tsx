import { notFound } from 'next/navigation'

import {
  api,
  type AuditEntry,
  type DomainPack,
  type ObservationRow,
} from '@/lib/api'
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
import { ReadingForm } from './ReadingForm'

const DOMAIN_PATTERN = /^[a-z0-9][a-z0-9_-]*$/

export default async function DomainPage({
  params,
}: {
  params: Promise<{ domain: string }>
}) {
  const { domain } = await params
  if (!DOMAIN_PATTERN.test(domain)) notFound()

  const [observations, activity, catalogue] = await Promise.all([
    api.runtime<ObservationRow[]>(`/v1/domains/${domain}/observations?limit=25`),
    api.runtime<AuditEntry[]>('/v1/audit-logs?limit=50'),
    api.runtime<DomainPack[]>('/v1/catalogue'),
  ])

  const rows = observations.ok ? observations.data : []
  const accepted = rows.filter((r) => r.status === 'accepted')
  const quarantined = rows.filter((r) => r.status === 'quarantined')
  const latest = accepted[0]
  const pack = catalogue.ok ? catalogue.data.find((p) => p.key === domain) : undefined

  const domainActivity = activity.ok
    ? activity.data.filter((e) => e.domain === domain).slice(0, 8)
    : []

  return (
    <>
      <PageHeader
        title={pack ? pack.label : domain}
        subtitle={
          pack
            ? `Reported in ${pack.metrics.length} business metrics · expects a reading every ${Math.round(pack.reporting_window_hours / 24)} days`
            : 'No domain pack — this domain reports pre-derived signals.'
        }
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
          gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))',
          gap: 16,
          marginBottom: 32,
        }}
      >
        <Stat
          label="Health"
          value={latest ? `${Math.round(latest.performance * 100)}%` : '—'}
          hint={latest ? formatWhen(latest.observed_at) : 'no accepted readings'}
          tone={latest && latest.performance < 0.6 ? 'high' : 'plain'}
        />
        <Stat
          label="Moved vs. baseline"
          value={latest ? `${Math.round(latest.drift_fraction * 100)}%` : '—'}
          hint="share of metrics drifting"
          tone={latest && latest.drift_fraction > 0.4 ? 'high' : 'plain'}
        />
        <Stat label="Accepted readings" value={String(accepted.length)} hint="most recent 25" />
        <Stat
          label="Quarantined"
          value={String(quarantined.length)}
          hint={quarantined.length ? 'excluded from decisions' : 'none rejected'}
          tone={quarantined.length ? 'high' : 'plain'}
        />
      </div>

      {latest && pack ? <LatestMetrics pack={pack} row={latest} /> : null}

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: pack ? '1fr' : 'repeat(auto-fit, minmax(300px, 1fr))',
          gap: 16,
          marginBottom: 32,
        }}
      >
        {pack ? (
          <ReadingForm domain={domain} pack={pack} />
        ) : (
          <PushObservation domain={domain} />
        )}
        <MonitoringControls domain={domain} />
      </div>

      {quarantined.length > 0 ? (
        <section style={{ marginBottom: 32 }}>
          <h2 className="label" style={{ marginBottom: 12 }}>
            Rejected readings
          </h2>
          <p
            style={{
              fontSize: 13,
              color: 'var(--color-ink-muted)',
              margin: '0 0 12px',
              maxWidth: '72ch',
            }}
          >
            These were kept but excluded from every decision. A repeating pattern here
            usually means a feed changed upstream rather than the business changing.
          </p>
          <div className="card">
            {quarantined.map((row, index) => (
              <div
                key={row.id}
                style={{
                  padding: '14px 18px',
                  borderBottom:
                    index === quarantined.length - 1 ? 'none' : '1px solid var(--color-line)',
                }}
              >
                <div
                  style={{
                    display: 'flex',
                    gap: 12,
                    alignItems: 'center',
                    flexWrap: 'wrap',
                    marginBottom: 8,
                  }}
                >
                  <span
                    className="mono"
                    style={{ fontSize: 11, color: 'var(--color-ink-faint)' }}
                  >
                    {formatWhen(row.observed_at)}
                  </span>
                  <span
                    className="mono"
                    style={{
                      fontSize: 9,
                      letterSpacing: '0.1em',
                      padding: '2px 7px',
                      color: 'var(--color-risk-high)',
                      background: 'var(--color-risk-high-dim)',
                    }}
                  >
                    QUARANTINED
                  </span>
                  <span
                    className="mono"
                    style={{ fontSize: 11, color: 'var(--color-ink-faint)' }}
                  >
                    via {row.source}
                  </span>
                </div>
                <ul style={{ margin: 0, paddingLeft: 18 }}>
                  {row.issues
                    .filter((i) => i.severity === 'error')
                    .map((issue, i) => (
                      <li
                        key={i}
                        style={{
                          fontSize: 13,
                          color: 'var(--color-ink)',
                          marginBottom: 3,
                        }}
                      >
                        {issue.message}
                      </li>
                    ))}
                </ul>
              </div>
            ))}
          </div>
        </section>
      ) : null}

      <section style={{ marginBottom: 32 }}>
        <h2 className="label" style={{ marginBottom: 12 }}>
          Reading history
        </h2>
        {accepted.length === 0 ? (
          <EmptyState
            title="No accepted readings yet"
            body="Send one above, or point a connector at this domain's readings endpoint."
          />
        ) : (
          <div className="card" style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr>
                  {['Observed', 'Health', 'Moved', ...headerMetrics(pack), 'Source'].map((h) => (
                    <th
                      key={h}
                      className="label"
                      style={{
                        textAlign: 'left',
                        padding: '11px 14px',
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
                {accepted.map((row) => (
                  <tr key={row.id}>
                    <td style={cell({ muted: true, nowrap: true })}>
                      {formatWhen(row.observed_at)}
                    </td>
                    <td style={cell({ danger: row.performance < 0.6 })}>
                      {Math.round(row.performance * 100)}%
                    </td>
                    <td style={cell({ danger: row.drift_fraction > 0.4 })}>
                      {Math.round(row.drift_fraction * 100)}%
                    </td>
                    {keyMetrics(pack).map((m) => (
                      <td key={m.key} style={cell({})}>
                        {row.metrics?.[m.key] !== undefined
                          ? formatMetric(row.metrics[m.key], m.unit)
                          : '—'}
                      </td>
                    ))}
                    <td style={cell({ muted: true })}>{row.source}</td>
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
            body="Decisions appear once the agent evaluates this domain, on its schedule or via Evaluate now."
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
                  style={{ fontSize: 12, color: 'var(--color-ink-faint)', minWidth: 150 }}
                >
                  {formatWhen(entry.created_at)}
                </span>
                <ActionTag action={entry.action} />
                <RiskPill level={entry.risk_level} />
                <span className="mono" style={{ fontSize: 11, color: 'var(--color-ink-faint)' }}>
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

/** The first few scored metrics, so the history table stays readable. */
function keyMetrics(pack: DomainPack | undefined) {
  if (!pack) return []
  return pack.metrics.filter((m) => m.direction !== 'neutral').slice(0, 3)
}

function headerMetrics(pack: DomainPack | undefined): string[] {
  return keyMetrics(pack).map((m) => m.label)
}

function formatMetric(value: number, unit: string): string {
  if (unit === 'ratio') return `${Math.round(value * 100)}%`
  if (unit === 'currency') return value.toLocaleString('en-US', { maximumFractionDigits: 0 })
  if (unit === 'days') return `${value}d`
  return String(value)
}

function cell(opts: {
  muted?: boolean
  danger?: boolean
  nowrap?: boolean
}): React.CSSProperties {
  return {
    padding: '10px 14px',
    borderBottom: '1px solid var(--color-line)',
    fontFamily: 'var(--font-mono)',
    fontVariantNumeric: 'tabular-nums',
    whiteSpace: opts.nowrap ? 'nowrap' : undefined,
    color: opts.danger
      ? 'var(--color-risk-high)'
      : opts.muted
        ? 'var(--color-ink-faint)'
        : 'var(--color-ink)',
  }
}

/** Per-metric health for the newest accepted reading — where the problem is. */
function LatestMetrics({ pack, row }: { pack: DomainPack; row: ObservationRow }) {
  const scored = pack.metrics.filter((m) => m.direction !== 'neutral')
  const reported = scored.filter((m) => row.metrics?.[m.key] !== undefined)
  if (reported.length === 0) return null

  return (
    <section style={{ marginBottom: 32 }}>
      <h2 className="label" style={{ marginBottom: 12 }}>
        Latest reading, metric by metric
      </h2>
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
          gap: 12,
        }}
      >
        {reported.map((metric) => {
          const value = row.metrics[metric.key]
          const [min, max] = metric.healthy_range
          const breached =
            (max !== null && max !== undefined && value > max) ||
            (min !== null && min !== undefined && value < min)
          return (
            <div
              key={metric.key}
              className="card"
              style={{
                padding: 16,
                borderLeft: `2px solid ${
                  breached ? 'var(--color-risk-high)' : 'var(--color-line)'
                }`,
              }}
              title={metric.description}
            >
              <div className="label">{metric.label}</div>
              <div
                className="mono"
                style={{
                  fontSize: 21,
                  marginTop: 8,
                  color: breached ? 'var(--color-risk-high)' : 'var(--color-ink)',
                }}
              >
                {formatMetric(value, metric.unit)}
              </div>
              <div
                style={{ fontSize: 11, color: 'var(--color-ink-faint)', marginTop: 5 }}
              >
                {max !== null && max !== undefined
                  ? `healthy below ${formatMetric(max, metric.unit)}`
                  : min !== null && min !== undefined
                    ? `healthy above ${formatMetric(min, metric.unit)}`
                    : ''}
              </div>
            </div>
          )
        })}
      </div>
    </section>
  )
}
