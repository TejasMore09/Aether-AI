"""The whole business, rendered for a prompt.

Diagnosis has always described one domain. That is why an explanation of
slowing collections could sit next to a separate explanation of a shortening
runway and neither would mention the other, leaving the customer to notice
what any advisor would have said in the first sentence.

This builds the context block that fixes it. Three things shape what goes in:

**Relevance, not completeness.** Every extra domain costs tokens, and tokens
are metered against a real per-tenant budget. A healthy domain unconnected to
the decision at hand teaches the model nothing, so only the domains named in a
finding and the ones actually impaired are included.

**The arithmetic has to be stated, not implied.** The block carries two
exposure figures — the domain's own and the finding's combined one — and a
model handed two numbers will helpfully add them. That would contradict the
engine's own figure in the same paragraph, which is the same failure as
quoting the wrong band (D14): a customer who spots it is right to stop
trusting the rest.

**Unvalidated claims stay out.** `findings.for_business` already filters
`plausible` relations, and nothing here reintroduces them. A hypothesis
nobody has tested must not reach a customer through a prompt any more than
through a dashboard.
"""

from __future__ import annotations

from aether.business.findings import CrossDomainFinding
from aether.business.state import BusinessState

# Fewer than this many words in a mechanism and it is not worth the tokens.
_MIN_MECHANISM_WORDS = 5


def _reading_line(state: BusinessState, domain: str) -> str | None:
    snapshot = state.get(domain)
    if snapshot is None:
        return None
    named = ", ".join(f"{k}={v:g}" for k, v in sorted(snapshot.metrics.items()))
    health = "impaired" if snapshot.impaired else "within its normal band"
    return f"- {snapshot.label} ({domain}): {health}. {named}"


def relevant_domains(
    state: BusinessState, focus: str, findings: tuple[CrossDomainFinding, ...]
) -> list[str]:
    """Which other domains are worth the tokens.

    Domains connected to the focus by a finding come first, because they are
    the reason this block exists. Impaired domains follow: they are not part
    of the story yet, but an approver deciding about collections should know
    the pipeline is also struggling.

    Healthy, unconnected domains are omitted. They would cost budget to say
    nothing.
    """
    connected: list[str] = []
    for finding in findings:
        if focus in finding.domains:
            connected.extend(d for d in finding.domains if d != focus)

    impaired = [s.domain for s in state.impaired if s.domain != focus]

    ordered: list[str] = []
    for domain in [*connected, *impaired]:
        if domain not in ordered:
            ordered.append(domain)
    return ordered


def context_block(
    state: BusinessState, focus: str, findings: tuple[CrossDomainFinding, ...]
) -> str:
    """The whole-business context for one domain's diagnosis, or "" if there
    is nothing useful to add."""
    connected = tuple(f for f in findings if focus in f.domains)
    others = relevant_domains(state, focus, findings)

    if not connected and not others:
        return ""

    lines: list[str] = ["Elsewhere in this business:"]

    for domain in others:
        line = _reading_line(state, domain)
        if line:
            lines.append(line)
    if state.silent:
        lines.append(
            f"- Configured but reporting nothing: {', '.join(state.silent)}. "
            f"Do not infer anything from their absence."
        )

    for finding in connected:
        lines.append("")
        lines.append(f"CONNECTED PROBLEM — {finding.label}")
        if len(finding.mechanism.split()) >= _MIN_MECHANISM_WORDS:
            lines.append(f"Mechanism: {finding.mechanism}")
        if finding.guidance:
            lines.append(f"Recommended emphasis: {finding.guidance}")
        if finding.lag_note:
            lines.append(f"Timing: {finding.lag_note}")
        if finding.corroborated_by:
            lines.append(
                "This client's own history supports it: " + "; ".join(finding.corroborated_by)
            )

        # Stated explicitly because a model given two exposure figures will
        # add them, and the engine's own number is the maximum. Contradicting
        # the decision inside the explanation of that decision is worse than
        # giving no explanation at all.
        lines.append(
            f"Combined exposure across {' and '.join(finding.domains)} is "
            f"${finding.daily_usd:,.2f} a day. This is the LARGEST single "
            f"exposure, not a total — these figures measure the same money "
            f"from two sides. Never add them together or state a larger sum."
        )
        if finding.also_seen:
            lines.append("The same situation is also visible as: " + "; ".join(finding.also_seen))

    return "\n".join(lines) + "\n\n"


def extra_instructions(findings: tuple[CrossDomainFinding, ...], focus: str) -> str:
    """What the explanation must do differently when domains are connected."""
    if not any(focus in f.domains for f in findings):
        return ""
    return (
        "This decision is part of a connected problem spanning several parts "
        "of the business. Lead with the connection rather than describing this "
        "domain alone: say what is happening across them, in that order. Treat "
        "the mechanism above as the explanation to give, and do not present the "
        "domains as separate issues that happen to coincide.\n"
    )
