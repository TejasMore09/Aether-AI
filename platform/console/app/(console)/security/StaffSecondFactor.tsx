'use client'

import { useState, useTransition } from 'react'

import {
  confirmStaffMfa,
  disableStaffMfa,
  startStaffMfa,
  type StaffMfaStatus,
} from '@/lib/actions'

/**
 * A second factor on the account that reaches every tenant.
 *
 * This surface matters more than the customer one: a stolen customer password
 * costs one organisation, and a stolen staff password costs the fleet. Which
 * is why the console got this at the same time and not later.
 *
 * The recovery codes are shown once. The platform keeps only hashes, so
 * somebody who clicks past this screen has genuinely lost them — and losing
 * both the phone and the codes on a staff account means an admin has to
 * intervene.
 */
export function StaffSecondFactor({ status }: { status: StaffMfaStatus }) {
  const [pending, start] = useTransition()
  const [error, setError] = useState<string | null>(null)
  const [secret, setSecret] = useState<string | null>(null)
  const [codes, setCodes] = useState<string[] | null>(null)
  const [code, setCode] = useState('')

  const run = (work: () => Promise<void>) =>
    start(async () => {
      setError(null)
      await work()
    })

  if (!status.available) {
    return (
      <p className="px-4 pb-4 text-[12.5px]" style={{ color: 'var(--ink-faint)' }}>
        Not configured on this deployment (<code>AETHER_MFA_KEY</code>). Switched off rather
        than storing a secret a stolen database could use.
      </p>
    )
  }

  if (codes) {
    return (
      <div className="px-4 pb-4">
        <p className="mb-2 text-[12.5px]" style={{ color: 'var(--ink-soft)' }}>
          <strong>Save these now.</strong> Each signs you in once if you lose your phone. They
          are not shown again — only hashes are kept.
        </p>
        <pre
          className="tnum mb-3 grid grid-cols-2 gap-x-6 gap-y-1 border px-4 py-3 text-[13px]"
          style={{ borderColor: 'var(--line)', background: 'var(--steel-950)' }}
        >
          {codes.map((value) => (
            <span key={value}>{value}</span>
          ))}
        </pre>
        <Button onClick={() => setCodes(null)}>I have saved them</Button>
      </div>
    )
  }

  if (status.confirmed) {
    return (
      <div className="px-4 pb-4">
        <p className="mb-3 text-[12.5px]" style={{ color: 'var(--ink-soft)' }}>
          On. {status.recovery_codes_left} recovery code
          {status.recovery_codes_left === 1 ? '' : 's'} left.
        </p>
        <CodeRow
          label="Turn it off"
          hint="Needs a current code, and is written to the staff trail."
          value={code}
          onChange={setCode}
          busy={pending}
          error={error}
          onSubmit={() =>
            run(async () => {
              const result = await disableStaffMfa(code)
              if (result && 'error' in result) setError(result.error)
              else setCode('')
            })
          }
        />
      </div>
    )
  }

  if (secret) {
    return (
      <div className="px-4 pb-4">
        <p className="mb-2 text-[12.5px]" style={{ color: 'var(--ink-soft)' }}>
          Add this to your authenticator, then enter the code it shows. Nothing changes until
          that code proves the app works.
        </p>
        <p
          className="mb-3 break-all border px-4 py-3 text-[12.5px]"
          style={{ borderColor: 'var(--line)', background: 'var(--steel-950)' }}
        >
          <span style={{ color: 'var(--ink-faint)' }}>Setup key: </span>
          <code className="tnum">{secret}</code>
        </p>
        <CodeRow
          label="Confirm"
          hint="Six digits from the app."
          value={code}
          onChange={setCode}
          busy={pending}
          error={error}
          onSubmit={() =>
            run(async () => {
              const result = await confirmStaffMfa(code)
              if ('error' in result) setError(result.error)
              else {
                setCodes(result.recoveryCodes)
                setSecret(null)
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
      <p className="mb-3 text-[12.5px]" style={{ color: 'var(--ink-soft)' }}>
        Off. Your password alone reaches every tenant on the platform.
      </p>
      {error && (
        <p className="mb-2 text-[12.5px]" style={{ color: 'var(--critical)' }}>
          {error}
        </p>
      )}
      <Button
        disabled={pending}
        onClick={() =>
          run(async () => {
            const result = await startStaffMfa()
            if ('error' in result) setError(result.error)
            else setSecret(result.secret)
          })
        }
      >
        {pending ? 'Starting…' : 'Turn on two-factor authentication'}
      </Button>
    </div>
  )
}

function Button({
  children,
  onClick,
  disabled,
}: {
  children: React.ReactNode
  onClick: () => void
  disabled?: boolean
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className="rounded-[4px] border px-3 py-[6px] text-[12.5px] font-medium disabled:opacity-50"
      style={{
        background: 'var(--steel-700)',
        borderColor: 'var(--steel-600)',
        color: 'var(--ink)',
      }}
    >
      {children}
    </button>
  )
}

function CodeRow({
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
        <p className="mb-2 text-[12.5px]" style={{ color: 'var(--critical)' }}>
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
          className="tnum w-[110px] rounded-[4px] border px-3 py-[6px] text-[13px] outline-none"
          style={{
            background: 'var(--steel-950)',
            borderColor: 'var(--line)',
            color: 'var(--ink)',
          }}
        />
        <Button disabled={busy || value.length < 6} onClick={onSubmit}>
          {busy ? 'Working…' : label}
        </Button>
        <span className="text-[11.5px]" style={{ color: 'var(--ink-faint)' }}>
          {hint}
        </span>
      </div>
    </>
  )
}
