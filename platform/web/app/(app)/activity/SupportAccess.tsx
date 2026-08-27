import { whenUTC } from '@/components/forge'
import type { AuditEntry } from '@/lib/api'

/**
 * Access to this organization by Aether platform staff.
 *
 * Given its own section above the agent's activity, rather than left as a row
 * in the trail. Someone from outside the company read their operating data —
 * that is not the same kind of event as an agent evaluating a metric, and
 * making the customer scan a list to notice it would be a way of technically
 * disclosing while practically hiding.
 *
 * Everything recorded is shown: who, why, for how long. A reason the customer
 * cannot read is a reason written for nobody.
 */
export function SupportAccess({ entries }: { entries: AuditEntry[] }) {
  if (entries.length === 0) return null

  // Pair each close with its open so a finished visit reads as one event.
  const closes = new Map<string, AuditEntry>()
  for (const e of entries) {
    if (e.action === 'support_access_closed') {
      const id = String(e.details?.grant_id ?? '')
      if (id) closes.set(id, e)
    }
  }
  const opens = entries.filter((e) => e.action === 'support_access_opened')

  return (
    <section className="mb-11">
      <div className="mb-4 flex flex-wrap items-baseline justify-between gap-3">
        <h2 className="text-[15px] font-semibold tracking-[-0.01em]">Access by Aether staff</h2>
        <p className="text-[12.5px]" style={{ color: 'var(--color-ink-faint)' }}>
          Recorded automatically. We cannot remove an entry from this list.
        </p>
      </div>

      <ul className="grid gap-3">
        {opens.map((entry) => {
          const staff = entry.triggered_by.replace(/^staff:/, '')
          const reason = String(entry.details?.reason ?? '')
          const scope = String(entry.details?.scope ?? 'read_only')
          const expiresAt = String(entry.details?.expires_at ?? '')
          const ended = closes.get(String(entry.details?.grant_id ?? ''))
          const stillOpen = !ended && (!expiresAt || new Date(expiresAt) > new Date())

          return (
            <li
              key={entry.id}
              className="rounded-[17px] px-[22px] py-[18px]"
              style={{
                background: 'var(--color-raised)',
                boxShadow: 'var(--raise-sm)',
                borderLeft: `3px solid ${
                  stillOpen ? 'var(--color-copper)' : 'var(--color-ink-faint)'
                }`,
              }}
            >
              <div className="flex flex-wrap items-center gap-[10px]">
                <span className="text-[14px] font-semibold">{staff}</span>
                <span
                  className="rounded-[7px] px-2 py-[3px] text-[11px] font-semibold uppercase tracking-[0.1em]"
                  style={{
                    background: 'var(--color-ground)',
                    color: stillOpen ? 'var(--color-copper)' : 'var(--color-ink-faint)',
                  }}
                >
                  {stillOpen ? 'Access open' : 'Ended'}
                </span>
                <span className="text-[12.5px]" style={{ color: 'var(--color-ink-faint)' }}>
                  {scope === 'operate' ? 'Could make changes' : 'Read only'}
                </span>
              </div>

              <p className="mt-[10px] max-w-[74ch] text-[13.5px] leading-relaxed">“{reason}”</p>

              <p className="tnum mt-[10px] text-[12px]" style={{ color: 'var(--color-ink-faint)' }}>
                Opened {whenUTC(entry.created_at)}
                {ended
                  ? ` · ended ${whenUTC(ended.created_at)}`
                  : expiresAt
                    ? ` · ends automatically ${whenUTC(expiresAt)}`
                    : ''}
              </p>
            </li>
          )
        })}
      </ul>
    </section>
  )
}
