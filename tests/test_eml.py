"""Tests for `scripts.mail.eml` -- the `.eml` draft-file backend.

Pure stdlib on both sides (the module builds a message, the test
parses it back with `email.message_from_bytes`), so this runs
identically on Windows / macOS / Linux CI.

The load-bearing property, asserted several ways below, is that
**every `cid:` reference in the HTML resolves to a real MIME part**.
A `.eml` that looks structurally fine but whose CIDs don't match is
exactly the failure the CID work exists to prevent: recipients see
broken-image icons and nobody notices until after the send.
"""

from __future__ import annotations

import email
import re
from email.message import EmailMessage
from pathlib import Path

import pytest

from scripts.mail.base import DraftEmail, MailHandler
from scripts.mail.cid import InlineImage, attach_inline_images
from scripts.mail.eml import (
    EmlBackend, build_eml, eml_path_for, write_eml,
)

# Minimal-but-real magic bytes so `extension_to_mime` and any
# future magic-byte check agree with the file extension.
JPEG_BYTES = b"\xff\xd8\xff" + b"JPEGPAYLOAD" * 4
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"PNGPAYLOAD" * 4

REPO_PREFIX = "https://raw.githubusercontent.com/owner/repo/main"


# ---------- helpers -----------------------------------------------------

def _asset_dir(tmp_path: Path, *, issue: int = 1,
               files: dict[str, bytes] | None = None) -> Path:
    """Build `assets/issue-N/` with the given files. Returns that dir."""
    d = tmp_path / "assets" / f"issue-{issue}"
    d.mkdir(parents=True)
    for name, data in (files or {"photo1.jpg": JPEG_BYTES}).items():
        (d / name).write_bytes(data)
    return d


def _draft(html: str, *, tmp_path: Path | None = None,
           **kw) -> DraftEmail:
    """A DraftEmail with sane defaults; `kw` overrides any field."""
    fields: dict = {
        "html": html,
        "subject": "MERIDIAN — VOL. II | ISSUE NO. 3 | MARCH 2026",
        "handler": MailHandler(kind="apple_mail", name="Mail"),
    }
    if tmp_path is not None:
        fields["preview_path"] = tmp_path / "dist" / "issue-1.html"
    fields.update(kw)
    return DraftEmail(**fields)


def _cids_referenced(html: str) -> set[str]:
    """Every `cid:` value referenced by an `<img src=>` in `html`."""
    return set(re.findall(r'src="cid:([^"]+)"', html))


def _content_ids(msg: EmailMessage) -> set[str]:
    """Every `Content-ID` in the message, angle brackets stripped."""
    out = set()
    for part in msg.walk():
        cid = part.get("Content-ID")
        if cid:
            out.add(cid.strip().lstrip("<").rstrip(">"))
    return out


def _part_by_type(msg: EmailMessage, ctype: str) -> EmailMessage | None:
    for part in msg.walk():
        if part.get_content_type() == ctype:
            return part
    return None


# ---------- MIME structure ---------------------------------------------

def test_build_eml_is_multipart_alternative_with_text_and_html():
    """Spam filters (Mimecast / Proofpoint / Defender) score HTML-only
    mail higher. The `.eml` must ship the same multipart/alternative
    the Outlook backend produces, not HTML alone."""
    msg = build_eml(_draft("<html><body><h1>Hello</h1><p>Body</p></body></html>"))

    assert msg.get_content_type() == "multipart/alternative"
    text = _part_by_type(msg, "text/plain")
    html = _part_by_type(msg, "text/html")
    assert text is not None, "no text/plain alternative"
    assert html is not None, "no text/html part"
    # HTML must come AFTER plaintext: clients render the LAST part
    # they understand, so the order decides what recipients see.
    types = [p.get_content_type() for p in msg.get_payload()]
    assert types.index("text/plain") < len(types) - 1
    assert types[-1] in ("text/html", "multipart/related")


def test_plaintext_part_preserves_structure():
    """The text part goes through `html_to_plaintext`, so headings keep
    their `=== MARKER ===` shape rather than collapsing to a wall of
    text (which SpamAssassin's LONG_LINE and Mimecast's structural
    checks both penalise)."""
    msg = build_eml(_draft(
        "<html><body><h1>Dean's message</h1>"
        "<p>Welcome to the issue.</p>"
        "<ul><li>First item</li></ul></body></html>"
    ))
    body = _part_by_type(msg, "text/plain").get_content()

    assert "=== DEAN'S MESSAGE ===" in body
    assert "Welcome to the issue." in body
    assert "• First item" in body
    assert "<p>" not in body


def test_x_unsent_header_marks_the_file_as_a_draft():
    """Without `X-Unsent: 1` Outlook opens the .eml read-only in the
    reading pane -- no Send button -- which defeats the entire point."""
    msg = build_eml(_draft("<html><body>x</body></html>"))
    assert msg["X-Unsent"] == "1"


def test_headers_are_populated_and_empty_ones_omitted():
    msg = build_eml(_draft(
        "<html><body>x</body></html>",
        to="dean@example.ac.jp",
        cc="office@example.ac.jp",
        bcc="a@example.ac.jp; b@example.ac.jp",
        reply_to="newsletter@example.ac.jp",
        from_addr="dept@example.ac.jp",
    ))
    assert msg["To"] == "dean@example.ac.jp"
    assert msg["Cc"] == "office@example.ac.jp"
    assert "b@example.ac.jp" in msg["Bcc"]
    assert msg["Reply-To"] == "newsletter@example.ac.jp"
    assert msg["From"] == "dept@example.ac.jp"

    # A draft with no recipients set must not carry empty headers --
    # some clients refuse to open such a file in compose mode.
    bare = build_eml(_draft("<html><body>x</body></html>"))
    for header in ("To", "Cc", "Bcc", "From", "Reply-To"):
        assert bare[header] is None, f"{header} should be absent, not empty"


def test_semicolon_joined_recipients_are_converted_to_rfc5322_commas():
    """The toolkit joins recipients with `"; "` for Outlook COM. Under
    RFC 5322 a semicolon terminates a *group*, so passing that form
    straight through keeps only the first address. Pin the conversion."""
    msg = build_eml(_draft(
        "<html><body>x</body></html>",
        bcc="a@example.ac.jp; b@example.ac.jp; c@example.ac.jp",
    ))
    parsed = email.message_from_bytes(msg.as_bytes())

    assert parsed["Bcc"] == "a@example.ac.jp, b@example.ac.jp, c@example.ac.jp"


def test_display_name_recipients_are_left_untouched():
    """Guard for callers outside `recipients.txt`: a value carrying
    display-name syntax must not be split through its quoted commas."""
    from scripts.mail.eml import _rfc5322_address_list

    value = '"Katsuno, Masahisa" <dean@example.ac.jp>'
    assert _rfc5322_address_list(value) == value


def test_bcc_survives_a_full_fifty_recipient_list():
    """The production send is ~50 BCC recipients; a header that long
    gets folded across lines by the serializer. Assert it round-trips
    through parse intact -- a silently truncated BCC would mean half
    the school never receives the newsletter."""
    addrs = [f"person{i:02d}@example.ac.jp" for i in range(50)]
    msg = build_eml(_draft("<html><body>x</body></html>",
                           bcc="; ".join(addrs)))
    parsed = email.message_from_bytes(msg.as_bytes())

    got = parsed["Bcc"]
    for a in addrs:
        assert a in got, f"{a} missing from BCC after serialization"


def test_japanese_subject_round_trips():
    """Bilingual JA/EN newsletter: the subject regularly contains
    Japanese. It must be RFC 2047 encoded on the wire and decode back
    to the exact original."""
    subject = "MERIDIAN — 第2巻 第3号 | 2026年3月"
    msg = build_eml(_draft("<html><body>x</body></html>", subject=subject))
    raw = msg.as_bytes()

    parsed = email.message_from_bytes(raw, policy=email.policy.default)
    assert str(parsed["Subject"]) == subject
    # And the raw bytes must be 7-bit-safe headers (encoded-word), not
    # raw UTF-8 smuggled into a header.
    header_block = raw.split(b"\r\n\r\n", 1)[0]
    assert b"\xe7" not in header_block, "raw UTF-8 leaked into headers"


# ---------- CID inline images ------------------------------------------

def test_inline_images_become_related_parts_with_matching_content_ids(tmp_path):
    """The end-to-end property: run the real CID rewriter over HTML,
    feed the result to `build_eml`, and assert every `cid:` the HTML
    references exists as a `Content-ID` in the message."""
    asset_dir = _asset_dir(tmp_path, files={"photo1.jpg": JPEG_BYTES,
                                            "photo2.png": PNG_BYTES})
    html = (
        f'<html><body>'
        f'<img src="{REPO_PREFIX}/assets/issue-1/photo1.jpg">'
        f'<img src="{REPO_PREFIX}/assets/issue-1/photo2.png">'
        f'</body></html>'
    )
    rewritten, inline = attach_inline_images(
        html, asset_dir, repo_url_prefix=REPO_PREFIX)
    assert len(inline) == 2, "precondition: rewriter found both images"

    msg = build_eml(_draft(rewritten, inline_images=inline))
    parsed = email.message_from_bytes(msg.as_bytes())

    referenced = _cids_referenced(rewritten)
    assert referenced, "precondition: HTML references cid: URLs"
    assert referenced <= _content_ids(parsed), (
        "every cid: in the HTML must resolve to a Content-ID part"
    )
    assert _part_by_type(parsed, "multipart/related") is not None


def test_inline_images_carry_real_mime_types_and_inline_disposition(tmp_path):
    """Gmail web falls back to 'show as attachment' when the part is
    `application/octet-stream`. Round-12 fought this on the Outlook
    side (PR_ATTACH_MIME_TAG); the .eml path must not reintroduce it."""
    asset_dir = _asset_dir(tmp_path, files={"photo1.jpg": JPEG_BYTES,
                                            "logo.png": PNG_BYTES})
    inline = (
        InlineImage(path=asset_dir / "photo1.jpg",
                    cid="meridian-issue-1-01-photo1.jpg@meridian.local",
                    original_url="https://example.invalid/photo1.jpg"),
        InlineImage(path=asset_dir / "logo.png",
                    cid="meridian-issue-1-02-logo.png@meridian.local",
                    original_url="https://example.invalid/logo.png"),
    )
    msg = build_eml(_draft("<html><body>x</body></html>",
                           inline_images=inline))
    parsed = email.message_from_bytes(msg.as_bytes())

    types = {p.get_content_type() for p in parsed.walk()}
    assert "image/jpeg" in types
    assert "image/png" in types
    assert "application/octet-stream" not in types

    for part in parsed.walk():
        if part.get_content_type().startswith("image/"):
            assert part.get("Content-Disposition", "").startswith("inline")


def test_long_content_ids_are_not_rfc2047_encoded(tmp_path):
    """Regression: Python treats `Content-ID` as unstructured text, so
    once the header exceeds the fold width it gets encoded-word wrapped
    (`=?utf-8?q?=3Cmeridian-...?=`). The HTML's `cid:` reference then
    matches nothing and the photo renders broken -- silently, and only
    for long filenames. The production masthead logo
    (`Nagoya_University_Graduate_school_medicine_logo.jpg`) is exactly
    long enough to trigger it."""
    long_name = "Nagoya_University_Graduate_school_medicine_logo.jpg"
    asset_dir = _asset_dir(tmp_path, files={long_name: JPEG_BYTES})
    cid = f"meridian-issue-3-01-{long_name.lower()}@meridian.local"
    assert len(cid) > 78, "precondition: CID long enough to force folding"

    inline = (InlineImage(path=asset_dir / long_name, cid=cid,
                          original_url="https://example.invalid/logo.jpg"),)
    html = f'<html><body><img src="cid:{cid}"></body></html>'

    parsed = email.message_from_bytes(
        build_eml(_draft(html, inline_images=inline)).as_bytes())

    assert cid in _content_ids(parsed)
    assert _cids_referenced(html) <= _content_ids(parsed)


def test_no_line_exceeds_the_rfc5322_hard_limit(tmp_path):
    """Keeping a long Content-ID unfolded must not push any line past
    the 998-octet limit that makes a message illegal on the wire."""
    long_name = "a" * 90 + ".jpg"
    asset_dir = _asset_dir(tmp_path, files={long_name: JPEG_BYTES})
    inline = (InlineImage(path=asset_dir / long_name,
                          cid=f"meridian-issue-3-01-{long_name}@meridian.local",
                          original_url="https://example.invalid/x.jpg"),)
    raw = build_eml(_draft(
        "<html><body>x</body></html>",
        inline_images=inline,
        bcc="; ".join(f"person{i:02d}@example.ac.jp" for i in range(50)),
    )).as_bytes()

    longest = max(len(line) for line in raw.split(b"\r\n"))
    assert longest <= 998, f"longest line is {longest} octets"


def test_image_bytes_round_trip_unchanged(tmp_path):
    """Base64 encode/decode must return the exact file. A corrupted
    photo would render as a broken image for all 50 recipients."""
    asset_dir = _asset_dir(tmp_path, files={"photo1.jpg": JPEG_BYTES})
    inline = (InlineImage(path=asset_dir / "photo1.jpg",
                          cid="meridian-01-photo1.jpg@meridian.local",
                          original_url="https://example.invalid/p.jpg"),)
    msg = build_eml(_draft("<html><body>x</body></html>",
                           inline_images=inline))
    parsed = email.message_from_bytes(msg.as_bytes())

    payloads = [p.get_payload(decode=True) for p in parsed.walk()
                if p.get_content_type() == "image/jpeg"]
    assert payloads == [JPEG_BYTES]


def test_missing_inline_image_is_skipped_not_raised(tmp_path, caplog):
    """A photo deleted between build and compose must not crash the
    send. The rest of the newsletter still goes out; the editor gets
    a warning in the console."""
    asset_dir = _asset_dir(tmp_path)
    inline = (InlineImage(path=asset_dir / "does-not-exist.jpg",
                          cid="meridian-01-gone.jpg@meridian.local",
                          original_url="https://example.invalid/gone.jpg"),)

    msg = build_eml(_draft("<html><body>x</body></html>",
                           inline_images=inline))

    assert _part_by_type(msg, "text/html") is not None
    assert "does-not-exist.jpg" in caplog.text


def test_editor_filesystem_path_never_reaches_the_message(tmp_path):
    """Round-12 deliverability MEDIUM 3 cleared `PR_ATTACH_PATHNAME` on
    the Outlook path so transport-rule debug headers can't leak the
    editor's local layout. The .eml must not leak it either: only the
    basename belongs in the message."""
    asset_dir = _asset_dir(tmp_path, files={"photo1.jpg": JPEG_BYTES})
    inline = (InlineImage(path=asset_dir / "photo1.jpg",
                          cid="meridian-01-photo1.jpg@meridian.local",
                          original_url="https://example.invalid/p.jpg"),)
    raw = build_eml(_draft("<html><body>x</body></html>",
                           inline_images=inline)).as_bytes()

    # The directory path must be absent; the bare filename is fine.
    assert str(asset_dir).encode() not in raw
    assert str(tmp_path).encode() not in raw
    assert b"photo1.jpg" in raw


def test_ordinary_attachments_promote_the_message_to_mixed(tmp_path):
    """Non-inline attachments must not be confused with CID photos:
    they belong outside the multipart/related, under multipart/mixed."""
    doc = tmp_path / "agenda.png"
    doc.write_bytes(PNG_BYTES)

    msg = build_eml(_draft("<html><body>x</body></html>",
                           attachments=(doc,)))
    parsed = email.message_from_bytes(msg.as_bytes())

    assert parsed.get_content_type() == "multipart/mixed"
    dispositions = [p.get("Content-Disposition", "") for p in parsed.walk()]
    assert any(d.startswith("attachment") and "agenda.png" in d
               for d in dispositions)


# ---------- plaintext fallback -----------------------------------------

def test_plaintext_falls_back_when_the_converter_raises(monkeypatch):
    """`html_to_plaintext` shouldn't raise, but a draft is a bad place
    to discover an unhandled exception. The strict tag-stripper keeps
    the message multipart/alternative rather than HTML-only."""
    import scripts.mail.eml as eml_mod

    def _boom(_html: str) -> str:
        raise RuntimeError("synthetic parser failure")

    monkeypatch.setattr(eml_mod, "html_to_plaintext", _boom)

    msg = build_eml(_draft(
        "<html><body><p>Newsletter body text</p></body></html>"))

    assert msg.get_content_type() == "multipart/alternative"
    body = _part_by_type(msg, "text/plain").get_content()
    assert "Newsletter body text" in body


def test_plaintext_empty_when_both_converters_raise(monkeypatch):
    """Last resort: still emit a (empty) text part rather than losing
    multipart/alternative or crashing the compose step."""
    import scripts.mail.eml as eml_mod

    def _boom(_html: str) -> str:
        raise RuntimeError("synthetic failure")

    monkeypatch.setattr(eml_mod, "html_to_plaintext", _boom)
    monkeypatch.setattr(eml_mod, "html_to_plaintext_strict_fallback", _boom)

    msg = build_eml(_draft("<html><body>x</body></html>"))
    assert msg.get_content_type() == "multipart/alternative"
    assert _part_by_type(msg, "text/plain") is not None


# ---------- path derivation + writing ----------------------------------

def test_eml_lands_next_to_the_rendered_html(tmp_path):
    draft = _draft("<html><body>x</body></html>", tmp_path=tmp_path)
    assert eml_path_for(draft) == tmp_path / "dist" / "issue-1.eml"


def test_eml_path_honours_output_dir(tmp_path):
    """`--output-dir` redirects dist/; the .eml must follow it rather
    than writing back into a possibly read-only toolkit folder
    (the macOS Downloads-sandbox bug from v1.1.2)."""
    elsewhere = tmp_path / "Documents" / "Meridian-Newsletter"
    draft = _draft("<html><body>x</body></html>",
                   preview_path=elsewhere / "dist" / "issue-7.html")
    assert eml_path_for(draft) == elsewhere / "dist" / "issue-7.eml"


def test_missing_preview_path_raises_an_actionable_error():
    """Never invent a location: an editor who can't find their
    newsletter is worse off than one who gets a clear error."""
    with pytest.raises(ValueError, match="build"):
        eml_path_for(_draft("<html><body>x</body></html>"))


def test_write_eml_creates_parent_directory_and_valid_bytes(tmp_path):
    draft = _draft("<html><body><p>hi</p></body></html>", tmp_path=tmp_path)
    out = write_eml(draft)

    assert out.exists() and out.suffix == ".eml"
    parsed = email.message_from_bytes(out.read_bytes())
    assert parsed["X-Unsent"] == "1"
    assert parsed.get_content_type() == "multipart/alternative"


def test_written_file_uses_crlf_line_endings(tmp_path):
    """RFC 5322 §2.3 mandates CRLF in mail bodies; bare LF can trip
    strict MIME validators on Exchange Send-As paths (the same issue
    round-10 fixed in the plaintext converter)."""
    draft = _draft("<html><body><p>hi</p></body></html>", tmp_path=tmp_path)
    raw = write_eml(draft).read_bytes()

    header_block = raw.split(b"\r\n\r\n", 1)[0]
    assert b"\r\n" in header_block
    assert re.search(rb"(?<!\r)\n", header_block) is None, \
        "bare LF found in header block"


# ---------- backend contract -------------------------------------------

def test_backend_declares_its_identity_and_capability():
    backend = EmlBackend()
    assert backend.name == "eml"
    assert backend.is_available() is True
    assert backend.supports_inline_images is True


def test_backend_is_never_auto_selected():
    """`.eml` is an explicit choice. Auto-selecting it would silently
    change what every existing editor sees at the end of a run --
    and Apple Mail opens a .eml read-only, so it is not yet a safe
    default there."""
    backend = EmlBackend()
    for kind in ("outlook", "apple_mail", "thunderbird", "browser",
                 "other", "unknown"):
        assert backend.matches(MailHandler(kind=kind, name=kind)) is False


def test_backend_compose_writes_the_file_and_opens_it(tmp_path, monkeypatch):
    import scripts.mail.eml as eml_mod
    opened: list[Path] = []
    monkeypatch.setattr(eml_mod, "open_with_default_app",
                        lambda p: opened.append(p) or True)

    draft = _draft("<html><body><p>hi</p></body></html>", tmp_path=tmp_path)
    EmlBackend().compose(draft)

    expected = tmp_path / "dist" / "issue-1.eml"
    assert expected.exists()
    assert opened == [expected]


def test_open_failure_does_not_lose_the_file(tmp_path, monkeypatch):
    """If the OS can't launch a handler the editor still has the file;
    the CLI prints where it is. A raised exception here would abort
    the run after the .eml was already written."""
    import scripts.mail.eml as eml_mod

    def _explode(_path):
        raise OSError("no handler registered")

    monkeypatch.setattr(eml_mod.os, "startfile", _explode, raising=False)
    monkeypatch.setattr(eml_mod.shutil, "which", lambda _n: None)

    out = write_eml(_draft("<html><body>x</body></html>", tmp_path=tmp_path))
    assert eml_mod.open_with_default_app(out) is False
    assert out.exists()


# ---------- dispatcher integration -------------------------------------

def test_select_backend_returns_eml_only_when_asked():
    from scripts.mail import select_backend

    assert select_backend("eml", MailHandler(kind="apple_mail",
                                             name="Mail")).name == "eml"
    # And `auto` must never land on it, on any platform.
    for kind in ("apple_mail", "thunderbird", "browser", "other", "unknown"):
        chosen = select_backend("auto", MailHandler(kind=kind, name=kind))
        assert chosen.name != "eml"


def test_auto_fallback_is_still_the_clipboard_backend():
    """Regression guard for the registry: `select_backend('auto')` used
    to return `_BACKENDS[-1]`, so appending any new backend to the list
    would silently redefine the universal fallback."""
    from scripts.mail import select_backend

    chosen = select_backend("auto", MailHandler(kind="unknown", name="?"))
    assert chosen.name == "clipboard_mailto"


def test_resolve_image_mode_auto_gives_cid_for_the_eml_backend():
    """The whole point of `--backend=eml`: photos travel inside the
    file, so no GitHub publishing step is needed."""
    from scripts.mail import resolve_image_mode

    for kind in ("apple_mail", "thunderbird", "browser", "unknown"):
        handler = MailHandler(kind=kind, name=kind)
        assert resolve_image_mode("auto", handler, "eml") == "cid"


def test_image_mode_key_maps_non_cid_backends_to_default():
    from scripts.mail import image_mode_key, select_backend

    handler = MailHandler(kind="apple_mail", name="Mail")
    assert image_mode_key(select_backend("eml", handler)) == "eml"
    assert image_mode_key(select_backend("default", handler)) == "default"
    assert image_mode_key(select_backend("outlook", handler)) == "outlook"


def test_compose_accepts_cid_mode_with_the_eml_backend(tmp_path, monkeypatch):
    """Before this bundle, `compose()` hard-coded
    `chosen.name != "outlook"` and would have rejected CID mode for
    any new backend, however capable."""
    from scripts.mail import compose
    import scripts.mail.eml as eml_mod

    monkeypatch.setattr(eml_mod, "open_with_default_app", lambda p: True)

    asset_dir = _asset_dir(tmp_path, files={"photo1.jpg": JPEG_BYTES})
    preview = tmp_path / "dist" / "issue-1.html"
    preview.parent.mkdir(parents=True)
    preview.write_text("<html></html>", encoding="utf-8")
    html = (f'<html><body><img src="{REPO_PREFIX}/assets/issue-1/photo1.jpg">'
            f'</body></html>')

    outcome = compose(
        html, subject="Test", backend="eml", image_mode="cid",
        asset_dir=asset_dir, preview_path=preview,
        bcc="a@example.ac.jp",
    )

    assert outcome.backend == "eml"
    assert outcome.image_mode == "cid"

    written = tmp_path / "dist" / "issue-1.eml"
    parsed = email.message_from_bytes(written.read_bytes())
    assert parsed["Bcc"] == "a@example.ac.jp"
    assert any(p.get_content_type() == "image/jpeg" for p in parsed.walk())


def test_compose_still_rejects_cid_for_the_clipboard_backend():
    from scripts.mail import compose

    with pytest.raises(ValueError, match="cid"):
        compose("<html></html>", subject="x", backend="default",
                image_mode="cid", asset_dir=Path("."))
