import {
  Empty,
  ErrorNote,
  PageHead,
  Panel,
  PanelHead,
  Stat,
  Tag,
  ago,
  whenUTC,
} from '@/components/instrument'
import { brain, type Fault, type OpsHealth } from '@/lib/api'
import { atLeast, readSession } from '@/lib/session'

import { ResolveButton } from './ResolveButton'

export const metadata = { title: 'Faults · Aether Console' }

/**
 * Where a broken platform becomes visible to a person.
 *
 * The alert email is the push half of 6.3 and it is the half most likely to
 * be down — it goes out through the same mail path a broken mail
 * configuration would take. This page is the pull half, and the two exist
 * together on purpose.
 *
 * **An observer sees every fault and the words of none.** That is not a
 * decision this page makes; the main brain omits `message` and `traceback`
 * from the payload entirely for that role. The page has to cope with their
 * absence, which is why the type marks them optional (D57).
 */
export default async function FaultsPage({
  searchParams,
}: {
  searchParams: Promise<{ resolved?: string }>
}) {
  const { resolved } = await searchParams
  const includeResolved = resolved === '1'

  const [session, faults, health] = await Promise.all([
    readSession(),
    brain<Fault[]>(`/v1/ops/errors?limit=100&include_resolved=${includeResolved}`),
    brain<OpsHealth>('/v1/ops/health'),
  ])
  const canResolve = session ? atLeast(session.role, 'engineer') : false

  return (
    <>
      <PageHead
        title="Faults"
        lede="Every unhandled exception across the three services, one row per distinct fault rather than one per occurrence. Stack traces are scrubbed before they are stored and are readable only by engineers, whose reads appear in the staff trail."
      />

      {!health.ok ? (
        <ErrorNote message={health.message} />
      ) : (
        <Panel>
          <PanelHead title="Platform" />
          <div className="grid grid-cols-2 md:grid-cols-4">
            <Stat
              label="Database"
              value={health.data.database.ok ? 'reachable' : 'down'}
              tone={health.data.database.ok ? 'ok' : 'critical'}
            />
            <Stat
              label="Open faults"
              value={health.data.errors.open ?? '—'}
              tone={(health.data.errors.open ?? 0) > 0 ? 'attention' : 'ok'}
            />
            <Stat label="Occurrences, 24h" value={health.data.errors.occurrences_last_day ?? '—'} />
            <Stat
              label="Alerting"
              value={health.data.alerts_configured ? 'configured' : 'not configured'}
              tone={health.data.alerts_configured ? 'ok' : 'critical'}
            />
          </div>
          {!health.data.alerts_configured && (
            /* Said out loud, because an alerting system nobody set up looks
               exactly like an alerting system with nothing to report. */
            <p
              className="border-t px-4 py-3 text-[12px]"
              style={{ borderColor: 'var(--line)', color: 'var(--ink-faint)' }}
            >
              No alert address is set (<code>AETHER_ALERT_EMAIL</code>), so faults are recorded
              here and nothing is pushed to anyone. This page is the only way anyone finds out.
            </p>
          )}
          {!health.data.mail_configured && (
            <p
              className="border-t px-4 py-3 text-[12px]"
              style={{ borderColor: 'var(--line)', color: 'var(--ink-faint)' }}
            >
              No mail transport is configured, so alerts and password resets both go nowhere.
            </p>
          )}
        </Panel>
      )}

      <div className="mt-5">
        {!faults.ok ? (
          <ErrorNote message={faults.message} />
        ) : (
          <Panel>
            <PanelHead
              title={includeResolved ? 'All faults' : 'Open faults'}
              aside={
                <a
                  href={includeResolved ? '/faults' : '/faults?resolved=1'}
                  className="text-[11.5px]"
                  style={{ color: 'var(--ink-faint)' }}
                >
                  {includeResolved ? 'show only open' : 'include resolved'}
                </a>
              }
            />
            {faults.data.length === 0 ? (
              <Empty
                title={includeResolved ? 'Nothing has ever broken' : 'Nothing is broken'}
                body="Unhandled exceptions from the control plane, agent runtime and main brain arrive here within a request."
              />
            ) : (
              <ul>
                {faults.data.map((fault) => (
                  <li
                    key={fault.fingerprint}
                    className="border-t px-4 py-3"
                    style={{ borderColor: 'var(--line)' }}
                  >
                    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[12.5px]">
                      <Tag tone={fault.resolved_at ? 'plain' : 'critical'}>
                        {fault.exception_type}
                      </Tag>
                      <span className="font-medium">{fault.location}</span>
                      <Tag tone="plain">{fault.service}</Tag>
                      <span className="tnum" style={{ color: 'var(--ink-faint)' }}>
                        {fault.occurrences}×
                      </span>
                      {/* One broken customer and every broken customer are
                          different emergencies. */}
                      {fault.tenants_seen > 0 && (
                        <Tag tone={fault.tenants_seen > 1 ? 'attention' : 'plain'}>
                          {fault.tenants_seen} tenant{fault.tenants_seen === 1 ? '' : 's'}
                        </Tag>
                      )}
                      <span className="ml-auto flex items-center gap-3">
                        <span className="tnum" style={{ color: 'var(--ink-faint)' }}>
                          {ago(fault.last_seen_at)}
                        </span>
                        {canResolve && !fault.resolved_at && (
                          <ResolveButton fingerprint={fault.fingerprint} />
                        )}
                      </span>
                    </div>

                    <div
                      className="mt-[6px] flex flex-wrap gap-x-4 text-[11.5px]"
                      style={{ color: 'var(--ink-faint)' }}
                    >
                      <span>first seen {whenUTC(fault.first_seen_at)}</span>
                      <span>reference {fault.reference}</span>
                      {!fault.alerted && !fault.resolved_at && <span>no alert sent</span>}
                      {fault.resolved_at && (
                        <span>
                          resolved by {fault.resolved_by} {ago(fault.resolved_at)}
                        </span>
                      )}
                    </div>

                    {fault.message ? (
                      <pre
                        className="mt-[10px] overflow-x-auto rounded-[9px] px-3 py-2 text-[11.5px] leading-[1.5]"
                        style={{ background: 'var(--ground)', boxShadow: 'var(--press)' }}
                      >
                        {fault.message}
                      </pre>
                    ) : (
                      <p className="mt-[10px] text-[11.5px]" style={{ color: 'var(--ink-faint)' }}>
                        The message and traceback need the engineer role. Your role can see that
                        this is broken and where, which is what it is for.
                      </p>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </Panel>
        )}
      </div>
    </>
  )
}
