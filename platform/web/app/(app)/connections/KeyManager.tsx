'use client'

import { AnimatePresence, motion, useReducedMotion } from 'framer-motion'
import { useState } from 'react'
import { toast } from 'sonner'

import { Inset, whenUTC } from '@/components/forge'
import { PressButton } from '@/components/motion'
import { issueApiKey, revokeApiKey } from '@/lib/actions'
import type { ApiKeyRow } from '@/lib/api'

const EASE = [0.16, 1, 0.3, 1] as const

type Issued = { id: string; name: string; prefix: string; secret: string }

/**
 * Issue, read and revoke ingest keys.
 *
 * The whole component is organised around one irreversible moment: the secret
 * exists in the browser exactly once, and the platform genuinely cannot show
 * it again. So the reveal is not a toast or a row in the table — it is a panel
 * that stays put until the person explicitly says they have stored it, and it
 * says out loud that closing it is final.
 */
export function KeyManager({ keys, canManage }: { keys: ApiKeyRow[]; canManage: boolean }) {
  const [issued, setIssued] = useState<Issued | null>(null)
  const [creating, setCreating] = useState(false)
  const [name, setName] = useState('')
  const reduced = useReducedMotion()

  async function create(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (creating) return
    setCreating(true)

    const form = new FormData()
    form.set('name', name)
    const result = await issueApiKey(null, form)

    setCreating(false)
    if (result?.ok) {
      setIssued(result)
      setName('')
      return
    }
    toast.error(result?.ok === false ? result.error : 'That key could not be issued.')
  }

  return (
    <>
      <AnimatePresence>
        {issued && (
          <SecretReveal
            key={issued.id}
            issued={issued}
            reduced={!!reduced}
            onDone={() => setIssued(null)}
          />
        )}
      </AnimatePresence>

      {canManage && (
        <form onSubmit={create} className="mb-9 flex flex-wrap items-end gap-3">
          <label className="min-w-[240px] flex-1">
            <span
              className="mb-2 block text-[12.5px] font-medium"
              style={{ color: 'var(--color-ink-faint)' }}
            >
              What will use this key?
            </span>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Xero nightly sync"
              maxLength={120}
              className="w-full rounded-[13px] px-[15px] py-[11px] text-[14px] outline-none transition-shadow duration-200 focus:shadow-[var(--press)]"
              style={{
                background: 'var(--color-ground)',
                boxShadow: 'var(--press-sm)',
                color: 'var(--color-ink)',
              }}
            />
          </label>
          <PressButton
            type="submit"
            disabled={creating || name.trim().length < 2}
            className="rounded-[13px] px-[19px] py-[11px] text-[13.5px] font-semibold disabled:opacity-45"
            style={{
              background: 'var(--color-raised)',
              boxShadow: 'var(--raise-sm)',
              color: 'var(--color-copper)',
            }}
          >
            {creating ? 'Issuing…' : 'Issue key'}
          </PressButton>
        </form>
      )}

      {keys.length === 0 ? (
        <Inset className="px-6 py-9 text-center">
          <p className="text-[14.5px] font-medium">No ingest keys yet</p>
          <p
            className="mx-auto mt-2 max-w-[46ch] text-[13.5px] leading-relaxed"
            style={{ color: 'var(--color-ink-faint)' }}
          >
            {canManage
              ? 'Issue one when you are ready to connect a system that pushes readings on its own — a nightly export, a warehouse job, an accounting sync.'
              : 'Your owner can issue a key when a system needs to push readings without a person signed in.'}
          </p>
        </Inset>
      ) : (
        <ul className="grid gap-3">
          {keys.map((key, i) => (
            <KeyRow
              key={key.id}
              row={key}
              canManage={canManage}
              index={i}
              reduced={!!reduced}
            />
          ))}
        </ul>
      )}
    </>
  )
}

// ── The one-time reveal ──────────────────────────────────────────────────────

function SecretReveal({
  issued,
  reduced,
  onDone,
}: {
  issued: Issued
  reduced: boolean
  onDone: () => void
}) {
  const [copied, setCopied] = useState(false)

  async function copy() {
    try {
      await navigator.clipboard.writeText(issued.secret)
      setCopied(true)
      // Not a toast: the confirmation belongs next to the thing copied, and a
      // toast here would sit on top of the value the person is reading.
      setTimeout(() => setCopied(false), 2200)
    } catch {
      toast.error('Your browser blocked the clipboard. Select the key and copy it manually.')
    }
  }

  return (
    <motion.div
      initial={reduced ? false : { opacity: 0, y: -12 }}
      animate={{ opacity: 1, y: 0 }}
      exit={reduced ? { opacity: 0 } : { opacity: 0, y: -8, transition: { duration: 0.22 } }}
      transition={{ duration: 0.5, ease: EASE }}
      className="mb-8 rounded-[20px] p-7"
      style={{
        background: 'var(--color-raised)',
        boxShadow: 'var(--raise)',
        borderLeft: '3px solid var(--color-copper)',
      }}
    >
      <p
        className="text-[11px] font-semibold uppercase tracking-[0.16em]"
        style={{ color: 'var(--color-copper)' }}
      >
        Copy this now
      </p>
      <h2 className="mt-[10px] text-[19px] font-bold tracking-[-0.015em]">
        {issued.name} is live
      </h2>
      <p
        className="mt-2 max-w-[62ch] text-[13.5px] leading-relaxed"
        style={{ color: 'var(--color-ink-soft)' }}
      >
        This is the only time this key will ever be shown. We store a one-way hash of it, so
        nobody — including us — can recover it later. If you lose it, revoke it and issue
        another.
      </p>

      <Inset className="mt-5 flex flex-wrap items-center gap-3 px-4 py-[14px]">
        <code
          className="min-w-0 flex-1 break-all font-mono text-[13px] leading-[1.6]"
          style={{ color: 'var(--color-ink)' }}
        >
          {issued.secret}
        </code>
        <PressButton
          type="button"
          onClick={copy}
          className="shrink-0 rounded-[11px] px-[15px] py-2 text-[12.5px] font-semibold"
          style={{
            background: 'var(--color-raised)',
            boxShadow: 'var(--raise-sm)',
            color: copied ? 'var(--color-good)' : 'var(--color-copper)',
          }}
        >
          {copied ? 'Copied' : 'Copy'}
        </PressButton>
      </Inset>

      <div className="mt-5 flex flex-wrap items-center gap-4">
        <PressButton
          type="button"
          onClick={onDone}
          className="rounded-[12px] px-[17px] py-[10px] text-[13px] font-semibold"
          style={{
            background: 'var(--color-raised)',
            boxShadow: 'var(--raise-sm)',
            color: 'var(--color-ink-soft)',
          }}
        >
          I have stored it
        </PressButton>
        <span className="text-[12.5px]" style={{ color: 'var(--color-ink-faint)' }}>
          Dismissing this is final.
        </span>
      </div>
    </motion.div>
  )
}

// ── One key ──────────────────────────────────────────────────────────────────

function KeyRow({
  row,
  canManage,
  index,
  reduced,
}: {
  row: ApiKeyRow
  canManage: boolean
  index: number
  reduced: boolean
}) {
  // Two-step rather than a dialog: revoking breaks a running integration, so
  // it should not be one stray click, but it also does not deserve a modal
  // that interrupts the page.
  const [confirming, setConfirming] = useState(false)
  const [pending, setPending] = useState(false)

  async function revoke() {
    setPending(true)
    const form = new FormData()
    form.set('key_id', row.id)
    form.set('key_name', row.name)
    const result = await revokeApiKey(null, form)

    if (result?.ok) {
      toast.success(`${result.name} revoked`, {
        description: 'Any system still using it will be refused from the next request.',
      })
      return // revalidation re-renders this row as revoked
    }
    setPending(false)
    setConfirming(false)
    toast.error(result?.ok === false ? result.error : 'That key could not be revoked.')
  }

  return (
    <motion.li
      initial={reduced ? false : { opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: EASE, delay: reduced ? 0 : Math.min(index, 6) * 0.045 }}
      className="grid grid-cols-1 items-center gap-4 rounded-[17px] px-[22px] py-[18px] sm:grid-cols-[minmax(0,1fr)_auto]"
      style={{
        background: 'var(--color-raised)',
        boxShadow: 'var(--raise-sm)',
        opacity: row.revoked ? 0.55 : 1,
      }}
    >
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-[10px]">
          <span className="text-[14.5px] font-semibold">{row.name}</span>
          <code
            className="rounded-[7px] px-2 py-[3px] font-mono text-[11.5px]"
            style={{ background: 'var(--color-ground)', color: 'var(--color-ink-faint)' }}
          >
            {row.prefix}…
          </code>
          {row.revoked && (
            <span
              className="rounded-[7px] px-2 py-[3px] text-[11px] font-semibold uppercase tracking-[0.1em]"
              style={{ background: 'var(--color-ground)', color: 'var(--color-risk)' }}
            >
              Revoked
            </span>
          )}
        </div>
        <p className="mt-[7px] text-[12.5px]" style={{ color: 'var(--color-ink-faint)' }}>
          {row.last_used_at
            ? `Last used ${whenUTC(row.last_used_at)}`
            : 'Never used — nothing has pushed with it yet'}
          {' · '}
          Issued {whenUTC(row.created_at)} by {row.created_by}
        </p>
      </div>

      {canManage && !row.revoked && (
        <div className="flex items-center gap-2 justify-self-start sm:justify-self-end">
          {confirming ? (
            <>
              <PressButton
                type="button"
                onClick={revoke}
                disabled={pending}
                className="rounded-[11px] px-[15px] py-2 text-[12.5px] font-semibold disabled:opacity-50"
                style={{
                  background: 'var(--color-raised)',
                  boxShadow: 'var(--raise-sm)',
                  color: 'var(--color-risk)',
                }}
              >
                {pending ? 'Revoking…' : 'Yes, revoke'}
              </PressButton>
              <button
                type="button"
                onClick={() => setConfirming(false)}
                disabled={pending}
                className="rounded-[11px] px-[13px] py-2 text-[12.5px] transition-colors duration-200"
                style={{ color: 'var(--color-ink-faint)' }}
              >
                Cancel
              </button>
            </>
          ) : (
            <PressButton
              type="button"
              onClick={() => setConfirming(true)}
              className="rounded-[11px] px-[15px] py-2 text-[12.5px] font-medium"
              style={{
                background: 'var(--color-raised)',
                boxShadow: 'var(--raise-sm)',
                color: 'var(--color-ink-faint)',
              }}
            >
              Revoke
            </PressButton>
          )}
        </div>
      )}
    </motion.li>
  )
}
