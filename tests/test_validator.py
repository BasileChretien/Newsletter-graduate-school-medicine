"""Tests for validator."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from scripts.config import GMAIL_CLIP_BYTES
from scripts.validator import report, validate


HTML_OK = """
<html><body>
<a href="https://example.com/page">link</a>
<img src="https://example.com/img.jpg" alt="x">
</body></html>
""".strip()


def _mock_response(status=200):
    class R:
        status_code = status
    return R()


def test_validate_size_ok():
    with patch("requests.head", return_value=_mock_response(200)):
        r = validate(HTML_OK)
    assert r.size_bytes < GMAIL_CLIP_BYTES
    assert r.ok
    assert not r.warnings


def test_validate_size_warns_when_too_big():
    big = "x" * (GMAIL_CLIP_BYTES + 100)
    r = validate(f"<html><body>{big}</body></html>", check_remote=False)
    assert any("Gmail" in w for w in r.warnings)


def test_validate_flags_unfilled_placeholders():
    html = (
        "<html><body><p>Welcome from [Author(s)] on "
        "[YYYY/MM/DD] in [Country].</p></body></html>"
    )
    r = validate(html, check_remote=False)
    placeholders = set(r.placeholders)
    assert "[Author(s)]" in placeholders
    assert "[YYYY/MM/DD]" in placeholders
    assert "[Country]" in placeholders
    # Wording was reframed in B17 to "brackets like ... you may want to fill"
    assert any("brackets" in w.lower() or "placeholder" in w.lower()
               for w in r.warnings)


def test_validate_no_placeholders_when_clean():
    html = "<html><body><p>Hello world.</p></body></html>"
    r = validate(html, check_remote=False)
    assert r.placeholders == ()
    assert not any("placeholder" in w.lower() for w in r.warnings)


def test_validate_blocks_unfilled_masthead():
    """Sending with `VOL. XX | ISSUE NO. XX | MONTH YEAR` in the masthead
    leaks "broken send" into recipients' inbox previews. Hard-block."""
    html = (
        "<html><body><p class='issue'>"
        "VOL. XX | ISSUE NO. XX | MONTH YEAR"
        "</p></body></html>"
    )
    r = validate(html, check_remote=False)
    assert not r.ok
    assert any("VOL. XX" in e for e in r.errors)


def test_validate_passes_filled_masthead():
    html = (
        "<html><body><p class='issue'>"
        "VOL. 12 | ISSUE NO. 3 | MARCH 2026"
        "</p></body></html>"
    )
    r = validate(html, check_remote=False)
    assert r.ok
    assert not any("VOL. XX" in e for e in r.errors)


def test_validate_blocks_nbsp_bypassed_masthead():
    """Word silently substitutes U+00A0 (NBSP) for ASCII space in
    pasted text. The unfilled-masthead guard must NFKC-normalize so
    `VOL. XX` is caught as if it were `VOL. XX` -- otherwise an
    editor pasting "VOL. XX" from another doc would ship the email
    with the placeholder still in the subject preview."""
    html = (
        "<html><body><p class='issue'>"
        "VOL. XX | ISSUE NO. XX | MONTH YEAR"
        "</p></body></html>"
    )
    r = validate(html, check_remote=False)
    assert not r.ok
    assert any("VOL. XX" in e for e in r.errors)


def test_validate_blocks_collapsed_whitespace_masthead():
    """Multiple spaces between tokens (e.g. accidental double-space
    after period) should still trigger the unfilled-masthead block."""
    html = "<html><body><p>VOL.   XX  TBD</p></body></html>"
    r = validate(html, check_remote=False)
    assert not r.ok
    assert any("VOL. XX" in e for e in r.errors)


# ---------- Bundle 26: hidden-content false-positive guard ---------------

def test_validate_ignores_display_none_masthead_token():
    """Tokens inside `display:none` blocks are not visible to recipients
    in their inbox preview, so they shouldn't fire the hard-block.

    This guards against templates that legitimately include the literal
    "VOL. XX" string inside a hidden preheader as a documentation /
    fallback (e.g. screen-reader-only text that the editor never sees)."""
    html = (
        "<html><body>"
        "<div style='display:none'>VOL. XX | ISSUE NO. XX | MONTH YEAR</div>"
        "<p>VOL. 12 | ISSUE NO. 3 | MARCH 2026</p>"
        "</body></html>"
    )
    r = validate(html, check_remote=False)
    assert r.ok, (
        "display:none should NOT trip the unfilled-masthead block; "
        f"got errors: {r.errors}"
    )


def test_validate_ignores_visibility_hidden_masthead_token():
    """Same logic for `visibility: hidden`."""
    html = (
        "<html><body>"
        "<span style='visibility:hidden'>VOL. XX</span>"
        "<p>VOL. 12 | ISSUE NO. 3 | MARCH 2026</p>"
        "</body></html>"
    )
    r = validate(html, check_remote=False)
    assert r.ok


def test_validate_ignores_hidden_attribute_masthead_token():
    """The HTML5 `hidden` attribute is also recipient-invisible."""
    html = (
        "<html><body>"
        "<div hidden>VOL. XX</div>"
        "<p>VOL. 12 | ISSUE NO. 3 | MARCH 2026</p>"
        "</body></html>"
    )
    r = validate(html, check_remote=False)
    assert r.ok


def test_validate_still_blocks_visible_token_when_hidden_present():
    """A hidden block alongside a visible unfilled token must still
    fail -- we filter the hidden block, but the visible one still
    has to trigger."""
    html = (
        "<html><body>"
        "<div style='display:none'>(harmless hidden text)</div>"
        "<p>Welcome to ISSUE NO. XX of our newsletter.</p>"
        "</body></html>"
    )
    r = validate(html, check_remote=False)
    assert not r.ok
    assert any("ISSUE NO. XX" in e for e in r.errors)


# ---------- Bundle 26: HTML comment is not a token leak ------------------

def test_validate_excludes_hidden_anchors_from_audit_trail():
    """Round-10 security LOW 5: a `<a href hidden>` (or `display:none`
    wrapper) is invisible to recipients but, before bundle 29, would
    end up in `result.anchor_urls` AND get a HEAD request. We now
    drop hidden elements before scanning."""
    html = (
        "<html><body>"
        "<div style='display:none'>"
        "<a href='https://hidden.example.com/secret'>x</a>"
        "</div>"
        "<p>Visible body. <a href='https://example.com/visible'>link</a></p>"
        "</body></html>"
    )
    r = validate(html, check_remote=False)
    # Only the visible link is in the audit trail.
    assert "https://example.com/visible" in r.anchor_urls
    assert "https://hidden.example.com/secret" not in r.anchor_urls


def test_validate_html_comment_does_not_false_positive():
    """The template's explanatory `<!-- ... VOL. XX ... -->` comment
    must not trigger the hard-block: it's documentation, not visible
    content. BeautifulSoup's get_text() already drops comments; this
    test pins the contract."""
    html = (
        "<html><body>"
        "<!-- NEVER include the placeholder issue-line tokens "
        "(VOL. XX | ISSUE NO. XX | MONTH YEAR) here. -->"
        "<p>VOL. 12 | ISSUE NO. 3 | MARCH 2026</p>"
        "</body></html>"
    )
    r = validate(html, check_remote=False)
    assert r.ok


def test_validate_broken_image_warns_not_errors():
    """Broken image URLs are now WARNINGS not ERRORS -- a flaky HEAD
    check shouldn't abort the editor's pipeline."""
    with patch("requests.head", return_value=_mock_response(404)):
        r = validate(HTML_OK)
    assert r.ok            # build still succeeds
    assert r.broken_images
    assert any("couldn't be reached" in w or "unreachable" in w
               for w in r.warnings)
    assert not r.errors


def test_validate_skip_remote():
    r = validate(HTML_OK, check_remote=False)
    assert r.ok
    assert not r.broken_images
    assert not r.broken_anchors
    assert len(r.image_urls) == 1
    assert len(r.anchor_urls) == 1


def test_validate_handles_request_exception():
    with patch("requests.head",
               side_effect=Exception("boom")):
        r = validate(HTML_OK)
    assert r.broken_images
    assert r.broken_anchors


def test_report_contains_size_and_counts():
    r = validate(HTML_OK, check_remote=False)
    text = report(r)
    assert "Size:" in text
    assert "Images:" in text
    assert "Links:" in text


# ---------------------------------------------------------------------
# Placeholder detection: reported as "[date] is not highlighted in the
# preview", which turned out to be the validator never reporting it.
# ---------------------------------------------------------------------

@pytest.mark.parametrize("token", [
    "[date]",                        # the reported miss
    "[handle]",
    "[inquiry@med.nagoya-u.ac.jp]",  # example address in the template
    "[joint research / student exchange / joint degree]",
    "[X]",                           # single character inside
    "[Author(s)]",                   # these already worked
    "[YYYY/MM/DD]",
    "[Paper Title]",
])
def test_unfilled_placeholders_are_reported_whatever_their_case(token):
    """`[A-Z]` required an uppercase ASCII first character, so every
    lowercase placeholder was invisible: no reminder, and no highlight
    in the preview. `[A-Z]` plus `{1,60}` also demanded two characters
    inside, which is why `[X]` was missed too."""
    from scripts.validator import PLACEHOLDER_RE
    assert PLACEHOLDER_RE.fullmatch(token), f"{token} would go unreported"


@pytest.mark.parametrize("token", ["[1]", "[12]", "[2023]", "[1-3]", "[42]"])
def test_numbered_citations_are_not_mistaken_for_placeholders(token):
    """The counterweight to the fix above. A newsletter carrying a
    reference list would otherwise flag every citation, burying the real
    placeholders the reminder exists to surface -- and, now that the
    preview highlights them, covering the document in false marks."""
    from scripts.validator import PLACEHOLDER_RE
    assert not PLACEHOLDER_RE.fullmatch(token), f"{token} is a citation"


def test_a_japanese_placeholder_would_be_caught():
    """The template is bilingual. It uses no Japanese placeholder today,
    so this guards a future one rather than current behaviour -- but
    silently missing it is the exact failure just fixed, and an
    ASCII-only rule would reintroduce it."""
    from scripts.validator import PLACEHOLDER_RE
    assert PLACEHOLDER_RE.fullmatch("[\u65e5\u4ed8]")


def test_the_shipped_template_has_no_unreported_placeholders():
    """The regression that matters: nine placeholders in the template
    the editor was never told about. Scans the DOCX itself rather than a
    fixture, so adding a lowercase placeholder to the template in future
    fails here instead of shipping unnoticed."""
    import re
    import zipfile

    from scripts.config import MERIDIAN_TEMPLATE
    from scripts.validator import PLACEHOLDER_RE

    with zipfile.ZipFile(MERIDIAN_TEMPLATE) as z:
        xml = b"".join(z.read(n) for n in z.namelist()
                       if n.startswith("word/") and n.endswith(".xml"))
    text = re.sub(rb"<[^>]+>", b"", xml).decode("utf-8", "replace")

    every_token = set(re.findall(r"\[[^\[\]]{1,60}\]", text))
    # Every bracket token in the template is a placeholder: it ships
    # unfilled by definition.
    missed = {t for t in every_token if not PLACEHOLDER_RE.fullmatch(t)}
    assert not missed, f"unreported placeholders in the template: {sorted(missed)}"


def test_the_masthead_check_stays_case_sensitive():
    """Pins a deliberate limitation, so nobody relaxes it the way the
    placeholder regex above was correctly relaxed.

    The masthead tokens are searched across the WHOLE visible document,
    not just the masthead. The shipped template's visitors table carries
    the body placeholder `[Month-Month Year]`, which contains "Month
    Year" in title case. A case-insensitive comparison collides with the
    masthead's `MONTH YEAR` and hard-blocks a correctly filled
    newsletter -- worse than the gap it closes, since this check aborts
    the build rather than warning.

    The real gap it leaves: an editor who retypes the issue line in
    title case is not caught. Closing that properly means scoping the
    search to the masthead element, not relaxing the match.
    """
    filled = ("<html><body><table><tr><td><p>MERIDIAN</p>"
              "<p>VOL. 12 | ISSUE NO. 3 | MARCH 2026</p></td></tr></table>"
              "<p>Visit: [Purpose] &middot; [Month–Month Year]</p>"
              "</body></html>")
    result = validate(filled, check_remote=False)
    assert not any("masthead" in e.lower() for e in result.errors), (
        "a filled masthead was blocked by body text containing "
        f"'Month Year': {result.errors}")

    unfilled = ("<html><body><table><tr><td><p>MERIDIAN</p>"
                "<p>VOL. XX | ISSUE NO. XX | MONTH YEAR</p></td></tr>"
                "</table><p>Body.</p></body></html>")
    assert any("masthead" in e.lower()
               for e in validate(unfilled, check_remote=False).errors)
