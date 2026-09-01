import Link from 'next/link'

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
  whenUTC,
} from '@/components/instrument'
import {
  brain,
  type FleetRow,
  type Grant,
  type TenantAuditEntry,
  type TenantObservation,
} from '@/lib/api'
import { readSession } from '@/lib/session'
import { signalsFor } from '@/lib/signals'

import { BreakGlass } from './BreakGlass'

export const metadata = { title: 'Tenant · Aether Console' }

export default async function TenantPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  const session = await readSession()

  const [fleet, grants] = await Promise.all([
    brain<FleetRow[]>('/v1/fleet'),
    brain<Grant[]>('/v1/grants'),
  ])

  if (!fleet.ok) {
    return (
      <>
        <PageHead title="Tenant" />
        <ErrorNote message={fleet.message} />
      </>
    )
  }

  const row = fleet.data.find((r) => r.tenant_id === id)
  if (!row) {
    return (
      <>
        <PageHead title="Tenant" />
        <ErrorNote message="No organization with that id." />
      </>
    )
  }

  const signals = signalsFor(row)
  const history = grants.ok ? grants.data.filter((g) => g.tenant_id === id) : []
  const myLiveGrant = history.find((g) => g.live && g.admin_email === session?.email)

  // Only fetched once a grant exists. Without one the brain refuses anyway;
  // asking and rendering the 403 would just be a slower way to say no.
  const [observations, audit] = myLiveGrant
    ? await Promise.all([
        brain<TenantObservation[]>(`/v1/tenants/${id}/observations?limit=25`),
        brain<TenantAuditEntry[]>(`/v1/tenants/${id}/audit-logs?limit=40`),
      ])
    : [null, null]

  return (
    <>
      <PageHead
        title={row.name}
        lede={`${row.slug} · created ${whenUTC(row.created_at)}`}
        aside={
          <div className="flex flex-wrap gap-[5px]">
            {signals.map((s) => (
              <Tag key={s.label} tone={s.tone}>
                {s.label}
              </Tag>
            ))}
          </div>
        }
      />

      <Panel className="mb-5 grid grid-cols-2 divide-x md:grid-cols-6">
        <Stat label="Readings" value={row.observation_count} />
        <Stat
          label="Quarantined"
          value={row.quarantined_count}
          tone={row.quarantined_count > 0 ? 'attention' : 'plain'}
        />
        <Stat label="Domains" value={row.configured_domains} />
        <Stat label="Awaiting" value={row.pending_approvals} />
        <Stat label="Active keys" value={row.active_keys} />
        <Stat label="Spend" value={usd(row.month_spend_usd, 2)} />
      </Panel>

      {/* ── What their agent remembers, and never what it is ──────────── */}
      <Panel className="mb-5">
        <PanelHead
          title="Agent memory"
          aside={
            <span className="text-[11.5px]" style={{ color: 'var(--ink-faint)' }}>
              last learned <Ago iso={row.last_knowledge_at} />
            </span>
          }
        />
        <div className="grid grid-cols-2 divide-x">
          <Stat label="Remembered" value={row.knowledge_chunks} />
          <Stat
            label="Unremembered decisions"
            value={row.unindexed_decisions}
            tone={row.unindexed_decisions >= 3 ? 'attention' : 'plain'}
          />
        </div>
        <p className="px-4 pb-4 text-[12px]" style={{ color: 'var(--ink-faint)' }}>
          Counts only. What this agent remembers is its owners&rsquo; own decisions, in
          plain sentences — reading one is tenant data and needs a grant, like their
          readings. A climbing unremembered count means indexing has stopped, which
          shows up nowhere else: their explanations just quietly stop referring to
          what they decided before.
        </p>
      </Panel>

      {/* ── Access ─────────────────────────────────────────────────────── */}
      <Panel className="mb-5">
        <PanelHead
          title={myLiveGrant ? 'Access open' : 'Break-glass access'}
          aside={
            <span className="text-[11.5px]" style={{ color: 'var(--ink-faint)' }}>
              last reading <Ago iso={row.last_observation_at} />
            </span>
          }
        />
        {myLiveGrant ? (
          <div className="px-4 py-4">
            <p className="text-[13px]" style={{ color: 'var(--ink-soft)' }}>
              You opened access {whenUTC(myLiveGrant.granted_at)} —{' '}
              {myLiveGrant.scope === 'operate' ? 'read + operate' : 'read only'}. End it from
              the bar above when you are done; it also ends by itself at{' '}
              <span className="tnum">{whenUTC(myLiveGrant.expires_at)}</span>.
            </p>
            <p className="mt-2 text-[13px]">&ldquo;{myLiveGrant.reason}&rdquo;</p>
          </div>
        ) : (
          <BreakGlass
            tenantId={row.tenant_id}
            tenantName={row.name}
            canOpen={session?.role !== 'observer'}
          />
        )}
      </Panel>

      {/* ── Their data, only once granted ──────────────────────────────── */}
      {myLiveGrant && (
        <>
          <Panel className="mb-5">
            <PanelHead title="Recent readings" />
            {!observations?.ok ? (
              <ErrorNote message={observations?.message ?? 'Could not load readings.'} />
            ) : observations.data.length === 0 ? (
              <Empty
                title="No readings"
                body="This organization has not pushed any telemetry yet."
              />
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[720px] border-collapse text-[12.5px]">
                  <thead>
                    <tr
                      className="text-left text-[10.5px] uppercase tracking-[0.1em]"
                      style={{ color: 'var(--ink-faint)' }}
                    >
                      <th className="px-4 py-[9px] font-medium" style={{ background: 'var(--steel-850)' }}>
                        When
                      </th>
                      <th className="px-4 py-[9px] font-medium" style={{ background: 'var(--steel-850)' }}>
                        Domain
                      </th>
                      <th className="px-4 py-[9px] font-medium" style={{ background: 'var(--steel-850)' }}>
                        Source
                      </th>
                      <th className="px-4 py-[9px] font-medium" style={{ background: 'var(--steel-850)' }}>
                        Metrics
                      </th>
                      <th className="px-4 py-[9px] font-medium" style={{ background: 'var(--steel-850)' }}>
                        Status
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {observations.data.map((o) => (
                      <tr key={o.id} className="border-t" style={{ borderColor: 'var(--line)' }}>
                        <td className="tnum px-4 py-[9px]" style={{ color: 'var(--ink-soft)' }}>
                          {whenUTC(o.observed_at)}
                        </td>
                        <td className="px-4 py-[9px]">{o.domain}</td>
                        <td className="mono px-4 py-[9px]" style={{ color: 'var(--ink-faint)' }}>
                          {o.source}
                        </td>
                        <td className="mono px-4 py-[9px] text-[11.5px]">
                          {Object.entries(o.metrics)
                            .map(([k, v]) => `${k}=${v}`)
                            .join('  ')}
                        </td>
                        <td className="px-4 py-[9px]">
                          <Tag tone={o.status === 'quarantined' ? 'attention' : 'ok'}>
                            {o.status}
                          </Tag>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Panel>

          <Panel className="mb-5">
            <PanelHead title="Their audit trail" />
            {!audit?.ok ? (
              <ErrorNote message={audit?.message ?? 'Could not load the audit trail.'} />
            ) : audit.data.length === 0 ? (
              <Empty title="Nothing recorded" body="This agent has not made a decision yet." />
            ) : (
              <ul>
                {audit.data.map((e) => (
                  <li
                    key={e.id}
                    className="flex flex-wrap items-center gap-3 border-t px-4 py-[9px] text-[12.5px]"
                    style={{ borderColor: 'var(--line)' }}
                  >
                    <span className="tnum w-[125px] shrink-0" style={{ color: 'var(--ink-faint)' }}>
                      {whenUTC(e.created_at)}
                    </span>
                    <span className="w-[190px] shrink-0">{e.action.replace(/_/g, ' ')}</span>
                    <span className="w-[110px] shrink-0" style={{ color: 'var(--ink-faint)' }}>
                      {e.domain}
                    </span>
                    <Tag
                      tone={
                        e.risk_level === 'HIGH'
                          ? 'critical'
                          : e.risk_level === 'MEDIUM'
                            ? 'attention'
                            : 'plain'
                      }
                    >
                      {e.risk_level}
                    </Tag>
                    <span className="min-w-0 flex-1 truncate" style={{ color: 'var(--ink-faint)' }}>
                      {e.triggered_by}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </Panel>
        </>
      )}

      {/* ── Who has looked, ever ───────────────────────────────────────── */}
      <Panel>
        <PanelHead title="Access history" />
        {history.length === 0 ? (
          <Empty
            title="No staff has ever opened this organization"
            body="Every grant, past and present, is listed here — and mirrored into the customer's own audit log."
          />
        ) : (
          <ul>
            {history.map((g) => (
              <li
                key={g.id}
                className="border-t px-4 py-[10px] text-[12.5px]"
                style={{ borderColor: 'var(--line)' }}
              >
                <div className="flex flex-wrap items-center gap-3">
                  <span className="font-medium">{g.admin_email}</span>
                  <Tag tone={g.live ? 'breach' : 'plain'}>{g.live ? 'open' : 'ended'}</Tag>
                  <span style={{ color: 'var(--ink-faint)' }}>
                    {g.scope === 'operate' ? 'read + operate' : 'read only'}
                  </span>
                  <span className="tnum" style={{ color: 'var(--ink-faint)' }}>
                    {whenUTC(g.granted_at)}
                    {g.ended_at ? ` → ${whenUTC(g.ended_at)}` : ` → expires ${whenUTC(g.expires_at)}`}
                  </span>
                </div>
                <p className="mt-1" style={{ color: 'var(--ink-soft)' }}>
                  &ldquo;{g.reason}&rdquo;
                </p>
              </li>
            ))}
          </ul>
        )}
      </Panel>

      <p className="mt-5 text-[12px]">
        <Link href="/" className="underline" style={{ color: 'var(--ink-faint)' }}>
          ← Back to fleet
        </Link>
      </p>
    </>
  )
}
