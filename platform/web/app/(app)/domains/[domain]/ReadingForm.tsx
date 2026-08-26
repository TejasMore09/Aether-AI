'use client'

import { useActionState } from 'react'

import { submitReading, type ReadingState } from '@/lib/actions'
import { SubmitButton } from '@/components/SubmitButton'
import type { DomainPack, MetricSpec, QualityIssue } from '@/lib/api'

/**
 * The reading form is generated from the domain pack, not hand-written per
 * domain. Adding a business function ships a YAML file and this form adapts —
 * the same constraint the backend holds itself to.
 */

function healthyHint(metric: MetricSpec): string {
  const [min, max] = metric.healthy_range
  if (max !== null && max !== undefined) return `healthy below ${max}${unitSuffix(metric)}`
  if (min !== null && min !== undefined) return `healthy above ${min}${unitSuffix(metric)}`
  return 'context only'
}

function unitSuffix(metric: MetricSpec): string {
  if (metric.unit === 'ratio') return ''
  if (metric.unit === 'days') return ' days'
  return metric.unit ? ` ${metric.unit}` : ''
}

function stepFor(metric: MetricSpec): string {
  if (metric.unit === 'ratio') return '0.01'
  if (metric.unit === 'currency' || metric.unit === 'count') return '1'
  return '0.1'
}

export function ReadingForm({ domain, pack }: { domain: string; pack: DomainPack }) {
  const [state, action] = useActionState(submitReading, null)

  return (
    <form action={action} className="card" style={{ padding: 22 }}>
      <div className="label">Send a reading</div>
      <p style={{ fontSize: 13, color: 'var(--color-ink-muted)', margin: '8px 0 4px' }}>
        {pack.summary}
      </p>
      <p style={{ fontSize: 12, color: 'var(--color-ink-faint)', margin: '0 0 18px' }}>
        Leave a field blank if you do not track it — blank means &ldquo;not reported&rdquo;,
        not zero. Required fields are marked.
      </p>

      <input type="hidden" name="domain" value={domain} />

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(210px, 1fr))',
          gap: 14,
        }}
      >
        {pack.metrics.map((metric) => (
          <label key={metric.key} style={{ display: 'block' }} title={metric.description}>
            <span className="label" style={{ display: 'block' }}>
              {metric.label}
              {metric.required ? (
                <span style={{ color: 'var(--color-risk-high)' }}> *</span>
              ) : null}
            </span>
            <input
              className="field"
              style={{ marginTop: 6 }}
              type="number"
              inputMode="decimal"
              step={stepFor(metric)}
              name={`metric:${metric.key}`}
              required={metric.required}
              aria-describedby={`hint-${metric.key}`}
            />
            <span
              id={`hint-${metric.key}`}
              className="mono"
              style={{
                display: 'block',
                fontSize: 10,
                color: 'var(--color-ink-faint)',
                marginTop: 4,
              }}
            >
              {healthyHint(metric)}
            </span>
          </label>
        ))}
      </div>

      <div style={{ marginTop: 18 }}>
        <SubmitButton pendingLabel="Checking…">Send reading</SubmitButton>
      </div>

      {state ? <Verdict state={state} /> : null}
    </form>
  )
}

function Verdict({ state }: { state: NonNullable<ReadingState> }) {
  const s = state

  if (!s.ok) {
    return (
      <div role="alert" style={panel('var(--color-risk-high)', 'var(--color-risk-high-dim)')}>
        {s.error}
      </div>
    )
  }

  if (s.accepted) {
    const warnings = s.issues.filter((i) => i.severity === 'warning')
    return (
      <div role="status" style={panel('var(--color-risk-low)', 'var(--color-risk-low-dim)')}>
        <strong>Reading accepted.</strong>
        {typeof s.performance === 'number' ? (
          <> Health scored {Math.round(s.performance * 100)}%.</>
        ) : null}
        {warnings.length > 0 ? (
          <ul style={{ margin: '8px 0 0', paddingLeft: 18 }}>
            {warnings.map((w, i) => (
              <li key={i} style={{ color: 'var(--color-risk-medium)' }}>
                {w.message}
              </li>
            ))}
          </ul>
        ) : null}
      </div>
    )
  }

  return (
    <div role="alert" style={panel('var(--color-risk-high)', 'var(--color-risk-high-dim)')}>
      <strong>Reading quarantined — it will not affect any decision.</strong>
      <ul style={{ margin: '8px 0 0', paddingLeft: 18 }}>
        {s.issues
          .filter((i) => i.severity === 'error')
          .map((issue, i) => (
            <li key={i} style={{ marginBottom: 4 }}>
              {issue.message}
            </li>
          ))}
      </ul>
    </div>
  )
}

function panel(color: string, background: string): React.CSSProperties {
  return {
    marginTop: 16,
    borderLeft: `2px solid ${color}`,
    background,
    color,
    padding: '12px 16px',
    fontSize: 13,
    lineHeight: 1.5,
  }
}
