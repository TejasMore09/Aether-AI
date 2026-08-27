'use client'

import { useState } from 'react'
import { toast } from 'sonner'

import { evaluateNow, setMonitoring } from '@/lib/actions'

/** Run the full monitor cycle on demand — same durable workflow the schedule uses. */
export function RunNow({ domain }: { domain: string }) {
  const [busy, setBusy] = useState(false)

  async function run() {
    setBusy(true)
    const form = new FormData()
    form.set('domain', domain)
    const result = await evaluateNow(null, form)
    setBusy(false)
    if (result?.error) toast.message(result.error)
    else toast.success('Run complete', { description: 'Any decision it reached is recorded.' })
  }

  return (
    <button
      type="button"
      onClick={run}
      disabled={busy}
      className="rounded-[13px] px-5 py-[11px] text-[13.5px] font-semibold transition-[box-shadow,color] duration-200 ease-[var(--ease-forge)] active:shadow-[var(--press)] disabled:opacity-60"
      style={{
        background: 'var(--color-raised)',
        boxShadow: 'var(--raise-sm)',
        color: 'var(--color-copper)',
      }}
    >
      {busy ? 'Running…' : 'Run now'}
    </button>
  )
}

export function MonitoringControls({ domain }: { domain: string }) {
  const [busy, setBusy] = useState(false)
  const [interval, setIntervalMins] = useState(60)

  async function apply(enable: boolean) {
    setBusy(true)
    const form = new FormData()
    form.set('domain', domain)
    form.set('enable', String(enable))
    form.set('interval_minutes', String(interval))
    const result = await setMonitoring(null, form)
    setBusy(false)
    if (result?.error) toast.error(result.error)
    else if (enable)
      toast.success('Monitoring on', { description: `Checking every ${interval} minutes.` })
    else toast.success('Monitoring off')
  }

  return (
    <div
      className="rounded-[20px] p-6"
      style={{ background: 'var(--color-raised)', boxShadow: 'var(--raise)' }}
    >
      <h3 className="text-[15px] font-semibold tracking-[-0.01em]">Autonomous monitoring</h3>
      <p className="mb-5 mt-2 max-w-[52ch] text-[13px]" style={{ color: 'var(--color-ink-soft)' }}>
        Your agent checks this domain on a schedule and holds high-risk actions for you.
      </p>

      <label className="block">
        <span className="block text-[12.5px] font-medium" style={{ color: 'var(--color-ink-soft)' }}>
          Check every
        </span>
        <span className="mt-2 flex items-center gap-3">
          <input
            type="number"
            min={5}
            max={1440}
            value={interval}
            onChange={(e) => setIntervalMins(Number(e.target.value))}
            className="tnum w-[110px] rounded-[11px] px-3 py-[10px] text-[14px] outline-none"
            style={{
              background: 'var(--color-ground)',
              boxShadow: 'var(--press-sm)',
              color: 'var(--color-ink)',
            }}
          />
          <span className="text-[13px]" style={{ color: 'var(--color-ink-faint)' }}>
            minutes
          </span>
        </span>
      </label>

      <div className="mt-5 flex flex-wrap gap-3">
        <button
          type="button"
          onClick={() => apply(true)}
          disabled={busy}
          className="rounded-[13px] px-5 py-[11px] text-[13.5px] font-semibold transition-[box-shadow,color] duration-200 ease-[var(--ease-forge)] active:shadow-[var(--press)] disabled:opacity-60"
          style={{
            background: 'var(--color-raised)',
            boxShadow: 'var(--raise-sm)',
            color: 'var(--color-copper)',
          }}
        >
          Turn on
        </button>
        <button
          type="button"
          onClick={() => apply(false)}
          disabled={busy}
          className="rounded-[13px] px-5 py-[11px] text-[13.5px] font-medium transition-[box-shadow,color] duration-200 ease-[var(--ease-forge)] active:shadow-[var(--press)] disabled:opacity-60"
          style={{
            background: 'var(--color-raised)',
            boxShadow: 'var(--raise-sm)',
            color: 'var(--color-ink-soft)',
          }}
        >
          Turn off
        </button>
      </div>
    </div>
  )
}
