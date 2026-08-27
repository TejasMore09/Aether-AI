import Link from 'next/link'

import {
  EmptyState,
  ErrorNote,
  Eyebrow,
  Figure,
  PageTitle,
  Panel,
  RiskPill,
  SectionTitle,
  usd,
  whenUTC,
} from '@/components/forge'
import { api, type Approval, type AuditEntry, type UsageReport } from '@/lib/api'

export default async function OverviewPage() {
  const [approvals, activity, usage] = await Promise.all([
    api.runtime<Approval[]>('/v1/approvals'),
    api.runtime<AuditEntry[]>('/v1/audit-logs?limit=8'),
    api.runtime<UsageReport>('/v1/usage/llm'),
  ])

  const pending = approvals.ok ? approvals.data : []
  const exposure = pending.reduce((sum, a) => sum + a.expected_loss_usd, 0)
  const firstError = [approvals, activity, usage].find((r) => !r.ok) as
    | { ok: false; message: string }
    | undefined

  return (
    <>
      <div className="mb-5">
        <Eyebrow>Aether Nano</Eyebrow>
      </div>

      <PageTitle
        title={
          pending.length > 0
            ? 'Your agent needs a decision from you.'
            : 'Everything is tracking normally.'
        }
        lede={
          pending.length > 0
            ? 'It has already done the analysis. What remains is the judgement call it will not make on its own.'
            : 'Your agent is watching, and will stop you only when something is worth your attention.'
        }
      />

      {firstError ? (
        <div className="mb-7">
          <ErrorNote message={firstError.message} />
        </div>
      ) : null}

      <div className="mb-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <Figure
          label="Awaiting your decision"
          value={String(pending.length)}
          note={pending.length ? 'Review in Approvals' : 'Nothing gated right now'}
          tone={pending.length ? 'risk' : 'plain'}
        />
        <Figure
          label="Exposure if unaddressed"
          value={usd(exposure, 0)}
          note="summed across gated decisions, per day"
          tone={exposure > 0 ? 'risk' : 'plain'}
        />
        <Figure
          label="AI spend this month"
          value={usage.ok ? usd(usage.data.month_spend_usd, 2) : '—'}
          note={usage.ok ? `of ${usd(usage.data.monthly_budget_usd, 0)} budget` : 'Unavailable'}
          tone="copper"
          gauge={
            usage.ok && usage.data.monthly_budget_usd > 0
              ? {
                  pct: (usage.data.month_spend_usd / usage.data.monthly_budget_usd) * 100,
                  tone: 'copper',
                }
              : undefined
          }
        />
      </div>

      <section>
        <div className="mb-4 flex items-baseline justify-between">
          <SectionTitle>Recent agent activity</SectionTitle>
          <Link
            href="/activity"
            className="text-[13px] transition-colors duration-200"
            style={{ color: 'var(--color-copper)' }}
          >
            View all
          </Link>
        </div>

        {!activity.ok || activity.data.length === 0 ? (
          <EmptyState
            title="Nothing recorded yet"
            body="Once telemetry arrives and monitoring is on, every decision your agent makes is written here permanently, with what triggered it."
          />
        ) : (
          <Panel className="!p-2">
            {activity.data.map((entry) => (
              <div
                key={entry.id}
                className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-4 rounded-[13px] px-4 py-[13px] sm:grid-cols-[150px_minmax(0,1fr)_auto_auto]"
              >
                <span
                  className="tnum text-[12.5px]"
                  style={{ color: 'var(--color-ink-faint)' }}
                >
                  {whenUTC(entry.created_at)}
                </span>
                <Link
                  href={`/domains/${entry.domain}`}
                  className="truncate text-[14px] font-medium transition-colors duration-200 hover:text-[var(--color-copper)]"
                >
                  {entry.action.replace(/_/g, ' ').toLowerCase()}
                  <span
                    className="ml-2 text-[13px] font-normal"
                    style={{ color: 'var(--color-ink-faint)' }}
                  >
                    {entry.domain}
                  </span>
                </Link>
                <RiskPill level={entry.risk_level} />
                <span
                  className="hidden text-[12px] sm:block"
                  style={{ color: 'var(--color-ink-faint)' }}
                >
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
