'use client'

import { useFormStatus } from 'react-dom'

/**
 * The only reason this is a client component: it reads the pending state of
 * the enclosing form so a submit cannot be double-fired.
 */
export function SubmitButton({
  children,
  pendingLabel,
  variant = 'primary',
  ...rest
}: {
  children: React.ReactNode
  pendingLabel?: string
  variant?: 'primary' | 'ghost' | 'danger'
} & React.ButtonHTMLAttributes<HTMLButtonElement>) {
  const { pending } = useFormStatus()
  return (
    <button
      type="submit"
      className={`btn btn-${variant}`}
      disabled={pending || rest.disabled}
      {...rest}
    >
      {pending ? (pendingLabel ?? 'Working…') : children}
    </button>
  )
}
