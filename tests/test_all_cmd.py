"""Round-15 CLI-integration tests for `all_cmd`'s early CID validation.

The round-13 M3 fix moved CID feasibility checking BEFORE
`_build_pipeline` so a non-Outlook fork passing `--image-mode=cid`
fails fast instead of producing a half-published state. The round-15
architect HIGH 1 + MEDIUM 2 audit found the predicate keyed on
`handler.is_outlook_desktop` instead of the dispatcher's actual
choice -- diverging in two cases:

  (a) Windows + Outlook OS-default + `OutlookBackend.is_available()`
      False (partial pywin32 / COM init failure).
  (b) Outlook OS-default + `--backend=default --image-mode=cid`.

These tests pin the round-15 fix: validation now keys on
`select_backend(...).name != "outlook"`, catching both cases.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from click.testing import CliRunner

import build_newsletter as bn
from scripts.mail import MailHandler


def _outlook_handler() -> MailHandler:
    return MailHandler(kind="outlook", name="Microsoft Outlook")


def _apple_handler() -> MailHandler:
    return MailHandler(kind="apple_mail", name="Apple Mail")


def test_all_cmd_rejects_cid_with_default_backend_on_outlook_box(tmp_path):
    """Outlook is the OS default, but the user explicitly passes
    `--backend=default --image-mode=cid` -- a contradictory pair. The
    round-15 fix must catch this BEFORE the build / publish-skip side
    effects run; otherwise the editor gets a half-published failure
    when `compose()` raises later. Round-15 architect MEDIUM 2."""
    handler = _outlook_handler()
    docx = tmp_path / "issue-1.docx"
    docx.write_bytes(b"placeholder")

    build_pipeline = MagicMock()

    with patch("build_newsletter.detect_default_mail_handler",
               return_value=handler), \
         patch("build_newsletter._build_pipeline", new=build_pipeline):
        runner = CliRunner()
        result = runner.invoke(
            bn.cli,
            ["all", "--input", str(docx), "--issue", "1",
             "--backend", "default", "--image-mode", "cid"],
        )

    assert result.exit_code == 2, (
        f"expected sys.exit(2) for cid+default+outlook combo; got "
        f"{result.exit_code}\n{result.output}"
    )
    assert "cid" in result.output.lower(), result.output
    # Critical: the build must NOT have run -- failing fast is the
    # whole point of moving validation upfront.
    build_pipeline.assert_not_called()


def test_all_cmd_rejects_cid_when_outlook_handler_but_unavailable(tmp_path):
    """Round-15 architect HIGH 1: Outlook reported by the OS, but
    `OutlookBackend.is_available()` returns False (e.g. partial pywin32
    install). Dispatcher falls through to clipboard. Explicit
    `--image-mode=cid` should fail fast, not run the build then crash
    in `compose()`."""
    handler = _outlook_handler()
    docx = tmp_path / "issue-1.docx"
    docx.write_bytes(b"placeholder")

    build_pipeline = MagicMock()

    with patch("build_newsletter.detect_default_mail_handler",
               return_value=handler), \
         patch("scripts.mail.outlook.OutlookBackend.is_available",
               return_value=False), \
         patch("build_newsletter._build_pipeline", new=build_pipeline):
        runner = CliRunner()
        result = runner.invoke(
            bn.cli,
            ["all", "--input", str(docx), "--issue", "1",
             "--backend", "auto", "--image-mode", "cid"],
        )

    assert result.exit_code == 2, (
        f"expected sys.exit(2) when Outlook handler detected but "
        f"backend unavailable; got {result.exit_code}\n{result.output}"
    )
    build_pipeline.assert_not_called()


def test_all_cmd_rejects_cid_on_non_outlook_box(tmp_path):
    """Round-13 baseline: Apple Mail handler + explicit `--image-mode=cid`.
    Round-15 must preserve this behaviour with the new chosen-backend
    predicate."""
    handler = _apple_handler()
    docx = tmp_path / "issue-1.docx"
    docx.write_bytes(b"placeholder")

    build_pipeline = MagicMock()

    with patch("build_newsletter.detect_default_mail_handler",
               return_value=handler), \
         patch("build_newsletter._build_pipeline", new=build_pipeline):
        runner = CliRunner()
        result = runner.invoke(
            bn.cli,
            ["all", "--input", str(docx), "--issue", "1",
             "--image-mode", "cid"],
        )

    assert result.exit_code == 2
    build_pipeline.assert_not_called()


def test_all_cmd_accepts_cid_with_explicit_outlook_backend(tmp_path):
    """A user explicitly forcing `--backend=outlook` IS allowed to
    request `--image-mode=cid`, even if the OS default isn't Outlook
    -- they're forcing the issue and accept downstream failure if
    Outlook actually isn't available. Validation must NOT block this
    combo. Round-15 sanity check: the new predicate
    (`chosen.name != "outlook"`) accepts this case because
    `select_backend("outlook", handler)` returns OutlookBackend
    regardless of handler.

    We don't run the full pipeline (it would attempt real COM); we
    only assert that early validation does NOT exit with code 2.
    """
    handler = _apple_handler()  # OS default isn't Outlook
    docx = tmp_path / "issue-1.docx"
    docx.write_bytes(b"placeholder")

    # Make _build_pipeline return a non-zero exit so the test stops
    # there cleanly without exercising publish/compose; we just need
    # to verify we got PAST the early-fail predicate.
    pipeline_result = bn.BuildResult(
        exit_code=99, subject="x", html_path=tmp_path / "x.html",
    )

    with patch("build_newsletter.detect_default_mail_handler",
               return_value=handler), \
         patch("build_newsletter._build_pipeline",
               return_value=pipeline_result):
        runner = CliRunner()
        result = runner.invoke(
            bn.cli,
            ["all", "--input", str(docx), "--issue", "1",
             "--backend", "outlook", "--image-mode", "cid"],
        )

    assert result.exit_code == 99, (
        "expected to reach _build_pipeline (exit=99 from our mock); "
        "if exit==2 the early-fail predicate is rejecting an "
        "explicitly-forced Outlook+CID combo it should accept.\n"
        f"output:\n{result.output}"
    )
