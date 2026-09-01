import type { Tone } from '@/components/instrument'
import type { FleetRow } from '@/lib/api'

/**
 * What is wrong with a tenant, and how badly.
 *
 * This is the console's only piece of real judgement, so it is kept in one
 * place rather than spread across the pages that display it.
 *
 * The distinction that matters most is between an agent that has gone quiet
 * and a tenant that never started. A new organization with no data is not an
 * incident; putting it in the same bucket as a monitored agent that stopped
 * reporting is exactly how a real outage gets lost in a wall of noise.
 */

// Matches AETHER_LLM_MONTHLY_BUDGET_USD_PER_TENANT on the platform.
const BUDGET_USD = Number(process.env.AETHER_TENANT_BUDGET_USD ?? '5')

const SILENT_HOURS = 48

// One or two is a model that was not downloaded when a decision happened, and
// a backfill fixes it. A steady climb is a pipeline that stopped.
const UNINDEXED_LIMIT = 3

export type Signal = { label: string; tone: Tone }

export function signalsFor(row: FleetRow): Signal[] {
  const signals: Signal[] = []

  if (!row.is_active) return [{ label: 'deactivated', tone: 'plain' }]

  const everReported = row.observation_count > 0
  const hoursSilent = row.last_observation_at
    ? (Date.now() - new Date(row.last_observation_at).getTime()) / 3_600_000
    : Infinity

  if (everReported && hoursSilent > SILENT_HOURS) {
    const days = Math.round(hoursSilent / 24)
    signals.push({ label: days >= 1 ? `silent ${days}d` : 'silent', tone: 'critical' })
  }
  if (row.failed_notifications > 0) {
    signals.push({ label: `${row.failed_notifications} undelivered`, tone: 'critical' })
  }

  const quarantineRate = everReported ? row.quarantined_count / row.observation_count : 0
  if (quarantineRate > 0.2) {
    signals.push({ label: `${Math.round(quarantineRate * 100)}% quarantined`, tone: 'attention' })
  }
  if (row.pending_approvals > 0) {
    signals.push({ label: `${row.pending_approvals} awaiting`, tone: 'attention' })
  }
  if (BUDGET_USD > 0 && row.month_spend_usd >= BUDGET_USD * 0.9) {
    signals.push({ label: 'budget', tone: 'attention' })
  }
  // An agent that stopped remembering shows no error anywhere else. Its
  // explanations simply stop mentioning what this business decided before,
  // and the customer cannot tell, never having seen the version that works.
  if (row.unindexed_decisions >= UNINDEXED_LIMIT) {
    signals.push({ label: `${row.unindexed_decisions} unremembered`, tone: 'attention' })
  }

  if (signals.length === 0 && !everReported) {
    signals.push({ label: 'no data yet', tone: 'plain' })
  }
  return signals
}

const RANK: Record<Tone, number> = { critical: 0, breach: 1, attention: 2, ok: 3, plain: 4 }

export function worstTone(signals: Signal[]): Tone {
  return signals.reduce<Tone>((worst, s) => (RANK[s.tone] < RANK[worst] ? s.tone : worst), 'ok')
}

export function severity(tone: Tone): number {
  return RANK[tone]
}

export type EnrichedRow = { row: FleetRow; signals: Signal[]; tone: Tone }

export function enrich(rows: FleetRow[]): EnrichedRow[] {
  return rows
    .map((row) => {
      const signals = signalsFor(row)
      return { row, signals, tone: worstTone(signals) }
    })
    .sort((a, b) => {
      const bySeverity = severity(a.tone) - severity(b.tone)
      if (bySeverity !== 0) return bySeverity
      return a.row.name.localeCompare(b.row.name)
    })
}
