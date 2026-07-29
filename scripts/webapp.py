"""Browser-facing build entry point -- one call, bytes in, artefacts out.

`build_newsletter.py`'s `_build_pipeline` is the CLI's pipeline: it
takes a filesystem path, prints with `click.echo`, and calls
`sys.exit`. None of that survives a translation to the browser, where
there is no argv, no console the editor will read, and no exit code.

This module is the same pipeline expressed as a pure function --
`build_from_bytes(docx_bytes, issue=N)` returns a `WebBuildResult`
dataclass and raises nothing for ordinary editorial mistakes. It is
what `web/app.js` calls through Pyodide, and it is equally usable
from a server or a notebook.

Deliberately NOT here: anything that touches a mail client, the
clipboard, the OS, or git. The one artefact this produces beyond the
HTML is a `.eml` draft (see `scripts.mail.eml`), which is the right
hand-back for a web build -- returning bare HTML would put the editor
back into copy/paste, which is the failure MERIDIAN exists to remove.

Validation semantics differ from the CLI in one deliberate way. The
CLI *deletes* `dist/issue-N.html` when validation hard-blocks, so the
editor cannot double-click a stale file and send it. In the browser
there is no file on disk to re-open, so a rejected build still returns
`preview_html` (the editor needs to SEE what is wrong) but returns
`eml=None` and `ok=False`. Nothing sendable is ever produced from a
build that failed validation -- the invariant is preserved, only the
mechanism changes.
"""

from __future__ import annotations

import base64
import logging
import shutil
import tempfile
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from scripts.config import IMAGES_DIR, TITLE, get_default_repo
from scripts.docx_parser import ImageRef, Masthead, parse
from scripts.image_handler import (
    extension_to_mime, extract_embedded, ingest_drop_folder, issue_dir,
    to_raw_url,
)
from scripts.inliner import inline
from scripts.mail.base import DraftEmail
from scripts.mail.cid import attach_inline_images
from scripts.mail.eml import build_eml
from scripts.renderer import attach_image_urls, render
from scripts.text_utils import sanitize_subject
from scripts.validator import report, validate

log = logging.getLogger(__name__)

# Image-delivery modes, mirroring the CLI's `--image-mode`.
IMAGE_MODES = ("cid", "url")


@dataclass(frozen=True)
class WebBuildResult:
    """Everything a caller needs to render a result screen.

    `ok`            -- validation passed; `eml` is populated.
    `subject`       -- sanitized subject line.
    `preview_html`  -- HTML with photos rewritten to `data:` URIs so a
                       browser preview shows the real images even
                       though nothing has been published to GitHub yet.
    `html`          -- the HTML as the CLI would have written it
                       (photos as `raw.githubusercontent.com` URLs).
    `eml`           -- RFC 5322 draft bytes, or None when `ok` is False.
    `errors`        -- hard blocks. Non-empty means `ok` is False.
    `warnings`      -- advisory only (size, subject length, placeholders).
    `report_text`   -- the same human summary the CLI prints.
    `photo_count`   -- photos that will travel inside the `.eml`.
    """

    ok: bool
    subject: str
    preview_html: str
    html: str
    eml: bytes | None
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    placeholders: tuple[str, ...] = ()
    report_text: str = ""
    size_bytes: int = 0
    section_count: int = 0
    photo_count: int = 0
    image_mode: str = "cid"


# Message shown when the DOCX yields nothing. Same wording as the CLI's
# round-17 fix -- the editor should read one voice across both paths.
_EMPTY_DOCX_ERROR = (
    "No content was extracted from your Word file. This usually means "
    "the file is empty, password-protected, or has a format the "
    "toolkit can't read. Open the .docx in Microsoft Word, confirm "
    "there's actual text or tables in the body (not just the header "
    "or footer), save, and try again."
)


def subject_from_masthead(issue: int, masthead: Masthead | None) -> str:
    """Build the email subject from a parsed masthead.

    Single source of truth shared with `build_newsletter.py` so the CLI
    and the web build can't drift into producing different subjects for
    the same issue. Runs the issue line through `sanitize_subject` so
    Word-pasted invisibles (ZWSP, NBSP, BOM, RLO) never reach the wire.

    Total by construction: a non-string `issue_line` from schema drift
    falls back to the generic subject rather than raising, because a
    TypeError here used to short-circuit the validate-before-write
    guard upstream.
    """
    try:
        issue_line = (masthead.issue_line or "") if masthead else ""
        issue_line = sanitize_subject(issue_line)
    except (AttributeError, TypeError) as e:
        log.warning(
            "Could not derive subject from masthead (%s); "
            "falling back to generic subject.", e)
        issue_line = ""
    if issue_line:
        return f"{TITLE} — {issue_line}"
    return f"{TITLE} — Issue {issue}"


def _data_uri(path: Path) -> str:
    """`data:` URI for a local image, for the in-browser preview.

    The preview cannot use the `raw.githubusercontent.com` URLs the
    renderer emits: for a brand-new issue nothing has been pushed
    there yet, so every photo would render as a broken-image icon and
    the editor would reasonably conclude the toolkit was broken.
    """
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{extension_to_mime(path)};base64,{b64}"


def _mirror_brand_assets(root: Path) -> None:
    """Copy the repo's `images/` into `root` unless it is already there.

    Best-effort: if the copy fails, the brand images simply stay as
    remote URLs (the pre-CID behaviour), which still renders for most
    recipients. Worth a warning, not worth failing the build.
    """
    dst = root / "images"
    if dst.exists() or not IMAGES_DIR.is_dir():
        return
    try:
        shutil.copytree(IMAGES_DIR, dst)
    except OSError as e:
        log.warning(
            "Could not mirror brand images into %s (%s); the logo and "
            "dean photo will be referenced by URL instead of embedded.",
            dst, e)


def _failed(subject: str, result, *, preview_html: str = "",
            html: str = "", section_count: int = 0,
            image_mode: str = "cid") -> WebBuildResult:
    """Build a rejected result -- never carries a `.eml`."""
    return WebBuildResult(
        ok=False,
        subject=subject,
        preview_html=preview_html,
        html=html,
        eml=None,
        errors=tuple(getattr(result, "errors", ()) or ()),
        warnings=tuple(getattr(result, "warnings", ()) or ()),
        placeholders=tuple(getattr(result, "placeholders", ()) or ()),
        report_text=report(result) if result is not None else "",
        size_bytes=getattr(result, "size_bytes", 0) or 0,
        section_count=section_count,
        image_mode=image_mode,
    )


def build_from_bytes(
    docx_bytes: bytes,
    *,
    issue: int,
    image_mode: str = "cid",
    bcc: str | None = None,
    to: str | None = None,
    drop_dir: Path | None = None,
    workdir: Path | None = None,
) -> WebBuildResult:
    """Run the full pipeline over an in-memory DOCX.

    `workdir` defaults to a fresh temp directory. It doubles as the
    repo root for raw-URL construction, so `assets/issue-N/photo.jpg`
    under it yields the same public URL the CLI would emit.

    `image_mode`:
      * `"cid"` (default) -- photos are embedded in the `.eml` as MIME
        parts. Nothing needs publishing to GitHub, which is the whole
        reason this is the browser default.
      * `"url"` -- photos stay as `raw.githubusercontent.com`
        references; they must be pushed before recipients open the
        mail. Offered for parity with the CLI, not recommended here.

    Raises `ValueError` only for a caller mistake (an unknown
    `image_mode`). Everything an *editor* can get wrong -- an empty
    document, an unfilled masthead -- comes back as a result with
    `ok=False` and readable `errors`.
    """
    if image_mode not in IMAGE_MODES:
        raise ValueError(
            f"image_mode must be one of {IMAGE_MODES} -- got {image_mode!r}")

    root = Path(workdir) if workdir is not None else Path(
        tempfile.mkdtemp(prefix="meridian-web-"))
    root.mkdir(parents=True, exist_ok=True)
    docx_path = root / f"issue-{issue}.docx"
    docx_path.write_bytes(docx_bytes)

    # The masthead logo and the dean photo are permanent brand assets in
    # `images/`, not content embedded in the DOCX. CID resolution looks
    # for them at `<root>/images/` (sibling of `assets/`), so mirror them
    # in -- otherwise they stay as `raw.githubusercontent.com` references
    # and CID mode silently ships a *partly* external email, which is the
    # mixed-mode rendering round 12 went out of its way to eliminate.
    _mirror_brand_assets(root)

    # 1) Parse.
    newsletter = parse(docx_path)
    if not newsletter.sections:
        return WebBuildResult(
            ok=False, subject=f"{TITLE} — Issue {issue}",
            preview_html="", html="", eml=None,
            errors=(_EMPTY_DOCX_ERROR,),
            report_text=_EMPTY_DOCX_ERROR,
            image_mode=image_mode,
        )
    log.info("Parsed %d sections", len(newsletter.sections))

    # 2) Extract photos out of the DOCX (and an optional drop folder).
    asset_dir = issue_dir(root / "assets", issue)
    embedded = extract_embedded(docx_path, asset_dir)
    drops = ingest_drop_folder(drop_dir, asset_dir) if drop_dir else []
    repo = get_default_repo()

    # 3) + 4) Public URLs for embedded photos and drop-folder inserts.
    url_map = {name: to_raw_url(p, root, repo) for name, p in embedded.items()}
    drop_inserts: dict[int, list[ImageRef]] = defaultdict(list)
    for d in drops:
        drop_inserts[d.section].append(ImageRef(
            rel_id="", filename=d.dst_path.name, alt=d.slug,
            url=to_raw_url(d.dst_path, root, repo),
        ))

    # 5) - 7) Inject URLs, render, inline.
    enriched = attach_image_urls(newsletter, url_map, drop_inserts)
    final_html = inline(render(enriched))
    subject = subject_from_masthead(issue, newsletter.masthead)

    # 8) Resolve photos to local files ONCE. The returned specs drive
    # both the `.eml` attachments and the data-URI preview, so the two
    # can never disagree about which photos made it in.
    cid_html, inline_images = attach_inline_images(final_html, asset_dir)
    preview_html = final_html
    for img in inline_images:
        try:
            preview_html = preview_html.replace(
                img.original_url, _data_uri(img.path))
        except OSError as e:
            log.warning("Preview: could not embed %s (%s); it will show "
                        "as a broken image in the preview only.",
                        img.path, e)

    # 9) Validate the URL HTML -- the same bytes the CLI validates.
    # `check_remote` is always False here: Pyodide has no synchronous
    # HTTP, and a browser build has no business making 30 blocking
    # HEAD requests to GitHub on the editor's behalf anyway.
    result = validate(final_html, check_remote=False)
    if not result.ok:
        return _failed(subject, result, preview_html=preview_html,
                       html=final_html,
                       section_count=len(newsletter.sections),
                       image_mode=image_mode)

    # 10) Build the draft. CID mode ships the rewritten HTML plus the
    # attachment specs; URL mode ships the original and no parts.
    draft = DraftEmail(
        html=cid_html if image_mode == "cid" else final_html,
        subject=subject,
        bcc=bcc, to=to,
        inline_images=inline_images if image_mode == "cid" else (),
    )
    eml_bytes = build_eml(draft).as_bytes()

    return WebBuildResult(
        ok=True,
        subject=subject,
        preview_html=preview_html,
        html=final_html,
        eml=eml_bytes,
        warnings=tuple(result.warnings or ()),
        placeholders=tuple(result.placeholders or ()),
        report_text=report(result),
        size_bytes=result.size_bytes,
        section_count=len(newsletter.sections),
        photo_count=len(inline_images) if image_mode == "cid" else 0,
        image_mode=image_mode,
    )


__all__ = [
    "IMAGE_MODES",
    "WebBuildResult",
    "build_from_bytes",
    "subject_from_masthead",
]
