'use client'

import { useActionState, useState } from 'react'

import { openGrant } from '@/lib/actions'

/**
 * The request form for break-glass access.
 *
 * Everything here exists to make the engineer aware of what they are about to
 * do. The customer-facing consequence is stated in the form, not buried in a
 * policy document: this organization will see your name and this reason in
 * their own audit log, and there is no way to take it back.
 *
 * The reason field is large and unlabelled-by-placeholder-alone on purpose.
 * A single-line input invites "debug"; a textarea with a real prompt invites
 * a sentence someone would be comfortable having read back to them.
 */
export function BreakGlass({
  tenantId,
  tenantName,
  canOpen,
}: {
  tenantId: string
  tenantName: string
  canOpen: boolean
}) {
  const [state, action, pending] = useActionState(openGrant, null)
  const [reason, setReason] = useState('')
  const [minutes, setMinutes] = useState(15)

  if (!canOpen) {
    return (
      <div className="px-4 py-5">
        <p className="text-[13px]" style={{ color: 'var(--ink-soft)' }}>
          Your role is <strong>observer</strong>, which sees fleet health only. Opening
          access to an organization&rsquo;s data requires the engineer role.
        </p>
      </div>
    )
  }

  return (
    <form action={action} className="px-4 py-4">
      <input type="hidden" name="tenant_id" value={tenantId} />
      <input type="hidden" name="tenant_name" value={tenantName} />

      <label className="block">
        <span className="mb-[6px] block text-[12px]" style={{ color: 'var(--ink-soft)' }}>
          Why do you need to look inside {tenantName}?
        </span>
        <textarea
          name="reason"
          rows={3}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="Customer reported the nightly sync stopped after key rotation, ticket SUP-118."
          className="w-full resize-y rounded-[4px] border px-3 py-2 text-[13px] leading-relaxed outline-none"
          style={{
            background: 'var(--steel-950)',
            borderColor: 'var(--line)',
            color: 'var(--ink)',
          }}
        />
      </label>

      <div className="mt-3 flex flex-wrap items-end gap-4">
        <label className="block">
          <span
            className="mb-[6px] block text-[11px] uppercase tracking-[0.1em]"
            style={{ color: 'var(--ink-faint)' }}
          >
            Scope
          </span>
          <select
            name="scope"
            defaultValue="read_only"
            className="rounded-[4px] border px-[9px] py-[6px] text-[12.5px] outline-none"
            style={{
              background: 'var(--steel-950)',
              borderColor: 'var(--line)',
              color: 'var(--ink)',
            }}
          >
            <option value="read_only">Read only</option>
            <option value="operate">Read + operate</option>
          </select>
        </label>

        <label className="block">
          <span
            className="mb-[6px] block text-[11px] uppercase tracking-[0.1em]"
            style={{ color: 'var(--ink-faint)' }}
          >
            Ends after
          </span>
          <select
            name="minutes"
            value={minutes}
            onChange={(e) => setMinutes(Number(e.target.value))}
            className="tnum rounded-[4px] border px-[9px] py-[6px] text-[12.5px] outline-none"
            style={{
              background: 'var(--steel-950)',
              borderColor: 'var(--line)',
              color: 'var(--ink)',
            }}
          >
            {[15, 30, 60, 120, 240].map((m) => (
              <option key={m} value={m}>
                {m < 60 ? `${m} minutes` : `${m / 60} hour${m === 60 ? '' : 's'}`}
              </option>
            ))}
          </select>
        </label>

        <button
          type="submit"
          disabled={pending || reason.trim().length < 12}
          className="ml-auto rounded-[4px] border px-4 py-[8px] text-[12.5px] font-semibold transition-colors duration-150 disabled:opacity-40"
          style={{
            borderColor: 'color-mix(in srgb, var(--breach) 50%, transparent)',
            background: 'color-mix(in srgb, var(--breach) 14%, transparent)',
            color: 'var(--breach)',
          }}
        >
          {pending ? 'Opening…' : 'Open access'}
        </button>
      </div>

      <p className="mt-3 text-[12px] leading-relaxed" style={{ color: 'var(--ink-faint)' }}>
        {tenantName} will see your email address and this reason, word for word, in their own
        audit log — immediately, and permanently. Nobody can remove that entry, including us.
        Access ends on its own; you do not have to remember to close it.
      </p>

      {state?.ok === false && (
        <p
          className="mt-3 border px-3 py-2 text-[12.5px]"
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
    </form>
  )
}
