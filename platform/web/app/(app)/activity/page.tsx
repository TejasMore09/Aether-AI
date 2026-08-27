import Link from 'next/link'

import {
  EmptyState,
  ErrorNote,
  Eyebrow,
  PageTitle,
  Panel,
  RiskPill,
  SectionTitle,
  whenUTC,
} from '@/components/forge'
import { api, type AuditEntry, type NotificationRow } from '@/lib/api'

const DELIVERY: Record<string, { label: string; tone: string }> = {
  sent: { label: 'Delivered', tone: 'var(--color-good)' },
  failed: { label: 'Delivery failed', tone: 'var(--color-risk)' },
  skipped_unconfigured: { label: 'Email not set up', tone: 'var(--color-ink-faint)' },
}

export default async function ActivityPage() {
  const [activity, notifications] = await Promise.all([
    api.runtime<AuditEntry[]>('/v1/audit-logs?limit=60'),
    api.runtime<NotificationRow[]>('/v1/notifications?limit=25'),
  ])

  return (
    <>
      <div className="mb-5">
        <Eyebrow>Permanent record</Eyebrow>
      </div>

      <PageTitle
        title="Activity"
        lede="Every decision your agent has made, and every notification sent about one. Entries are append-only — nothing here is edited or removed."
      />

      <section className="mb-11">
        <SectionTitle>Audit trail</SectionTitle>
        {!activity.ok ? (
          <ErrorNote message={activity.message} />
        ) : activity.data.length === 0 ? (
          <EmptyState
            title="Nothing recorded yet"
            body="Every evaluation your agent runs is written here permanently, with who or what triggered it."
          />
        ) : (
          <Panel className="!p-2">
            {activity.data.map((entry) => (
              <div
                key={entry.id}
                className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3 rounded-[13px] px-4 py-3 sm:grid-cols-[152px_minmax(0,1fr)_auto_120px_auto]"
              >
                <span className="tnum text-[12.5px]" style={{ color: 'var(--color-ink-faint)' }}>
                  {whenUTC(entry.created_at)}
                </span>
                <Link
                  href={`/domains/${entry.domain}`}
                  className="truncate text-[14px] font-medium transition-colors duration-200 hover:text-[var(--color-copper)]"
                >
                  {entry.action.replace(/_/g, ' ').toLowerCase()}
                </Link>
                <RiskPill level={entry.risk_level} />
                <span
                  className="hidden truncate text-[12px] sm:block"
                  style={{ color: 'var(--color-ink-faint)' }}
                  title={entry.triggered_by}
                >
                  {entry.triggered_by}
                </span>
                <span className="hidden text-[12px] sm:block" style={{ color: 'var(--color-ink-faint)' }}>
                  {entry.status}
                </span>
              </div>
            ))}
          </Panel>
        )}
      </section>

      <section>
        <SectionTitle>Notifications</SectionTitle>
        {!notifications.ok ? (
          <ErrorNote message={notifications.message} />
        ) : notifications.data.length === 0 ? (
          <EmptyState
            title="No notifications yet"
            body="When a decision is gated, every owner is emailed. Each attempt is recorded here — including ones that could not be sent."
          />
        ) : (
          <Panel className="!p-2">
            {notifications.data.map((row) => {
              const d = DELIVERY[row.status] ?? { label: row.status, tone: 'var(--color-ink-faint)' }
              return (
                <div
                  key={row.id}
                  className="flex flex-wrap items-center justify-between gap-4 rounded-[13px] px-4 py-3"
                >
                  <div className="min-w-0">
                    <p className="truncate text-[13.5px]">{row.subject || row.kind}</p>
                    <p className="tnum mt-1 text-[11.5px]" style={{ color: 'var(--color-ink-faint)' }}>
                      {row.recipient} · {whenUTC(row.created_at)}
                    </p>
                  </div>
                  <span className="text-[12px] font-medium" style={{ color: d.tone }}>
                    {d.label}
                  </span>
                </div>
              )
            })}
          </Panel>
        )}
      </section>
    </>
  )
}
