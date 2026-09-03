import { cn } from '@/lib/utils'

/**
 * The Forge component layer.
 *
 * Every page composes from these rather than re-implementing its own cards and
 * tables, which is what made the previous UI feel assembled rather than
 * designed. Server components by default — none of these need interactivity,
 * so none ship JavaScript.
 *
 * The recurring technique is the Double Bezel: a soft outer shell holding an
 * inset inner core, with the inner radius mathematically derived from the
 * outer. That concentricity is most of why machined hardware looks machined,
 * and it is the detail cheap neumorphism always skips.
 */

/* ── Surfaces ─────────────────────────────────────────────────────────── */

export function Panel({
  className,
  children,
  tone = 'default',
  ...rest
}: React.ComponentProps<'div'> & { tone?: 'default' | 'risk' }) {
  return (
    <div
      className={cn('rounded-[20px] bg-raised p-6', className)}
      style={{
        background: 'var(--color-raised)',
        boxShadow: 'var(--raise)',
        ...(tone === 'risk' ? { borderLeft: '3px solid var(--color-risk)' } : null),
      }}
      {...rest}
    >
      {children}
    </div>
  )
}

/** Recessed well — for machine output, quoted values, anything "inside". */
export function Inset({ className, children, ...rest }: React.ComponentProps<'div'>) {
  return (
    <div
      className={cn('rounded-[13px] px-4 py-3', className)}
      style={{ background: 'var(--color-ground)', boxShadow: 'var(--press)' }}
      {...rest}
    >
      {children}
    </div>
  )
}

/**
 * The Double Bezel. Outer shell at radius R, inner core at R − padding, so the
 * curves stay concentric the way a lens sits in a barrel.
 */
export function Bezel({
  className,
  innerClassName,
  children,
  radius = 22,
  pad = 5,
}: {
  className?: string
  innerClassName?: string
  children: React.ReactNode
  radius?: number
  pad?: number
}) {
  return (
    <div
      className={cn('h-full', className)}
      style={{
        borderRadius: radius,
        padding: pad,
        background: 'var(--color-raised)',
        boxShadow: 'var(--raise)',
      }}
    >
      <div
        className={cn('h-full', innerClassName)}
        style={{
          borderRadius: radius - pad,
          background: 'var(--color-ground)',
          boxShadow: 'var(--press-sm)',
        }}
      >
        {children}
      </div>
    </div>
  )
}

/* ── Type ─────────────────────────────────────────────────────────────── */

export function Eyebrow({ children, className }: { children: React.ReactNode; className?: string }) {
  return <span className={cn('eyebrow', className)}>{children}</span>
}

export function PageTitle({
  title,
  lede,
  meta,
  action,
}: {
  title: string
  lede?: string
  meta?: string
  action?: React.ReactNode
}) {
  return (
    <header className="mb-8 flex flex-wrap items-end justify-between gap-6">
      <div>
        <h1
          className="max-w-[19ch] text-[clamp(1.75rem,3.4vw,2.5rem)] font-bold leading-[1.08] tracking-[-0.032em]"
          style={{ textWrap: 'balance' }}
        >
          {title}
        </h1>
        {lede ? (
          <p className="mt-3 max-w-[60ch] text-[15px]" style={{ color: 'var(--color-ink-soft)' }}>
            {lede}
          </p>
        ) : null}
        {meta ? (
          <p className="mt-3 text-[13px]" style={{ color: 'var(--color-ink-faint)' }}>
            {meta}
          </p>
        ) : null}
      </div>
      {action}
    </header>
  )
}

export function SectionTitle({ children }: { children: React.ReactNode }) {
  return <h2 className="mb-4 text-[15px] font-semibold tracking-[-0.01em]">{children}</h2>
}

/* ── Status ───────────────────────────────────────────────────────────── */

const RISK_COLOR: Record<string, string> = {
  HIGH: 'var(--color-risk)',
  MEDIUM: 'var(--color-warn)',
  LOW: 'var(--color-good)',
}

export function RiskPill({ level }: { level: string }) {
  const color = RISK_COLOR[level] ?? 'var(--color-ink-soft)'
  return (
    <span
      className="rounded-full px-3 py-[5px] text-[11px] font-bold tracking-[0.07em]"
      style={{ color, background: 'var(--color-ground)', boxShadow: 'var(--press-sm)' }}
    >
      {level}
    </span>
  )
}

/** A gauge whose true width is always correct; only a transform animates. */
export function Gauge({ pct, tone = 'good' }: { pct: number; tone?: 'good' | 'risk' | 'copper' }) {
  const width = `${Math.max(3, Math.min(100, pct))}%`
  const fill =
    tone === 'risk'
      ? 'linear-gradient(90deg, var(--color-risk-dim), var(--color-risk))'
      : tone === 'copper'
        ? 'linear-gradient(90deg, var(--color-copper-dim), var(--color-copper))'
        : 'linear-gradient(90deg, #5c7a4d, var(--color-good))'
  return (
    <span
      className="block h-[9px] overflow-hidden rounded-full"
      style={{ background: 'var(--color-ground)', boxShadow: 'var(--press-sm)' }}
    >
      <span
        className="block h-full rounded-full motion-safe:animate-[aether-fill-in_850ms_var(--ease-forge)]"
        style={{ width, background: fill, transformOrigin: 'left' }}
      />
    </span>
  )
}

/* ── Composed blocks ──────────────────────────────────────────────────── */

export function Figure({
  label,
  value,
  note,
  tone = 'plain',
  gauge,
}: {
  label: string
  value: React.ReactNode
  note?: string
  tone?: 'plain' | 'risk' | 'copper'
  gauge?: { pct: number; tone?: 'good' | 'risk' | 'copper' }
}) {
  const color =
    tone === 'risk'
      ? 'var(--color-risk)'
      : tone === 'copper'
        ? 'var(--color-copper)'
        : 'var(--color-ink)'
  return (
    <Panel className="flex flex-col gap-2 !p-[22px]">
      <span className="text-[13px] font-medium" style={{ color: 'var(--color-ink-soft)' }}>
        {label}
      </span>
      <span
        data-figure
        className="text-[37px] font-bold leading-[1.02] tracking-[-0.035em]"
        style={{ color }}
      >
        {value}
      </span>
      {gauge ? <Gauge pct={gauge.pct} tone={gauge.tone} /> : null}
      {note ? (
        <span className="text-[12.5px]" style={{ color: 'var(--color-ink-faint)' }}>
          {note}
        </span>
      ) : null}
    </Panel>
  )
}

export function EmptyState({
  title,
  body,
  action,
}: {
  title: string
  body: string
  action?: React.ReactNode
}) {
  return (
    <Bezel radius={20} pad={5}>
      <div className="flex flex-col items-center gap-3 px-8 py-14 text-center">
        <span
          className="grid h-11 w-11 place-items-center rounded-full"
          style={{ background: 'var(--color-raised)', boxShadow: 'var(--raise-sm)' }}
          aria-hidden="true"
        >
          <span
            className="block h-[6px] w-[6px] rounded-full"
            style={{ background: 'var(--color-ink-faint)' }}
          />
        </span>
        <p className="text-[15px] font-semibold">{title}</p>
        <p className="max-w-[52ch] text-[13.5px]" style={{ color: 'var(--color-ink-soft)' }}>
          {body}
        </p>
        {action ? <div className="mt-2">{action}</div> : null}
      </div>
    </Bezel>
  )
}

export function ErrorNote({ message }: { message: string }) {
  return (
    <div
      role="alert"
      className="rounded-[13px] px-4 py-3 text-[13.5px]"
      style={{
        background: 'var(--color-ground)',
        boxShadow: 'var(--press)',
        color: 'var(--color-risk)',
      }}
    >
      {message}
    </div>
  )
}

/* ── Formatting ───────────────────────────────────────────────────────── */

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

export function whenUTC(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return `${d.toISOString().slice(0, 16).replace('T', ' ')} UTC`
}
