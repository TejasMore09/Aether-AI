import Link from 'next/link'

import { api, type Approval, type AuditEntry, type UsageReport } from '@/lib/api'
import {
  ActionTag,
  EmptyState,
  ErrorNote,
  PageHeader,
  RiskPill,
  Stat,
  formatUsd,
  formatWhen,
} from '@/components/ui'

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
      <PageHeader
        title="Overview"
        subtitle="What your Nano agent has decided, and what needs you."
      />

      {firstError ? (
        <div style={{ marginBottom: 24 }}>
          <ErrorNote message={firstError.message} />
        </div>
      ) : null}

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(210px, 1fr))',
          gap: 16,
          marginBottom: 36,
        }}
      >
        <Stat
          label="Awaiting your decision"
          value={String(pending.length)}
          hint={pending.length ? 'Review in Approvals' : 'Nothing gated right now'}
          tone={pending.length ? 'high' : 'plain'}
        />
        <Stat
          label="Exposure if unaddressed"
          value={formatUsd(exposure)}
          hint="Sum of estimated daily loss"
          tone={exposure > 0 ? 'high' : 'plain'}
        />
        <Stat
          label="AI spend this month"
          value={usage.ok ? formatUsd(usage.data.month_spend_usd) : '—'}
          hint={
            usage.ok
              ? `of ${formatUsd(usage.data.monthly_budget_usd)} budget`
              : 'Unavailable'
          }
          tone="accent"
        />
      </div>

      <section>
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'baseline',
            marginBottom: 12,
          }}
        >
          <h2 className="label">Recent agent activity</h2>
          <Link href="/activity" className="mono" style={{ fontSize: 11, color: 'var(--color-accent)' }}>
            VIEW ALL
          </Link>
        </div>

        {!activity.ok || activity.data.length === 0 ? (
          <EmptyState
            title="No activity yet"
            body="Once telemetry arrives and monitoring is enabled, every decision your agent makes is recorded here."
          />
        ) : (
          <div className="card" style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr>
                  {['When', 'Domain', 'Action', 'Risk', 'Triggered by'].map((h) => (
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
                {activity.data.map((entry) => (
                  <tr key={entry.id}>
                    <td
                      className="mono"
                      style={{
                        padding: '11px 16px',
                        borderBottom: '1px solid var(--color-line)',
                        color: 'var(--color-ink-muted)',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {formatWhen(entry.created_at)}
                    </td>
                    <td style={{ padding: '11px 16px', borderBottom: '1px solid var(--color-line)' }}>
                      <Link href={`/domains/${entry.domain}`} style={{ color: 'var(--color-ink)' }}>
                        {entry.domain}
                      </Link>
                    </td>
                    <td style={{ padding: '11px 16px', borderBottom: '1px solid var(--color-line)' }}>
                      <ActionTag action={entry.action} />
                    </td>
                    <td style={{ padding: '11px 16px', borderBottom: '1px solid var(--color-line)' }}>
                      <RiskPill level={entry.risk_level} />
                    </td>
                    <td
                      className="mono"
                      style={{
                        padding: '11px 16px',
                        borderBottom: '1px solid var(--color-line)',
                        color: 'var(--color-ink-faint)',
                        fontSize: 12,
                      }}
                    >
                      {entry.triggered_by}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  )
}
