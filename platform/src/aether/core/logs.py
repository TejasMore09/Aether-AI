"""One logging setup, so the log lines exist and can be tied together.

Until now only the worker configured logging. The three API services never
did, which meant every `logger.info` in the platform — throttle locks, mail
outcomes, skipped notifications — went nowhere at all, and errors arrived as
bare unattributed lines through Python's last-resort handler. A good deal of
careful logging had been written into this codebase and none of it was
reaching anyone.

**Every line carries the request reference.** That is the whole reason this
module exists rather than a `basicConfig` call in three places. During an
incident the useful question is not "what errors happened" but "what happened
during *this* request" — the one the customer is on the phone about, quoting
the reference from their 500. Without a correlation id in every line, the log
is a pile of true statements in no relation to each other.

The reference comes from a context variable rather than being threaded through
every call, because the alternative is passing a string into functions that
have no other reason to know about HTTP.

Format is plain text, not JSON. There is no log aggregator yet and none is
planned before 6.1; JSON now would be less readable in the terminal where
these are actually read today, in exchange for a benefit nothing can collect.
When there is somewhere to ship logs, this is the one place to change.
"""

from __future__ import annotations

import logging
import sys

from aether.core.errors import current_reference

_configured = False


class _Reference(logging.Filter):
    """Attach the current request's reference to every record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.reference = current_reference.get() or "-"
        return True


def configure(service: str, *, level: int | None = None) -> None:
    """Set up logging for one process. Safe to call more than once.

    Idempotent because the services are imported by tests and by each other,
    and a second call would otherwise double every line — which during an
    incident reads as twice as much going wrong.
    """
    global _configured
    if _configured:
        return

    if level is None:
        # INFO everywhere, dev included. DEBUG on the root logger turns on
        # every third-party library's internals — asyncio announcing its event
        # loop implementation, the HTTP client narrating each connection — and
        # buries the platform's own lines in a module whose entire purpose is
        # making those lines findable. A caller who wants DEBUG asks for it.
        level = logging.INFO

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        logging.Formatter(
            f"%(asctime)s %(levelname)-7s [{service}] %(reference)s %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    handler.addFilter(_Reference())

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)

    # Noisy at INFO and saying nothing a person acts on: every statement
    # SQLAlchemy compiles, one line per HTTP request the access log already
    # covers, and libraries narrating their own plumbing. Turned down rather
    # than off, so a genuine problem in any of them still surfaces.
    for noisy in ("sqlalchemy.engine", "uvicorn.access", "asyncio", "httpcore", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    _configured = True
