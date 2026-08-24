/**
 * Shared presentational pieces. Server components by default — none of these
 * need interactivity, so none ship JavaScript to the browser.
 */

const RISK_STYLES: Record<string, { color: string; bg: string }> = {
  HIGH: { color: 'var(--color-risk-high)', bg: 'var(--color-risk-high-dim)' },
  MEDIUM: { color: 'var(--color-risk-medium)', bg: 'var(--color-risk-medium-dim)' },
  LOW: { color: 'var(--color-risk-low)', bg: 'var(--color-risk-low-dim)' },
}

export function RiskPill({ level }: { level: string }) {
  const style = RISK_STYLES[level] ?? {
    color: 'var(--color-ink-muted)',
    bg: 'var(--color-surface-raised)',
  }
  return (
    <span
      className="mono"
      style={{
        color: style.color,
        background: style.bg,
        fontSize: 10,
        fontWeight: 600,
        letterSpacing: '0.1em',
        padding: '3px 8px',
      }}
    >
      {level}
    </span>
  )
}

export function ActionTag({ action }: { action: string }) {
  const isAct = action === 'RETRAIN' || action === 'FLAG_ANOMALY'
  return (
    <span
      className="mono"
      style={{
        fontSize: 11,
        fontWeight: 600,
        color: isAct ? 'var(--color-ink)' : 'var(--color-ink-muted)',
      }}
    >
      {action.replace(/_/g, ' ')}
    </span>
  )
}

export function Stat({
  label,
  value,
  hint,
  tone,
}: {
  label: string
  value: string
  hint?: string
  tone?: 'high' | 'accent' | 'plain'
}) {
  const color =
    tone === 'high'
      ? 'var(--color-risk-high)'
      : tone === 'accent'
        ? 'var(--color-accent)'
        : 'var(--color-ink)'
  return (
    <div className="card" style={{ padding: 20 }}>
      <div className="label">{label}</div>
      <div
        className="mono"
        style={{ fontSize: 28, marginTop: 10, color, lineHeight: 1.1 }}
      >
        {value}
      </div>
      {hint ? (
        <div style={{ fontSize: 12, color: 'var(--color-ink-faint)', marginTop: 6 }}>
          {hint}
        </div>
      ) : null}
    </div>
  )
}

export function EmptyState({ title, body }: { title: string; body: string }) {
  return (
    <div
      className="card"
      style={{ padding: 40, textAlign: 'center', color: 'var(--color-ink-muted)' }}
    >
      <div style={{ fontSize: 15, color: 'var(--color-ink)', marginBottom: 6 }}>{title}</div>
      <div style={{ fontSize: 13, maxWidth: '52ch', margin: '0 auto' }}>{body}</div>
    </div>
  )
}

export function ErrorNote({ message }: { message: string }) {
  return (
    <div
      role="alert"
      style={{
        borderLeft: '2px solid var(--color-risk-high)',
        background: 'var(--color-risk-high-dim)',
        color: 'var(--color-risk-high)',
        padding: '10px 14px',
        fontSize: 13,
      }}
    >
      {message}
    </div>
  )
}

export function PageHeader({
  title,
  subtitle,
  right,
}: {
  title: string
  subtitle?: string
  right?: React.ReactNode
}) {
  return (
    <header
      style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'flex-end',
        gap: 24,
        borderBottom: '1px solid var(--color-line)',
        paddingBottom: 16,
        marginBottom: 28,
      }}
    >
      <div>
        <h1 style={{ fontSize: 24, fontWeight: 600, letterSpacing: '-0.01em' }}>{title}</h1>
        {subtitle ? (
          <p style={{ color: 'var(--color-ink-muted)', fontSize: 14, marginTop: 6 }}>
            {subtitle}
          </p>
        ) : null}
      </div>
      {right}
    </header>
  )
}

export function formatUsd(value: number): string {
  return `$${value.toLocaleString('en-US', { maximumFractionDigits: 2 })}`
}

export function formatWhen(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  return date.toISOString().slice(0, 16).replace('T', ' ') + ' UTC'
}
