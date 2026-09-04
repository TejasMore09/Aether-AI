'use client'

import Link from 'next/link'
import { useActionState } from 'react'

import { AuthField, AuthShell, AuthSubmit } from '@/components/AuthShell'
import { forgotPassword } from '@/lib/actions'

/**
 * The form deliberately tells you nothing.
 *
 * Whatever you type, it answers the same way — that is the point, and it is
 * why the lede says so out loud rather than leaving a customer wondering
 * whether their address was recognised. A form that quietly withholds looks
 * broken; one that explains why it is withholding reads as careful.
 */
export default function ForgotPasswordPage() {
  const [state, action] = useActionState(forgotPassword, null)
  const notice = state && 'notice' in state ? state.notice : undefined

  return (
    <AuthShell
      title="Reset your password"
      lede="We will email a link to the address you sign in with. For everyone's safety this page answers the same way whether or not it finds an account."
      footer={
        <>
          Remembered it?{' '}
          <Link href="/login" style={{ color: 'var(--color-copper)' }}>
            Sign in
          </Link>
        </>
      }
      error={state && 'error' in state ? state.error : undefined}
      notice={notice}
      action={action}
    >
      {notice ? null : (
        <>
          <AuthField
            label="Work email"
            name="email"
            type="email"
            autoComplete="username"
            required
          />
          <AuthSubmit pending="Sending…">Email me a link</AuthSubmit>
        </>
      )}
    </AuthShell>
  )
}
