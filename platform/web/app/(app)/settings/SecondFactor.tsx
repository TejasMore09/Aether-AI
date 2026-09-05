'use client'

import { useState, useTransition } from 'react'

import {
  confirmMfaEnrolment,
  disableMfa,
  startMfaEnrolment,
  type MfaStatus,
} from '@/lib/actions'

/**
 * Turning a second factor on, and the two things that usually go wrong.
 *
 * **The recovery codes are shown once and the page says so.** Without them a
 * lost phone is a lost account, which is the same lockout password reset was
 * built to prevent. They are not fetchable again — the platform keeps only
 * hashes — so a person who skips past this screen has genuinely lost them.
 *
 * **Turning it off asks for a code.** That is enforced by the API, not here;
 * this form asks because the API will refuse otherwise, and a stolen session
 * that could switch the factor off would have made the whole thing decoration.
 */
export function SecondFactor({ status }: { status: MfaStatus }) {
  const [pending, start] = useTransition()
  const [error, setError] = useState<string | null>(null)
  const [setup, setSetup] = useState<{ secret: string; uri: string } | null>(null)
  const [codes, setCodes] = useState<string[] | null>(null)
  const [code, setCode] = useState('')

  const run = (work: () => Promise<void>) =>
    start(async () => {
      setError(null)
      await work()
    })

  if (!status.available) {
    return (
      <p className="px-4 pb-4 text-[12.5px]" style={{ color: 'var(--color-ink-faint)' }}>
        Two-factor authentication is not configured on this deployment
        (<code>AETHER_MFA_KEY</code>). It is switched off rather than storing a secret that a
        stolen database could use.
      </p>
    )
  }

  // Shown exactly once, immediately after confirming.
  if (codes) {
    return (
      <div className="px-4 pb-4">
        <p className="mb-2 text-[12.5px]" style={{ color: 'var(--color-ink-soft)' }}>
          <strong>Save these now.</strong> Each one signs you in once if you lose your phone.
          They are not shown again and cannot be recovered — only hashes are kept.
        </p>
        <pre
          className="tnum mb-3 grid grid-cols-2 gap-x-6 gap-y-1 rounded-[10px] px-4 py-3 text-[13px]"
          style={{ background: 'var(--color-ground)', boxShadow: 'var(--press)' }}
        >
          {codes.map((c) => (
            <span key={c}>{c}</span>
          ))}
        </pre>
        <button
          type="button"
          onClick={() => setCodes(null)}
          className="rounded-[9px] px-3 py-[6px] text-[12.5px] font-medium"
          style={{ background: 'var(--color-raised)', boxShadow: 'var(--raise-sm)' }}
        >
          I have saved them
        </button>
      </div>
    )
  }

  if (status.confirmed) {
    return (
      <div className="px-4 pb-4">
        <p className="mb-3 text-[12.5px]" style={{ color: 'var(--color-ink-soft)' }}>
          On. Signing in asks for a code from your authenticator app.{' '}
          {status.recovery_codes_left} recovery code
          {status.recovery_codes_left === 1 ? '' : 's'} left.
        </p>
        {status.recovery_codes_left <= 2 && (
          <p className="mb-3 text-[12.5px]" style={{ color: 'var(--color-risk)' }}>
            Running low. Turn this off and on again to get a fresh set.
          </p>
        )}
        <Row
          label="Turn it off"
          hint="Needs a current code, because a stolen session must not be able to."
          value={code}
          onChange={setCode}
          busy={pending}
          error={error}
          onSubmit={() =>
            run(async () => {
              const result = await disableMfa(code)
              if (result && 'error' in result) setError(result.error)
              else setCode('')
            })
          }
        />
      </div>
    )
  }

  if (setup) {
    return (
      <div className="px-4 pb-4">
        <p className="mb-2 text-[12.5px]" style={{ color: 'var(--color-ink-soft)' }}>
          Add this to your authenticator app, then enter the code it shows. Nothing changes
          until that code proves the app is working.
        </p>
        <p
          className="mb-3 break-all rounded-[10px] px-4 py-3 text-[12.5px]"
          style={{ background: 'var(--color-ground)', boxShadow: 'var(--press)' }}
        >
          <span style={{ color: 'var(--color-ink-faint)' }}>Setup key: </span>
          <code className="tnum">{setup.secret}</code>
        </p>
        <Row
          label="Confirm"
          hint="Six digits from the app."
          value={code}
          onChange={setCode}
          busy={pending}
          error={error}
          onSubmit={() =>
            run(async () => {
              const result = await confirmMfaEnrolment(code)
              if ('error' in result!) setError(result.error)
              else if (result && 'recoveryCodes' in result) {
                setCodes(result.recoveryCodes)
                setSetup(null)
                setCode('')
              }
            })
          }
        />
      </div>
    )
  }

  return (
    <div className="px-4 pb-4">
      <p className="mb-3 text-[12.5px]" style={{ color: 'var(--color-ink-soft)' }}>
        Off. A password alone signs you in. Adding a second factor means a stolen or reused
        password is not enough on its own.
      </p>
      {error && (
        <p className="mb-2 text-[12.5px]" style={{ color: 'var(--color-risk)' }}>
          {error}
        </p>
      )}
      <button
        type="button"
        disabled={pending}
        onClick={() =>
          run(async () => {
            const result = await startMfaEnrolment()
            if (result && 'error' in result) setError(result.error)
            else if (result && 'secret' in result) {
              setSetup({ secret: result.secret, uri: result.otpauth_uri })
            }
          })
        }
        className="rounded-[9px] px-3 py-[6px] text-[12.5px] font-medium disabled:opacity-50"
        style={{ background: 'var(--color-raised)', boxShadow: 'var(--raise-sm)' }}
      >
        {pending ? 'Starting…' : 'Turn on two-factor authentication'}
      </button>
    </div>
  )
}

function Row({
  label,
  hint,
  value,
  onChange,
  onSubmit,
  busy,
  error,
}: {
  label: string
  hint: string
  value: string
  onChange: (next: string) => void
  onSubmit: () => void
  busy: boolean
  error: string | null
}) {
  return (
    <>
      {error && (
        <p className="mb-2 text-[12.5px]" style={{ color: 'var(--color-risk)' }}>
          {error}
        </p>
      )}
      <div className="flex flex-wrap items-center gap-2">
        <input
          value={value}
          onChange={(event) => onChange(event.target.value)}
          inputMode="numeric"
          placeholder="123456"
          aria-label={label}
          className="tnum w-[110px] rounded-[9px] px-3 py-[6px] text-[13px]"
          style={{ background: 'var(--color-ground)', boxShadow: 'var(--press)' }}
        />
        <button
          type="button"
          disabled={busy || value.length < 6}
          onClick={onSubmit}
          className="rounded-[9px] px-3 py-[6px] text-[12.5px] font-medium disabled:opacity-50"
          style={{ background: 'var(--color-raised)', boxShadow: 'var(--raise-sm)' }}
        >
          {busy ? 'Working…' : label}
        </button>
        <span className="text-[11.5px]" style={{ color: 'var(--color-ink-faint)' }}>
          {hint}
        </span>
      </div>
    </>
  )
}
