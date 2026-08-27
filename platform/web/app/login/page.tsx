'use client'

import Link from 'next/link'
import { useActionState } from 'react'

import { AuthField, AuthShell, AuthSubmit } from '@/components/AuthShell'
import { login } from '@/lib/actions'

export default function LoginPage() {
  const [state, action] = useActionState(login, null)

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
          <Link href="/explore" style={{ color: 'var(--color-ink-faint)' }}>
            See it without signing up
          </Link>
        </>
      }
      error={state?.error}
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
