'use client'

import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import { Suspense, useActionState } from 'react'

import { AuthField, AuthShell, AuthSubmit } from '@/components/AuthShell'
import { completeSignIn, login, type LoginState } from '@/lib/actions'

function pending(state: LoginState): { mfaChallenge: string; email: string } | null {
  return state && 'mfaChallenge' in state ? state : null
}

function errorOf(state: LoginState): string | undefined {
  return state && 'error' in state ? state.error : undefined
}

/**
 * The second step of a sign-in that stopped for a code.
 *
 * A separate form with its own action rather than a branch inside the first
 * one, because the two send different things to different endpoints. The
 * challenge rides in a hidden field: it is a half-identity with a five-minute
 * life, and putting it in a cookie would be storing exactly the thing that
 * must not outlive the form.
 */
function SecondFactor({ challenge, email, error }: { challenge: string; email: string; error?: string }) {
  const [state, action] = useActionState(completeSignIn, null)
  const stillPending = pending(state)

  return (
    <AuthShell
      title="One more step"
      lede={`Enter the six-digit code from your authenticator app for ${email}.`}
      footer={
        <>
          Lost your phone? Use one of the recovery codes you saved when you turned this on —
          they work in the same box.
        </>
      }
      error={errorOf(state) ?? error}
      action={action}
    >
      <input type="hidden" name="challenge" value={stillPending?.mfaChallenge ?? challenge} />
      <input type="hidden" name="email" value={email} />
      <AuthField
        label="Authentication code"
        name="code"
        inputMode="numeric"
        autoComplete="one-time-code"
        placeholder="123456"
        autoFocus
        required
      />
      <AuthSubmit pending="Checking…">Sign in</AuthSubmit>
    </AuthShell>
  )
}

function LoginForm() {
  const [state, action] = useActionState(login, null)
  // Somebody who just set a new password arrives here with no idea whether it
  // worked. Signing them in automatically would be the other way to close
  // that gap, and it is the wrong one: a reset proves control of a mailbox,
  // and the password they just chose is what proves control of the account.
  const justReset = useSearchParams().get('reset') === '1'

  const awaiting = pending(state)
  if (awaiting) {
    return <SecondFactor challenge={awaiting.mfaChallenge} email={awaiting.email} />
  }

  return (
    <AuthShell
      title="Sign in"
      lede="Your agent has been watching while you were away."
      footer={
        <>
          No account yet?{' '}
          <Link href="/signup" style={{ color: 'var(--color-copper)' }}>
            Create an organization
          </Link>
          {' · '}
          <Link href="/forgot" style={{ color: 'var(--color-ink-faint)' }}>
            Forgot your password?
          </Link>
          {' · '}
          <Link href="/explore" style={{ color: 'var(--color-ink-faint)' }}>
            See it without signing up
          </Link>
        </>
      }
      error={errorOf(state)}
      notice={justReset ? 'Password changed. Sign in with your new one.' : undefined}
      action={action}
    >
      <AuthField label="Work email" name="email" type="email" autoComplete="username" required />
      <AuthField
        label="Password"
        name="password"
        type="password"
        autoComplete="current-password"
        required
      />
      <AuthField
        label="Organization"
        name="org_slug"
        hint="Only needed if you belong to more than one"
        placeholder="acme"
      />
      <AuthSubmit pending="Signing in…">Sign in</AuthSubmit>
    </AuthShell>
  )
}

export default function LoginPage() {
  return (
    <Suspense fallback={null}>
      <LoginForm />
    </Suspense>
  )
}
