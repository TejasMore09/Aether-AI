'use client'

import { useActionState } from 'react'

import { signIn } from '@/lib/actions'

export default function StaffLoginPage() {
  const [state, action, pending] = useActionState(signIn, null)

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

        {state?.error && (
          <p
            className="border px-3 py-2 text-[12.5px]"
            style={{
              borderColor: 'color-mix(in srgb, var(--critical) 40%, transparent)',
              background: 'color-mix(in srgb, var(--critical) 8%, transparent)',
              color: 'var(--critical)',
            }}
            role="alert"
          >
            {state.error}
          </p>
        )}

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
