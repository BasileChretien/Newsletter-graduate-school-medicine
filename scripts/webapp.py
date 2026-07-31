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
`standalone_html` (the editor needs to SEE what is wrong) but returns
`eml=None` and `ok=False`. Nothing sendable is ever produced from a
build that failed validation -- the invariant is preserved, only the
mechanism changes.
"""

from __future__ import annotations

import logging
import re
import shutil
import tempfile
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from scripts.config import TITLE, get_default_repo
from scripts.docx_parser import ImageRef, parse
from scripts.html_utils import parse_html
from scripts.image_handler import (
    DEFAULT_IMAGE_QUALITY, DEFAULT_MAX_IMAGE_PX,
    extract_embedded, ingest_drop_folder, issue_dir,
    to_raw_url,
)
from scripts.inliner import inline
from scripts.mail.base import DraftEmail
from scripts.mail.cid import (
    DEFAULT_MAX_IMAGE_BYTES, attach_inline_images, count_remote_images,
)
from scripts.mail.eml import build_eml
from scripts.recipients import sanitize_addresses
from scripts.renderer import attach_image_urls, render
from scripts.standalone import to_standalone_html
from scripts.subject import subject_from_masthead
from scripts.validator import ValidationResult, report, validate

log = logging.getLogger(__name__)

# Image-delivery modes, mirroring the CLI's `--image-mode`.
IMAGE_MODES = ("cid", "url")

# Upper bound on the issue number. Purely a sanity rail: at a quarterly
# cadence 9999 is about 2500 years of newsletters, while an unbounded
# value reaches the filesystem as a several-hundred-digit filename that
# the OS rejects with a bare `OSError`.
_MAX_ISSUE = 9999


@dataclass(frozen=True)
class WebBuildResult:
    """Everything a caller needs to render a result screen.

    `ok`            -- validation passed; `eml` is populated.
    `subject`       -- sanitized subject line.
    `standalone_html`
                    -- the newsletter as a SELF-CONTAINED document:
                       photos rewritten to `data:` URIs, nothing left to
                       fetch. This is what the browser build previews
                       *and* what it offers for download.

                       It was called `preview_html`, and that name
                       caused a reported bug: the download link was
                       wired to `html` instead, so every downloaded file
                       had missing photos. Nothing about this document
                       is preview-only.
    `html`          -- the MAIL html, with photos as
                       `raw.githubusercontent.com` URLs. Those URLs are
                       correct only after `publish-images` has pushed
                       the photos -- which the browser build NEVER does,
                       because it always uses CID. So treat this as the
                       bytes to validate and to hand the mail backend,
                       never as a file to give an editor.
    `eml`           -- RFC 5322 draft bytes, or None when `ok` is False.
    `errors`        -- hard blocks. Non-empty means `ok` is False.
    `warnings`      -- advisory only (size, subject length, placeholders).
    `report_text`   -- the same human summary the CLI prints.
    `photo_count`   -- photos that will travel inside the `.eml`.
    """

    ok: bool
    subject: str
    standalone_html: str
    html: str
    eml: bytes | None
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    placeholders: tuple[str, ...] = ()
    report_text: str = ""
    size_bytes: int = 0
    section_count: int = 0
    photo_count: int = 0
    unembedded_photo_count: int = 0
    recipient_count: int = 0
    rejected_addresses: tuple[str, ...] = ()
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


def _clean_addresses(
    value: str | None,
) -> tuple[str | None, list[str], bool]:
    """Validate a free-text recipient box. -> (joined, rejected, truncated).

    The browser hands us whatever the editor typed or pasted, split on
    newlines, commas and semicolons. Everything then goes through the
    SAME guard `recipients.txt` gets -- see
    `scripts.recipients.sanitize_addresses` for why that matters.
    """
    if not value:
        return None, [], False
    accepted, rejected, truncated = sanitize_addresses(
        re.split(r"[\n,;]+", value))
    return ("; ".join(accepted) or None), rejected, truncated


def _failed(subject: str, result: ValidationResult | None, *,
            standalone_html: str = "",
            html: str = "", section_count: int = 0,
            image_mode: str = "cid") -> WebBuildResult:
    """Build a rejected result -- never carries a `.eml`."""
    return WebBuildResult(
        ok=False,
        subject=subject,
        standalone_html=standalone_html,
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
    issue: int | str,
    image_mode: str = "cid",
    bcc: str | None = None,
    to: str | None = None,
    drop_dir: Path | None = None,
    workdir: Path | None = None,
    max_image_bytes: int = DEFAULT_MAX_IMAGE_BYTES,
    max_image_px: int | None = DEFAULT_MAX_IMAGE_PX,
    image_quality: int = DEFAULT_IMAGE_QUALITY,
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

    When `workdir` is omitted the temp directory this creates is also
    removed before returning. Everything a caller needs -- the HTML,
    the preview with its photos already inlined as data URIs, the
    `.eml` bytes -- is in the returned dataclass, so nothing on disk
    outlives the call. A caller that *wants* the extracted files passes
    an explicit `workdir` and owns its lifetime.

    Raises `ValueError` only for a caller mistake (an unknown
    `image_mode`). Everything an *editor* can get wrong -- an empty
    document, an unfilled masthead -- comes back as a result with
    `ok=False` and readable `errors`.
    """
    if image_mode not in IMAGE_MODES:
        raise ValueError(
            f"image_mode must be one of {IMAGE_MODES} -- got {image_mode!r}")
    # `issue` reaches the filesystem through `issue_dir()`. A caller
    # outside the browser (a server handler wiring a query parameter
    # straight through) could otherwise hand us `../..`; the int cast
    # makes that impossible rather than merely unlikely.
    # `bool` is an `int` subclass, and `int(3.7e300)` silently succeeds
    # into a 300-digit number that produces an unopenable filename --
    # so accept only whole numbers or their digit strings.
    if isinstance(issue, bool) or not isinstance(issue, (int, str)):
        raise ValueError(
            f"issue must be a whole number -- got {type(issue).__name__}")
    try:
        issue = int(issue)
    except (TypeError, ValueError) as e:
        raise ValueError(
            f"issue must be a whole number -- got {issue!r}") from e
    if issue < 0:
        raise ValueError(f"issue must not be negative -- got {issue}")
    if issue > _MAX_ISSUE:
        raise ValueError(
            f"issue must be at most {_MAX_ISSUE} -- got {issue}")

    if workdir is not None:
        return _build_in(
            Path(workdir), docx_bytes, issue=issue, image_mode=image_mode,
            bcc=bcc, to=to, drop_dir=drop_dir,
            max_image_bytes=max_image_bytes,
            max_image_px=max_image_px, image_quality=image_quality)

    scratch = Path(tempfile.mkdtemp(prefix="meridian-web-"))
    try:
        return _build_in(
            scratch, docx_bytes, issue=issue, image_mode=image_mode,
            bcc=bcc, to=to, drop_dir=drop_dir,
            max_image_bytes=max_image_bytes,
            max_image_px=max_image_px, image_quality=image_quality)
    finally:
        # `ignore_errors`: a failed cleanup of a temp directory must not
        # turn a successful build into an exception.
        shutil.rmtree(scratch, ignore_errors=True)


def _build_in(
    root: Path,
    docx_bytes: bytes,
    *,
    issue: int,
    image_mode: str,
    bcc: str | None,
    to: str | None,
    drop_dir: Path | None,
    max_image_bytes: int,
    max_image_px: int | None,
    image_quality: int,
) -> WebBuildResult:
    """The pipeline itself, rooted at an already-chosen directory.

    Split out so `build_from_bytes` can own the lifetime of a temp
    workdir it created without wrapping a hundred lines in a `try`.
    Arguments are pre-validated by the caller.
    """
    root.mkdir(parents=True, exist_ok=True)
    docx_path = root / f"issue-{issue}.docx"
    docx_path.write_bytes(docx_bytes)

    # No brand-asset mirroring needed: `scripts.mail.cid` resolves
    # `images/<file>` against `scripts.config.IMAGES_DIR` directly, so
    # the logo and dean photo embed without each build copying them into
    # its own workdir.

    # 1) Parse. A file named `.docx` that is not a valid OPC package --
    # a renamed `.doc`, a truncated download, an unsynced OneDrive
    # placeholder, a password-protected file -- raises out of
    # `python-docx`. Left unhandled it reached the browser as "this is a
    # bug in the toolkit, not in your Word file", which is exactly
    # backwards: it IS their file, and it is fixable in thirty seconds.
    try:
        newsletter = parse(docx_path)
    except Exception as e:  # noqa: BLE001 -- any parse failure is editorial
        log.warning("Could not parse %s: %s", docx_path.name, e)
        return WebBuildResult(
            ok=False, subject=f"{TITLE} — Issue {issue}",
            standalone_html="", html="", eml=None,
            errors=(_EMPTY_DOCX_ERROR,),
            report_text=_EMPTY_DOCX_ERROR,
            image_mode=image_mode,
        )
    if not newsletter.sections:
        return WebBuildResult(
            ok=False, subject=f"{TITLE} — Issue {issue}",
            standalone_html="", html="", eml=None,
            errors=(_EMPTY_DOCX_ERROR,),
            report_text=_EMPTY_DOCX_ERROR,
            image_mode=image_mode,
        )
    log.info("Parsed %d sections", len(newsletter.sections))

    # 2) Extract photos out of the DOCX (and an optional drop folder).
    asset_dir = issue_dir(root / "assets", issue)
    embedded = extract_embedded(docx_path, asset_dir,
                                max_image_px=max_image_px,
                                image_quality=image_quality)
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
    cid_html, inline_images = attach_inline_images(
        final_html, asset_dir, max_image_bytes=max_image_bytes)
    # Shared with the CLI (`scripts/standalone.py`) so the file an editor
    # downloads from the page and the one the desktop build writes are
    # the same document, produced by the same code.
    standalone_html = to_standalone_html(final_html, inline_images)

    # 9) Validate the URL HTML -- the same bytes the CLI validates.
    # `check_remote` is always False here: Pyodide has no synchronous
    # HTTP, and a browser build has no business making 30 blocking
    # HEAD requests to GitHub on the editor's behalf anyway.
    media_bytes = sum(p.stat().st_size for p in asset_dir.glob('*')
                      if p.is_file() and p.suffix.lower() != '.json')
    result = validate(final_html, check_remote=False,
                      attachment_bytes=media_bytes)
    if not result.ok:
        return _failed(subject, result, standalone_html=standalone_html,
                       html=final_html,
                       section_count=len(newsletter.sections),
                       image_mode=image_mode)

    # 10) Validate the recipient boxes with the same guard the CLI
    # applies to `recipients.txt`, then build the draft. CID mode ships
    # the rewritten HTML plus the attachment specs; URL mode ships the
    # original and no parts.
    clean_bcc, rejected_bcc, bcc_truncated = _clean_addresses(bcc)
    clean_to, rejected_to, to_truncated = _clean_addresses(to)
    rejected = tuple(rejected_bcc + rejected_to)

    draft = DraftEmail(
        html=cid_html if image_mode == "cid" else final_html,
        subject=subject,
        bcc=clean_bcc, to=clean_to,
        inline_images=inline_images if image_mode == "cid" else (),
    )
    eml_bytes = build_eml(draft).as_bytes()

    # 11) Warnings the validator cannot produce, because they are about
    # the DRAFT rather than the HTML.
    warnings = list(result.warnings or ())
    unembedded = count_remote_images(cid_html) if image_mode == "cid" else 0
    if unembedded:
        warnings.append(
            f"{unembedded} photo(s) could not be placed inside the "
            "email, so they are linked from the web instead -- and "
            "recipients will see a broken image where they should be. "
            "The usual causes are a photo larger than 2 MB, or a photo "
            "the toolkit could not find. Fix: in Word, right-click any "
            "large photo, choose 'Compress Pictures', check every photo "
            "still displays, save, and build again."
        )
    if bcc_truncated or to_truncated:
        # The CLI at least logs this. Dropping it silently in the browser
        # would mean an editor who pastes an over-long list sees a
        # recipient count that quietly disagrees with what they pasted.
        warnings.append(
            f"Only the first {len(clean_bcc.split('; ')) if clean_bcc else 0} "
            "addresses were kept -- the list you pasted is longer than "
            "this toolkit accepts. Send in smaller batches, and note the "
            "university mail server caps a single send at about 50 "
            "recipients anyway."
        )
    if rejected:
        shown = ", ".join(rejected[:5])
        more = f" (+{len(rejected) - 5} more)" if len(rejected) > 5 else ""
        warnings.append(
            f"{len(rejected)} recipient address(es) did not look like "
            f"valid email addresses and were left out: {shown}{more}. "
            "Check them and build again if they should be included."
        )

    recipient_count = len(clean_bcc.split("; ")) if clean_bcc else 0

    return WebBuildResult(
        ok=True,
        subject=subject,
        standalone_html=standalone_html,
        html=final_html,
        eml=eml_bytes,
        warnings=tuple(warnings),
        placeholders=tuple(result.placeholders or ()),
        report_text=report(result),
        size_bytes=result.size_bytes,
        section_count=len(newsletter.sections),
        photo_count=len(inline_images) if image_mode == "cid" else 0,
        unembedded_photo_count=unembedded,
        recipient_count=recipient_count,
        rejected_addresses=rejected,
        image_mode=image_mode,
    )


__all__ = [
    "IMAGE_MODES",
    "WebBuildResult",
    "build_from_bytes",
    "subject_from_masthead",
]
