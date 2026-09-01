import { Inset, usd } from '@/components/forge'
import type { CrossDomainFinding } from '@/lib/api'

/**
 * Problems that span more than one part of the business.
 *
 * Given its own treatment above everything else, and deliberately unlike a
 * per-domain card. The whole value of this section is the claim that two
 * symptoms are one problem, and rendering it in the same shape as the
 * single-domain findings underneath would bury the only thing that makes it
 * worth reading.
 *
 * The mechanism is shown in full rather than truncated behind a link. It is
 * the reasoning, not decoration — a customer who cannot see why we think two
 * numbers are connected has been asked to take it on trust, which is the
 * opposite of what this product is for.
 */
export function ConnectedProblems({ findings }: { findings: CrossDomainFinding[] }) {
  if (findings.length === 0) return null

  return (
    <section className="mb-11">
      <div className="mb-4 flex flex-wrap items-baseline justify-between gap-3">
        <h2 className="text-[15px] font-semibold tracking-[-0.01em]">
          {findings.length === 1 ? 'A connected problem' : 'Connected problems'}
        </h2>
        <p className="text-[12.5px]" style={{ color: 'var(--color-ink-faint)' }}>
          Spanning more than one part of the business
        </p>
      </div>

      <ul className="grid gap-4">
        {findings.map((finding) => (
          <Finding key={finding.relation_id} finding={finding} />
        ))}
      </ul>
    </section>
  )
}

function Finding({ finding }: { finding: CrossDomainFinding }) {
  const urgent = finding.requires_approval || finding.inherited_risk_level === 'HIGH'

  return (
    <li
      className="rounded-[20px] p-7"
      style={{
        background: 'var(--color-raised)',
        boxShadow: 'var(--raise)',
        borderLeft: `3px solid ${urgent ? 'var(--color-risk)' : 'var(--color-copper)'}`,
      }}
    >
      <div className="flex flex-wrap items-center gap-[10px]">
        {finding.domains.map((domain) => (
          <span
            key={domain}
            className="rounded-[7px] px-2 py-[3px] text-[11px] font-semibold uppercase tracking-[0.09em]"
            style={{ background: 'var(--color-ground)', color: 'var(--color-ink-faint)' }}
          >
            {domain.replace(/_/g, ' ')}
          </span>
        ))}
        {finding.requires_approval && (
          <span
            className="rounded-[7px] px-2 py-[3px] text-[11px] font-semibold uppercase tracking-[0.09em]"
            style={{ background: 'var(--color-ground)', color: 'var(--color-risk)' }}
          >
            Needs your decision
          </span>
        )}
      </div>

      <h3 className="mt-[14px] text-[19px] font-bold tracking-[-0.015em]">{finding.label}</h3>

      <p
        className="mt-[10px] max-w-[74ch] text-[14px] leading-relaxed"
        style={{ color: 'var(--color-ink-soft)' }}
      >
        {finding.mechanism}
      </p>

      {finding.lag_note && (
        <p
          className="mt-3 max-w-[74ch] text-[13px] leading-relaxed"
          style={{ color: 'var(--color-ink-faint)' }}
        >
          {finding.lag_note}
        </p>
      )}

      <Inset className="mt-5 px-5 py-[18px]">
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <span className="tnum text-[22px] font-semibold" style={{ color: 'var(--color-risk)' }}>
            {usd(finding.daily_usd)}
          </span>
          <span className="text-[13px]" style={{ color: 'var(--color-ink-faint)' }}>
            a day at risk
          </span>
        </div>
        {/* The basis says this is the largest exposure rather than a total.
            Showing it matters: a reader who assumed we had added the two
            domains together would think we were overstating, and be right to. */}
        <p className="mt-2 text-[12.5px] leading-relaxed" style={{ color: 'var(--color-ink-faint)' }}>
          {finding.exposure_basis}
        </p>
      </Inset>

      {finding.guidance && (
        <div className="mt-5">
          <p
            className="text-[11px] font-semibold uppercase tracking-[0.14em]"
            style={{ color: 'var(--color-ink-faint)' }}
          >
            What to do
          </p>
          <p className="mt-2 max-w-[74ch] text-[14px] leading-relaxed">{finding.guidance}</p>
        </div>
      )}

      <div
        className="mt-5 flex flex-wrap gap-x-5 gap-y-1 text-[12px]"
        style={{ color: 'var(--color-ink-faint)' }}
      >
        <span>
          {finding.confidence === 'mechanical'
            ? 'Follows from the arithmetic'
            : 'A direct, well-understood link'}
        </span>
        {finding.corroborated && <span>Your own history shows this pattern</span>}
        {finding.also_seen.length > 0 && <span>Also visible as: {finding.also_seen[0]}</span>}
      </div>
    </li>
  )
}
