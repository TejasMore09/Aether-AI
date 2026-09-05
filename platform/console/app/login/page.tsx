'use client'

import { useActionState } from 'react'

import { completeSignIn, signIn, type SignInState } from '@/lib/actions'

function awaitingCode(state: SignInState): { mfaChallenge: string; email: string } | null {
  return state && 'mfaChallenge' in state ? state : null
}

function errorOf(state: SignInState): string | undefined {
  return state && 'error' in state ? state.error : undefined
}

export default function StaffLoginPage() {
  const [state, action, pending] = useActionState(signIn, null)
  const challenge = awaitingCode(state)

  if (challenge) {
    return <SecondFactor challenge={challenge.mfaChallenge} email={challenge.email} />
  }

  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-[380px] flex-col justify-center px-6">
      <div className="mb-7">
        <div className="mb-4 flex items-center gap-[10px]">
          <span
            className="grid h-[22px] w-[22px] place-items-center rounded-[3px] text-[11px] font-bold"
            style={{ background: 'var(--steel-700)', color: 'var(--ink-soft)' }}
            aria-hidden="true"
          >
            Æ
          </span>
          <span
            className="text-[11px] font-semibold uppercase tracking-[0.16em]"
            style={{ color: 'var(--ink-faint)' }}
          >
            Platform Console
          </span>
        </div>
        <h1 className="text-[19px] font-semibold tracking-[-0.01em]">Staff sign-in</h1>
        <p className="mt-[6px] text-[12.5px] leading-relaxed" style={{ color: 'var(--ink-soft)' }}>
          This console operates every customer&rsquo;s agent. Everything you do here is
          recorded against your name, including what you read.
        </p>
      </div>

      <form action={action} className="grid gap-3">
        <Field label="Staff email" name="email" type="email" autoComplete="username" />
        <Field
          label="Password"
          name="password"
          type="password"
          autoComplete="current-password"
        />

        <Problem message={errorOf(state)} />

        <button
          type="submit"
          disabled={pending}
          className="mt-1 rounded-[4px] border px-4 py-[9px] text-[13px] font-semibold transition-colors duration-150 disabled:opacity-50"
          style={{
            background: 'var(--steel-700)',
            borderColor: 'var(--steel-600)',
            color: 'var(--ink)',
          }}
        >
          {pending ? 'Signing in…' : 'Sign in'}
        </button>
      </form>
    </main>
  )
}

/**
 * The second step of a staff sign-in.
 *
 * A staff credential reaches every tenant on the platform, which is why this
 * surface is the one where a second factor matters most. The challenge rides
 * in a hidden field: it is a half-identity with a five-minute life and must
 * not outlive the form it belongs to.
 */
function SecondFactor({ challenge, email }: { challenge: string; email: string }) {
  const [state, action, pending] = useActionState(completeSignIn, null)
  const still = awaitingCode(state)

  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-[380px] flex-col justify-center px-6">
      <div className="mb-7">
        <h1 className="text-[19px] font-semibold tracking-[-0.01em]">One more step</h1>
        <p className="mt-[6px] text-[12.5px] leading-relaxed" style={{ color: 'var(--ink-soft)' }}>
          Enter the code from your authenticator app for {email}. A recovery code works here
          too.
        </p>
      </div>

      <form action={action} className="grid gap-3">
        <input type="hidden" name="challenge" value={still?.mfaChallenge ?? challenge} />
        <input type="hidden" name="email" value={email} />
        <Field
          label="Authentication code"
          name="code"
          type="text"
          autoComplete="one-time-code"
        />
        <Problem message={errorOf(state) ?? (still ? 'That code is not right.' : undefined)} />
        <button
          type="submit"
          disabled={pending}
          className="mt-1 rounded-[4px] border px-4 py-[9px] text-[13px] font-semibold transition-colors duration-150 disabled:opacity-50"
          style={{
            background: 'var(--steel-700)',
            borderColor: 'var(--steel-600)',
            color: 'var(--ink)',
          }}
        >
          {pending ? 'Checking…' : 'Sign in'}
        </button>
      </form>
    </main>
  )
}

function Problem({ message }: { message?: string }) {
  if (!message) return null
  return (
    <p
      className="border px-3 py-2 text-[12.5px]"
      style={{
        borderColor: 'color-mix(in srgb, var(--critical) 40%, transparent)',
        background: 'color-mix(in srgb, var(--critical) 8%, transparent)',
        color: 'var(--critical)',
      }}
      role="alert"
    >
      {message}
    </p>
  )
}

function Field({
  label,
  name,
  type,
  autoComplete,
}: {
  label: string
  name: string
  type: string
  autoComplete: string
}) {
  return (
    <label className="block">
      <span
        className="mb-[6px] block text-[11px] font-medium uppercase tracking-[0.1em]"
        style={{ color: 'var(--ink-faint)' }}
      >
        {label}
      </span>
      <input
        name={name}
        type={type}
        autoComplete={autoComplete}
        required
        className="w-full rounded-[4px] border px-3 py-[9px] text-[13.5px] outline-none"
        style={{
          background: 'var(--steel-950)',
          borderColor: 'var(--line)',
          color: 'var(--ink)',
        }}
      />
    </label>
  )
}
