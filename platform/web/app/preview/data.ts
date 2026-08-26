/**
 * Mock data for the design preview only — no API calls, no real tenant data.
 * Numbers are deliberately organic rather than round, and the business is a
 * plausible SME rather than a placeholder like "Acme Corp".
 */

export const business = {
  name: 'Kestrel Joinery',
  domain: 'receivables',
  domainLabel: 'Cash & Receivables',
  summary:
    'How much the business is owed, how late it is arriving, and what the delay costs.',
  reportedAt: '14 Aug 2026',
  reportingWindowDays: 8,
}

export type Metric = {
  key: string
  label: string
  value: string
  raw: number
  healthy: string
  health: number // 0..1
  breached: boolean
  note: string
}

export const metrics: Metric[] = [
  {
    key: 'dso_days',
    label: 'Days sales outstanding',
    value: '71',
    raw: 71,
    healthy: 'under 45 days',
    health: 0.42,
    breached: true,
    note: 'Up from 46 days across the last four reports.',
  },
  {
    key: 'overdue_ratio',
    label: 'Overdue share of the book',
    value: '34%',
    raw: 0.34,
    healthy: 'under 15%',
    health: 0.24,
    breached: true,
    note: 'Concentrated in eleven accounts on 30-day terms.',
  },
  {
    key: 'avg_days_past_due',
    label: 'Average days past due',
    value: '38',
    raw: 38,
    healthy: 'under 15 days',
    health: 0.49,
    breached: true,
    note: 'Two invoices have crossed 90 days.',
  },
  {
    key: 'collection_effectiveness',
    label: 'Collection effectiveness',
    value: '61%',
    raw: 0.61,
    healthy: 'above 80%',
    health: 0.24,
    breached: true,
    note: 'Collection effort has not kept pace with billing.',
  },
  {
    key: 'top5_concentration',
    label: 'Top-5 customer concentration',
    value: '52%',
    raw: 0.52,
    healthy: 'under 45%',
    health: 0.77,
    breached: true,
    note: 'Hartwell Contracts alone is 23% of the book.',
  },
  {
    key: 'disputed_ratio',
    label: 'Disputed share of the book',
    value: '4%',
    raw: 0.04,
    healthy: 'under 3%',
    health: 0.92,
    breached: false,
    note: 'One disputed fit-out invoice, unresolved since June.',
  },
]

export const decision = {
  action: 'Escalate collections',
  risk: 'HIGH' as const,
  exposurePerDay: 3874.56,
  arTotal: 284_600,
  overdueShare: 0.34,
  interventionCost: 400,
  paybackDays: 0.1,
  reason:
    '$3,874.56 a day at risk — 34% of 284,600 outstanding, carried at 15% a year — against a $400.00 one-off cost to act.',
  diagnosis:
    'Receivables have slipped materially since the last report. Days sales outstanding moved from 46 to 71, and the overdue share of the book nearly doubled to 34%. This is not a broad decline: eleven accounts on 30-day terms account for most of the movement, and Hartwell Contracts is 23% of the book on its own. Two invoices have now crossed 90 days, which is where recovery rates start to fall sharply.\n\nThe practical step this week is to chase the eleven overdue accounts largest-first, and to pause further credit to the two accounts past 90 days until they settle.',
  diagnosisSource: 'AI analysis' as const,
}

export const history = [
  { date: '14 Aug', dso: 71, overdue: 0.34, health: 0.31 },
  { date: '07 Aug', dso: 63, overdue: 0.29, health: 0.42 },
  { date: '31 Jul', dso: 55, overdue: 0.21, health: 0.58 },
  { date: '24 Jul', dso: 49, overdue: 0.17, health: 0.74 },
  { date: '17 Jul', dso: 46, overdue: 0.14, health: 0.88 },
]

export const quarantined = {
  date: '10 Aug',
  source: 'Xero sync',
  message:
    'Overdue share of the book came through as 46 ratio, above the possible maximum of 1. This usually means a unit mismatch upstream.',
}

export const health = 0.31
