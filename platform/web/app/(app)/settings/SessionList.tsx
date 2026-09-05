'use client'

import { useState, useTransition } from 'react'

import { signOutEverywhereElse } from '@/lib/actions'

export type SessionRow = {
  id: string
  created_at: string
  last_seen_at: string
  created_from: string
  current: boolean
}

function when(iso: string): string {
  const minutes = Math.round((Date.now() - new Date(iso).getTime()) / 60000)
  if (minutes < 1) return 'just now'
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.round(minutes / 60)
  if (hours < 48) return `${hours}h ago`
  return `${Math.round(hours / 24)}d ago`
}

/**
 * Where somebody sees they are signed in somewhere they did not expect.
 *
 * Deliberately thin. Recognising your own session well enough to end one you
 * do not recognise is the job; building a record of where a customer works is
 * not, so there is no device fingerprint here and no history of addresses.
 *
 * The button keeps the session doing the asking. The alternative signs you out
 * on the very machine you were worried about and asks for your password there.
 */
export function SessionList({ sessions }: { sessions: SessionRow[] }) {
  const [pending, start] = useTransition()
  const [error, setError] = useState<string | null>(null)
  const others = sessions.filter((s) => !s.current).length

  return (
    <div className="px-4 pb-4">
      <ul className="mb-3">
        {sessions.map((s) => (
          <li
            key={s.id}
            className="flex flex-wrap items-center gap-x-3 gap-y-1 border-t py-[9px] text-[12.5px]"
            style={{ borderColor: 'var(--color-line)' }}
          >
            <span className="w-[110px] shrink-0" style={{ color: 'var(--color-ink-soft)' }}>
              {s.current ? 'This device' : 'Signed in'}
            </span>
            <span className="tnum" style={{ color: 'var(--color-ink-faint)' }}>
              last used {when(s.last_seen_at)}
            </span>
            {s.created_from && (
              <span className="tnum" style={{ color: 'var(--color-ink-faint)' }}>
                from {s.created_from}
              </span>
            )}
          </li>
        ))}
      </ul>

      {error && (
        <p className="mb-2 text-[12.5px]" style={{ color: 'var(--color-risk)' }}>
          {error}
        </p>
      )}

      <button
        type="button"
        disabled={pending || others === 0}
        onClick={() =>
          start(async () => {
            const result = await signOutEverywhereElse()
            setError(result && 'error' in result ? result.error : null)
          })
        }
        className="rounded-[9px] px-3 py-[6px] text-[12.5px] font-medium disabled:opacity-50"
        style={{ background: 'var(--color-raised)', boxShadow: 'var(--raise-sm)' }}
      >
        {pending
          ? 'Signing out…'
          : others === 0
            ? 'No other sessions'
            : `Sign out ${others} other session${others === 1 ? '' : 's'}`}
      </button>
    </div>
  )
}
