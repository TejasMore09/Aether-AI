import Link from 'next/link'

/**
 * Instrument primitives.
 *
 * Flat panels with a single hairline border, no shadows, no radius beyond 4px.
 * Everything here optimises for one thing: how fast a reader can find the row
 * that is wrong.
 */

export function Panel({
  className = '',
  children,
}: {
  className?: string
  children: React.ReactNode
}) {
  return (
    <div
      className={`border ${className}`}
      style={{ background: 'var(--steel-900)', borderColor: 'var(--line)' }}
    >
      {children}
    </div>
  )
}

export function PanelHead({
  title,
  aside,
}: {
  title: string
  aside?: React.ReactNode
}) {
  return (
    <div
      className="flex items-center justify-between gap-4 border-b px-4 py-[10px]"
      style={{ borderColor: 'var(--line)', background: 'var(--steel-850)' }}
    >
      <h2
        className="text-[11px] font-semibold uppercase tracking-[0.13em]"
        style={{ color: 'var(--ink-soft)' }}
      >
        {title}
      </h2>
      {aside}
    </div>
  )
}

export function PageHead({
  title,
  lede,
  aside,
}: {
  title: string
  lede?: string
  aside?: React.ReactNode
}) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="text-[20px] font-semibold tracking-[-0.01em]">{title}</h1>
        {lede && (
          <p className="mt-[6px] max-w-[76ch] text-[13px]" style={{ color: 'var(--ink-soft)' }}>
            {lede}
          </p>
        )}
      </div>
      {aside}
    </div>
  )
}

/** A count with a label. The number is the message; the label is the caption. */
export function Stat({
  label,
  value,
  tone = 'plain',
  suffix,
}: {
  label: string
  value: string | number
  tone?: Tone
  suffix?: string
}) {
  return (
    <div className="px-4 py-[14px]">
      <p
        className="text-[10.5px] font-medium uppercase tracking-[0.12em]"
        style={{ color: 'var(--ink-faint)' }}
      >
        {label}
      </p>
      <p className="tnum mt-[6px] text-[22px] font-semibold" style={{ color: toneColor(tone) }}>
        {value}
        {suffix && (
          <span className="ml-1 text-[12px] font-normal" style={{ color: 'var(--ink-faint)' }}>
            {suffix}
          </span>
        )}
      </p>
    </div>
  )
}

export type Tone = 'plain' | 'ok' | 'attention' | 'critical' | 'breach'

export function toneColor(tone: Tone): string {
  switch (tone) {
    case 'ok':
      return 'var(--ok)'
    case 'attention':
      return 'var(--attention)'
    case 'critical':
      return 'var(--critical)'
    case 'breach':
      return 'var(--breach)'
    default:
      return 'var(--ink)'
  }
}

export function Tag({ tone = 'plain', children }: { tone?: Tone; children: React.ReactNode }) {
  return (
    <span
      className="inline-flex items-center rounded-[3px] px-[6px] py-[2px] text-[10.5px] font-semibold uppercase tracking-[0.09em]"
      style={{
        color: toneColor(tone),
        background: `color-mix(in srgb, ${toneColor(tone)} 14%, transparent)`,
      }}
    >
      {children}
    </span>
  )
}

export function Empty({ title, body }: { title: string; body: string }) {
  return (
    <div className="px-4 py-10 text-center">
      <p className="text-[13.5px] font-medium">{title}</p>
      <p
        className="mx-auto mt-[6px] max-w-[52ch] text-[12.5px] leading-relaxed"
        style={{ color: 'var(--ink-faint)' }}
      >
        {body}
      </p>
    </div>
  )
}

export function ErrorNote({ message }: { message: string }) {
  return (
    <div
      className="border px-4 py-3 text-[13px]"
      style={{
        borderColor: 'color-mix(in srgb, var(--critical) 40%, transparent)',
        background: 'color-mix(in srgb, var(--critical) 8%, transparent)',
        color: 'var(--critical)',
      }}
    >
      {message}
    </div>
  )
}

export function TenantLink({ id, name, slug }: { id: string; name: string; slug: string }) {
  return (
    <Link href={`/tenants/${id}`} className="group min-w-0 block">
      <span className="block truncate text-[13.5px] font-medium group-hover:underline">
        {name}
      </span>
      <span className="mono block truncate text-[11px]" style={{ color: 'var(--ink-faint)' }}>
        {slug}
      </span>
    </Link>
  )
}

// ── Formatting ───────────────────────────────────────────────────────────────

export function whenUTC(iso: string): string {
  return `${iso.slice(0, 10)} ${iso.slice(11, 16)}`
}

/** "4m ago" — relative is what an operator actually wants for freshness. */
export function ago(iso: string | null): string {
  if (!iso) return 'never'
  const seconds = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000)
  if (seconds < 90) return `${Math.round(seconds)}s ago`
  const minutes = seconds / 60
  if (minutes < 90) return `${Math.round(minutes)}m ago`
  const hours = minutes / 60
  if (hours < 36) return `${Math.round(hours)}h ago`
  return `${Math.round(hours / 24)}d ago`
}

/**
 * Money, in the currency the business actually uses.
 *
 * `Intl.NumberFormat` already knows every rule this needs, including that an
 * Indian reader writes ₹1,50,000 rather than ₹150,000 — so the locale follows
 * the currency instead of being pinned to en-US, which is what made every
 * figure here a dollar amount regardless of who was reading it.
 *
 * Nothing converts. The amount arrives in the tenant's own currency and is
 * only being written down; see platform/src/aether/core/money.py for why an
 * FX rate is a liability rather than a feature.
 */
const LOCALE: Record<string, string> = {
  INR: 'en-IN', // lakh and crore grouping
  USD: 'en-US',
  EUR: 'en-IE',
  GBP: 'en-GB',
}

export function money(value: number, currency = 'USD', decimals = 2): string {
  const code = (currency || 'USD').toUpperCase()
  try {
    return new Intl.NumberFormat(LOCALE[code] ?? 'en-US', {
      style: 'currency',
      currency: code,
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
    }).format(value)
  } catch {
    // An unknown code should cost a symbol, never a rendered page.
    return `${value.toLocaleString('en-US', {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
    })} ${code}`
  }
}

/** Platform spend, which genuinely is billed to us in dollars. */
export function usd(value: number, decimals = 2): string {
  return money(value, 'USD', decimals)
}
