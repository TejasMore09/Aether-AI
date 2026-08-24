import { api, type UsageReport } from '@/lib/api'
import { EmptyState, ErrorNote, PageHeader, Stat, formatUsd } from '@/components/ui'

export default async function UsagePage() {
  const usage = await api.runtime<UsageReport>('/v1/usage/llm')

  if (!usage.ok) {
    return (
      <>
        <PageHeader title="AI Usage" />
        <ErrorNote message={usage.message} />
      </>
    )
  }

  const { month_spend_usd, monthly_budget_usd, budget_remaining_usd, by_purpose } = usage.data
  const usedPct =
    monthly_budget_usd > 0
      ? Math.min(100, (month_spend_usd / monthly_budget_usd) * 100)
      : 0
  const purposes = Object.entries(by_purpose)

  return (
    <>
      <PageHeader
        title="AI Usage"
        subtitle="What your agent's analysis costs, metered to your organization alone."
      />

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
          gap: 16,
          marginBottom: 28,
        }}
      >
        <Stat
          label="Spent this month"
          value={formatUsd(month_spend_usd)}
          tone="accent"
          hint={`${usedPct.toFixed(1)}% of budget`}
        />
        <Stat label="Monthly budget" value={formatUsd(monthly_budget_usd)} />
        <Stat
          label="Remaining"
          value={formatUsd(budget_remaining_usd)}
          tone={budget_remaining_usd === 0 ? 'high' : 'plain'}
          hint={
            budget_remaining_usd === 0
              ? 'Analysis falls back to local summaries'
              : undefined
          }
        />
      </div>

      <div className="card" style={{ padding: 20, marginBottom: 32 }}>
        <div className="label">Budget consumed</div>
        <div
          style={{
            height: 8,
            background: 'var(--color-canvas)',
            border: '1px solid var(--color-line)',
            marginTop: 12,
          }}
        >
          <div
            style={{
              width: `${usedPct}%`,
              height: '100%',
              background:
                usedPct > 90 ? 'var(--color-risk-high)' : 'var(--color-accent)',
            }}
          />
        </div>
        <p style={{ fontSize: 12, color: 'var(--color-ink-faint)', marginTop: 10 }}>
          When the budget is exhausted, your agent keeps working — diagnoses are generated
          locally from the numbers instead of by the model, and are labelled as such.
        </p>
      </div>

      <section>
        <h2 className="label" style={{ marginBottom: 12 }}>
          By purpose
        </h2>
        {purposes.length === 0 ? (
          <EmptyState
            title="No AI usage yet"
            body="Your agent calls a model only to explain a gated decision. Until one is gated, this stays at zero."
          />
        ) : (
          <div className="card" style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr>
                  {['Purpose', 'Calls', 'Tokens', 'Cost'].map((h) => (
                    <th
                      key={h}
                      className="label"
                      style={{
                        textAlign: 'left',
                        padding: '11px 16px',
                        borderBottom: '1px solid var(--color-line)',
                        background: 'var(--color-surface-raised)',
                      }}
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {purposes.map(([purpose, agg]) => (
                  <tr key={purpose}>
                    <td
                      className="mono"
                      style={{ padding: '11px 16px', borderBottom: '1px solid var(--color-line)' }}
                    >
                      {purpose}
                    </td>
                    <td
                      className="mono"
                      style={{
                        padding: '11px 16px',
                        borderBottom: '1px solid var(--color-line)',
                        color: 'var(--color-ink-muted)',
                      }}
                    >
                      {agg.calls}
                    </td>
                    <td
                      className="mono"
                      style={{
                        padding: '11px 16px',
                        borderBottom: '1px solid var(--color-line)',
                        color: 'var(--color-ink-muted)',
                      }}
                    >
                      {agg.tokens.toLocaleString('en-US')}
                    </td>
                    <td
                      className="mono"
                      style={{ padding: '11px 16px', borderBottom: '1px solid var(--color-line)' }}
                    >
                      ${agg.cost_usd.toFixed(6)}
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
