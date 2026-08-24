'use client'

import { useActionState } from 'react'

import { resolveApproval } from '@/lib/actions'
import { SubmitButton } from '@/components/SubmitButton'
import { ErrorNote, RiskPill, formatUsd, formatWhen } from '@/components/ui'
import type { Approval } from '@/lib/api'

export function ApprovalCard({
  approval,
  canResolve,
}: {
  approval: Approval
  canResolve: boolean
}) {
  const [state, action] = useActionState(resolveApproval, null)

  return (
    <article className="card" style={{ padding: 0 }}>
      <div
        style={{
          padding: '16px 20px',
          borderBottom: '1px solid var(--color-line)',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'flex-start',
          gap: 20,
          flexWrap: 'wrap',
        }}
      >
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span className="mono" style={{ fontSize: 15, fontWeight: 600 }}>
              {approval.action.replace(/_/g, ' ')}
            </span>
            <RiskPill level={approval.risk_level} />
          </div>
          <div style={{ fontSize: 13, color: 'var(--color-ink-muted)', marginTop: 6 }}>
            Domain <span className="mono" style={{ color: 'var(--color-ink)' }}>{approval.domain}</span>
            {' · gated '}
            {formatWhen(approval.created_at)}
          </div>
        </div>

        <div style={{ textAlign: 'right' }}>
          <div className="label">Estimated daily loss</div>
          <div
            className="mono"
            style={{ fontSize: 20, color: 'var(--color-risk-high)', marginTop: 4 }}
          >
            {formatUsd(approval.expected_loss_usd)}
          </div>
        </div>
      </div>

      <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--color-line)' }}>
        <div className="label">Engine reasoning</div>
        <p style={{ fontSize: 13, color: 'var(--color-ink-muted)', marginTop: 6 }}>
          {approval.reason}
        </p>
      </div>

      <div style={{ padding: '16px 20px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span className="label">Diagnosis</span>
          {approval.diagnosis_source ? (
            <span
              className="mono"
              style={{
                fontSize: 9,
                letterSpacing: '0.1em',
                padding: '2px 6px',
                color:
                  approval.diagnosis_source === 'llm'
                    ? 'var(--color-accent)'
                    : 'var(--color-ink-faint)',
                border: `1px solid ${
                  approval.diagnosis_source === 'llm'
                    ? 'var(--color-accent-dim)'
                    : 'var(--color-line-strong)'
                }`,
              }}
              title={
                approval.diagnosis_source === 'llm'
                  ? 'Written by the diagnosis model from your telemetry'
                  : 'Generated locally from the numbers — the model was unavailable or over budget'
              }
            >
              {approval.diagnosis_source === 'llm' ? 'AI ANALYSIS' : 'LOCAL FALLBACK'}
            </span>
          ) : null}
        </div>

        <div
          style={{
            fontSize: 13.5,
            lineHeight: 1.65,
            color: 'var(--color-ink)',
            marginTop: 10,
            whiteSpace: 'pre-wrap',
          }}
        >
          {approval.diagnosis ?? (
            <span style={{ color: 'var(--color-ink-faint)' }}>
              Diagnosis pending — the agent is still analysing this decision.
            </span>
          )}
        </div>
      </div>

      <form
        action={action}
        style={{
          padding: '14px 20px',
          borderTop: '1px solid var(--color-line)',
          background: 'var(--color-surface-raised)',
          display: 'flex',
          flexDirection: 'column',
          gap: 12,
        }}
      >
        {state?.error ? <ErrorNote message={state.error} /> : null}
        <input type="hidden" name="approval_id" value={approval.id} />

        {canResolve ? (
          <div style={{ display: 'flex', gap: 10 }}>
            <SubmitButton
              name="decision"
              value="approved"
              pendingLabel="Approving…"
              variant="primary"
            >
              Approve
            </SubmitButton>
            <SubmitButton
              name="decision"
              value="rejected"
              pendingLabel="Rejecting…"
              variant="danger"
            >
              Reject
            </SubmitButton>
          </div>
        ) : (
          <p style={{ fontSize: 12, color: 'var(--color-ink-faint)' }}>
            Only an organization owner can approve or reject this action.
          </p>
        )}
      </form>
    </article>
  )
}
