"""Taking customers' data back out of error messages.

Aether is a multi-tenant platform holding other companies' operating data, and
error tracking is the one place that data walks out of its tenant on purpose:
a stack trace crosses the boundary by nature, and platform staff read it.

Exception text is far more revealing than it looks. A duplicate signup raises
an `IntegrityError` whose string carries the customer's email address in full.
SQLAlchemy appends `[parameters: ...]` — every bound value of the statement
that failed, which for this product means real revenue figures, real invoice
totals, real names. A validation error echoes what was submitted. None of that
is written by us, and none of it was meant to leave the tenant.

**This is a filter, not a guarantee, and the difference matters.** A scrubber
matches the shapes it was taught. It cannot recognise a customer's data in a
form nobody anticipated — a free-text note, a product name, a number that is
merely a number. So it is one of three defences and not the main one:

1. Request and response bodies are never captured at all. Not scrubbed:
   never read. The safest data is the data that was not collected.
2. What is captured is scrubbed here.
3. Reading a scrubbed message still requires the `engineer` role and is
   written to the staff trail. `observer` sees that something broke and where,
   never the text (D57).

Erring towards over-redaction is deliberate. A stack trace with a missing
value still says which line failed, which is most of what a fix needs. A stack
trace with a customer's revenue in it cannot be un-read.
"""

from __future__ import annotations

import re

REDACTED = "<redacted>"

# SQLAlchemy appends the bound parameters of a failed statement. For this
# product that is the single richest leak in any exception string: every value
# of the row somebody tried to write. Dropped whole rather than scrubbed
# field by field, because the whole point is that we do not know what is in
# there.
#
# Everything from `[parameters:` to the end of the string goes, rather than
# just the bracketed block. A parameter *value* can contain a `]` — a customer
# note, a product name — so there is no reliable way to find where the block
# ends, and a non-greedy match to the first `]` would stop early and leave the
# rest of the values standing. In practice the block is last; the only thing
# lost with it is SQLAlchemy's constant documentation URL.
_SQL_PARAMETERS = re.compile(r"\[parameters:.*", re.DOTALL)

# Postgres names the offending value when a unique constraint is violated:
#   Key (email)=(alice@realcompany.com) already exists.
# The column name is ours and is worth keeping; the value is the customer's.
_PG_KEY = re.compile(r"(Key \([^)]*\)=\()[^)]*(\))")

_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")

# Three base64url segments: a JWT, which is a live session if it is anything.
_JWT = re.compile(r"\beyJ[\w-]+\.[\w-]+\.[\w-]+\b")

# Two patterns, because one rule was wrong in a way a test caught. A single
# `label <separator> \S+` matched "Authorization: Bearer sk-live-…" with the
# value being the *word* "Bearer" — it redacted the scheme and published the
# credential. So the scheme is skipped explicitly here, and a bare
# "Bearer <token>" with no label in front of it is handled separately below.
_LABELLED_SECRET = re.compile(
    r"(?i)\b(authorization|api[-_ ]?key|token|password|secret)\b(\s*[:=]\s*)(?:bearer\s+)?\S+"
)
_BEARER = re.compile(r"(?i)\bbearer\s+\S+")

# Nine or more digits in a row: account numbers, card numbers, phone numbers,
# tax identifiers. Short runs are left alone because dates, ports, row counts
# and durations are the ordinary furniture of a useful error message.
_LONG_DIGITS = re.compile(r"\b\d{9,}\b")

# A long opaque run of token-ish characters. Deliberately requires a mix of
# cases or digits so that ordinary long identifiers in our own code —
# `test_a_completed_reset_unlocks_the_account` — survive.
_OPAQUE = re.compile(r"\b(?=[\w-]*[A-Z])(?=[\w-]*\d)[\w-]{24,}\b")


def text(value: str | None, *, limit: int = 4000) -> str:
    """Scrub one string. Safe on None, never raises, always returns a string."""
    if not value:
        return ""
    try:
        out = _SQL_PARAMETERS.sub(f"[parameters: {REDACTED}]", value)
        out = _PG_KEY.sub(rf"\1{REDACTED}\2", out)
        out = _JWT.sub(REDACTED, out)
        out = _LABELLED_SECRET.sub(rf"\1\2{REDACTED}", out)
        out = _BEARER.sub(f"Bearer {REDACTED}", out)
        out = _EMAIL.sub(REDACTED, out)
        out = _LONG_DIGITS.sub(REDACTED, out)
        out = _OPAQUE.sub(REDACTED, out)
    except Exception:  # noqa: BLE001
        # A scrubber that throws must not become a way to store unscrubbed
        # text, nor a second failure inside the failure handler.
        return f"<scrubbing failed for {len(value)} characters>"
    return out[:limit]
