'use client'

import { useState, useTransition } from 'react'

import { eraseMe, eraseOrganisation } from '@/lib/actions'

/**
 * The rights D31 made obligations, as buttons rather than an email address.
 *
 * A right of access that requires writing to support and waiting is a right on
 * paper. These do it now.
 *
 * The two destructive ones ask for different confirmations on purpose. Your
 * own account asks you to type DELETE; the organisation asks for its own name,
 * because a generic word is too easy to type into the wrong window and the
 * name of the thing being destroyed is not.
 */
export function YourData({ slug, isOwner }: { slug: string; isOwner: boolean }) {
  const [pending, start] = useTransition()
  const [error, setError] = useState<string | null>(null)
  const [confirming, setConfirming] = useState<'me' | 'org' | null>(null)
  const [password, setPassword] = useState('')
  const [phrase, setPhrase] = useState('')

  const download = (path: string, name: string) =>
    start(async () => {
      setError(null)
      // Fetched through the app's own route rather than the platform API: the
      // browser has no token and no way to reach the API directly, which is
      // the whole backend-for-frontend arrangement.
      const response = await fetch(path)
      if (!response.ok) {
        setError('That export could not be produced.')
        return
      }
      const blob = new Blob([JSON.stringify(await response.json(), null, 2)], {
        type: 'application/json',
      })
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = name
      anchor.click()
      URL.revokeObjectURL(url)
    })

  return (
    <div className="px-4 pb-4">
      <p className="mb-3 text-[12.5px]" style={{ color: 'var(--color-ink-soft)' }}>
        Everything Aether holds, as JSON you can take elsewhere. Your own data is separate
        from your organisation&rsquo;s.
      </p>

      {error && (
        <p className="mb-2 text-[12.5px]" style={{ color: 'var(--color-risk)' }}>
          {error}
        </p>
      )}

      <div className="mb-4 flex flex-wrap gap-2">
        <Action onClick={() => download('/api/export/me', 'aether-my-data.json')} busy={pending}>
          Download my data
        </Action>
        {isOwner && (
          <Action
            onClick={() => download('/api/export/organisation', `aether-${slug}.json`)}
            busy={pending}
          >
            Download {slug}
          </Action>
        )}
      </div>

      {confirming === null && (
        <div className="flex flex-wrap gap-2">
          <Action onClick={() => setConfirming('me')} busy={pending} danger>
            Delete my account
          </Action>
          {isOwner && (
            <Action onClick={() => setConfirming('org')} busy={pending} danger>
              Delete {slug}
            </Action>
          )}
        </div>
      )}

      {confirming && (
        <div
          className="rounded-[10px] px-4 py-3"
          style={{ background: 'var(--color-ground)', boxShadow: 'var(--press)' }}
        >
          <p className="mb-3 text-[12.5px]" style={{ color: 'var(--color-risk)' }}>
            {confirming === 'me'
              ? 'This cannot be undone. Your decisions stay in your organisation’s record with your name replaced — the account itself goes.'
              : `This deletes ${slug} and every reading, decision and memory in it. It cannot be undone. The people in it keep their accounts.`}
          </p>
          <div className="flex flex-wrap items-center gap-2">
            <input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder="Your password"
              aria-label="Your password"
              className="w-[170px] rounded-[9px] px-3 py-[6px] text-[13px]"
              style={{ background: 'var(--color-raised)', boxShadow: 'var(--press)' }}
            />
            <input
              value={phrase}
              onChange={(event) => setPhrase(event.target.value)}
              placeholder={confirming === 'me' ? 'DELETE' : slug}
              aria-label="Confirmation"
              className="w-[150px] rounded-[9px] px-3 py-[6px] text-[13px]"
              style={{ background: 'var(--color-raised)', boxShadow: 'var(--press)' }}
            />
            <Action
              busy={pending}
              danger
              onClick={() =>
                start(async () => {
                  setError(null)
                  const result =
                    confirming === 'me'
                      ? await eraseMe(password, phrase)
                      : await eraseOrganisation(password, phrase)
                  if (result && 'error' in result) setError(result.error)
                })
              }
            >
              {pending ? 'Deleting…' : 'Confirm deletion'}
            </Action>
            <button
              type="button"
              onClick={() => {
                setConfirming(null)
                setPassword('')
                setPhrase('')
                setError(null)
              }}
              className="text-[12.5px]"
              style={{ color: 'var(--color-ink-faint)' }}
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

function Action({
  children,
  onClick,
  busy,
  danger,
}: {
  children: React.ReactNode
  onClick: () => void
  busy: boolean
  danger?: boolean
}) {
  return (
    <button
      type="button"
      disabled={busy}
      onClick={onClick}
      className="rounded-[9px] px-3 py-[6px] text-[12.5px] font-medium disabled:opacity-50"
      style={{
        background: 'var(--color-raised)',
        boxShadow: 'var(--raise-sm)',
        color: danger ? 'var(--color-risk)' : undefined,
      }}
    >
      {children}
    </button>
  )
}
