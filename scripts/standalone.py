"""The newsletter as a self-contained document, photos included.

Why this exists
---------------
The renderer emits `<img src="https://raw.githubusercontent.com/...">`.
Those URLs are correct only once `publish-images` has pushed the photos
-- and in CID mode nothing ever does, because the photos travel inside
the message as MIME attachments instead. So the HTML on disk points at
files that were never uploaded, and every photo in it 404s.

That bit the browser build first: the download had dead URLs while the
preview looked perfect, reported from the field as "the images are gone
when downloading the html". The desktop `preview` command has the same
shape -- it opens `dist/issue-N.html`, which in CID mode is exactly that
document.

Two things this module is deliberately NOT for
----------------------------------------------
1. **The email body.** `data:` URIs are stripped by Outlook and Gmail,
   so a message built from this would lose every photo. The mail path
   needs the URL form, which `attach_inline_images` rewrites to `cid:`.
   `compose` reads `dist/issue-N.html` for exactly that reason, which is
   why that file must keep its URLs and this one is written separately.
2. **Rescuing photos the mail build dropped.** Oversized photos are left
   as URLs here just as they are in the message, so a preview shows the
   same gap a recipient would. Making the preview prettier than the
   email is the one change that would actively mislead an editor.
"""

from __future__ import annotations

import base64
import logging
from collections.abc import Iterable
from pathlib import Path

from scripts.image_handler import extension_to_mime
from scripts.mail.cid import InlineImage

log = logging.getLogger(__name__)


def data_uri(path: Path) -> str:
    """`data:` URI for a local image file."""
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{extension_to_mime(path)};base64,{b64}"


def to_standalone_html(html: str, inline_images: Iterable[InlineImage]) -> str:
    """Rewrite `html`'s photo URLs to `data:` URIs.

    Takes the `InlineImage` specs rather than recomputing them, so the
    document shows exactly the photos the message carries -- the two can
    never disagree about which ones made it in.

    A photo that cannot be read is left as its original URL and logged.
    That degrades to one broken image rather than losing the document.
    """
    out = html
    for img in inline_images:
        try:
            out = out.replace(img.original_url, data_uri(img.path))
        except OSError as e:
            log.warning(
                "Could not embed %s (%s); it will show as a broken image "
                "in the standalone HTML only -- the email is unaffected.",
                img.path, e)
    return out
