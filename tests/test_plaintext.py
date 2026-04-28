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
    so the plaintext is readable without HTML rendering."""
    out = html_to_plaintext(
        "<p>First paragraph.</p>"
        "<p>Second paragraph.</p>"
    )
    assert "First paragraph.\nSecond paragraph." in out or \
           "First paragraph.\n\nSecond paragraph." in out


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
    assert html_to_plaintext("") == "\n" or html_to_plaintext("") == ""
    assert html_to_plaintext("<html><body></body></html>") in ("\n", "")


def test_plaintext_preserves_text_order():
    """Order of visible text must match the document order so
    plaintext readers see the same sequence as HTML readers."""
    out = html_to_plaintext(
        "<h1>Title</h1>"
        "<p>Intro paragraph.</p>"
        "<h2>Section</h2>"
        "<p>Section body.</p>"
    )
    # Verify the order within the joined plaintext.
    title_pos = out.find("Title")
    intro_pos = out.find("Intro paragraph.")
    section_pos = out.find("Section")
    body_pos = out.find("Section body.")
    assert 0 <= title_pos < intro_pos < section_pos < body_pos


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
