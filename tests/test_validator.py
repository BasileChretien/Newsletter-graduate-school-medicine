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
    with patch("scripts.validator.requests.head", return_value=_mock_response(200)):
        r = validate(HTML_OK)
    assert r.size_bytes < GMAIL_CLIP_BYTES
    assert r.ok
    assert not r.warnings


def test_validate_size_warns_when_too_big():
    big = "x" * (GMAIL_CLIP_BYTES + 100)
    r = validate(f"<html><body>{big}</body></html>", check_remote=False)
    assert any("Gmail clips" in w for w in r.warnings)


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
    assert any("placeholder" in w.lower() for w in r.warnings)


def test_validate_no_placeholders_when_clean():
    html = "<html><body><p>Hello world.</p></body></html>"
    r = validate(html, check_remote=False)
    assert r.placeholders == ()
    assert not any("placeholder" in w.lower() for w in r.warnings)


def test_validate_broken_image_warns_not_errors():
    """Broken image URLs are now WARNINGS not ERRORS -- a flaky HEAD
    check shouldn't abort the editor's pipeline."""
    with patch("scripts.validator.requests.head", return_value=_mock_response(404)):
        r = validate(HTML_OK)
    assert r.ok            # build still succeeds
    assert r.broken_images
    assert any("unreachable" in w for w in r.warnings)
    assert not r.errors


def test_validate_skip_remote():
    r = validate(HTML_OK, check_remote=False)
    assert r.ok
    assert not r.broken_images
    assert not r.broken_anchors
    assert len(r.image_urls) == 1
    assert len(r.anchor_urls) == 1


def test_validate_handles_request_exception():
    with patch("scripts.validator.requests.head",
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
