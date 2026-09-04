'use client'

import Link from 'next/link'
import { Suspense, useActionState } from 'react'
import { useSearchParams } from 'next/navigation'

import { AuthField, AuthShell, AuthSubmit } from '@/components/AuthShell'
import { resetPassword } from '@/lib/actions'

/**
 * Where the emailed link lands.
 *
 * The token rides in the query string because it has to — it arrives in an
 * email, and an email carries a URL and nothing else. It is put straight into
 * a hidden field and posted from the server action, so it never reaches the
 * platform API from the browser and never ends up in a client-side fetch log.
 */
function ResetForm() {
  const token = useSearchParams().get('token') ?? ''
  const [state, action] = useActionState(resetPassword, null)

  if (!token) {
    return (
      <AuthShell
        title="That link is incomplete"
        lede="A reset link carries a token, and this one arrived without it — usually a mail client breaking the URL across two lines."
        footer={
          <Link href="/forgot" style={{ color: 'var(--color-copper)' }}>
            Request a new link
          </Link>
        }
        action={() => {}}
      >
        <></>
      </AuthShell>
    )
  }

  return (
    <AuthShell
      title="Choose a new password"
      lede="This link works once, and only for the next 45 minutes."
      footer={
        <>
          Link expired?{' '}
          <Link href="/forgot" style={{ color: 'var(--color-copper)' }}>
            Request a new one
          </Link>
        </>
      }
      error={state?.error}
      action={action}
    >
      <input type="hidden" name="token" value={token} />
      <AuthField
        label="New password"
        name="password"
        type="password"
        autoComplete="new-password"
        hint="At least 10 characters"
        required
      />
      <AuthField
        label="Confirm password"
        name="confirm"
        type="password"
        autoComplete="new-password"
        required
      />
      <AuthSubmit pending="Saving…">Set password and continue</AuthSubmit>
    </AuthShell>
  )
}

export default function ResetPasswordPage() {
  // useSearchParams needs a boundary, and prerendering this page without one
  // fails the build rather than at runtime.
  return (
    <Suspense fallback={null}>
      <ResetForm />
    </Suspense>
  )
}
