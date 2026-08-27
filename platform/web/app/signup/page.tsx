'use client'

import Link from 'next/link'
import { useActionState } from 'react'

import { AuthField, AuthShell, AuthSubmit } from '@/components/AuthShell'
import { signup } from '@/lib/actions'

export default function SignupPage() {
  const [state, action] = useActionState(signup, null)

  return (
    <AuthShell
      title="Create your organization"
      lede="Your data lives in its own isolated tenant from the first reading. You become its owner."
      footer={
        <>
          Already have an account?{' '}
          <Link href="/login" style={{ color: 'var(--color-copper)' }}>
            Sign in
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
      <AuthField label="Organization name" name="org_name" placeholder="Kestrel Joinery" required />
      <AuthField
        label="Organization slug"
        name="org_slug"
        placeholder="kestrel"
        pattern="[a-z0-9][a-z0-9\-]*"
        title="Lowercase letters, numbers and dashes"
        hint="Used in your sign-in and API calls"
        required
      />
      <AuthField label="Your name" name="display_name" />
      <AuthField label="Work email" name="email" type="email" autoComplete="username" required />
      <AuthField
        label="Password"
        name="password"
        type="password"
        autoComplete="new-password"
        minLength={10}
        hint="At least 10 characters"
        required
      />
      <AuthSubmit pending="Creating…">Create organization</AuthSubmit>
    </AuthShell>
  )
}
