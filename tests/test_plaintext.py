"""Tests for the HTML -> plaintext alternative builder.

The plaintext alt is set on Outlook drafts so the email serializes
as `multipart/alternative` (HTML + text), which scores lower with
corporate spam filters than HTML-only mail.
"""

from __future__ import annotations

from scripts.mail.plaintext import html_to_plaintext


def test_plaintext_strips_html_tags():
    out = html_to_plaintext("<p>Hello <strong>world</strong></p>")
    assert "<" not in out
    assert ">" not in out
    assert "Hello world" in out


def test_plaintext_inserts_line_breaks_for_block_elements():
    """<p>, <h1>, <li>, <br>, <tr>, <div> -- all produce newlines
    so the plaintext is readable without HTML rendering.

    Bundle 29 normalises all newlines to CRLF (round-10 deliverability
    HIGH 1) so we match against `\\r\\n` here."""
    out = html_to_plaintext(
        "<p>First paragraph.</p>"
        "<p>Second paragraph.</p>"
    )
    assert (
        "First paragraph.\r\nSecond paragraph." in out
        or "First paragraph.\r\n\r\nSecond paragraph." in out
    )


def test_plaintext_renders_anchor_url_after_label():
    """A link should show its URL after the label so plaintext
    readers can copy/click."""
    out = html_to_plaintext(
        '<a href="https://example.com/">click here</a>'
    )
    assert "click here" in out
    assert "https://example.com/" in out


def test_plaintext_drops_script_and_style():
    """Script/style content must NOT leak into the plaintext."""
    out = html_to_plaintext(
        "<style>body { color: red; }</style>"
        "<script>alert(1)</script>"
        "<p>Visible</p>"
    )
    assert "alert" not in out
    assert "color: red" not in out
    assert "Visible" in out


def test_plaintext_drops_hidden_elements():
    """display:none / visibility:hidden / hidden attribute -- all
    invisible to recipients, all should be invisible in plaintext."""
    out = html_to_plaintext(
        "<div style='display:none'>SECRET</div>"
        "<div style='visibility: hidden'>HIDDEN</div>"
        "<span hidden>GONE</span>"
        "<p>Visible content</p>"
    )
    assert "SECRET" not in out
    assert "HIDDEN" not in out
    assert "GONE" not in out
    assert "Visible content" in out


def test_plaintext_drops_html_comments():
    """HTML comments are documentation, not body text."""
    out = html_to_plaintext(
        "<!-- editor note: review before sending -->"
        "<p>The email body.</p>"
    )
    # BeautifulSoup default does drop comments via get_text -- pin it.
    assert "editor note" not in out
    assert "The email body." in out


def test_plaintext_collapses_whitespace_runs():
    """Runs of spaces/tabs collapse to single space within a line,
    runs of >2 blank lines collapse to one blank line between blocks."""
    out = html_to_plaintext(
        "<p>Lots    of   space.</p>"
        "<p></p><p></p><p></p>"
        "<p>After several blanks.</p>"
    )
    assert "Lots of space." in out
    # No more than one consecutive blank line.
    assert "\n\n\n" not in out


def test_plaintext_handles_empty_input():
    """Bundle 29 emits CRLF-only output (round-10 deliverability HIGH 1)."""
    assert html_to_plaintext("") in ("\r\n", "")
    assert html_to_plaintext("<html><body></body></html>") in ("\r\n", "")


def test_plaintext_preserves_text_order():
    """Order of visible text must match the document order so
    plaintext readers see the same sequence as HTML readers.

    Bundle 28: <h1> / <h2> are now uppercased and wrapped in
    `=== ... ===` markers (round-9 email H2 -- richer plaintext
    for spam-filter scoring), so we search for the upper-cased form."""
    out = html_to_plaintext(
        "<h1>Title</h1>"
        "<p>Intro paragraph.</p>"
        "<h2>Section</h2>"
        "<p>Section body.</p>"
    )
    title_pos = out.find("TITLE")
    intro_pos = out.find("Intro paragraph.")
    section_pos = out.find("SECTION")
    body_pos = out.find("Section body.")
    assert 0 <= title_pos < intro_pos < section_pos < body_pos


# ---------- Bundle 28: richer plaintext for spam-filter scoring ----------

def test_plaintext_h1_h2_get_uppercase_marker_wrapping():
    """Round-9 email H2: `<h1>` / `<h2>` produce `=== HEADING ===`
    blocks in plaintext so the multipart/alternative text part has
    visible structure (better spam-filter scoring + more readable for
    plaintext clients)."""
    out = html_to_plaintext("<h1>Important News</h1><p>Body.</p>")
    assert "=== IMPORTANT NEWS ===" in out


def test_plaintext_h3_through_h6_get_minor_marker():
    out = html_to_plaintext(
        "<h3>Sub-heading</h3><h4>Tier 4</h4>"
        "<h5>Tier 5</h5><h6>Tier 6</h6>"
    )
    assert "--- Sub-heading ---" in out
    assert "--- Tier 4 ---" in out
    assert "--- Tier 5 ---" in out
    assert "--- Tier 6 ---" in out


def test_plaintext_li_gets_bullet_glyph():
    out = html_to_plaintext(
        "<ul><li>First</li><li>Second</li></ul>"
    )
    assert "• First" in out
    assert "• Second" in out


def test_plaintext_drops_javascript_url():
    """Round-9 security MEDIUM: the URL allowlist must drop unsafe
    schemes. Only the visible label survives, not the URL."""
    out = html_to_plaintext('<a href="javascript:alert(1)">click</a>')
    assert "javascript:" not in out
    assert "alert" not in out
    assert "click" in out


def test_plaintext_drops_data_url():
    out = html_to_plaintext('<a href="data:text/html,XSS">link</a>')
    assert "data:" not in out
    assert "XSS" not in out
    assert "link" in out


def test_plaintext_drops_file_url():
    out = html_to_plaintext('<a href="file:///etc/passwd">label</a>')
    assert "file://" not in out
    assert "passwd" not in out
    assert "label" in out


def test_plaintext_drops_tel_url():
    """`tel:` is not in the safe-scheme allowlist."""
    out = html_to_plaintext('<a href="tel:+1234567890">phone</a>')
    assert "tel:" not in out
    assert "+1234567890" not in out
    assert "phone" in out


def test_plaintext_drops_vbscript_url():
    """`vbscript:` is the legacy IE / Outlook desktop WebView vector;
    not in `_SAFE_URL_SCHEMES`. Round-10 code-review MEDIUM."""
    out = html_to_plaintext('<a href="vbscript:msgbox(1)">click</a>')
    assert "vbscript:" not in out
    assert "msgbox" not in out
    assert "click" in out


def test_plaintext_accepts_uppercase_https():
    """Round-10 security MEDIUM 3: the scheme allowlist check is
    case-INsensitive so legitimate `HTTPS://example.com` survives.
    Bundle 28's case-sensitive check would silently drop the URL."""
    out = html_to_plaintext('<a href="HTTPS://example.com/">click</a>')
    assert "HTTPS://example.com/" in out
    assert "click" in out


def test_plaintext_drops_mixed_case_javascript():
    """Mixed-case `JavaScript:` must still be rejected after the
    case-insensitive change (we allowlist, not denylist)."""
    out = html_to_plaintext('<a href="JavaScript:alert(1)">click</a>')
    # JavaScript scheme must NOT survive in the output.
    assert "JavaScript:" not in out
    assert "javascript:" not in out
    assert "alert" not in out
    assert "click" in out


def test_plaintext_heading_with_link_does_not_leak_url_into_marker():
    """Round-10 python-reviewer HIGH: bundle 28 ran link expansion
    BEFORE heading rewriting, so `<h2><a href="x">Link</a></h2>` got
    rewritten to a NavigableString `Link (x)`, then wrapped in
    `=== ... ===`, producing `=== LINK (HTTPS://X.COM) ===`. Bundle
    29 swaps the order so the URL never appears in the heading marker."""
    out = html_to_plaintext(
        '<h2><a href="https://example.com/">Lab News</a></h2>'
        '<p>Body.</p>'
    )
    # Heading marker uppercased label, no URL leak.
    assert "=== LAB NEWS ===" in out
    # The URL still appears OUTSIDE the heading marker (in the body
    # if there's a separate link, or not at all in this case since
    # the link was inside the heading and consumed by it).
    # Specifically: no URL inside any === ... === block.
    import re as _re
    for marker in _re.findall(r"===\s*[^=]*\s*===", out):
        assert "://" not in marker, (
            f"URL leaked into heading marker: {marker!r}"
        )


def test_plaintext_heading_uppercase_consistent_for_nested_tags():
    """Round-10 deliverability M2: `<h2>` heading text must be
    uppercased in BOTH the simple-string and nested-tag cases.
    `<h2>Section <em>Foo</em></h2>` -> `=== SECTION FOO ===` (not
    `=== Section Foo ===`)."""
    out = html_to_plaintext("<h2>Section <em>Foo</em></h2>")
    assert "=== SECTION FOO ===" in out


def test_plaintext_uses_crlf_line_endings():
    """Round-10 deliverability HIGH 1: RFC 5322 mandates CRLF in
    mail bodies. Bundle 28's bare-LF output would trip strict MIME
    validators on Send-As / forwarded paths."""
    out = html_to_plaintext("<p>One</p><p>Two</p>")
    assert "\r\n" in out
    # No bare LF that isn't already part of CRLF.
    bare_lf_count = out.count("\n") - out.count("\r\n")
    assert bare_lf_count == 0, (
        f"Plaintext contains {bare_lf_count} bare LF; must be all CRLF."
    )


def test_plaintext_keeps_mailto_url():
    """`mailto:` IS in the allowlist."""
    out = html_to_plaintext('<a href="mailto:dean@nu.ac.jp">email</a>')
    assert "mailto:dean@nu.ac.jp" in out
    assert "email" in out


def test_plaintext_handles_unclosed_tags_gracefully():
    """Round-9 code-review LOW: malformed HTML from a Word paste must
    not raise. BeautifulSoup handles unclosed tags; pin the contract."""
    out = html_to_plaintext("<p>Unclosed paragraph<p>Next one.")
    assert "Unclosed paragraph" in out
    assert "Next one" in out


def test_plaintext_handles_html_entity():
    """`&#160;` (NBSP entity) and `&amp;` should normalise sanely."""
    out = html_to_plaintext("<p>A&nbsp;B&amp;C&#160;D</p>")
    # NBSP collapses to space, & survives.
    assert "A B&C D" in out or "A B & C D" in out


def test_plaintext_strict_fallback_strips_tags():
    """The strict regex-based fallback (used when html_to_plaintext
    raises) produces SOME plaintext rather than letting Outlook
    auto-generate a poor one from HTML."""
    from scripts.mail.plaintext import html_to_plaintext_strict_fallback
    out = html_to_plaintext_strict_fallback(
        "<p>Hello <strong>world</strong></p>"
    )
    assert "<" not in out
    assert ">" not in out
    assert "Hello" in out
    assert "world" in out


def test_plaintext_for_realistic_newsletter_fragment():
    """A small newsletter-shaped HTML produces readable plaintext."""
    html = """
    <html><body>
      <h1>MERIDIAN</h1>
      <p class="issue">VOL. 12 | ISSUE NO. 3 | MARCH 2026</p>
      <h2>Section 1 - Research</h2>
      <p>Recent grant awarded to Prof. Tanaka.</p>
      <ul>
        <li>JSPS Kakenhi 2026</li>
        <li>AMED Translational</li>
      </ul>
      <p><a href="https://example.com/grant">Press release</a></p>
    </body></html>
    """
    out = html_to_plaintext(html)
    assert "MERIDIAN" in out
    assert "VOL. 12" in out
    assert "Recent grant awarded" in out
    assert "JSPS Kakenhi 2026" in out
    assert "Press release" in out
    assert "https://example.com/grant" in out
