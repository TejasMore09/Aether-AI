"""One way out of the building for email.

There were two before this: `notifications` spoke SMTP, and a Resend key sat
in the configuration doing nothing. Two send paths means two places to
misconfigure, two sets of failure behaviour, and a password reset that works
in testing while alerts silently do not — or the reverse, which is worse
because nobody notices.

**Resend first, SMTP second, honest silence third.** An API is preferred to
SMTP where both exist: deliverability is somebody else's problem, failures
come back as status codes rather than timeouts, and there is no long-lived
connection to nurse. SMTP stays because it is the escape hatch — a business
that must send through its own server, or a local Mailpit during development,
should not need this file changed.

**Never raises.** Every caller here is doing something else that matters more:
recording an approval, completing a password reset. A mail server having a bad
afternoon must not undo work that has already happened, so this returns a
status and the caller decides.

**The limitation that will bite, stated where it is configured.** Resend's
shared sender only delivers to the address that owns the account. Until a
domain is verified, a password reset to a real customer leaves here reporting
success and arrives nowhere. That is not something this module can detect, so
it is written down in `.env` beside the key and in the requirements page.
"""

from __future__ import annotations

import json
import logging
import smtplib
import urllib.error
import urllib.request
from email.mime.text import MIMEText

from aether.core.config import get_settings

logger = logging.getLogger(__name__)

_RESEND_ENDPOINT = "https://api.resend.com/emails"
_TIMEOUT_SECONDS = 15

# Statuses are the same three the notifications table already records, so
# adding a transport did not change what a stored row can say.
SENT = "sent"
FAILED = "failed"
SKIPPED = "skipped_unconfigured"


def configured() -> bool:
    """Whether anything could be sent at all."""
    settings = get_settings()
    return bool(settings.resend_api_key or settings.smtp_host)


def send(recipient: str, subject: str, body: str, *, html: str | None = None) -> tuple[str, str]:
    """Deliver one message. Returns `(status, detail)` and never raises."""
    settings = get_settings()

    if settings.resend_api_key:
        return _via_resend(settings, recipient, subject, body, html)
    if settings.smtp_host:
        return _via_smtp(settings, recipient, subject, body)
    return SKIPPED, "no mail transport configured (AETHER_RESEND_API_KEY or AETHER_SMTP_HOST)"


def _via_resend(
    settings, recipient: str, subject: str, body: str, html: str | None
) -> tuple[str, str]:
    sender = settings.email_from or settings.smtp_from
    payload = {
        "from": sender,
        "to": [recipient],
        "subject": subject,
        # Both parts: a plain-text alternative is what stops a transactional
        # message being filed as marketing, and some clients render nothing
        # else.
        "text": body,
        "html": html or f'<pre style="font:14px/1.5 ui-monospace,monospace">{body}</pre>',
    }
    request = urllib.request.Request(
        _RESEND_ENDPOINT,
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {settings.resend_api_key}",
            "Content-Type": "application/json",
            # Without a real user agent the request is refused by the edge
            # before it reaches the API, with a 403 that looks exactly like a
            # rejected key. Cost me a diagnosis once already.
            "User-Agent": "aether/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
            return SENT, str(json.load(response).get("id", ""))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode()[:300]
        logger.error("resend rejected mail to %s: %s %s", recipient, exc.code, detail)
        return FAILED, f"HTTP {exc.code}: {detail}"
    except Exception as exc:  # noqa: BLE001 - see the module docstring
        logger.error("resend unreachable for %s: %s", recipient, exc)
        return FAILED, f"{type(exc).__name__}: {exc}"


def _via_smtp(settings, recipient: str, subject: str, body: str) -> tuple[str, str]:
    try:
        message = MIMEText(body, "plain", "utf-8")
        message["Subject"] = subject
        message["From"] = settings.smtp_from
        message["To"] = recipient
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=_TIMEOUT_SECONDS) as smtp:
            smtp.ehlo()
            if settings.smtp_starttls:
                smtp.starttls()
                smtp.ehlo()
            if settings.smtp_username:
                smtp.login(settings.smtp_username, settings.smtp_password)
            smtp.sendmail(settings.smtp_from, [recipient], message.as_string())
        return SENT, ""
    except Exception as exc:  # noqa: BLE001 - see the module docstring
        logger.error("smtp send failed to %s: %s", recipient, exc)
        return FAILED, f"{type(exc).__name__}: {exc}"
