'use client'

import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import { Suspense, useActionState } from 'react'

import { AuthField, AuthShell, AuthSubmit } from '@/components/AuthShell'
import { login } from '@/lib/actions'

function LoginForm() {
  const [state, action] = useActionState(login, null)
  // Somebody who just set a new password arrives here with no idea whether it
  // worked. Signing them in automatically would be the other way to close
  // that gap, and it is the wrong one: a reset proves control of a mailbox,
  // and the password they just chose is what proves control of the account.
  const justReset = useSearchParams().get('reset') === '1'

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
      error={state?.error}
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
