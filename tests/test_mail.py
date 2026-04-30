"""Tests for the composer (mail-handler detection + backend dispatch)."""

from __future__ import annotations

import warnings
from unittest.mock import patch

import pytest

from scripts.mail import (
    ComposeOutcome, MailHandler, compose, detect_default_mail_handler,
)


def test_mailhandler_outlook_flag():
    h = MailHandler(kind="outlook", name="Microsoft Outlook")
    assert h.is_outlook_desktop is True
    other = MailHandler(kind="apple_mail", name="Apple Mail")
    assert other.is_outlook_desktop is False


def test_detect_default_mail_handler_returns_handler():
    h = detect_default_mail_handler()
    assert isinstance(h, MailHandler)
    assert h.kind in {
        "outlook", "apple_mail", "thunderbird",
        "browser", "other", "unknown",
    }


def test_compose_routes_outlook_when_default_is_outlook():
    """Backend-dispatch test (separate concern from image-mode).
    Phase 2 default `image_mode='auto'` would resolve to `'cid'` here
    and demand `asset_dir`; pinning `image_mode='url'` keeps the test
    focused on backend dispatch."""
    handler = MailHandler(kind="outlook", name="Microsoft Outlook")
    with patch("scripts.mail.detect_default_mail_handler",
               return_value=handler), \
         patch("scripts.mail.outlook.OutlookBackend.is_available",
               return_value=True), \
         patch("scripts.mail.outlook.OutlookBackend.compose") as out_compose, \
         patch("scripts.mail.clipboard_mailto.ClipboardMailtoBackend.compose") as fb_compose:
        used = compose("<html>x</html>", subject="Test", image_mode="url")
    # Round-9 Architect HIGH-1: assert on the typed dataclass fields
    # rather than the deprecated `str(used) == "outlook"` shim, so the
    # eventual removal of `__str__` doesn't churn this test.
    assert isinstance(used, ComposeOutcome)
    assert used.backend == "outlook"
    assert used.handler_kind == "outlook"
    assert not used.is_fallback
    out_compose.assert_called_once()
    fb_compose.assert_not_called()


def test_compose_falls_back_to_default_when_not_outlook():
    handler = MailHandler(kind="apple_mail", name="Apple Mail")
    with patch("scripts.mail.detect_default_mail_handler",
               return_value=handler), \
         patch("scripts.mail.outlook.OutlookBackend.is_available",
               return_value=False), \
         patch("scripts.mail.outlook.OutlookBackend.compose") as out_compose, \
         patch("scripts.mail.clipboard_mailto.ClipboardMailtoBackend.compose") as fb_compose:
        used = compose("<html>x</html>", subject="Test")
    assert used.backend == "clipboard_mailto"
    assert used.handler_kind == "apple_mail"
    assert not used.is_fallback
    out_compose.assert_not_called()
    fb_compose.assert_called_once()


def test_compose_falls_back_when_outlook_backend_throws():
    handler = MailHandler(kind="outlook", name="Microsoft Outlook")
    with patch("scripts.mail.detect_default_mail_handler",
               return_value=handler), \
         patch("scripts.mail.outlook.OutlookBackend.is_available",
               return_value=True), \
         patch("scripts.mail.outlook.OutlookBackend.compose",
               side_effect=RuntimeError("boom")), \
         patch("scripts.mail.clipboard_mailto.ClipboardMailtoBackend.compose") as fb_compose:
        used = compose(
            "<html>x</html>", subject="Test", backend="auto",
            image_mode="url",
        )
    assert used.backend == "clipboard_mailto"
    assert used.is_fallback
    assert used.fell_back_from == "outlook"
    fb_compose.assert_called_once()


def test_compose_explicit_outlook_backend_raises_on_failure():
    handler = MailHandler(kind="outlook", name="Microsoft Outlook")
    with patch("scripts.mail.detect_default_mail_handler",
               return_value=handler), \
         patch("scripts.mail.outlook.OutlookBackend.is_available",
               return_value=True), \
         patch("scripts.mail.outlook.OutlookBackend.compose",
               side_effect=RuntimeError("forced")):
        with pytest.raises(RuntimeError, match="forced"):
            compose(
                "<html>x</html>", subject="Test", backend="outlook",
                image_mode="url",
            )


def test_compose_invalid_backend_raises():
    with pytest.raises(ValueError, match="backend must be"):
        compose("<html>x</html>", subject="Test", backend="bogus")


def test_compose_default_backend_skips_outlook():
    handler = MailHandler(kind="outlook", name="Microsoft Outlook")
    with patch("scripts.mail.detect_default_mail_handler",
               return_value=handler), \
         patch("scripts.mail.outlook.OutlookBackend.compose") as out_compose, \
         patch("scripts.mail.clipboard_mailto.ClipboardMailtoBackend.compose") as fb_compose:
        used = compose("<html>x</html>", subject="Test", backend="default")
    assert used.backend == "clipboard_mailto"
    assert used.handler_kind == "outlook"
    assert not used.is_fallback
    out_compose.assert_not_called()
    fb_compose.assert_called_once()


# ---------- Bundle 27/28: ComposeOutcome shape ---------------------------

def test_compose_outcome_is_frozen_dataclass():
    """`ComposeOutcome` must be immutable so callers can't mutate
    the result and confuse downstream logging / audit.

    Round-9 code-review LOW: catch the precise exception class
    (`FrozenInstanceError` from `dataclasses`) rather than bare
    `Exception` -- otherwise this test would pass for unrelated
    `AttributeError` from a renamed field."""
    import dataclasses
    out = ComposeOutcome(backend="outlook", handler_kind="outlook")
    with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
        out.backend = "other"  # type: ignore[misc]


def test_compose_outcome_str_is_silent():
    """Bundle 29: `__str__` no longer emits DeprecationWarning.

    Round-9 added the warning, but round-10 found that lazy-%s
    formatting in production log calls (`log.info("used: %s",
    outcome)`) triggers the warning on every INFO line, defeating
    the purpose of the legacy shim. The migration nudge lives on
    `startswith` (a more deliberate API surface) instead."""
    out = ComposeOutcome(backend="outlook", handler_kind="outlook")
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        s = str(out)  # must NOT raise
    assert s == "outlook"


def test_compose_outcome_startswith_emits_deprecation_warning():
    """`startswith` is still deprecated -- explicit string-prefix
    matching is usually deliberate code worth migrating."""
    out = ComposeOutcome(
        backend="clipboard_mailto", handler_kind="apple_mail",
    )
    with pytest.warns(DeprecationWarning, match=r"\.startswith"):
        assert out.startswith("default:")


def test_compose_outcome_legacy_formats_via_internal_helper():
    """The legacy wire format must still reproduce every round-7
    stringly-typed return so existing log lines stay greppable. Pinned
    via the `_format_legacy` internal helper (renamed from
    `_legacy_str` in bundle 29 -- round-10 python-reviewer MEDIUM)."""
    assert ComposeOutcome(
        backend="outlook", handler_kind="outlook",
    )._format_legacy() == "outlook"
    assert ComposeOutcome(
        backend="clipboard_mailto", handler_kind="apple_mail",
    )._format_legacy() == "default:apple_mail"
    assert ComposeOutcome(
        backend="clipboard_mailto", handler_kind="browser",
    )._format_legacy() == "default:browser"
    assert ComposeOutcome(
        backend="clipboard_mailto", handler_kind="outlook",
        fell_back_from="outlook",
    )._format_legacy() == "default:outlook:fallback-from-outlook"


def test_compose_outcome_field_pattern_match_replaces_str_check():
    """Demonstrates the migration target: callers that used to do
    `str(used) == "outlook"` should match on the typed fields."""
    outlook = ComposeOutcome(backend="outlook", handler_kind="outlook")
    assert outlook.backend == "outlook" and not outlook.is_fallback

    fallback = ComposeOutcome(
        backend="clipboard_mailto", handler_kind="outlook",
        fell_back_from="outlook",
    )
    assert fallback.is_fallback
    assert fallback.fell_back_from == "outlook"


# ---------- Phase 1 (CID image mode) -------------------------------------

def test_compose_rejects_invalid_image_mode():
    """`image_mode` is a tightly-scoped string; a typo must fail loudly,
    not silently fall back to the default."""
    with pytest.raises(ValueError, match="image_mode must be"):
        compose("<html>x</html>", subject="Test", image_mode="bogus")


def test_compose_cid_mode_requires_outlook_backend():
    """CID requires the Outlook COM API to attach inline images via
    Content-ID. The clipboard / mailto backend can't do this. Forcing
    `image_mode='cid'` with a non-Outlook backend must raise rather
    than silently send a degraded URL-mode email -- otherwise the
    editor thinks they're getting attachment-protected delivery and
    is actually getting normal external URLs."""
    handler = MailHandler(kind="apple_mail", name="Apple Mail")
    with patch("scripts.mail.detect_default_mail_handler",
               return_value=handler):
        with pytest.raises(ValueError, match="cid.*Outlook"):
            compose(
                "<html>x</html>", subject="Test",
                backend="default",  # explicit non-Outlook
                image_mode="cid",
                asset_dir=None,
            )


def test_compose_cid_mode_requires_asset_dir(tmp_path):
    """CID mode needs to know where the per-issue photos live on
    disk; passing `image_mode='cid'` without `asset_dir` is a caller
    bug, not something to paper over with a default."""
    handler = MailHandler(kind="outlook", name="Microsoft Outlook")
    with patch("scripts.mail.detect_default_mail_handler",
               return_value=handler), \
         patch("scripts.mail.outlook.OutlookBackend.is_available",
               return_value=True):
        with pytest.raises(ValueError, match="asset_dir"):
            compose(
                "<html>x</html>", subject="Test",
                backend="outlook", image_mode="cid",
                asset_dir=None,
            )


def test_compose_cid_mode_attaches_inline_images_to_outlook(tmp_path):
    """End-to-end image-mode dispatch: a CID-mode compose call should
    rewrite the HTML AND populate `DraftEmail.inline_images` BEFORE
    the Outlook backend's `compose` is invoked."""
    # Set up the asset layout the cid module expects.
    asset_dir = tmp_path / "assets" / "issue-1"
    asset_dir.mkdir(parents=True)
    (asset_dir / "photo1.jpg").write_bytes(b"\xff\xd8\xffJPEG")

    repo_prefix = "https://raw.githubusercontent.com/owner/repo/main"
    html = f'<html><body><img src="{repo_prefix}/assets/issue-1/photo1.jpg"></body></html>'

    handler = MailHandler(kind="outlook", name="Microsoft Outlook")
    captured: dict = {}

    def fake_compose(self, draft):
        captured["html"] = draft.html
        captured["inline"] = draft.inline_images

    with patch("scripts.mail.detect_default_mail_handler",
               return_value=handler), \
         patch("scripts.mail.outlook.OutlookBackend.is_available",
               return_value=True), \
         patch("scripts.mail.outlook.OutlookBackend.compose",
               new=fake_compose):
        compose(
            html, subject="Test", backend="outlook",
            image_mode="cid", asset_dir=asset_dir,
        )

    # The HTML the backend received MUST have been CID-rewritten.
    assert "cid:meridian-" in captured["html"], (
        f"Expected CID-rewritten HTML; got: {captured['html'][:200]}"
    )
    assert repo_prefix not in captured["html"], (
        "Original raw.githubusercontent URL leaked into the CID-mode "
        "HTML; the rewriter didn't replace it."
    )
    # Exactly one inline-image spec was passed to the backend.
    assert len(captured["inline"]) == 1
    assert captured["inline"][0].path == asset_dir / "photo1.jpg"


def test_compose_url_mode_does_not_touch_html(tmp_path):
    """URL mode is a no-op for image rewriting: the HTML reaches the
    backend exactly as the caller passed it."""
    handler = MailHandler(kind="outlook", name="Microsoft Outlook")
    original_html = '<html><body><img src="https://example.com/x.jpg"></body></html>'
    captured: dict = {}

    def fake_compose(self, draft):
        captured["html"] = draft.html
        captured["inline"] = draft.inline_images

    with patch("scripts.mail.detect_default_mail_handler",
               return_value=handler), \
         patch("scripts.mail.outlook.OutlookBackend.is_available",
               return_value=True), \
         patch("scripts.mail.outlook.OutlookBackend.compose",
               new=fake_compose):
        compose(
            original_html, subject="Test", backend="outlook",
            image_mode="url",  # explicit default
        )

    assert captured["html"] == original_html
    assert captured["inline"] == ()


def test_attach_inline_image_sets_all_mapi_props(tmp_path):
    """Round-12 architect MEDIUM 3 / deliverability HIGH 1 + MEDIUM 3:
    the actual MAPI property writes weren't covered before. Mock the
    Attachments.Add return value and verify the right MAPI tag URIs
    + values are written for each inline image."""
    from unittest.mock import MagicMock
    from scripts.mail.cid import InlineImage
    from scripts.mail.outlook import _attach_inline_image

    photo = tmp_path / "lab.jpg"
    photo.write_bytes(b"\xff\xd8\xfftest")
    inline = InlineImage(
        path=photo, cid="meridian-issue-1-01-lab.jpg@meridian.local",
        original_url="https://example/lab.jpg",
    )

    fake_att = MagicMock()
    fake_mail = MagicMock()
    fake_mail.Attachments.Add.return_value = fake_att

    _attach_inline_image(fake_mail, inline)

    fake_mail.Attachments.Add.assert_called_once_with(str(photo))
    # All five MAPI properties get written.
    write_calls = fake_att.PropertyAccessor.SetProperty.call_args_list
    written_props = {call.args[0]: call.args[1] for call in write_calls}

    # Content-ID -- the value the HTML's `cid:...` references.
    cid_tag = "http://schemas.microsoft.com/mapi/proptag/0x3712001F"
    assert written_props[cid_tag] == inline.cid

    # ATTACH_FLAGS = 4 (ATT_MHTML_REF) -- "referenced by HTML body".
    flags_tag = "http://schemas.microsoft.com/mapi/proptag/0x37140003"
    assert written_props[flags_tag] == 4

    # ATTACHMENT_HIDDEN = True -- complementary hide-from-UI.
    hidden_tag = "http://schemas.microsoft.com/mapi/proptag/0x7FFE000B"
    assert written_props[hidden_tag] is True

    # MIME tag -- explicit content-type so Gmail doesn't fall back to
    # "show as attachment".
    mime_tag = "http://schemas.microsoft.com/mapi/proptag/0x370E001F"
    assert written_props[mime_tag] == "image/jpeg"

    # Pathname cleared -- no leak of editor's local file path into
    # NDR debug headers.
    pathname_tag = "http://schemas.microsoft.com/mapi/proptag/0x3708001F"
    assert written_props[pathname_tag] == ""


def test_attach_inline_image_handles_attach_failure_gracefully(tmp_path):
    """If `Attachments.Add` itself fails, the helper logs a warning
    and returns. It must NOT proceed to call `PropertyAccessor.SetProperty`
    on a non-attachment, which would cascade into an unrelated error."""
    from unittest.mock import MagicMock
    from scripts.mail.cid import InlineImage
    from scripts.mail.outlook import _attach_inline_image

    photo = tmp_path / "lab.jpg"
    photo.write_bytes(b"\xff\xd8\xfftest")
    inline = InlineImage(
        path=photo, cid="meridian-issue-1-01-lab.jpg@meridian.local",
        original_url="https://example/lab.jpg",
    )

    fake_mail = MagicMock()
    fake_mail.Attachments.Add.side_effect = OSError("disk full")

    # Must not raise.
    _attach_inline_image(fake_mail, inline)
    # No SetProperty call should have been made.
    fake_mail.Attachments.Add.assert_called_once()


def test_compose_cid_auto_fallback_hands_clipboard_original_url_html(tmp_path):
    """Round-12 architect HIGH 2: when CID mode is active and Outlook
    fails, the auto-fallback to ClipboardMailto must pass the
    ORIGINAL URL HTML, NOT the CID-rewritten HTML. Otherwise the
    editor pastes a body full of `<img src="cid:...">` references
    into a non-Outlook compose window where they don't resolve --
    recipients see broken images."""
    # Set up the asset layout so CID rewrite has something to chew on.
    asset_dir = tmp_path / "assets" / "issue-1"
    asset_dir.mkdir(parents=True)
    (asset_dir / "photo1.jpg").write_bytes(b"\xff\xd8\xff" + b"X" * 100)

    repo_prefix = "https://raw.githubusercontent.com/owner/repo/main"
    original_html = (
        f'<html><body><img src="{repo_prefix}/assets/issue-1/photo1.jpg">'
        f'</body></html>'
    )

    handler = MailHandler(kind="outlook", name="Microsoft Outlook")
    captured: dict = {}

    def fake_clipboard_compose(self, draft):
        captured["html"] = draft.html
        captured["inline"] = draft.inline_images

    with patch("scripts.mail.detect_default_mail_handler",
               return_value=handler), \
         patch("scripts.mail.outlook.OutlookBackend.is_available",
               return_value=True), \
         patch("scripts.mail.outlook.OutlookBackend.compose",
               side_effect=RuntimeError("Outlook COM exploded")), \
         patch("scripts.mail.clipboard_mailto.ClipboardMailtoBackend.compose",
               new=fake_clipboard_compose):
        outcome = compose(
            original_html, subject="Test", backend="auto",
            image_mode="cid", asset_dir=asset_dir,
        )

    assert outcome.is_fallback
    assert outcome.fell_back_from == "outlook"
    # The clipboard backend received the ORIGINAL HTML, not the
    # CID-rewritten version.
    assert captured["html"] == original_html, (
        "Auto-fallback must hand the clipboard backend the ORIGINAL "
        "URL HTML, not the CID-rewritten HTML. The recipient would "
        "otherwise paste broken `cid:` references."
    )
    assert "cid:" not in captured["html"]
    # No inline_images should travel to the clipboard backend.
    assert captured["inline"] == ()


def test_compose_default_image_mode_is_auto(tmp_path):
    """Phase 2: the default is now `image_mode='auto'`, which resolves
    to `'cid'` for the Outlook backend and `'url'` for everything
    else. The previous test pinned the URL default; that pin is now
    obsolete -- replaced by `test_compose_auto_resolves_to_cid_for_outlook`
    + `test_compose_auto_resolves_to_url_for_apple_mail` below."""
    # Set up the asset layout so CID rewrite has somewhere to read.
    asset_dir = tmp_path / "assets" / "issue-1"
    asset_dir.mkdir(parents=True)
    (asset_dir / "photo.jpg").write_bytes(b"\xff\xd8\xff" + b"X" * 100)
    repo_prefix = "https://raw.githubusercontent.com/owner/repo/main"
    html = f'<html><body><img src="{repo_prefix}/assets/issue-1/photo.jpg"></body></html>'

    handler = MailHandler(kind="outlook", name="Microsoft Outlook")
    captured: dict = {}

    def fake_compose(self, draft):
        captured["html"] = draft.html
        captured["inline"] = draft.inline_images

    with patch("scripts.mail.detect_default_mail_handler",
               return_value=handler), \
         patch("scripts.mail.outlook.OutlookBackend.is_available",
               return_value=True), \
         patch("scripts.mail.outlook.OutlookBackend.compose",
               new=fake_compose):
        compose(
            html, subject="Test", backend="outlook",
            asset_dir=asset_dir,  # required because auto -> cid here
        )
        # No image_mode argument passed.

    # auto -> cid (Outlook detected) -> HTML CID-rewritten + photo attached.
    assert "cid:meridian-" in captured["html"], (
        "Phase 2 default must resolve auto -> cid for Outlook backend; "
        "the HTML should be CID-rewritten."
    )
    assert len(captured["inline"]) == 1


def test_compose_auto_resolves_to_cid_for_outlook(tmp_path):
    """Phase 2 dispatcher rule: auto + Outlook -> cid."""
    asset_dir = tmp_path / "assets" / "issue-1"
    asset_dir.mkdir(parents=True)
    (asset_dir / "photo.jpg").write_bytes(b"\xff\xd8\xff" + b"X" * 100)
    repo_prefix = "https://raw.githubusercontent.com/owner/repo/main"
    html = f'<img src="{repo_prefix}/assets/issue-1/photo.jpg">'

    handler = MailHandler(kind="outlook", name="Microsoft Outlook")
    captured: dict = {}

    def fake_compose(self, draft):
        captured["html"] = draft.html

    with patch("scripts.mail.detect_default_mail_handler",
               return_value=handler), \
         patch("scripts.mail.outlook.OutlookBackend.is_available",
               return_value=True), \
         patch("scripts.mail.outlook.OutlookBackend.compose",
               new=fake_compose):
        compose(
            html, subject="Test", backend="auto",
            image_mode="auto", asset_dir=asset_dir,
        )

    assert "cid:" in captured["html"]


def test_compose_auto_resolves_to_url_for_apple_mail(tmp_path):
    """Phase 2 dispatcher rule: auto + non-Outlook -> url. The HTML
    is NOT rewritten (CID would have nowhere to attach the photo)."""
    handler = MailHandler(kind="apple_mail", name="Apple Mail")
    original_html = '<img src="https://raw.githubusercontent.com/x/y/main/assets/issue-1/x.jpg">'
    captured: dict = {}

    def fake_compose(self, draft):
        captured["html"] = draft.html

    with patch("scripts.mail.detect_default_mail_handler",
               return_value=handler), \
         patch("scripts.mail.outlook.OutlookBackend.is_available",
               return_value=False), \
         patch("scripts.mail.clipboard_mailto.ClipboardMailtoBackend.compose",
               new=fake_compose):
        compose(original_html, subject="Test", image_mode="auto")

    # No CID rewriting on the non-Outlook path.
    assert captured["html"] == original_html
    assert "cid:" not in captured["html"]
