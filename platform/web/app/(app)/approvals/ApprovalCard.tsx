'use client'

import { motion, useReducedMotion } from 'framer-motion'
import { useState } from 'react'
import { toast } from 'sonner'

import { Inset, RiskPill, usd, whenUTC } from '@/components/forge'
import { resolveApproval } from '@/lib/actions'
import type { Approval } from '@/lib/api'

const EASE = [0.16, 1, 0.3, 1] as const

/**
 * One gated decision, and the two buttons that resolve it.
 *
 * The action is called as a promise from the click handler rather than through
 * useActionState. That is deliberate: resolving revalidates the list, which
 * unmounts this card, and a useEffect in an unmounting component never runs —
 * so a confirmation raised from an effect is silently lost. A promise
 * continuation is not tied to the component lifecycle and still fires.
 *
 * The confirmation itself is a toast rather than an in-card state, because the
 * card is legitimately gone once the decision is made. Without it the operator
 * clicks Approve on a money decision and the row simply vanishes, with no
 * signal that the click was taken.
 */
export function ApprovalCard({
  approval,
  canResolve,
}: {
  approval: Approval
  canResolve: boolean
}) {
  const [pending, setPending] = useState<null | 'approved' | 'rejected'>(null)
  const reduced = useReducedMotion()
  const label = approval.action.replace(/_/g, ' ').toLowerCase()

  async function decide(decision: 'approved' | 'rejected') {
    setPending(decision)

    const form = new FormData()
    form.set('approval_id', approval.id)
    form.set('decision', decision)
    form.set('action_label', label)

    const result = await resolveApproval(null, form)

    if (result?.ok) {
      toast.success(`${result.action} ${result.decision}`, {
        description: 'Recorded in the audit trail against your account.',
      })
      return // the card is being removed by revalidation; leave it pending
    }

    // Failed: restore the buttons rather than leave a false confirmation.
    setPending(null)
    toast.error(result?.ok === false ? result.error : 'That could not be recorded.')
  }

  return (
    <motion.article
      initial={reduced ? false : { opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.45, ease: EASE }}
      className="rounded-[20px] p-7"
      style={{
        background: 'var(--color-raised)',
        boxShadow: 'var(--raise)',
        borderLeft: '3px solid var(--color-risk)',
      }}
    >
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <span
          className="h-[9px] w-[9px] rounded-full"
          style={{
            background: 'var(--color-risk)',
            boxShadow: '0 0 0 4px rgba(217,112,92,0.16)',
          }}
          aria-hidden="true"
        />
        <h2 className="text-xl font-bold tracking-[-0.025em]">{label}</h2>
        <RiskPill level={approval.risk_level} />
        <span
          className="ml-auto text-xs"
          style={{ color: 'var(--color-ink-faint)' }}
          title="How this explanation was produced"
        >
          {approval.diagnosis_source === 'llm'
            ? 'AI analysis'
            : approval.diagnosis_source === 'fallback'
              ? 'Local summary'
              : 'Analysing…'}
        </span>
      </div>

      <div className="mb-5 flex flex-wrap items-baseline gap-x-6 gap-y-2">
        <span
          data-figure
          className="text-[34px] font-bold leading-none tracking-[-0.035em]"
          style={{ color: 'var(--color-risk)' }}
        >
          {usd(approval.expected_loss_usd)}
        </span>
        <span className="text-[13px]" style={{ color: 'var(--color-ink-faint)' }}>
          at risk each day · {approval.domain} · gated {whenUTC(approval.created_at)}
        </span>
      </div>

      <Inset className="mb-5">
        <span
          className="font-mono text-[12.5px] leading-[1.7]"
          style={{ color: 'var(--color-ink-soft)' }}
        >
          {approval.reason}
        </span>
      </Inset>

      <p
        className="max-w-[68ch] whitespace-pre-wrap text-[15px] leading-[1.65]"
        style={{ color: 'var(--color-ink-soft)' }}
      >
        {approval.diagnosis ?? 'The agent is still analysing this decision.'}
      </p>

      {canResolve ? (
        <div className="mt-6 flex flex-wrap gap-3">
          <PressButton
            tone="primary"
            disabled={pending !== null}
            onClick={() => decide('approved')}
          >
            {pending === 'approved' ? 'Recording…' : 'Approve'}
          </PressButton>
          <PressButton
            tone="ghost"
            disabled={pending !== null}
            onClick={() => decide('rejected')}
          >
            {pending === 'rejected' ? 'Recording…' : 'Reject'}
          </PressButton>
        </div>
      ) : (
        <p className="mt-6 text-xs" style={{ color: 'var(--color-ink-faint)' }}>
          Only an organization owner can resolve this.
        </p>
      )}
    </motion.article>
  )
}

/** Neumorphic button that presses inward. The affordance is physical. */
function PressButton({
  children,
  tone,
  ...rest
}: React.ComponentProps<'button'> & { tone: 'primary' | 'ghost' }) {
  return (
    <button
      type="button"
      className="rounded-[14px] px-6 py-3 text-sm font-semibold transition-[box-shadow,color] duration-200 ease-[var(--ease-forge)] active:shadow-[var(--press)] disabled:cursor-not-allowed disabled:opacity-60"
      style={{
        background: 'var(--color-raised)',
        boxShadow: 'var(--raise-sm)',
        color: tone === 'primary' ? 'var(--color-copper)' : 'var(--color-ink-soft)',
      }}
      {...rest}
    >
      {children}
    </button>
  )
}
