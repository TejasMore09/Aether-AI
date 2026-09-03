'use client'

import Link from 'next/link'
import { useActionState, useEffect, useState } from 'react'

import { AuthField, AuthSelect, AuthShell, AuthSubmit } from '@/components/AuthShell'
import { signup } from '@/lib/actions'
import type { SectorOption } from '@/lib/api'

const CURRENCIES = [
  { value: 'INR', label: 'Indian rupee (INR)' },
  { value: 'USD', label: 'US dollar (USD)' },
  { value: 'EUR', label: 'Euro (EUR)' },
  { value: 'GBP', label: 'Pound sterling (GBP)' },
]

export default function SignupPage() {
  const [state, action] = useActionState(signup, null)
  const [sectors, setSectors] = useState<SectorOption[]>([])
  const [chosen, setChosen] = useState('other')

  // Fetched rather than baked in: the catalogue is the platform's answer to
  // what it can and cannot judge, and a copy here would drift from it.
  useEffect(() => {
    fetch('/api/sectors')
      .then((r) => (r.ok ? r.json() : []))
      .then(setSectors)
      .catch(() => setSectors([]))
  }, [])

  const picked = sectors.find((s) => s.key === chosen)

  return (
    <AuthShell
      title="Create your organization"
      lede="Your data lives in its own isolated tenant from the first reading. You become its owner."
      footer={
        <>
          Already have an account?{' '}
          <Link href="/login" style={{ color: 'var(--color-copper)' }}>
            Sign in
          </Link>
          {' · '}
          <Link href="/explore" style={{ color: 'var(--color-ink-faint)' }}>
            See it without signing up
          </Link>
        </>
      }
      error={state?.error}
      action={action}
    >
      <AuthField label="Organization name" name="org_name" placeholder="Kestrel Joinery" required />
      <AuthField
        label="Organization slug"
        name="org_slug"
        placeholder="kestrel"
        pattern="[a-z0-9][a-z0-9\-]*"
        title="Lowercase letters, numbers and dashes"
        hint="Used in your sign-in and API calls"
        required
      />
      <AuthField label="Your name" name="display_name" />
      <AuthSelect
        label="Currency"
        name="currency"
        defaultValue="INR"
        options={CURRENCIES}
        hint="What your figures are counted in. Nothing is ever converted."
      />
      {sectors.length > 0 ? (
        <AuthSelect
          label="What kind of business is this?"
          name="sector"
          defaultValue="other"
          onChange={(e) => setChosen(e.target.value)}
          options={sectors.map((s) => ({ value: s.key, label: s.label }))}
          hint={picked ? <SectorEffect sector={picked} /> : 'You can change this later.'}
        />
      ) : null}
      <AuthField label="Work email" name="email" type="email" autoComplete="username" required />
      <AuthField
        label="Password"
        name="password"
        type="password"
        autoComplete="new-password"
        minLength={10}
        hint="At least 10 characters"
        required
      />
      <AuthSubmit pending="Creating…">Create organization</AuthSubmit>
    </AuthShell>
  )
}

/**
 * What the choice actually does, said before it is made.
 *
 * A dropdown that silently changes how a business is judged is worse than no
 * dropdown. Choosing Retail is agreeing to a stricter collection standard than
 * the default; choosing Marketing changes nothing at all. Both are stated —
 * including, deliberately, that the figures behind them describe US public
 * companies rather than businesses like this one.
 */
function SectorEffect({ sector }: { sector: SectorOption }) {
  if (sector.changes_nothing) {
    return (
      <>
        {sector.summary}
        {sector.bands_note ? (
          <>
            {' '}
            <span style={{ color: 'var(--color-ink-soft)' }}>{sector.bands_note}</span>
          </>
        ) : null}
      </>
    )
  }
  return (
    <>
      {sector.summary}{' '}
      {sector.changes.map((c) => (
        <span key={`${c.domain}.${c.metric}`} style={{ color: 'var(--color-ink-soft)' }}>
          {c.metric_label} healthy below {c.sector_good}
          {c.unit === 'ratio' ? '' : ` ${c.unit}`} rather than {c.pack_good}
          {c.stricter ? ' — stricter than the default.' : ' — more room than the default.'}{' '}
        </span>
      ))}
      <span style={{ color: 'var(--color-ink-faint)' }}>{sector.source_note}</span>
    </>
  )
}
