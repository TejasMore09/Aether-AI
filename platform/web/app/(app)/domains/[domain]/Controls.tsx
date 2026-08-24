'use client'

import { useActionState } from 'react'

import { evaluateNow, pushObservation, setMonitoring } from '@/lib/actions'
import { SubmitButton } from '@/components/SubmitButton'
import { ErrorNote } from '@/components/ui'

export function MonitoringControls({ domain }: { domain: string }) {
  const [state, action] = useActionState(setMonitoring, null)

  return (
    <form action={action} className="card" style={{ padding: 20 }}>
      <div className="label">Autonomous monitoring</div>
      <p style={{ fontSize: 13, color: 'var(--color-ink-muted)', margin: '8px 0 14px' }}>
        Your agent evaluates this domain on a schedule and gates high-risk actions for you.
      </p>

      <input type="hidden" name="domain" value={domain} />

      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        {state?.error ? <ErrorNote message={state.error} /> : null}

        <label style={{ display: 'block' }}>
          <span className="label">Check every (minutes)</span>
          <input
            className="field"
            style={{ marginTop: 6, maxWidth: 160 }}
            type="number"
            name="interval_minutes"
            defaultValue={60}
            min={5}
            max={1440}
          />
        </label>

        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
          <SubmitButton name="enable" value="true" pendingLabel="Enabling…">
            Enable / update
          </SubmitButton>
          <SubmitButton
            name="enable"
            value="false"
            variant="ghost"
            pendingLabel="Disabling…"
          >
            Disable
          </SubmitButton>
        </div>
      </div>
    </form>
  )
}

export function PushObservation({ domain }: { domain: string }) {
  const [state, action] = useActionState(pushObservation, null)

  return (
    <form action={action} className="card" style={{ padding: 20 }}>
      <div className="label">Send a reading</div>
      <p style={{ fontSize: 13, color: 'var(--color-ink-muted)', margin: '8px 0 14px' }}>
        Normally a connector does this. Use it to test how your agent reacts.
      </p>

      <input type="hidden" name="domain" value={domain} />

      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        {state?.error ? <ErrorNote message={state.error} /> : null}

        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
          <label style={{ display: 'block' }}>
            <span className="label">Drift (0–1)</span>
            <input
              className="field"
              style={{ marginTop: 6, maxWidth: 120 }}
              type="number"
              name="drift_fraction"
              step="0.01"
              min="0"
              max="1"
              defaultValue="0.2"
              required
            />
          </label>
          <label style={{ display: 'block' }}>
            <span className="label">Performance (0–1)</span>
            <input
              className="field"
              style={{ marginTop: 6, maxWidth: 120 }}
              type="number"
              name="performance"
              step="0.01"
              min="0"
              max="1"
              defaultValue="0.9"
              required
            />
          </label>
        </div>

        <SubmitButton variant="ghost" pendingLabel="Sending…">
          Send reading
        </SubmitButton>
      </div>
    </form>
  )
}

export function EvaluateNow({ domain }: { domain: string }) {
  const [state, action] = useActionState(evaluateNow, null)

  return (
    <form action={action} style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      <input type="hidden" name="domain" value={domain} />
      {state?.error ? <ErrorNote message={state.error} /> : null}
      <SubmitButton variant="ghost" pendingLabel="Evaluating…">
        Evaluate now
      </SubmitButton>
    </form>
  )
}
