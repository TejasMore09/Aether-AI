import { EmptyState, ErrorNote, Eyebrow, Figure, PageTitle, money, usd } from '@/components/forge'
import { api, type Approval } from '@/lib/api'
import { readSession } from '@/lib/session'

import { ApprovalCard } from './ApprovalCard'

export default async function ApprovalsPage() {
  const [session, approvals] = await Promise.all([
    readSession(),
    api.runtime<Approval[]>('/v1/approvals'),
  ])

  if (!approvals.ok) {
    return (
      <>
        <PageTitle title="Approvals" />
        <ErrorNote message={approvals.message} />
      </>
    )
  }

  const pending = approvals.data
  const exposure = pending.reduce((sum, a) => sum + a.expected_loss, 0)
  // Every approval carries the tenant's currency; they cannot differ
  // within one business, so the first is the whole page's.
  const currency = pending[0]?.currency ?? 'USD'
  const canResolve = session?.role === 'owner'

  return (
    <>
      <div className="mb-5">
        <Eyebrow>Human in the loop</Eyebrow>
      </div>

      <PageTitle
        title={
          pending.length === 0
            ? 'Nothing is waiting on you.'
            : pending.length === 1
              ? 'One decision is waiting on you.'
              : `${pending.length} decisions are waiting on you.`
        }
        lede="Your agent will not take a high-risk action without a person agreeing to it. Each one below is held until you decide."
      />

      {pending.length > 0 ? (
        <div className="mb-9 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <Figure
            label="Total exposure"
            value={money(exposure, currency, 0)}
            note="per day, while these remain unresolved"
            tone="risk"
          />
          <Figure label="Awaiting decision" value={String(pending.length)} tone="copper" />
          <Figure
            label="Your role"
            value={session?.role ?? '—'}
            note={canResolve ? 'You can approve or reject' : 'View only'}
          />
        </div>
      ) : null}

      {pending.length === 0 ? (
        <EmptyState
          title="No decisions are gated right now"
          body="Your agent only stops for high-risk actions where the money at risk outweighs the cost of acting. When that happens the decision appears here with its reasoning, and every owner is emailed."
        />
      ) : (
        <div className="flex flex-col gap-5">
          {pending.map((approval) => (
            <ApprovalCard key={approval.id} approval={approval} canResolve={canResolve} />
          ))}
        </div>
      )}
    </>
  )
}
