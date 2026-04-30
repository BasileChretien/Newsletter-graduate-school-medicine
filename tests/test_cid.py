"""Tests for `scripts.mail.cid` -- the CID inline-image rewriter.

This module is COM-free (no Outlook involved), so it's exercised
end-to-end on every platform. The Outlook side of the CID flow
(actually attaching files via `mail.Attachments.Add()` and setting
`PR_ATTACH_CONTENT_ID`) is covered by `tests/test_mail.py` with
mocks; here we focus on:

  * URL-to-local-path resolution
  * HTML rewriting (`src=https://...` -> `src=cid:...`)
  * deduplication when the same image appears twice
  * graceful fallthrough when an `<img>` doesn't resolve locally
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.mail.cid import (
    InlineImage, _make_cid, _resolve_local_path, attach_inline_images,
)


# ---------- helpers -----------------------------------------------------

def _make_asset_layout(tmp_path: Path, *,
                       issue: int = 1,
                       image_files: tuple[str, ...] = ("photo1.jpg",),
                       brand_files: tuple[str, ...] = ()) -> Path:
    """Mirror the toolkit's expected layout under `tmp_path`:

      assets/issue-N/<file>   (per-issue uploaded photos)
      images/<file>           (permanent brand assets)

    Returns `assets/issue-N/` so tests can pass it as `asset_dir`."""
    assets = tmp_path / "assets" / f"issue-{issue}"
    assets.mkdir(parents=True)
    for name in image_files:
        (assets / name).write_bytes(b"\xff\xd8\xffJPEGBYTES")
    images = tmp_path / "images"
    images.mkdir()
    for name in brand_files:
        (images / name).write_bytes(b"\x89PNG\r\n\x1a\nPNG")
    return assets


REPO_PREFIX = "https://raw.githubusercontent.com/owner/repo/main"


# ---------- _make_cid ---------------------------------------------------

def test_make_cid_strips_unsafe_chars():
    out = _make_cid("My Photo (final).jpg", 1)
    # Lowercase, no spaces, no parentheses, no leading/trailing dashes.
    assert out == "meridian-01-my-photo-final-.jpg" or \
           out == "meridian-01-my-photo--final-.jpg" or \
           out.startswith("meridian-01-my-photo")
    assert " " not in out
    assert "(" not in out and ")" not in out


def test_make_cid_zero_pads_index():
    """Stable 2-digit index keeps CIDs sortable when there are <100 images."""
    assert _make_cid("a.jpg", 1).startswith("meridian-01-")
    assert _make_cid("a.jpg", 12).startswith("meridian-12-")


def test_make_cid_handles_unicode_only_basename():
    """A basename that's all non-ASCII shouldn't produce an empty CID."""
    out = _make_cid("写真.jpg", 3)
    # Either the strip leaves nothing -> falls back to image-N, OR
    # the .jpg suffix survives. Either way: non-empty, prefixed.
    assert out.startswith("meridian-03-")
    assert len(out) > len("meridian-03-")


def test_make_cid_is_deterministic():
    """Same inputs => same CID. This matters for re-sends of the
    same issue: the editor regenerates after fixing a typo and the
    CIDs stay identical."""
    assert _make_cid("photo.jpg", 5) == _make_cid("photo.jpg", 5)


# ---------- _resolve_local_path -----------------------------------------

def test_resolve_local_path_assets_hit(tmp_path: Path):
    asset_dir = _make_asset_layout(tmp_path, image_files=("photo1.jpg",))
    url = f"{REPO_PREFIX}/assets/issue-1/photo1.jpg"
    resolved = _resolve_local_path(url, asset_dir, REPO_PREFIX)
    assert resolved == asset_dir / "photo1.jpg"


def test_resolve_local_path_images_dir_hit(tmp_path: Path):
    asset_dir = _make_asset_layout(
        tmp_path, image_files=(), brand_files=("seal.png",))
    url = f"{REPO_PREFIX}/images/seal.png"
    resolved = _resolve_local_path(url, asset_dir, REPO_PREFIX)
    assert resolved == tmp_path / "images" / "seal.png"


def test_resolve_local_path_unknown_prefix_returns_none(tmp_path: Path):
    asset_dir = _make_asset_layout(tmp_path)
    # An external image (e.g. an editor pasted a Wikimedia URL) doesn't
    # match our prefix -- correctly returns None and stays external.
    url = "https://upload.wikimedia.org/foo/bar.jpg"
    assert _resolve_local_path(url, asset_dir, REPO_PREFIX) is None


def test_resolve_local_path_missing_file_returns_none(tmp_path: Path):
    asset_dir = _make_asset_layout(tmp_path, image_files=("photo1.jpg",))
    # URL points at our prefix + assets dir, but the file isn't on disk.
    # (e.g. the editor referenced a photo that the build pipeline failed
    # to extract.) Don't crash, don't fabricate -- return None.
    url = f"{REPO_PREFIX}/assets/issue-1/missing.jpg"
    assert _resolve_local_path(url, asset_dir, REPO_PREFIX) is None


def test_resolve_local_path_data_uri_returns_none(tmp_path: Path):
    asset_dir = _make_asset_layout(tmp_path)
    # `data:` URIs and `cid:` references are out-of-scope for the
    # rewriter -- it should leave them alone.
    assert _resolve_local_path(
        "data:image/jpeg;base64,...", asset_dir, REPO_PREFIX) is None
    assert _resolve_local_path("cid:foo", asset_dir, REPO_PREFIX) is None


# ---------- attach_inline_images (the public API) ------------------------

def test_attach_inline_images_rewrites_known_url(tmp_path: Path):
    asset_dir = _make_asset_layout(tmp_path, image_files=("photo1.jpg",))
    html = (
        f'<html><body>'
        f'<img src="{REPO_PREFIX}/assets/issue-1/photo1.jpg">'
        f'</body></html>'
    )
    rewritten, inline = attach_inline_images(
        html, asset_dir, repo_url_prefix=REPO_PREFIX + "/")
    assert len(inline) == 1
    assert inline[0].path == asset_dir / "photo1.jpg"
    assert inline[0].cid.startswith("meridian-")
    assert f'src="cid:{inline[0].cid}"' in rewritten
    # Original URL no longer present in the rewritten output.
    assert REPO_PREFIX not in rewritten


def test_attach_inline_images_leaves_unresolvable_untouched(tmp_path: Path):
    asset_dir = _make_asset_layout(tmp_path, image_files=("photo1.jpg",))
    html = (
        f'<html><body>'
        # Resolves locally:
        f'<img src="{REPO_PREFIX}/assets/issue-1/photo1.jpg">'
        # External (Wikimedia):
        f'<img src="https://upload.wikimedia.org/wiki/foo.jpg">'
        # Repo-prefix but missing on disk:
        f'<img src="{REPO_PREFIX}/assets/issue-1/missing.jpg">'
        f'</body></html>'
    )
    rewritten, inline = attach_inline_images(
        html, asset_dir, repo_url_prefix=REPO_PREFIX + "/")
    # Only the resolvable image was rewritten + attached.
    assert len(inline) == 1
    # Wikimedia URL must survive unchanged.
    assert "upload.wikimedia.org/wiki/foo.jpg" in rewritten
    # Missing-file URL must survive unchanged (graceful degrade).
    assert "missing.jpg" in rewritten


def test_attach_inline_images_dedupes_repeated_image(tmp_path: Path):
    """If the same local image is referenced twice (logo in masthead +
    footer), attach the file ONCE but rewrite both `<img>` tags to use
    the same CID."""
    asset_dir = _make_asset_layout(
        tmp_path, image_files=(), brand_files=("seal.png",))
    html = (
        f'<html><body>'
        f'<img src="{REPO_PREFIX}/images/seal.png">'  # masthead
        f'<p>middle</p>'
        f'<img src="{REPO_PREFIX}/images/seal.png">'  # footer
        f'</body></html>'
    )
    rewritten, inline = attach_inline_images(
        html, asset_dir, repo_url_prefix=REPO_PREFIX + "/")
    assert len(inline) == 1, (
        f"Expected exactly 1 attachment for 2 references to the same "
        f"file; got {len(inline)}: {inline!r}"
    )
    cid = inline[0].cid
    assert rewritten.count(f"cid:{cid}") == 2


def test_attach_inline_images_returns_immutable_tuple(tmp_path: Path):
    asset_dir = _make_asset_layout(tmp_path, image_files=("photo1.jpg",))
    html = (
        f'<img src="{REPO_PREFIX}/assets/issue-1/photo1.jpg">'
    )
    _, inline = attach_inline_images(
        html, asset_dir, repo_url_prefix=REPO_PREFIX + "/")
    assert isinstance(inline, tuple), (
        "Public API must return a tuple so callers can't mutate the "
        "attachment list out from under the Outlook backend."
    )


def test_attach_inline_images_preserves_alt_and_other_attrs(tmp_path: Path):
    """Rewriting `src` must not clobber `alt`, `width`, `height`, or
    inline styles. Email clients depend on these for accessibility
    and layout."""
    asset_dir = _make_asset_layout(tmp_path, image_files=("photo1.jpg",))
    html = (
        f'<img src="{REPO_PREFIX}/assets/issue-1/photo1.jpg" '
        f'alt="Lab photo" width="600" height="400" '
        f'style="display:block;border:0;">'
    )
    rewritten, _ = attach_inline_images(
        html, asset_dir, repo_url_prefix=REPO_PREFIX + "/")
    assert 'alt="Lab photo"' in rewritten
    assert 'width="600"' in rewritten
    assert 'height="400"' in rewritten
    assert "display:block" in rewritten


def test_attach_inline_images_skips_already_cid_refs(tmp_path: Path):
    asset_dir = _make_asset_layout(tmp_path)
    html = '<img src="cid:already-a-cid">'
    rewritten, inline = attach_inline_images(
        html, asset_dir, repo_url_prefix=REPO_PREFIX + "/")
    # Already-CID images are not double-attached.
    assert inline == ()
    assert "cid:already-a-cid" in rewritten


def test_attach_inline_images_handles_missing_src(tmp_path: Path):
    """An `<img>` with no `src` (uncommon but legal HTML) must not
    crash the rewriter."""
    asset_dir = _make_asset_layout(tmp_path)
    html = '<img alt="placeholder">'
    rewritten, inline = attach_inline_images(
        html, asset_dir, repo_url_prefix=REPO_PREFIX + "/")
    assert inline == ()
    assert 'alt="placeholder"' in rewritten


def test_attach_inline_images_default_prefix_matches_real_repo():
    """The module's default `repo_url_prefix` must match what the
    image_handler actually emits. If someone changes the default
    here without changing image_handler.to_raw_url, the CID rewrite
    silently stops working in production."""
    import inspect
    src = inspect.getsource(attach_inline_images)
    assert "raw.githubusercontent.com" in src


def test_inline_image_is_frozen():
    """`InlineImage` must be a frozen dataclass so callers can't
    mutate the attachment spec between rewrite and Outlook send."""
    img = InlineImage(
        path=Path("/tmp/x.jpg"), cid="meridian-01-x.jpg",
        original_url="https://example.com/x.jpg",
    )
    import dataclasses
    with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
        img.cid = "tampered"  # type: ignore[misc]
