import Link from 'next/link'

import { api, type AuditEntry, type NotificationRow } from '@/lib/api'
import {
  ActionTag,
  EmptyState,
  ErrorNote,
  PageHeader,
  RiskPill,
  formatWhen,
} from '@/components/ui'

const NOTIFICATION_STATUS_HINT: Record<string, string> = {
  sent: 'Delivered',
  failed: 'Delivery failed',
  skipped_unconfigured: 'Email not configured — nothing was sent',
}

export default async function ActivityPage() {
  const [activity, notifications] = await Promise.all([
    api.runtime<AuditEntry[]>('/v1/audit-logs?limit=60'),
    api.runtime<NotificationRow[]>('/v1/notifications?limit=25'),
  ])

  return (
    <>
      <PageHeader
        title="Activity"
        subtitle="The immutable record of every decision, and every notification sent about one."
      />

      <section style={{ marginBottom: 40 }}>
        <h2 className="label" style={{ marginBottom: 12 }}>
          Audit trail
        </h2>
        {!activity.ok ? (
          <ErrorNote message={activity.message} />
        ) : activity.data.length === 0 ? (
          <EmptyState
            title="Nothing recorded yet"
            body="Every evaluation your agent runs is written here permanently, with who or what triggered it."
          />
        ) : (
          <div className="card" style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr>
                  {['When', 'Domain', 'Action', 'Risk', 'Triggered by', 'Status'].map((h) => (
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
                        padding: '10px 16px',
                        borderBottom: '1px solid var(--color-line)',
                        color: 'var(--color-ink-muted)',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {formatWhen(entry.created_at)}
                    </td>
                    <td style={{ padding: '10px 16px', borderBottom: '1px solid var(--color-line)' }}>
                      <Link
                        href={`/domains/${entry.domain}`}
                        className="mono"
                        style={{ color: 'var(--color-ink)', fontSize: 12 }}
                      >
                        {entry.domain}
                      </Link>
                    </td>
                    <td style={{ padding: '10px 16px', borderBottom: '1px solid var(--color-line)' }}>
                      <ActionTag action={entry.action} />
                    </td>
                    <td style={{ padding: '10px 16px', borderBottom: '1px solid var(--color-line)' }}>
                      <RiskPill level={entry.risk_level} />
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
                      {entry.triggered_by}
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
                      {entry.status}
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
          Notifications
        </h2>
        {!notifications.ok ? (
          <ErrorNote message={notifications.message} />
        ) : notifications.data.length === 0 ? (
          <EmptyState
            title="No notifications yet"
            body="When a decision is gated, every owner is emailed. Each attempt is recorded here — including attempts that could not be sent."
          />
        ) : (
          <div className="card">
            {notifications.data.map((row, index) => (
              <div
                key={row.id}
                style={{
                  padding: '12px 16px',
                  borderBottom:
                    index === notifications.data.length - 1
                      ? 'none'
                      : '1px solid var(--color-line)',
                  display: 'flex',
                  justifyContent: 'space-between',
                  gap: 16,
                  flexWrap: 'wrap',
                }}
              >
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontSize: 13 }}>{row.subject || row.kind}</div>
                  <div
                    className="mono"
                    style={{ fontSize: 11, color: 'var(--color-ink-faint)', marginTop: 4 }}
                  >
                    {row.recipient} · {formatWhen(row.created_at)}
                  </div>
                </div>
                <span
                  className="mono"
                  style={{
                    fontSize: 10,
                    letterSpacing: '0.08em',
                    alignSelf: 'center',
                    color:
                      row.status === 'sent'
                        ? 'var(--color-risk-low)'
                        : row.status === 'failed'
                          ? 'var(--color-risk-high)'
                          : 'var(--color-ink-faint)',
                    whiteSpace: 'nowrap',
                  }}
                  title={NOTIFICATION_STATUS_HINT[row.status] ?? row.status}
                >
                  {(NOTIFICATION_STATUS_HINT[row.status] ?? row.status).toUpperCase()}
                </span>
              </div>
            ))}
          </div>
        )}
      </section>
    </>
  )
}
