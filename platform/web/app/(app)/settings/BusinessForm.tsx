'use client'

import { useState } from 'react'
import { toast } from 'sonner'

import { Inset } from '@/components/forge'
import { PressButton } from '@/components/motion'
import { updateBusiness } from '@/lib/actions'
import type { SectorOption } from '@/lib/api'

const CURRENCIES = [
  { value: 'INR', label: 'Indian rupee (INR)' },
  { value: 'USD', label: 'US dollar (USD)' },
  { value: 'EUR', label: 'Euro (EUR)' },
  { value: 'GBP', label: 'Pound sterling (GBP)' },
]

/**
 * Changing what kind of business this is, with the consequence shown first.
 *
 * The whole component is organised around one thing: a person changing this
 * dropdown is changing how their business will be judged from now on, and they
 * should be able to see exactly how before they save. The preview updates as
 * they browse, so the comparison is between what they have and what they would
 * get — not a description they have to trust.
 *
 * The two facts a vendor would leave out are on the page. That these figures
 * describe US public companies rather than businesses like theirs, and that
 * for some sectors there is no figure at all.
 */
export function BusinessForm({
  sectors,
  currentSector,
  currentCurrency,
  canEdit,
}: {
  sectors: SectorOption[]
  currentSector: string
  currentCurrency: string
  canEdit: boolean
}) {
  const [sector, setSector] = useState(currentSector)
  const [currency, setCurrency] = useState(currentCurrency)
  const [saving, setSaving] = useState(false)

  const picked = sectors.find((s) => s.key === sector)
  const dirty = sector !== currentSector || currency !== currentCurrency

  async function save() {
    if (saving || !dirty) return
    setSaving(true)
    const result = await updateBusiness(sector, currency)
    setSaving(false)
    if (result?.error) {
      toast.error(result.error)
      return
    }
    toast.success('Saved. New readings will be judged against this.')
  }

  return (
    <div className="px-4 py-4">
      <div className="grid gap-4 md:grid-cols-2">
        <Field label="What kind of business is this?">
          <select
            value={sector}
            disabled={!canEdit}
            onChange={(e) => setSector(e.target.value)}
            className="w-full rounded-[10px] px-3 py-[9px] text-[14px] outline-none"
            style={{ background: 'var(--color-ground)', boxShadow: 'var(--press-sm)' }}
          >
            {sectors.map((s) => (
              <option key={s.key} value={s.key}>
                {s.label}
              </option>
            ))}
          </select>
        </Field>

        <Field label="Currency">
          <select
            value={currency}
            disabled={!canEdit}
            onChange={(e) => setCurrency(e.target.value)}
            className="w-full rounded-[10px] px-3 py-[9px] text-[14px] outline-none"
            style={{ background: 'var(--color-ground)', boxShadow: 'var(--press-sm)' }}
          >
            {CURRENCIES.map((c) => (
              <option key={c.value} value={c.value}>
                {c.label}
              </option>
            ))}
          </select>
        </Field>
      </div>

      {picked ? <Effect sector={picked} /> : null}

      {canEdit ? (
        <div className="mt-4 flex items-center gap-3">
          <PressButton onClick={save} disabled={!dirty || saving}>
            {saving ? 'Saving…' : 'Save'}
          </PressButton>
          {dirty ? (
            <span className="text-[12px]" style={{ color: 'var(--color-ink-faint)' }}>
              Readings already stored keep the band they were judged against. Only new
              readings change.
            </span>
          ) : null}
        </div>
      ) : (
        <p className="mt-4 text-[12.5px]" style={{ color: 'var(--color-ink-faint)' }}>
          Only an owner can change this — it moves the thresholds every future reading is
          judged against.
        </p>
      )}
    </div>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-2 block text-[12.5px] font-medium" style={{ color: 'var(--color-ink-soft)' }}>
        {label}
      </span>
      {children}
    </label>
  )
}

function Effect({ sector }: { sector: SectorOption }) {
  return (
    <Inset className="mt-4">
      <p className="text-[13px]">{sector.summary}</p>

      {sector.changes_nothing ? (
        <p className="mt-2 text-[13px]" style={{ color: 'var(--color-ink-soft)' }}>
          <strong>No sector adjustment applies.</strong> {sector.bands_note}
        </p>
      ) : (
        <>
          <ul className="mt-2 space-y-[6px]">
            {sector.changes.map((c) => (
              <li key={`${c.domain}.${c.metric}`} className="text-[13px]">
                <span style={{ color: 'var(--color-ink-soft)' }}>{c.domain_label}:</span>{' '}
                {c.metric_label} healthy below{' '}
                <span className="tnum font-semibold">
                  {c.sector_good}
                  {c.unit === 'ratio' ? '' : ` ${c.unit}`}
                </span>{' '}
                <span style={{ color: 'var(--color-ink-faint)' }}>
                  (default {c.pack_good}
                  {c.unit === 'ratio' ? '' : ` ${c.unit}`}
                  {c.stricter ? ' — stricter' : ' — more room'})
                </span>
              </li>
            ))}
          </ul>
          <p className="mt-2 text-[12px]" style={{ color: 'var(--color-ink-faint)' }}>
            {sector.source_note}
          </p>
        </>
      )}
    </Inset>
  )
}
