import {
  EmptyState,
  ErrorNote,
  Eyebrow,
  Figure,
  PageTitle,
  Panel,
  SectionTitle,
  usd,
} from '@/components/forge'
import { api, type UsageReport } from '@/lib/api'

export default async function UsagePage() {
  const usage = await api.runtime<UsageReport>('/v1/usage/llm')

  if (!usage.ok) {
    return (
      <>
        <PageTitle title="AI usage" />
        <ErrorNote message={usage.message} />
      </>
    )
  }

  const { month_spend_usd, monthly_budget_usd, budget_remaining_usd, by_purpose } = usage.data
  const usedPct = monthly_budget_usd > 0 ? (month_spend_usd / monthly_budget_usd) * 100 : 0
  const purposes = Object.entries(by_purpose)
  const exhausted = budget_remaining_usd <= 0

  return (
    <>
      <div className="mb-5">
        <Eyebrow>Metered to your organization alone</Eyebrow>
      </div>

      <PageTitle
        title="AI usage"
        lede="What your agent's analysis costs. Your budget is yours — no other organization can spend against it, and running out never stops the agent working."
      />

      <div className="mb-9 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <Figure
          label="Spent this month"
          value={usd(month_spend_usd, 4)}
          note={`${usedPct.toFixed(1)}% of budget`}
          tone="copper"
          gauge={{ pct: usedPct, tone: usedPct > 90 ? 'risk' : 'copper' }}
        />
        <Figure label="Monthly budget" value={usd(monthly_budget_usd, 2)} />
        <Figure
          label="Remaining"
          value={usd(Math.max(0, budget_remaining_usd), 4)}
          note={exhausted ? 'Explanations fall back to local summaries' : undefined}
          tone={exhausted ? 'risk' : 'plain'}
        />
      </div>

      <section>
        <SectionTitle>By purpose</SectionTitle>
        {purposes.length === 0 ? (
          <EmptyState
            title="No AI usage yet"
            body="Your agent calls a model only to explain a decision it has gated. Until one is gated, this stays at zero."
          />
        ) : (
          <Panel className="!p-2">
            {purposes.map(([purpose, agg]) => (
              <div
                key={purpose}
                className="grid grid-cols-[minmax(0,1fr)_auto_auto] items-center gap-6 rounded-[13px] px-4 py-[13px]"
              >
                <span className="text-[14px] font-medium">{purpose}</span>
                <span className="tnum text-[13px]" style={{ color: 'var(--color-ink-faint)' }}>
                  {agg.calls} call{agg.calls === 1 ? '' : 's'} · {agg.tokens.toLocaleString('en-US')} tokens
                </span>
                <span className="tnum text-[14px] font-semibold">{usd(agg.cost_usd, 6)}</span>
              </div>
            ))}
          </Panel>
        )}
      </section>
    </>
  )
}
