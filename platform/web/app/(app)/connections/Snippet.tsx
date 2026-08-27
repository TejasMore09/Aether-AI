'use client'

import { useState } from 'react'

import { PressButton } from '@/components/motion'

/**
 * A copyable command. Small on purpose: the integration docs are worth nothing
 * if the person has to hand-retype a curl invocation to test their key.
 */
export function Snippet({ code, label }: { code: string; label: string }) {
  const [copied, setCopied] = useState(false)

  async function copy() {
    try {
      await navigator.clipboard.writeText(code)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      setCopied(false)
    }
  }

  return (
    <div className="relative">
      <div
        className="overflow-x-auto rounded-[15px] px-5 py-[18px]"
        style={{ background: 'var(--color-deep)', boxShadow: 'var(--press-sm)' }}
      >
        <pre className="font-mono text-[12.5px] leading-[1.75]" style={{ color: 'var(--color-ink-soft)' }}>
          <code>{code}</code>
        </pre>
      </div>
      <PressButton
        type="button"
        onClick={copy}
        aria-label={`Copy ${label}`}
        className="absolute right-3 top-3 rounded-[9px] px-[11px] py-[5px] text-[11.5px] font-semibold"
        style={{
          background: 'var(--color-raised)',
          boxShadow: 'var(--raise-sm)',
          color: copied ? 'var(--color-good)' : 'var(--color-ink-faint)',
        }}
      >
        {copied ? 'Copied' : 'Copy'}
      </PressButton>
    </div>
  )
}
