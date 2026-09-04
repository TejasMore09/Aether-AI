"""Things that must be true of every test, whether or not it thought about them.

**No test may send real email.** This is not hypothetical: the moment
`notifications` was pointed at the unified `core.mail`, a test that had always
passed against an unconfigured SMTP host started finding the live Resend key
in `.env` instead, and the suite made a genuine outbound API call trying to
mail a made-up address. It failed only because the sending domain is not
verified yet — with a verified domain it would have quietly succeeded, and a
full test run would have emailed strangers.

So the default state for every test is *no mail transport at all*, and the two
transports are replaced with something that fails loudly. A test that wants to
observe sending patches `aether.core.mail.send`, which sits above both.

This is the same failure shape as the timestamp collision in 4.x: a test that
passes for a reason nobody chose is not evidence, and the reason it passes has
to be pinned down rather than inherited from whatever happens to be in the
environment.
"""

import pytest

from aether.core import mail
from aether.core.config import get_settings


@pytest.fixture(autouse=True)
def no_real_mail(monkeypatch):
    """Every test runs with no mail configured unless it says otherwise."""
    settings = get_settings()
    monkeypatch.setattr(settings, "resend_api_key", "", raising=False)
    monkeypatch.setattr(settings, "smtp_host", "", raising=False)

    def refuse(*args, **kwargs):
        raise AssertionError(
            "a test tried to send real email — patch aether.core.mail.send instead "
            "of configuring a transport"
        )

    # Only reachable if a test deliberately sets a transport, which is exactly
    # when the loud failure is wanted.
    monkeypatch.setattr(mail, "_via_resend", refuse)
    monkeypatch.setattr(mail, "_via_smtp", refuse)
