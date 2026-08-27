import Link from 'next/link'

import { Empty, ErrorNote, PageHead, Panel, PanelHead, Tag, whenUTC } from '@/components/instrument'
import { brain, type TrailEntry } from '@/lib/api'

export const metadata = { title: 'Staff trail · Aether Console' }

const TONE: Record<string, 'breach' | 'attention' | 'plain'> = {
  'break_glass.open': 'breach',
  'break_glass.read': 'breach',
  'break_glass.close': 'plain',
  'staff.create': 'attention',
  'staff.bootstrap': 'attention',
  'staff.login': 'plain',
}

export default async function TrailPage() {
  const trail = await brain<TrailEntry[]>('/v1/staff-trail?limit=200')

  return (
    <>
      <PageHead
        title="Staff trail"
        lede="Everything platform staff have done, reads included. Append-only at the database — a trigger refuses UPDATE and DELETE, so this holds even against the application writing it."
      />

      {!trail.ok ? (
        <ErrorNote message={trail.message} />
      ) : (
        <Panel>
          <PanelHead
            title="Most recent first"
            aside={
              <span className="text-[11.5px]" style={{ color: 'var(--ink-faint)' }}>
                visible to every staff member, not only admins
              </span>
            }
          />
          {trail.data.length === 0 ? (
            <Empty
              title="Nothing recorded yet"
              body="Sign-ins, grants, and every read of a customer's data appear here."
            />
          ) : (
            <ul>
              {trail.data.map((e) => (
                <li
                  key={e.id}
                  className="flex flex-wrap items-center gap-x-3 gap-y-1 border-t px-4 py-[9px] text-[12.5px]"
                  style={{ borderColor: 'var(--line)' }}
                >
                  <span className="tnum w-[125px] shrink-0" style={{ color: 'var(--ink-faint)' }}>
                    {whenUTC(e.created_at)}
                  </span>
                  <span className="w-[165px] shrink-0">
                    <Tag tone={TONE[e.action] ?? 'plain'}>{e.action}</Tag>
                  </span>
                  <span className="w-[190px] shrink-0 truncate">{e.admin_email}</span>
                  <span className="w-[110px] shrink-0">
                    {e.tenant_id ? (
                      <Link
                        href={`/tenants/${e.tenant_id}`}
                        className="mono underline"
                        style={{ color: 'var(--ink-faint)' }}
                      >
                        {e.tenant_id.slice(0, 8)}
                      </Link>
                    ) : (
                      <span style={{ color: 'var(--ink-faint)' }}>—</span>
                    )}
                  </span>
                  <span className="min-w-0 flex-1 truncate" style={{ color: 'var(--ink-soft)' }}>
                    {detail(e)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      )}
    </>
  )
}

function detail(entry: TrailEntry): string {
  const d = entry.details ?? {}
  if (typeof d.reason === 'string') return d.reason
  if (typeof d.resource === 'string') return `read ${d.resource}`
  if (typeof d.created === 'string') return `created ${d.created} as ${String(d.role ?? '')}`
  if (typeof d.role === 'string') return String(d.role)
  return ''
}
