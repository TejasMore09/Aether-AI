'use client'

import { useMemo, useState } from 'react'

import { Ago } from '@/components/Ago'
import { Empty, Tag, TenantLink, toneColor, usd } from '@/components/instrument'
import type { EnrichedRow } from '@/lib/signals'

type Filter = 'attention' | 'all' | 'quiet'

/**
 * The fleet, filtered and searchable.
 *
 * Defaults to "needs attention" rather than "all". A console that opens on a
 * list of every organization makes the reader do the triage the console
 * should have done — and at a few hundred tenants, that list is scrollable
 * noise with the one broken agent somewhere inside it.
 */
export function FleetTable({ rows }: { rows: EnrichedRow[] }) {
  const [filter, setFilter] = useState<Filter>('attention')
  const [query, setQuery] = useState('')

  const counts = useMemo(
    () => ({
      attention: rows.filter((r) => r.tone === 'critical' || r.tone === 'attention').length,
      all: rows.length,
      quiet: rows.filter((r) => r.row.observation_count === 0).length,
    }),
    [rows],
  )

  const shown = useMemo(() => {
    const q = query.trim().toLowerCase()
    return rows.filter(({ row, tone }) => {
      if (filter === 'attention' && tone !== 'critical' && tone !== 'attention') return false
      if (filter === 'quiet' && row.observation_count !== 0) return false
      if (q && !row.name.toLowerCase().includes(q) && !row.slug.toLowerCase().includes(q)) {
        return false
      }
      return true
    })
  }, [rows, filter, query])

  return (
    <>
      <div
        className="flex flex-wrap items-center gap-2 border-b px-4 py-[9px]"
        style={{ borderColor: 'var(--line)' }}
      >
        {(['attention', 'all', 'quiet'] as const).map((f) => (
          <button
            key={f}
            type="button"
            onClick={() => setFilter(f)}
            className="rounded-[3px] border px-[9px] py-[4px] text-[11.5px] transition-colors duration-150"
            style={{
              borderColor: filter === f ? 'var(--steel-600)' : 'transparent',
              background: filter === f ? 'var(--steel-800)' : 'transparent',
              color: filter === f ? 'var(--ink)' : 'var(--ink-faint)',
            }}
          >
            {f === 'attention' ? 'Needs attention' : f === 'all' ? 'All' : 'Never reported'}
            <span className="tnum ml-[6px]" style={{ color: 'var(--ink-faint)' }}>
              {counts[f]}
            </span>
          </button>
        ))}

        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Filter by name or slug…"
          className="ml-auto w-[220px] rounded-[3px] border px-[9px] py-[4px] text-[12px] outline-none"
          style={{
            background: 'var(--steel-950)',
            borderColor: 'var(--line)',
            color: 'var(--ink)',
          }}
        />
      </div>

      {shown.length === 0 ? (
        <Empty
          title={filter === 'attention' ? 'Nothing needs attention' : 'No matches'}
          body={
            filter === 'attention'
              ? 'No agent is silent, over budget, quarantining readings, or holding a decision. Switch to All to browse the fleet.'
              : 'No organization matches that filter.'
          }
        />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[880px] border-collapse">
            <thead>
              <tr
                className="text-left text-[10.5px] uppercase tracking-[0.1em]"
                style={{ color: 'var(--ink-faint)' }}
              >
                <Th className="w-[26%]">Organization</Th>
                <Th className="w-[22%]">Status</Th>
                <Th align="right">Readings</Th>
                <Th align="right">Held</Th>
                <Th align="right">Domains</Th>
                <Th align="right">Keys</Th>
                <Th align="right">Spend</Th>
                <Th align="right">Last reading</Th>
              </tr>
            </thead>
            <tbody>
              {shown.map(({ row, signals, tone }) => (
                <tr
                  key={row.tenant_id}
                  className="border-t"
                  style={{ borderColor: 'var(--line)' }}
                >
                  <Td>
                    <div className="flex items-center gap-[9px]">
                      <span
                        className="h-[6px] w-[6px] shrink-0 rounded-full"
                        style={{ background: toneColor(tone) }}
                        aria-hidden="true"
                      />
                      <TenantLink id={row.tenant_id} name={row.name} slug={row.slug} />
                    </div>
                  </Td>
                  <Td>
                    <div className="flex flex-wrap gap-[5px]">
                      {signals.map((s) => (
                        <Tag key={s.label} tone={s.tone}>
                          {s.label}
                        </Tag>
                      ))}
                      {signals.length === 0 && <Tag tone="ok">healthy</Tag>}
                    </div>
                  </Td>
                  <Num>{row.observation_count}</Num>
                  <Num tone={row.quarantined_count > 0 ? 'attention' : undefined}>
                    {row.quarantined_count}
                  </Num>
                  <Num>{row.configured_domains}</Num>
                  <Num>{row.active_keys}</Num>
                  <Num>{usd(row.month_spend_usd, 2)}</Num>
                  <Num>
                    <Ago iso={row.last_observation_at} />
                  </Num>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  )
}

function Th({
  children,
  align = 'left',
  className = '',
}: {
  children: React.ReactNode
  align?: 'left' | 'right'
  className?: string
}) {
  return (
    <th
      className={`px-4 py-[9px] font-medium ${align === 'right' ? 'text-right' : ''} ${className}`}
      style={{ background: 'var(--steel-850)' }}
    >
      {children}
    </th>
  )
}

function Td({ children }: { children: React.ReactNode }) {
  return <td className="px-4 py-[10px] align-middle">{children}</td>
}

function Num({ children, tone }: { children: React.ReactNode; tone?: 'attention' }) {
  return (
    <td
      className="tnum px-4 py-[10px] text-right text-[12.5px]"
      style={{ color: tone ? toneColor(tone) : 'var(--ink-soft)' }}
    >
      {children}
    </td>
  )
}
