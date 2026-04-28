"""Tests for the shared hidden-element filter (`scripts/html_utils.py`).

Round-9 code-review HIGH: the same 5-selector list lived in
`scripts/validator.py` (deciding what's visible to recipients for
the masthead-token guard) and `scripts/mail/plaintext.py` (deciding
what survives into the multipart/text body). Consolidated here.
Tests pin the contract so re-divergence becomes impossible.
"""

from __future__ import annotations

from bs4 import BeautifulSoup

from scripts.html_utils import remove_hidden_elements


def _parse(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


def test_remove_hidden_drops_display_none():
    soup = _parse("<div style='display:none'>SECRET</div><p>visible</p>")
    remove_hidden_elements(soup)
    assert "SECRET" not in soup.get_text()
    assert "visible" in soup.get_text()


def test_remove_hidden_drops_display_none_with_space():
    soup = _parse("<div style='display: none'>HIDDEN</div><p>visible</p>")
    remove_hidden_elements(soup)
    assert "HIDDEN" not in soup.get_text()


def test_remove_hidden_drops_visibility_hidden():
    soup = _parse("<span style='visibility:hidden'>GONE</span><p>seen</p>")
    remove_hidden_elements(soup)
    assert "GONE" not in soup.get_text()


def test_remove_hidden_drops_visibility_hidden_with_space():
    soup = _parse(
        "<span style='visibility: hidden'>GONE</span><p>seen</p>"
    )
    remove_hidden_elements(soup)
    assert "GONE" not in soup.get_text()


def test_remove_hidden_drops_hidden_attribute():
    soup = _parse("<div hidden>HTML5_HIDDEN</div><p>seen</p>")
    remove_hidden_elements(soup)
    assert "HTML5_HIDDEN" not in soup.get_text()


def test_remove_hidden_keeps_normal_elements():
    soup = _parse(
        "<p>visible 1</p>"
        "<div>visible 2</div>"
        "<span>visible 3</span>"
    )
    remove_hidden_elements(soup)
    text = soup.get_text()
    for n in (1, 2, 3):
        assert f"visible {n}" in text


def test_remove_hidden_is_in_place():
    """Mutates the soup; returns None (no chaining)."""
    soup = _parse("<div hidden>X</div>")
    result = remove_hidden_elements(soup)
    assert result is None


def test_validator_references_the_shared_remove_hidden_elements():
    """Round-9 code-review HIGH + round-10 code-review MEDIUM:
    assert IDENTITY (the same callable object) rather than name
    presence -- a re-export under a different name OR a local
    function literally named `remove_hidden_elements` would have
    passed the bundle-28 check. Pin the identity so re-divergence
    becomes structurally impossible."""
    import scripts.validator as v
    assert any(
        getattr(v, name, None) is remove_hidden_elements
        for name in dir(v)
    ), (
        "scripts.validator does not reference the shared "
        "remove_hidden_elements -- the round-9 de-duplication "
        "regressed."
    )


def test_plaintext_references_the_shared_remove_hidden_elements():
    import scripts.mail.plaintext as p
    assert any(
        getattr(p, name, None) is remove_hidden_elements
        for name in dir(p)
    ), (
        "scripts.mail.plaintext does not reference the shared "
        "remove_hidden_elements -- the round-9 de-duplication "
        "regressed."
    )


# ---------- Bundle 29: parse_html + visible_text ------------------------

def test_parse_html_returns_beautifulsoup_with_correct_parser():
    """`parse_html` is the toolkit's single entry point for BS4
    construction so a future migration to `lxml` is one-line."""
    from scripts.html_utils import parse_html
    soup = parse_html("<p>x</p>")
    assert soup.find("p").text == "x"
    # It's an actual BeautifulSoup instance, not a NavigableString.
    from bs4 import BeautifulSoup
    assert isinstance(soup, BeautifulSoup)


def test_visible_text_drops_hidden_blocks():
    """`visible_text(html)` is the shorthand for "what does the
    recipient actually read?" -- used by the masthead-token guard
    and any future plaintext-ratio computations."""
    from scripts.html_utils import visible_text
    html = (
        "<p>Hello.</p>"
        "<div style='display:none'>SECRET</div>"
        "<p>World.</p>"
    )
    text = visible_text(html)
    assert "Hello." in text
    assert "World." in text
    assert "SECRET" not in text


def test_visible_text_drops_html_comments():
    """BS4's get_text drops comments by default; pin it."""
    from scripts.html_utils import visible_text
    text = visible_text("<p>Body.</p><!-- editor note -->")
    assert "editor note" not in text
    assert "Body." in text
