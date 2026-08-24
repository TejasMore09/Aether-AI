import { api, type Approval } from '@/lib/api'
import { readSession } from '@/lib/session'
import { EmptyState, ErrorNote, PageHeader, formatUsd } from '@/components/ui'

import { ApprovalCard } from './ApprovalCard'

export default async function ApprovalsPage() {
  const [session, approvals] = await Promise.all([
    readSession(),
    api.runtime<Approval[]>('/v1/approvals'),
  ])

  if (!approvals.ok) {
    return (
      <>
        <PageHeader title="Approvals" />
        <ErrorNote message={approvals.message} />
      </>
    )
  }

  const pending = approvals.data
  const exposure = pending.reduce((sum, a) => sum + a.expected_loss_usd, 0)
  const canResolve = session?.role === 'owner'

  return (
    <>
      <PageHeader
        title="Approvals"
        subtitle="High-risk actions your agent will not take without a human decision."
        right={
          pending.length > 0 ? (
            <div style={{ textAlign: 'right' }}>
              <div className="label">Total exposure</div>
              <div
                className="mono"
                style={{ fontSize: 18, color: 'var(--color-risk-high)', marginTop: 4 }}
              >
                {formatUsd(exposure)}
              </div>
            </div>
          ) : undefined
        }
      />

      {pending.length === 0 ? (
        <EmptyState
          title="Nothing awaiting a decision"
          body="Your agent gates only high-risk actions where the estimated loss outweighs the cost of acting. When that happens, the decision and its diagnosis appear here — and every owner gets an email."
        />
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
          {pending.map((approval) => (
            <ApprovalCard key={approval.id} approval={approval} canResolve={canResolve} />
          ))}
        </div>
      )}
    </>
  )
}
