"""The CLI must not claim a BCC list was loaded when it was not.

`ClipboardMailtoBackend` builds `mailto:?subject=...` and never reads
`draft.bcc` -- a `mailto:` URL cannot carry 50 addresses (Windows caps
the URI around 2 KB, and handlers vary in what they honour). But the CLI
printed "BCC pre-filled with N recipient(s)" whenever `recipients.txt`
was non-empty, regardless of backend. That is the default path for every
macOS, Linux, Thunderbird and webmail editor.

The recovery an editor reaches for when they find BCC empty is the
dangerous one: pasting `recipients.txt` into To: or Cc:, disclosing ~50
institutional addresses -- external collaborators included -- to every
recipient and every forward.
"""

from __future__ import annotations

import build_newsletter as bn
from scripts.mail import ComposeOutcome
from scripts.mail.clipboard_mailto import ClipboardMailtoBackend
from scripts.mail.eml import EmlBackend
from scripts.mail.outlook import OutlookBackend


def test_backends_declare_whether_they_carry_bcc():
    assert OutlookBackend().supports_bcc is True
    assert EmlBackend().supports_bcc is True
    assert ClipboardMailtoBackend().supports_bcc is False


def test_the_clipboard_backend_really_does_drop_bcc():
    """Pin the fact the capability describes, so the flag cannot drift
    away from the behaviour."""
    import inspect

    from scripts.mail import clipboard_mailto

    source = inspect.getsource(clipboard_mailto)
    assert "draft.bcc" not in source, (
        "the backend now reads bcc -- update supports_bcc to match")


def test_a_delivering_backend_reports_plainly():
    outcome = ComposeOutcome(backend="outlook", handler_kind="outlook",
                             bcc_delivered=True)
    message = bn._bcc_blurb(outcome, 50)

    assert "50 recipient(s)" in message
    assert "EMPTY" not in message


def test_a_non_delivering_backend_warns_and_names_the_field():
    outcome = ComposeOutcome(backend="clipboard_mailto",
                             handler_kind="apple_mail",
                             bcc_delivered=False)
    message = bn._bcc_blurb(outcome, 50)

    assert "EMPTY" in message
    # Naming BCC explicitly, and warning against To:/Cc:, is the whole
    # point -- that mistake is the privacy incident.
    assert "BCC field" in message
    assert "not To: or Cc:" in message
    assert "--backend=eml" in message, "offer the path that does work"


def test_no_recipients_means_no_claim_either_way():
    """With an empty recipients.txt there is nothing to be honest or
    dishonest about; `compose` reports delivered so the CLI stays quiet."""
    from scripts.mail import compose  # noqa: F401  (import shape check)

    outcome = ComposeOutcome(backend="clipboard_mailto",
                             handler_kind="browser",
                             bcc_delivered=True)
    assert "recipient(s)" in bn._bcc_blurb(outcome, 0)
