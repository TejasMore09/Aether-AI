'use client'

import { useState, useTransition } from 'react'

import { resolveFault } from '@/lib/actions'

/**
 * Resolving is the only write on this page, and it is deliberately quiet.
 *
 * An observer never sees this button — the server decides that, not the
 * browser, and this component is simply not rendered for them. That is the
 * cosmetic half of the check; the real one is that the endpoint requires the
 * engineer role and would refuse regardless of what the page shows.
 */
export function ResolveButton({ fingerprint }: { fingerprint: string }) {
  const [pending, start] = useTransition()
  const [error, setError] = useState<string | null>(null)

  return (
    <span className="flex items-center gap-2">
      {error && (
        <span className="text-[11.5px]" style={{ color: 'var(--critical)' }}>
          {error}
        </span>
      )}
      <button
        type="button"
        disabled={pending}
        onClick={() =>
          start(async () => {
            const result = await resolveFault(fingerprint)
            setError(result && 'error' in result ? result.error : null)
          })
        }
        className="rounded-[7px] px-[10px] py-[5px] text-[11.5px] font-medium disabled:opacity-50"
        style={{ background: 'var(--raised)', boxShadow: 'var(--raise-sm)' }}
      >
        {pending ? 'Resolving…' : 'Resolve'}
      </button>
    </span>
  )
}
