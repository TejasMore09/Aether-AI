'use client'

import { motion, useReducedMotion } from 'framer-motion'
import { useState } from 'react'
import { toast } from 'sonner'

import { submitReading } from '@/lib/actions'
import type { DomainPack, MetricSpec, QualityIssue } from '@/lib/api'

/**
 * The reading form is generated from the domain pack, not written per domain:
 * fields, required flags, step sizes and healthy hints all come from the
 * catalogue. Adding a business function ships a YAML file and this adapts —
 * the same constraint the backend holds itself to.
 *
 * The quality gate's verdict is shown to whoever entered the data, because a
 * rejected reading is a fact they need immediately, with the reason.
 */

function hint(metric: MetricSpec): string {
  const [min, max] = metric.healthy_range
  const unit = metric.unit === 'days' ? ' days' : metric.unit === 'ratio' ? '' : ''
  if (max !== null && max !== undefined) return `healthy below ${max}${unit}`
  if (min !== null && min !== undefined) return `healthy above ${min}${unit}`
  return 'context only'
}

function step(metric: MetricSpec): string {
  if (metric.unit === 'ratio') return '0.01'
  if (metric.unit === 'currency' || metric.unit === 'count') return '1'
  return '0.1'
}

type Verdict =
  | { kind: 'accepted'; performance?: number; warnings: QualityIssue[] }
  | { kind: 'quarantined'; errors: QualityIssue[] }
  | null

export function ReadingForm({ domain, pack }: { domain: string; pack: DomainPack }) {
  const [busy, setBusy] = useState(false)
  const [verdict, setVerdict] = useState<Verdict>(null)
  const reduced = useReducedMotion()

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setBusy(true)
    setVerdict(null)

    const form = new FormData(event.currentTarget)
    form.set('domain', domain)
    const result = await submitReading(null, form)
    setBusy(false)

    if (!result || !result.ok) {
      toast.error(result?.ok === false ? result.error : 'That reading could not be sent.')
      return
    }

    if (result.accepted) {
      setVerdict({
        kind: 'accepted',
        performance: result.performance,
        warnings: result.issues.filter((i) => i.severity === 'warning'),
      })
      toast.success('Reading accepted', {
        description:
          typeof result.performance === 'number'
            ? `Health scored ${Math.round(result.performance * 100)}%.`
            : undefined,
      })
    } else {
      const errors = result.issues.filter((i) => i.severity === 'error')
      setVerdict({ kind: 'quarantined', errors })
      toast.error('Reading quarantined', {
        description: 'It will not affect any decision. See the reason below.',
      })
    }
  }

  return (
    <form
      onSubmit={onSubmit}
      className="rounded-[20px] p-6"
      style={{ background: 'var(--color-raised)', boxShadow: 'var(--raise)' }}
    >
      <h3 className="text-[15px] font-semibold tracking-[-0.01em]">Send a reading</h3>
      <p className="mt-2 max-w-[62ch] text-[13px]" style={{ color: 'var(--color-ink-soft)' }}>
        {pack.summary}
      </p>
      <p className="mb-6 mt-2 text-[12px]" style={{ color: 'var(--color-ink-faint)' }}>
        Leave a field blank if you do not track it — blank means not reported, not zero.
      </p>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {pack.metrics.map((metric) => (
          <label key={metric.key} className="block" title={metric.description}>
            <span className="block text-[12.5px] font-medium" style={{ color: 'var(--color-ink-soft)' }}>
              {metric.label}
              {metric.required ? (
                <span style={{ color: 'var(--color-risk)' }} aria-hidden="true">
                  {' '}
                  *
                </span>
              ) : null}
            </span>
            <input
              type="number"
              inputMode="decimal"
              step={step(metric)}
              name={`metric:${metric.key}`}
              required={metric.required}
              aria-required={metric.required}
              aria-describedby={`hint-${metric.key}`}
              className="tnum mt-2 w-full rounded-[11px] px-3 py-[10px] text-[14px] outline-none"
              style={{
                background: 'var(--color-ground)',
                boxShadow: 'var(--press-sm)',
                color: 'var(--color-ink)',
              }}
            />
            <span
              id={`hint-${metric.key}`}
              className="mt-[6px] block text-[11px]"
              style={{ color: 'var(--color-ink-faint)' }}
            >
              {hint(metric)}
            </span>
          </label>
        ))}
      </div>

      <button
        type="submit"
        disabled={busy}
        className="mt-6 rounded-[14px] px-6 py-3 text-sm font-semibold transition-[box-shadow,color] duration-200 ease-[var(--ease-forge)] active:shadow-[var(--press)] disabled:cursor-not-allowed disabled:opacity-60"
        style={{
          background: 'var(--color-raised)',
          boxShadow: 'var(--raise-sm)',
          color: 'var(--color-copper)',
        }}
      >
        {busy ? 'Checking…' : 'Send reading'}
      </button>

      {verdict ? (
        <motion.div
          initial={reduced ? false : { opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
          role={verdict.kind === 'quarantined' ? 'alert' : 'status'}
          className="mt-5 rounded-[13px] px-4 py-3 text-[13.5px]"
          style={{ background: 'var(--color-ground)', boxShadow: 'var(--press)' }}
        >
          {verdict.kind === 'accepted' ? (
            <>
              <strong style={{ color: 'var(--color-good)' }}>Accepted.</strong>{' '}
              {typeof verdict.performance === 'number' ? (
                <span style={{ color: 'var(--color-ink-soft)' }}>
                  Health scored {Math.round(verdict.performance * 100)}%.
                </span>
              ) : null}
              {verdict.warnings.length > 0 ? (
                <ul className="mt-2 list-disc pl-5" style={{ color: 'var(--color-warn)' }}>
                  {verdict.warnings.map((w, i) => (
                    <li key={i}>{w.message}</li>
                  ))}
                </ul>
              ) : null}
            </>
          ) : (
            <>
              <strong style={{ color: 'var(--color-risk)' }}>
                Quarantined — this will not affect any decision.
              </strong>
              <ul className="mt-2 list-disc pl-5" style={{ color: 'var(--color-ink-soft)' }}>
                {verdict.errors.map((e, i) => (
                  <li key={i} className="mb-1">
                    {e.message}
                  </li>
                ))}
              </ul>
            </>
          )}
        </motion.div>
      ) : null}
    </form>
  )
}
