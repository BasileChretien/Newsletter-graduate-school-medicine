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


def test_validator_and_plaintext_share_the_helper():
    """Round-9 code-review HIGH: pin the de-duplication. Both
    `scripts.validator` and `scripts.mail.plaintext` must reference
    the shared helper, NOT roll their own selector list."""
    import scripts.validator as v
    import scripts.mail.plaintext as p
    # Both modules import remove_hidden_elements (or reference it via
    # `from scripts.html_utils import remove_hidden_elements`).
    assert "remove_hidden_elements" in dir(v) or any(
        getattr(v, name, None) is remove_hidden_elements for name in dir(v)
    )
    assert "remove_hidden_elements" in dir(p) or any(
        getattr(p, name, None) is remove_hidden_elements for name in dir(p)
    )
