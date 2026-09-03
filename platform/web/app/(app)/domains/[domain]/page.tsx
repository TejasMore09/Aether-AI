import { notFound } from 'next/navigation'

import {
  Bezel,
  EmptyState,
  ErrorNote,
  Eyebrow,
  Figure,
  Gauge,
  PageTitle,
  Panel,
  RiskPill,
  SectionTitle,
  whenUTC,
} from '@/components/forge'
import {
  api,
  type AuditEntry,
  type DomainPack,
  type MetricSpec,
  type UsedBand,
  type ObservationRow,
} from '@/lib/api'

import { MonitoringControls, RunNow } from './Controls'
import { ReadingForm } from './ReadingForm'

const DOMAIN_PATTERN = /^[a-z0-9][a-z0-9_-]*$/

function fmt(value: number, unit: string): string {
  if (unit === 'ratio') return `${Math.round(value * 100)}%`
  if (unit === 'currency') return value.toLocaleString('en-US', { maximumFractionDigits: 0 })
  if (unit === 'days') return `${value}d`
  return String(value)
}

/**
 * Was this value outside the band the engine actually used?
 *
 * The band, not the pack's published default. Since sector bands landed, the
 * two are often different — a shop is judged against 18 days where the pack
 * says 45 — and marking a figure against a threshold that played no part in
 * the decision is how a page contradicts the verdict printed beside it.
 */
function breached(metric: MetricSpec, value: number, band?: UsedBand): boolean {
  const [min, max] = metric.healthy_range
  const ceiling = band ? band.good : max
  const floor = band ? band.good : min

  if (max !== null && max !== undefined) return value > (ceiling ?? max)
  if (min !== null && min !== undefined) return value < (floor ?? min)
  return false
}

/** Where a threshold came from, in words a customer can act on. */
function provenance(band: UsedBand | undefined, metric: MetricSpec): string {
  const [min, max] = metric.healthy_range
  if (!band) {
    return max !== null && max !== undefined
      ? `healthy below ${fmt(max, metric.unit)}`
      : min !== null && min !== undefined
        ? `healthy above ${fmt(min, metric.unit)}`
        : ''
  }
  const direction = max !== null && max !== undefined ? 'below' : 'above'
  const where = {
    pack: 'the general default',
    sector: 'normal for your industry',
    tenant: `your own normal, from ${band.readings} readings`,
  }[band.source]
  return `healthy ${direction} ${fmt(band.good, metric.unit)} — ${where}`
}

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

  const scored = pack?.metrics.filter((m) => m.direction !== 'neutral') ?? []
  const reported = latest ? scored.filter((m) => latest.metrics?.[m.key] !== undefined) : []

  return (
    <>
      <div className="mb-5">
        <Eyebrow>{pack ? `Pack v${pack.version}` : 'Raw signals'}</Eyebrow>
      </div>

      <PageTitle
        title={pack ? pack.label : domain}
        lede={pack?.summary}
        meta={
          pack
            ? `Reported in ${pack.metrics.length} metrics · expects a reading every ${Math.round(
                pack.reporting_window_hours / 24,
              )} days`
            : 'This domain reports pre-derived signals.'
        }
        action={<RunNow domain={domain} />}
      />

      {!observations.ok ? (
        <div className="mb-7">
          <ErrorNote message={observations.message} />
        </div>
      ) : null}

      <div className="mb-9 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Figure
          label="Health"
          value={latest ? `${Math.round(latest.performance * 100)}%` : '—'}
          note={latest ? whenUTC(latest.observed_at) : 'no accepted readings'}
          tone={latest && latest.performance < 0.6 ? 'risk' : 'plain'}
          gauge={
            latest
              ? {
                  pct: latest.performance * 100,
                  tone: latest.performance < 0.6 ? 'risk' : 'good',
                }
              : undefined
          }
        />
        <Figure
          label="Moved vs. baseline"
          value={latest ? `${Math.round(latest.drift_fraction * 100)}%` : '—'}
          note="share of metrics drifting"
          tone={latest && latest.drift_fraction > 0.4 ? 'risk' : 'plain'}
        />
        <Figure label="Accepted readings" value={String(accepted.length)} note="most recent 25" />
        <Figure
          label="Quarantined"
          value={String(quarantined.length)}
          note={quarantined.length ? 'excluded from decisions' : 'none rejected'}
          tone={quarantined.length ? 'risk' : 'plain'}
        />
      </div>

      {reported.length > 0 && latest ? (
        <section className="mb-9">
          <SectionTitle>Latest reading, metric by metric</SectionTitle>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {reported.map((metric) => {
              const value = latest.metrics[metric.key]
              const band = latest.bands?.[metric.key]
              const bad = breached(metric, value, band)
              return (
                <Bezel key={metric.key} radius={18} pad={4}>
                  <div className="px-5 py-4" title={metric.description}>
                    <span className="text-[12.5px]" style={{ color: 'var(--color-ink-soft)' }}>
                      {metric.label}
                    </span>
                    <div
                      data-figure
                      className="mt-2 text-[25px] font-bold leading-none tracking-[-0.03em]"
                      style={{ color: bad ? 'var(--color-risk)' : 'var(--color-ink)' }}
                    >
                      {fmt(value, metric.unit)}
                    </div>
                    <p
                      className="mt-2 text-[11.5px]"
                      style={{ color: 'var(--color-ink-faint)' }}
                      title={band?.basis ?? undefined}
                    >
                      {provenance(band, metric)}
                    </p>
                  </div>
                </Bezel>
              )
            })}
          </div>
        </section>
      ) : null}

      <div className="mb-9 grid gap-4 lg:grid-cols-[1.5fr_1fr]">
        {pack ? <ReadingForm domain={domain} pack={pack} bands={latest?.bands ?? {}} /> : <div />}
        <MonitoringControls domain={domain} />
      </div>

      {quarantined.length > 0 ? (
        <section className="mb-9">
          <SectionTitle>Rejected readings</SectionTitle>
          <p className="mb-4 max-w-[70ch] text-[13px]" style={{ color: 'var(--color-ink-soft)' }}>
            Kept, but excluded from every decision. A pattern here usually means a feed changed
            upstream rather than the business changing.
          </p>
          <Panel className="!p-2">
            {quarantined.map((row) => (
              <div key={row.id} className="rounded-[13px] px-4 py-3">
                <div className="mb-2 flex flex-wrap items-center gap-3">
                  <span className="tnum text-[11.5px]" style={{ color: 'var(--color-ink-faint)' }}>
                    {whenUTC(row.observed_at)}
                  </span>
                  <span
                    className="rounded-full px-[9px] py-[3px] text-[10px] font-bold"
                    style={{
                      color: 'var(--color-risk)',
                      background: 'var(--color-ground)',
                      boxShadow: 'var(--press-sm)',
                    }}
                  >
                    QUARANTINED
                  </span>
                  <span className="text-[11.5px]" style={{ color: 'var(--color-ink-faint)' }}>
                    via {row.source}
                  </span>
                </div>
                <ul className="list-disc pl-5">
                  {row.issues
                    .filter((i) => i.severity === 'error')
                    .map((issue, i) => (
                      <li
                        key={i}
                        className="mb-1 text-[13.5px]"
                        style={{ color: 'var(--color-ink-soft)' }}
                      >
                        {issue.message}
                      </li>
                    ))}
                </ul>
              </div>
            ))}
          </Panel>
        </section>
      ) : null}

      <section className="mb-9">
        <SectionTitle>Reading history</SectionTitle>
        {accepted.length === 0 ? (
          <EmptyState
            title="No accepted readings yet"
            body="Send one above, or point a connector at this domain&rsquo;s readings endpoint."
          />
        ) : (
          <Panel className="!p-2">
            {accepted.map((row) => (
              <div
                key={row.id}
                className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-4 rounded-[13px] px-4 py-3 sm:grid-cols-[150px_70px_70px_minmax(0,1fr)_auto]"
              >
                <span className="tnum text-[12.5px]" style={{ color: 'var(--color-ink-faint)' }}>
                  {whenUTC(row.observed_at)}
                </span>
                <span
                  className="tnum text-[14px] font-semibold"
                  style={{
                    color: row.performance < 0.6 ? 'var(--color-risk)' : 'var(--color-ink)',
                  }}
                >
                  {Math.round(row.performance * 100)}%
                </span>
                <span
                  className="tnum hidden text-[13px] sm:block"
                  style={{ color: 'var(--color-ink-soft)' }}
                >
                  {Math.round(row.drift_fraction * 100)}%
                </span>
                <span className="hidden sm:block">
                  <Gauge
                    pct={row.performance * 100}
                    tone={row.performance < 0.6 ? 'risk' : 'good'}
                  />
                </span>
                <span className="text-[11.5px]" style={{ color: 'var(--color-ink-faint)' }}>
                  {row.source}
                </span>
              </div>
            ))}
          </Panel>
        )}
      </section>

      <section>
        <SectionTitle>Decisions for this domain</SectionTitle>
        {domainActivity.length === 0 ? (
          <EmptyState
            title="No decisions recorded"
            body="Decisions appear once the agent evaluates this domain, on its schedule or via Run now."
          />
        ) : (
          <Panel className="!p-2">
            {domainActivity.map((entry) => (
              <div
                key={entry.id}
                className="flex flex-wrap items-center gap-4 rounded-[13px] px-4 py-3"
              >
                <span
                  className="tnum min-w-[150px] text-[12.5px]"
                  style={{ color: 'var(--color-ink-faint)' }}
                >
                  {whenUTC(entry.created_at)}
                </span>
                <span className="text-[14px] font-medium">
                  {entry.action.replace(/_/g, ' ').toLowerCase()}
                </span>
                <RiskPill level={entry.risk_level} />
                <span className="text-[12px]" style={{ color: 'var(--color-ink-faint)' }}>
                  {entry.status}
                </span>
              </div>
            ))}
          </Panel>
        )}
      </section>
    </>
  )
}
