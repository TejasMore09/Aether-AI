'use client'

import Link from 'next/link'
import { useEffect, useState } from 'react'
import { toast } from 'sonner'

import { endGrant } from '@/lib/actions'
import type { Grant } from '@/lib/api'

/**
 * The bar that follows you while you are inside a customer's data.
 *
 * Sticky, full-width, in a colour reserved for exactly this. The countdown is
 * live because "expires at 01:25" requires the reader to know what time it is
 * and do arithmetic, while "12m left" does not — and the number that matters
 * during an incident is how long you have, not when it ends.
 *
 * Ending is one click and always available. Friction belongs on opening a
 * grant, never on closing one.
 */
export function OpenGrantBar({ grants }: { grants: Grant[] }) {
  if (grants.length === 0) return null
  return (
    <div
      className="sticky top-[45px] z-10 border-b"
      style={{
        background: 'color-mix(in srgb, var(--breach) 13%, var(--steel-950))',
        borderColor: 'color-mix(in srgb, var(--breach) 35%, transparent)',
      }}
    >
      <div className="mx-auto flex max-w-[1320px] flex-col gap-2 px-5 py-[9px]">
        {grants.map((g) => (
          <Row key={g.id} grant={g} />
        ))}
      </div>
    </div>
  )
}

function Row({ grant }: { grant: Grant }) {
  const [ending, setEnding] = useState(false)
  const left = useCountdown(grant.expires_at)

  async function close() {
    setEnding(true)
    const form = new FormData()
    form.set('grant_id', grant.id)
    form.set('tenant_id', grant.tenant_id)
    const result = await endGrant(null, form)
    if (result?.ok) {
      toast.success(`Access to ${grant.tenant_name} ended`)
      return // revalidation removes this row
    }
    setEnding(false)
    toast.error(result?.ok === false ? result.error : 'That grant could not be ended.')
  }

  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[12.5px]">
      <span
        className="breach-dot h-[7px] w-[7px] shrink-0 rounded-full"
        style={{ background: 'var(--breach)' }}
        aria-hidden="true"
      />
      <span className="font-semibold" style={{ color: 'var(--breach)' }}>
        Inside {grant.tenant_name}
      </span>
      <span style={{ color: 'var(--ink-soft)' }}>
        {grant.scope === 'operate' ? 'read + operate' : 'read only'}
      </span>
      <span className="tnum" style={{ color: 'var(--ink-soft)' }}>
        {left}
      </span>
      <span className="min-w-0 flex-1 truncate" style={{ color: 'var(--ink-faint)' }}>
        {grant.reason}
      </span>
      <Link
        href={`/tenants/${grant.tenant_id}`}
        className="shrink-0 underline"
        style={{ color: 'var(--ink-soft)' }}
      >
        Open
      </Link>
      <button
        type="button"
        onClick={close}
        disabled={ending}
        className="shrink-0 rounded-[3px] border px-[9px] py-[3px] text-[11.5px] font-semibold disabled:opacity-50"
        style={{
          borderColor: 'color-mix(in srgb, var(--breach) 45%, transparent)',
          color: 'var(--breach)',
        }}
      >
        {ending ? 'Ending…' : 'End access'}
      </button>
    </div>
  )
}

/**
 * Ticks once a second, and says "expired" rather than counting negative.
 *
 * `now` starts null rather than Date.now(). Seeding it during render means the
 * server and the client evaluate it a second apart, and a countdown that
 * disagrees by one second is still a hydration mismatch — an intermittent one,
 * which is worse, because it only appears when the two renders happen to
 * straddle a second boundary.
 */
function useCountdown(expiresAt: string): string {
  const [now, setNow] = useState<number | null>(null)

  useEffect(() => {
    setNow(Date.now())
    const id = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(id)
  }, [])

  if (now === null) return '' // first paint on both sides: no clock yet

  const ms = new Date(expiresAt).getTime() - now
  if (ms <= 0) return 'expired'
  const total = Math.floor(ms / 1000)
  const minutes = Math.floor(total / 60)
  const seconds = total % 60
  if (minutes >= 60) return `${Math.floor(minutes / 60)}h ${minutes % 60}m left`
  return `${minutes}:${String(seconds).padStart(2, '0')} left`
}
