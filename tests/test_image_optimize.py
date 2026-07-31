"""Photo resizing and the whole-message size budget.

The newsletter renders images at 560 px wide, but a photo off a camera
or a phone is 1500-6000 px. Every recipient's client was already
downscaling them, so the message carried several times more bytes than
anyone could see -- paid for in message size, mailbox quota and load
time on a slow connection.

Measured on the reported production document: 1.6 MB of media becomes
~470 KB, and the estimated `.eml` payload drops from ~2.2 MB to ~640 KB
with no visible difference.
"""

from __future__ import annotations

import io

import pytest

from scripts.image_handler import (
    DEFAULT_IMAGE_QUALITY, DEFAULT_MAX_IMAGE_PX, optimize_image,
)
from scripts.validator import validate

Image = pytest.importorskip("PIL.Image", reason="Pillow not installed")


def _photo(path, width, height, fmt="JPEG", colour=(120, 90, 60)):
    """A noisy image, so it does not compress to nothing and the
    before/after comparison means something."""
    import random
    from PIL import Image as I

    rng = random.Random(1)
    im = I.new("RGB", (width, height), colour)
    px = im.load()
    for x in range(0, width, 3):
        for y in range(0, height, 3):
            px[x, y] = (rng.randrange(256), rng.randrange(256),
                        rng.randrange(256))
    im.save(path, fmt, quality=95) if fmt == "JPEG" else im.save(path, fmt)
    return path


def test_an_oversized_photo_is_resized_and_gets_much_smaller(tmp_path):
    p = _photo(tmp_path / "camera.jpg", 4000, 3000)
    before = p.stat().st_size

    changed, after = optimize_image(p)

    assert changed is True
    assert after < before / 2, f"{before} -> {after} is not a real saving"
    with Image.open(p) as im:
        assert im.width == DEFAULT_MAX_IMAGE_PX
        assert im.height == pytest.approx(DEFAULT_MAX_IMAGE_PX * 3 / 4, abs=2)


def test_an_already_small_photo_is_left_alone(tmp_path):
    """Re-encoding a small image would lose quality for no benefit."""
    p = _photo(tmp_path / "small.jpg", 800, 600)
    before = p.read_bytes()

    changed, _ = optimize_image(p)

    assert changed is False
    assert p.read_bytes() == before, "an in-budget photo was re-encoded"


def test_a_png_stays_a_png(tmp_path):
    """Diagrams and charts are usually PNG. Resizing is safe -- they
    display at 560 px regardless -- but re-encoding one as JPEG would
    put ringing around fine text, so the format must be preserved."""
    p = _photo(tmp_path / "diagram.png", 3000, 2000, fmt="PNG")

    changed, _ = optimize_image(p)

    assert changed is True
    with Image.open(p) as im:
        assert im.format == "PNG"
        assert im.width == DEFAULT_MAX_IMAGE_PX


def test_exif_gps_does_not_survive_into_the_newsletter(tmp_path):
    """A phone photo routinely carries the coordinates it was taken at.
    That should not reach ~50 recipients, nor a public GitHub path in
    hosted-photo mode. The resize round-trip drops EXIF entirely."""
    from PIL import Image as I

    p = _photo(tmp_path / "gps.jpg", 2400, 1800)
    with I.open(p) as im:
        exif = im.getexif()
        exif[0x8825] = {1: "N", 2: (35.0, 10.0, 0.0)}   # GPSInfo
        im.save(p, "JPEG", quality=95, exif=exif)
    assert I.open(p).getexif().get(0x8825) is not None, "precondition"

    optimize_image(p)

    with I.open(p) as im:
        assert not im.getexif().get(0x8825), "GPS survived the resize"


def test_quality_knob_changes_the_result(tmp_path):
    a = _photo(tmp_path / "a.jpg", 3000, 2000)
    b = _photo(tmp_path / "b.jpg", 3000, 2000)

    optimize_image(a, quality=95)
    optimize_image(b, quality=50)

    assert b.stat().st_size < a.stat().st_size


def test_resizing_can_be_turned_off(tmp_path):
    """`--max-image-px 0` maps to `max_image_px=None` -- an editor who
    genuinely needs full resolution must be able to say so."""
    from scripts.image_handler import extract_embedded
    # exercised through extract_embedded in test_docx_hardening; here we
    # only pin that a huge threshold is a no-op.
    p = _photo(tmp_path / "c.jpg", 2000, 1500)
    before = p.read_bytes()

    changed, _ = optimize_image(p, max_px=99_000)

    assert changed is False
    assert p.read_bytes() == before


def test_a_corrupt_image_is_left_alone_rather_than_failing_the_build(tmp_path):
    """Optimisation is best-effort. A newsletter that ships a
    slightly-too-large photo beats one that refuses to build."""
    p = tmp_path / "broken.jpg"
    p.write_bytes(b"\xff\xd8\xff" + b"not really a jpeg")

    changed, size = optimize_image(p)

    assert changed is False
    assert size == p.stat().st_size


# ---------- whole-message size budget ---------------------------------

_HTML = "<html><body><p>hello</p></body></html>"


def test_size_budget_counts_the_photos_not_just_the_html():
    """`validate` only ever measured the HTML, so a 24 MB newsletter
    passed silently and then bounced off the recipients' mail servers --
    which the editor discovers hours later as a pile of NDRs."""
    small = validate(_HTML, check_remote=False, attachment_bytes=0)
    assert small.ok
    assert not any("MB" in w for w in small.warnings)

    near = validate(_HTML, check_remote=False, attachment_bytes=16_000_000)
    assert near.ok, "a large-but-sendable email must not be blocked"
    assert any("mail servers" in w for w in near.warnings)


def test_an_unsendable_email_is_blocked_with_actionable_advice():
    result = validate(_HTML, check_remote=False, attachment_bytes=30_000_000)

    assert not result.ok
    message = " ".join(result.errors)
    assert "bounce" in message
    assert "Compress Pictures" in message, "tell them how to fix it"


def test_base64_inflation_is_accounted_for():
    """Attachments are base64-encoded on the wire, which adds ~37%. A
    budget measured against the raw bytes would let a message through
    that is actually over the limit."""
    just_under_raw = validate(
        _HTML, check_remote=False, attachment_bytes=23_000_000)
    assert not just_under_raw.ok, (
        "23 MB of photos is ~31.5 MB encoded and must be blocked")
