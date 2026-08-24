'use client'

import Link from 'next/link'
import { useActionState } from 'react'

import { login } from '@/lib/actions'
import { SubmitButton } from '@/components/SubmitButton'
import { ErrorNote } from '@/components/ui'

export default function LoginPage() {
  const [state, action] = useActionState(login, null)

  return (
    <main
      style={{
        minHeight: '100vh',
        display: 'grid',
        placeItems: 'center',
        padding: 24,
      }}
    >
      <div style={{ width: '100%', maxWidth: 400 }}>
        <div style={{ marginBottom: 28 }}>
          <div className="label" style={{ color: 'var(--color-accent)' }}>
            Aether Nano
          </div>
          <h1 style={{ fontSize: 26, fontWeight: 600, marginTop: 8 }}>Sign in</h1>
          <p style={{ color: 'var(--color-ink-muted)', fontSize: 14, marginTop: 6 }}>
            Autonomous operations monitoring for your business.
          </p>
        </div>

        <form action={action} className="card" style={{ padding: 24 }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            {state?.error ? <ErrorNote message={state.error} /> : null}

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
              <span className="label">Password</span>
              <input
                className="field"
                style={{ marginTop: 6 }}
                type="password"
                name="password"
                autoComplete="current-password"
                required
              />
            </label>

            <label style={{ display: 'block' }}>
              <span className="label">Organization slug (only if you belong to several)</span>
              <input
                className="field"
                style={{ marginTop: 6 }}
                type="text"
                name="org_slug"
                placeholder="acme"
              />
            </label>

            <SubmitButton pendingLabel="Signing in…">Sign in</SubmitButton>
          </div>
        </form>

        <p style={{ fontSize: 13, color: 'var(--color-ink-muted)', marginTop: 18 }}>
          New here?{' '}
          <Link href="/signup" style={{ color: 'var(--color-accent)' }}>
            Create an organization
          </Link>
        </p>
      </div>
    </main>
  )
}
