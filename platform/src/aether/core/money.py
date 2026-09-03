"""Money, in the currency the business actually uses.

Everything monetary in this system was USD by name — `expected_loss_usd`, and
every figure quoted as `$71.89`. Serving India, the US and Europe (D31) makes
that unusable rather than merely imprecise: an explanation telling a Pune
manufacturer they are losing $147 a day is a number they cannot check against
anything they know.

Three decisions shape this module.

**The system never converts.** No FX rate is stored, fetched or applied. A
rate is a fact about a moment, and a stale one silently corrupts every figure
downstream — including figures already shown to a customer and already acted
on. Everything a business reports is in their own currency and stays there.
Conveniently, most of the product is already currency-neutral: DSO is days,
overdue share is a fraction, coverage is a ratio. Only the money is affected.

**Two different kinds of money exist here and must not be merged.** The
*customer's* money — exposure, cost to act, balances — is in their currency.
*Our* money — what a diagnosis costs us at the model provider — is billed in
USD regardless of who the tenant is. `LLMUsage.cost_usd` therefore keeps its
name, and that is correct rather than an oversight.

**Indian grouping is not a nicety.** ₹1,50,000 and ₹150,000 are the same
number written two ways, and only one of them reads as money to someone in
India. Getting it wrong is a small, constant signal that the product was not
built for them. It is about fifteen lines, so there is no excuse.

Deliberately not done: per-locale symbol placement and separators. A German
reader writes `1.234,56 €` and gets `€1,234.56` here. That is a real gap, and
a much smaller one than the number itself being in the wrong currency — but it
should be fixed before anyone is charged money for this.
"""

from __future__ import annotations

from dataclasses import dataclass


class UnsupportedCurrency(ValueError):
    """A currency the platform has no formatting rules for.

    Raised rather than falling back to USD. A figure silently relabelled into
    a currency the business does not use is worse than an error, because
    nothing downstream can tell it happened.
    """


@dataclass(frozen=True)
class Currency:
    code: str
    symbol: str
    # South Asian grouping: the last three digits, then twos. 1,50,000 rather
    # than 150,000.
    lakh_grouping: bool = False


SUPPORTED: dict[str, Currency] = {
    "INR": Currency("INR", "₹", lakh_grouping=True),
    "USD": Currency("USD", "$"),
    "EUR": Currency("EUR", "€"),
    "GBP": Currency("GBP", "£"),
}

DEFAULT = "USD"


def currency(code: str | None) -> Currency:
    """Resolve a code, distinguishing "not recorded" from "not supported".

    None or empty means nobody said, which happens for a row written before
    currency existed and for an object not yet flushed. The default is the
    right answer there, and refusing would turn a cosmetic gap into a failed
    explanation.

    A code that is present but unknown is a different thing entirely: someone
    stated a currency this platform cannot render, and quietly showing their
    money with the wrong symbol is worse than an error, because nothing
    downstream could tell it happened.
    """
    if not code:
        return SUPPORTED[DEFAULT]
    try:
        return SUPPORTED[code.upper()]
    except KeyError:
        raise UnsupportedCurrency(
            f"{code!r} is not supported. Known: {', '.join(sorted(SUPPORTED))}"
        ) from None


def _group(digits: str, lakh: bool) -> str:
    """Thousands separators, in the convention the reader expects."""
    if not lakh or len(digits) <= 3:
        return f"{int(digits):,}"

    # Last three stay together; everything before is grouped in twos.
    head, tail = digits[:-3], digits[-3:]
    parts: list[str] = []
    while len(head) > 2:
        parts.insert(0, head[-2:])
        head = head[:-2]
    if head:
        parts.insert(0, head)
    return ",".join([*parts, tail])


def fmt(amount: float, code: str | None = DEFAULT, *, decimals: int = 2) -> str:
    """One amount, written the way its reader writes money.

    fmt(147.0, "INR")     ->  ₹147.00
    fmt(150000.0, "INR")  ->  ₹1,50,000.00
    fmt(150000.0, "USD")  ->  $150,000.00
    """
    cur = currency(code)
    negative = amount < 0
    whole = f"{abs(amount):.{decimals}f}"
    digits, _, fraction = whole.partition(".")

    grouped = _group(digits, cur.lakh_grouping)
    body = f"{grouped}.{fraction}" if fraction else grouped
    return f"{'-' if negative else ''}{cur.symbol}{body}"


def per_day(amount: float, code: str | None = DEFAULT) -> str:
    """The phrase this product says more than any other."""
    return f"{fmt(amount, code)} a day"


def for_tenant(tenant_id, db=None) -> str:
    """The currency this business reports in.

    Pass the session you already hold. Every caller here is mid-transaction,
    and opening a second connection to read one column doubles this path's
    demand on the pool for no reason — which showed up as an intermittent
    failure under a full test run before this took a session.

    Falls back to the default rather than raising: a missing currency should
    cost a correct symbol, never a decision or an explanation. Wrong-looking
    money is visible and reportable; a diagnosis that failed to render is not.
    """
    from aether.core.models import Tenant

    def read(session) -> str:
        tenant = session.get(Tenant, tenant_id)
        return tenant.currency if tenant and tenant.currency else DEFAULT

    try:
        if db is not None:
            return read(db)
        from aether.core.db import tenant_session

        with tenant_session(tenant_id) as owned:
            return read(owned)
    except Exception:  # noqa: BLE001 - see the docstring
        return DEFAULT
