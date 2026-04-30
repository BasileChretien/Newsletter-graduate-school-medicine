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
    """Pin the EXACT output for a deterministic input. Round-12
    python-reviewer HIGH 4: the previous test used `or out.startswith(...)`,
    which would have passed for `meridian-01-my-photo-GARBAGE` too --
    a tautology. Now the assertion proves the regex behaves correctly."""
    out = _make_cid("My Photo (final).jpg", 1)
    # `My Photo (final).jpg` -> lower -> `my photo (final).jpg`
    # -> `_CID_SAFE_RE.sub("-", ...)` collapses runs of unsafe chars
    #    (` `, `(`) to single `-`: `my-photo-final-.jpg`
    # -> `.strip("-")` doesn't touch internal `-` or the trailing `.jpg`
    # -> issue_part empty (no issue_tag), index `01`
    # -> domain suffix `@meridian.local`
    expected = "meridian-01-my-photo-final-.jpg@meridian.local"
    assert out == expected, f"Expected {expected!r}, got {out!r}"


def test_make_cid_includes_domain_suffix():
    """Round-12 deliverability M2: every CID must look like an
    RFC 2822 `msg-id` (`local-part@domain`) so older Outlook builds
    that don't auto-wrap in `<...>` still produce a valid Content-ID
    header."""
    out = _make_cid("photo.jpg", 1)
    assert "@" in out, f"CID missing domain suffix: {out!r}"
    assert out.endswith("@meridian.local"), out


def test_make_cid_sanitizes_issue_tag_with_spaces_and_special_chars():
    """Round-12 architect LOW N3: an issue_tag like `My Issue 5!` (or
    a maliciously-named asset directory) should be sanitized through
    `_CID_SAFE_RE` before going into the CID. No spaces, no
    punctuation, no header-injection characters."""
    out = _make_cid("photo.jpg", 1, issue_tag="My Issue 5!")
    # The issue tag becomes `my-issue-5-` after lowercase + safe-re sub
    # + strip; the trailing dash is stripped, so we end up with
    # `my-issue-5`. The dash before the index uses our zero-pad pattern.
    assert "my-issue-5" in out
    assert " " not in out
    assert "!" not in out
    assert "<" not in out


def test_make_cid_unicode_issue_tag_falls_back_gracefully():
    """An all-non-ASCII issue tag (e.g. accidentally `第3号`) should
    not produce a malformed CID. After `_CID_SAFE_RE.sub` the result
    is empty, which `_make_cid` handles by skipping the issue prefix
    altogether (rather than crashing or producing `meridian--01-...`)."""
    out = _make_cid("photo.jpg", 1, issue_tag="第3号")
    # Should NOT contain a double-dash artifact from an empty issue_part.
    assert "--" not in out
    # Should still end in the standard suffix.
    assert out.endswith("@meridian.local")


def test_make_cid_uses_issue_tag_for_cross_issue_disambig():
    """Round-12 architect HIGH 1: the same basename across two
    different issues must produce DIFFERENT CIDs so a forwarded
    thread that contains both issues doesn't dedupe the second
    image into the first via Content-ID collision."""
    a = _make_cid("photo1.jpg", 1, issue_tag="issue-5")
    b = _make_cid("photo1.jpg", 1, issue_tag="issue-6")
    assert a != b, (
        f"CIDs identical across issues: {a!r}; cross-issue forwarded "
        "threads would dedupe one image."
    )
    assert "issue-5" in a
    assert "issue-6" in b


def test_make_cid_zero_pads_index():
    """Stable 2-digit index keeps CIDs sortable when there are <100 images."""
    assert _make_cid("a.jpg", 1).startswith("meridian-01-")
    assert _make_cid("a.jpg", 12).startswith("meridian-12-")


def test_make_cid_handles_unicode_only_basename():
    """A basename whose ASCII-safe portion is JUST the extension
    (`.jpg`) -- the Cambridge case where the regex preserves only
    the dot+ext."""
    out = _make_cid("写真.jpg", 3)
    # `写真.jpg` -> `写真.jpg` (lower is no-op for kanji) -> regex
    # replaces the `写真` run with `-`, leaving `-.jpg`. After
    # `.strip("-")` we get `.jpg`. So safe = `.jpg`, NOT empty.
    assert out == "meridian-03-.jpg@meridian.local", out


def test_make_cid_falls_back_to_image_n_for_empty_safe_basename():
    """Round-12 python-reviewer MEDIUM 3: the test for the
    `image-N` fallback path needs a basename whose safe portion
    really IS empty after the regex + strip. A truly extension-less
    all-non-ASCII basename hits this."""
    out = _make_cid("写真", 5)
    # `写真` -> regex collapses to `-` -> strip yields `` -> fallback
    # to `image-5`.
    assert "image-5" in out, out
    assert out.startswith("meridian-")


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


# ---------- Round-12 security HIGH: path-traversal hardening -------------

def test_resolve_local_path_rejects_dotdot_in_assets_branch(tmp_path: Path):
    """Round-12 security H1: a crafted DOCX with
    `<img src="https://raw.githubusercontent.com/.../assets/issue-1/../../../etc/passwd">`
    must NOT resolve to a path outside `asset_dir.parent`. Without
    the `_confined` guard, `Path.joinpath` resolves `..` lexically
    and `is_file()` happily returns True for genuinely-existing
    files. CID mode would then attach `/etc/passwd` to the email."""
    asset_dir = _make_asset_layout(tmp_path, image_files=("photo1.jpg",))
    # The decoy URL points outside the project tree via `..` segments.
    # The exact target doesn't matter -- we just want it to NOT resolve.
    url = f"{REPO_PREFIX}/assets/issue-1/../../../../etc/passwd"
    assert _resolve_local_path(url, asset_dir, REPO_PREFIX + "/") is None


def test_resolve_local_path_rejects_dotdot_in_images_branch(tmp_path: Path):
    """Round-12 security H2: same defence on the `images/` branch,
    which has root `asset_dir.parent.parent / images` -- one level
    higher in the tree, even more dangerous if traversal succeeds."""
    asset_dir = _make_asset_layout(
        tmp_path, image_files=(), brand_files=("seal.png",))
    url = f"{REPO_PREFIX}/images/../../../etc/passwd"
    assert _resolve_local_path(url, asset_dir, REPO_PREFIX + "/") is None


def test_resolve_local_path_handles_url_with_query_string(tmp_path: Path):
    """Round-12 python-reviewer HIGH 3: URLs sometimes carry
    query strings (cache-busters, session tokens). `urlparse`
    isolates the path, so the `?token=abc` suffix shouldn't break
    resolution."""
    asset_dir = _make_asset_layout(tmp_path, image_files=("photo1.jpg",))
    url = f"{REPO_PREFIX}/assets/issue-1/photo1.jpg?token=abc123"
    resolved = _resolve_local_path(url, asset_dir, REPO_PREFIX + "/")
    assert resolved is not None
    assert resolved.name == "photo1.jpg"


def test_resolve_local_path_handles_url_with_fragment(tmp_path: Path):
    asset_dir = _make_asset_layout(tmp_path, image_files=("photo1.jpg",))
    url = f"{REPO_PREFIX}/assets/issue-1/photo1.jpg#section"
    resolved = _resolve_local_path(url, asset_dir, REPO_PREFIX + "/")
    assert resolved is not None
    assert resolved.name == "photo1.jpg"


def test_resolve_local_path_rejects_percent_encoded_dotdot(tmp_path: Path):
    """Round-12 security M1: `%2E%2E` is currently safe by accident
    (urlparse leaves it encoded, joinpath treats it as a literal
    directory name, is_file() returns False). Pin this so a future
    refactor that calls unquote() doesn't silently reopen the hole."""
    asset_dir = _make_asset_layout(tmp_path, image_files=("photo1.jpg",))
    url = f"{REPO_PREFIX}/assets/issue-1/%2E%2E/%2E%2E/etc/passwd"
    assert _resolve_local_path(url, asset_dir, REPO_PREFIX + "/") is None


def test_resolve_local_path_rejects_null_byte_in_segment(tmp_path: Path):
    """Null bytes in URL paths are a classic filesystem-API trick.
    Some Path implementations on some platforms truncate at `\\x00`."""
    asset_dir = _make_asset_layout(tmp_path, image_files=("photo1.jpg",))
    url = f"{REPO_PREFIX}/assets/issue-1/photo1.jpg\x00.png"
    assert _resolve_local_path(url, asset_dir, REPO_PREFIX + "/") is None


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


def test_attach_inline_images_skips_files_over_size_cap(tmp_path: Path):
    """Round-12 deliverability HIGH 2 / MEDIUM 1: a 4 MB hospital
    photo would bloat every forwarded copy of the message. Files
    over the cap stay as URLs (graceful per-image degrade)."""
    asset_dir = _make_asset_layout(tmp_path)
    big_path = asset_dir / "big.jpg"
    big_path.write_bytes(b"\xff\xd8\xff" + b"X" * 600_000)
    small_path = asset_dir / "small.jpg"
    small_path.write_bytes(b"\xff\xd8\xff" + b"X" * 1_000)
    html = (
        f'<html><body>'
        f'<img src="{REPO_PREFIX}/assets/issue-1/big.jpg">'
        f'<img src="{REPO_PREFIX}/assets/issue-1/small.jpg">'
        f'</body></html>'
    )
    rewritten, inline = attach_inline_images(
        html, asset_dir, repo_url_prefix=REPO_PREFIX + "/",
        max_image_bytes=500_000,
    )
    # Only the small image was attached.
    assert len(inline) == 1
    assert inline[0].path == small_path
    # The big image's URL survives as-is (no CID rewrite).
    assert "big.jpg" in rewritten
    assert f"{REPO_PREFIX}/assets/issue-1/big.jpg" in rewritten


def test_attach_inline_images_default_size_cap_is_2mb():
    """Round-12 architect N1: pin the production default size cap.
    A future PR that lowers this number would silently start
    sending mixed-mode emails (some inline, some external) for
    typical institutional photos. Pin the constant."""
    from scripts.mail.cid import DEFAULT_MAX_IMAGE_BYTES
    assert DEFAULT_MAX_IMAGE_BYTES == 2_000_000, (
        f"DEFAULT_MAX_IMAGE_BYTES is {DEFAULT_MAX_IMAGE_BYTES}; expected "
        "2_000_000 (2 MB). Lowering this would silently degrade typical "
        "institutional photos (200-800 KB) to URL mode for SOME images "
        "while attaching others -- inconsistent rendering for recipients "
        "on filtered networks."
    )


def test_attach_inline_images_typical_institutional_photo_attaches_inline(
    tmp_path: Path
):
    """At the production default, a 600 KB photo (typical of a
    Word-pasted institutional image) MUST attach inline. Round-12
    architect N1 found that the bundle-12 default of 500 KB was
    pushing this into URL mode."""
    from scripts.mail.cid import DEFAULT_MAX_IMAGE_BYTES
    asset_dir = _make_asset_layout(tmp_path)
    photo_path = asset_dir / "lab.jpg"
    photo_path.write_bytes(b"\xff\xd8\xff" + b"X" * 600_000)  # 600 KB
    html = f'<img src="{REPO_PREFIX}/assets/issue-1/lab.jpg">'
    _, inline = attach_inline_images(
        html, asset_dir, repo_url_prefix=REPO_PREFIX + "/",
    )  # default cap
    assert len(inline) == 1, (
        f"600 KB photo should attach at default cap "
        f"({DEFAULT_MAX_IMAGE_BYTES} bytes); got {len(inline)} attachments."
    )


def test_attach_inline_images_uses_asset_dir_name_as_issue_tag(tmp_path: Path):
    """Round-12 architect HIGH 1: the same `photo1.jpg` in two
    different issues must produce different CIDs. `asset_dir.name`
    is the issue-tag carrier."""
    # issue-5 layout
    issue5 = tmp_path / "assets" / "issue-5"
    issue5.mkdir(parents=True)
    (issue5 / "photo.jpg").write_bytes(b"\xff\xd8\xff5")
    # issue-6 layout
    issue6 = tmp_path / "assets" / "issue-6"
    issue6.mkdir(parents=True)
    (issue6 / "photo.jpg").write_bytes(b"\xff\xd8\xff6")
    html5 = f'<img src="{REPO_PREFIX}/assets/issue-5/photo.jpg">'
    html6 = f'<img src="{REPO_PREFIX}/assets/issue-6/photo.jpg">'
    _, inline5 = attach_inline_images(
        html5, issue5, repo_url_prefix=REPO_PREFIX + "/")
    _, inline6 = attach_inline_images(
        html6, issue6, repo_url_prefix=REPO_PREFIX + "/")
    assert inline5[0].cid != inline6[0].cid, (
        "CIDs collide across issues -- forwarded thread would dedupe."
    )
    assert "issue-5" in inline5[0].cid
    assert "issue-6" in inline6[0].cid


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


# -- Round-15 architect LOW 4: documented bypass-vector tests ----------

def test_resolve_local_path_rejects_windows_drive_letter(tmp_path: Path):
    """A crafted URL that smuggles a Windows drive letter into the
    /assets/ segment must NOT resolve to a file outside the project.
    On Windows, `joinpath('C:', 'Windows', ...)` produces a drive-anchored
    absolute path; `Path.resolve()` then escapes the project root,
    and `is_relative_to()` rejects.

    On POSIX `C:` is just an opaque directory name; the test below
    pins POSIX behaviour explicitly with a positive-control
    counterpart (`test_..._positive_control_posix`) that creates a
    real `C:`-named directory under tmp_path -- proving the guard
    (not just `is_file()`-returns-False) is what rejects the path."""
    asset_dir = _make_asset_layout(tmp_path)
    # Smuggle a drive-letter segment in place of `issue-1`.
    url = f"{REPO_PREFIX}/assets/C:/Windows/win.ini"
    resolved = _resolve_local_path(url, asset_dir, REPO_PREFIX)
    assert resolved is None, (
        f"Windows drive letter in URL must not resolve outside the "
        f"project root; got {resolved!r}"
    )


def test_resolve_local_path_drive_letter_posix_documents_behaviour(
    tmp_path: Path,
):
    """Round-16 architect MEDIUM follow-up: the original
    `test_resolve_local_path_rejects_windows_drive_letter` test
    passes on POSIX because the resolver maps
    `{prefix}/assets/C:/Windows/win.ini` to
    `asset_dir.parent / "C:" / "Windows" / "win.ini"` -- which
    doesn't exist by default, so `is_file()` returns False and
    `_confined` returns None. The architect audit asked: "does the
    test pass for the *right* reason?"

    Answer (this test): on POSIX, `C:` is just an opaque directory
    name. If a real file happens to exist at the URL's resolved
    POSIX path (because, say, a malicious DOCX co-author created
    such a directory and dropped a JPEG in it), the resolver WILL
    accept it -- because the file is genuinely inside `asset_dir.parent`,
    so the path-traversal guard has no reason to reject. This is
    correct behaviour for POSIX (drive-letter smuggling is a Windows
    concept; on POSIX it just creates oddly-named directories).
    The test pins this so a future "over-eager" tightening (e.g.
    blanket-rejecting `:` in URL segments) would be visible.

    Skipped on Windows: the OS forbids `:` in directory names so
    `mkdir` raises before we can set up the fixture. Windows is
    covered by the original
    `test_resolve_local_path_rejects_windows_drive_letter` test --
    on Windows, `joinpath('C:', ...)` makes an absolute path that
    escapes `asset_dir.parent` and `is_relative_to` rejects it."""
    import sys

    if sys.platform == "win32":
        pytest.skip("`:` in directory names is forbidden on Windows")

    asset_dir = _make_asset_layout(tmp_path)
    # The URL resolves to asset_dir.parent / "C:" / ... not asset_dir /
    # ... -- the resolver treats `assets/<rel>` as `asset_dir.parent /
    # <rel>`. Create the smuggled file at the SAME path the resolver
    # will compute, so we exercise the "file exists, is_file=True"
    # branch.
    smuggled = asset_dir.parent / "C:" / "Windows"
    smuggled.mkdir(parents=True, exist_ok=True)
    real_file = smuggled / "win.ini"
    real_file.write_bytes(b"\xff\xd8\xff\xe0fake")

    url = f"{REPO_PREFIX}/assets/C:/Windows/win.ini"
    resolved = _resolve_local_path(url, asset_dir, REPO_PREFIX)

    # Documents POSIX behaviour: the file IS resolvable because it's
    # genuinely inside asset_dir.parent. This is not a security bug
    # -- on POSIX a drive-letter-named directory is just a directory
    # the editor put there, and the path stays inside the project.
    # If this assertion fails (resolved is None), the resolver has
    # become over-eager -- it would also reject legitimate files in
    # oddly-named subdirectories.
    assert resolved is not None, (
        f"On POSIX, a real file at {real_file} (genuinely inside "
        f"asset_dir.parent) should resolve. resolved={resolved!r}. "
        "Over-eager rejection would block legitimate files in "
        "subdirectories with `:` in their names."
    )
    assert resolved == real_file.resolve()


def test_resolve_local_path_rejects_symlink_escape(tmp_path: Path):
    """If `assets/issue-1/photo1.jpg` is a symlink pointing to a file
    OUTSIDE the project tree, `_resolve_local_path` must reject it.
    `Path.resolve(strict=False)` follows symlinks and `is_relative_to()`
    then catches the escape.

    Skipped on Windows, where creating a symlink requires admin
    privileges or developer-mode -- `os.symlink` raises OSError
    otherwise, and we don't want flaky CI."""
    import os
    import sys

    asset_dir = _make_asset_layout(tmp_path)
    outside = tmp_path / "outside" / "secret.jpg"
    outside.parent.mkdir(parents=True, exist_ok=True)
    outside.write_bytes(b"\xff\xd8\xff\xe0secret")

    link = asset_dir / "evil.jpg"
    try:
        os.symlink(outside, link)
    except (OSError, NotImplementedError) as e:
        pytest.skip(f"symlinks unavailable on this platform: {e}")

    if sys.platform == "win32" and not link.is_symlink():
        pytest.skip("symlink creation silently succeeded but produced "
                    "a regular file -- developer mode disabled")

    url = f"{REPO_PREFIX}/assets/issue-1/evil.jpg"
    resolved = _resolve_local_path(url, asset_dir, REPO_PREFIX)
    assert resolved is None, (
        f"symlink pointing outside the project root must be rejected; "
        f"got {resolved!r}"
    )
