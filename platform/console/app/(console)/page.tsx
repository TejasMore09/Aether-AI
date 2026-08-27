import { Ago } from '@/components/Ago'
import {
  Empty,
  ErrorNote,
  PageHead,
  Panel,
  PanelHead,
  Stat,
  Tag,
  usd,
} from '@/components/instrument'
import { brain, type FleetRow } from '@/lib/api'
import { enrich } from '@/lib/signals'

import { FleetTable } from './FleetTable'

export const metadata = { title: 'Fleet · Aether Console' }

export default async function FleetPage() {
  const fleet = await brain<FleetRow[]>('/v1/fleet')

  if (!fleet.ok) {
    return (
      <>
        <PageHead title="Fleet" />
        <ErrorNote message={fleet.message} />
      </>
    )
  }

  const rows = fleet.data
  const enriched = enrich(rows)

  const critical = enriched.filter((e) => e.tone === 'critical').length
  const attention = enriched.filter((e) => e.tone === 'attention').length
  const reporting = rows.filter((r) => r.is_active && r.observation_count > 0).length
  const spend = rows.reduce((sum, r) => sum + r.month_spend_usd, 0)

  return (
    <>
      <PageHead
        title="Fleet"
        lede="Every tenant agent, worst first. Counts and timestamps only — reading what is actually inside an organization takes a break-glass grant, and tells them you did."
        aside={
          <Tag tone={critical > 0 ? 'critical' : attention > 0 ? 'attention' : 'ok'}>
            {critical > 0
              ? `${critical} critical`
              : attention > 0
                ? `${attention} need attention`
                : 'all clear'}
          </Tag>
        }
      />

      <Panel className="mb-5 grid grid-cols-2 divide-x md:grid-cols-4">
        <Stat label="Organizations" value={rows.length} />
        <Stat label="Reporting" value={reporting} tone={reporting > 0 ? 'ok' : 'plain'} />
        <Stat
          label="Need attention"
          value={critical + attention}
          tone={critical > 0 ? 'critical' : attention > 0 ? 'attention' : 'ok'}
        />
        <Stat label="AI spend, month" value={usd(spend, 2)} suffix="all tenants" />
      </Panel>

      <Panel>
        <PanelHead
          title="Tenants"
          aside={
            <span className="text-[11.5px]" style={{ color: 'var(--ink-faint)' }}>
              newest reading <Ago iso={newestReading(rows)} />
            </span>
          }
        />
        {rows.length === 0 ? (
          <Empty
            title="No organizations yet"
            body="Tenants appear here the moment they sign up, before they have sent any data."
          />
        ) : (
          <FleetTable rows={enriched} />
        )}
      </Panel>
    </>
  )
}

function newestReading(rows: FleetRow[]): string | null {
  const times = rows
    .map((r) => r.last_observation_at)
    .filter((t): t is string => t !== null)
    .sort()
  return times.length > 0 ? times[times.length - 1] : null
}
