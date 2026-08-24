'use client'

import Link from 'next/link'
import { useActionState } from 'react'

import { signup } from '@/lib/actions'
import { SubmitButton } from '@/components/SubmitButton'
import { ErrorNote } from '@/components/ui'

export default function SignupPage() {
  const [state, action] = useActionState(signup, null)

  return (
    <main style={{ minHeight: '100vh', display: 'grid', placeItems: 'center', padding: 24 }}>
      <div style={{ width: '100%', maxWidth: 440 }}>
        <div style={{ marginBottom: 28 }}>
          <div className="label" style={{ color: 'var(--color-accent)' }}>
            Aether Nano
          </div>
          <h1 style={{ fontSize: 26, fontWeight: 600, marginTop: 8 }}>
            Create your organization
          </h1>
          <p style={{ color: 'var(--color-ink-muted)', fontSize: 14, marginTop: 6 }}>
            Your data lives in its own isolated tenant. You become its owner.
          </p>
        </div>

        <form action={action} className="card" style={{ padding: 24 }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            {state?.error ? <ErrorNote message={state.error} /> : null}

            <label style={{ display: 'block' }}>
              <span className="label">Organization name</span>
              <input
                className="field"
                style={{ marginTop: 6 }}
                name="org_name"
                placeholder="Acme Manufacturing"
                required
              />
            </label>

            <label style={{ display: 'block' }}>
              <span className="label">Organization slug</span>
              <input
                className="field"
                style={{ marginTop: 6 }}
                name="org_slug"
                placeholder="acme"
                pattern="[a-z0-9][a-z0-9\-]*"
                title="Lowercase letters, numbers and dashes"
                required
              />
            </label>

            <label style={{ display: 'block' }}>
              <span className="label">Your name</span>
              <input className="field" style={{ marginTop: 6 }} name="display_name" />
            </label>

            <label style={{ display: 'block' }}>
              <span className="label">Work email</span>
              <input
                className="field"
                style={{ marginTop: 6 }}
                type="email"
                name="email"
                autoComplete="username"
                required
              />
            </label>

            <label style={{ display: 'block' }}>
              <span className="label">Password — at least 10 characters</span>
              <input
                className="field"
                style={{ marginTop: 6 }}
                type="password"
                name="password"
                autoComplete="new-password"
                minLength={10}
                required
              />
            </label>

            <SubmitButton pendingLabel="Creating…">Create organization</SubmitButton>
          </div>
        </form>

        <p style={{ fontSize: 13, color: 'var(--color-ink-muted)', marginTop: 18 }}>
          Already have an account?{' '}
          <Link href="/login" style={{ color: 'var(--color-accent)' }}>
            Sign in
          </Link>
        </p>
      </div>
    </main>
  )
}
