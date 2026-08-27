'use client'

import { motion, useReducedMotion } from 'framer-motion'
import { useFormStatus } from 'react-dom'

/**
 * The signed-out surface: sign in and sign up.
 *
 * Same Forge language as the product so the transition into it is continuous,
 * but calmer — a single centred panel on the bare ground, with the copper
 * bloom behind it. Nothing here should feel like a different application.
 */

export function AuthShell({
  title,
  lede,
  footer,
  error,
  action,
  children,
}: {
  title: string
  lede: string
  footer: React.ReactNode
  error?: string
  action: (formData: FormData) => void
  children: React.ReactNode
}) {
  const reduced = useReducedMotion()

  return (
    <main className="relative grid min-h-dvh place-items-center overflow-hidden px-5 py-16">
      <div
        aria-hidden="true"
        className="pointer-events-none absolute -top-48 right-[-12%] -z-10 h-[560px] w-[560px] rounded-full"
        style={{
          background: 'radial-gradient(circle, rgba(201,138,75,0.14), transparent 68%)',
        }}
      />

      <motion.div
        initial={reduced ? false : { opacity: 0, y: 18 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
        className="w-full max-w-[430px]"
      >
        <div className="mb-8 flex items-center gap-3">
          <span
            className="grid h-[34px] w-[34px] place-items-center rounded-[11px]"
            style={{ background: 'var(--color-raised)', boxShadow: 'var(--raise-sm)' }}
            aria-hidden="true"
          >
            <span
              className="block h-[13px] w-[13px] rounded-[3px]"
              style={{
                background:
                  'linear-gradient(145deg, var(--color-copper), var(--color-copper-dim))',
              }}
            />
          </span>
          <span className="text-[17px] font-bold tracking-[-0.015em]">Aether</span>
        </div>

        <h1 className="text-[30px] font-bold leading-[1.1] tracking-[-0.03em]">{title}</h1>
        <p className="mb-8 mt-3 text-[14.5px]" style={{ color: 'var(--color-ink-soft)' }}>
          {lede}
        </p>

        <form
          action={action}
          className="flex flex-col gap-[18px] rounded-[20px] p-7"
          style={{ background: 'var(--color-raised)', boxShadow: 'var(--raise)' }}
        >
          {error ? (
            <div
              role="alert"
              className="rounded-[12px] px-4 py-3 text-[13.5px]"
              style={{
                background: 'var(--color-ground)',
                boxShadow: 'var(--press)',
                color: 'var(--color-risk)',
              }}
            >
              {error}
            </div>
          ) : null}
          {children}
        </form>

        <p className="mt-6 text-[13px]" style={{ color: 'var(--color-ink-soft)' }}>
          {footer}
        </p>
      </motion.div>
    </main>
  )
}

export function AuthField({
  label,
  hint,
  name,
  ...rest
}: React.ComponentProps<'input'> & { label: string; hint?: string }) {
  return (
    <label className="block">
      <span className="block text-[12.5px] font-medium" style={{ color: 'var(--color-ink-soft)' }}>
        {label}
      </span>
      <input
        name={name}
        className="mt-2 w-full rounded-[12px] px-[14px] py-[11px] text-[14.5px] outline-none"
        style={{
          background: 'var(--color-ground)',
          boxShadow: 'var(--press-sm)',
          color: 'var(--color-ink)',
        }}
        {...rest}
      />
      {hint ? (
        <span className="mt-[6px] block text-[11.5px]" style={{ color: 'var(--color-ink-faint)' }}>
          {hint}
        </span>
      ) : null}
    </label>
  )
}

export function AuthSubmit({
  children,
  pending,
}: {
  children: React.ReactNode
  pending: string
}) {
  const { pending: busy } = useFormStatus()
  return (
    <button
      type="submit"
      disabled={busy}
      className="mt-1 rounded-[14px] px-6 py-[13px] text-[14px] font-semibold transition-[box-shadow,color] duration-200 ease-[var(--ease-forge)] active:shadow-[var(--press)] disabled:opacity-60"
      style={{
        background: 'var(--color-raised)',
        boxShadow: 'var(--raise-sm)',
        color: 'var(--color-copper)',
      }}
    >
      {busy ? pending : children}
    </button>
  )
}
