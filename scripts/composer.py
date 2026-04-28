"""Open the rendered newsletter directly in the editor's default email client.

Strategy
--------
1. **Detect** the user's actual default email handler — Outlook desktop,
   Apple Mail, Thunderbird, Gmail-via-browser, etc. — by querying the OS
   (Windows registry, macOS LaunchServices, Linux xdg-mime).
2. **Route**:
   - If the default is **Outlook desktop on Windows**, use the Outlook COM
     API (via pywin32) to open a fully populated HTML draft. The editor
     just types recipients and clicks Send — no copy/paste at all.
   - Otherwise, **copy the HTML to the system clipboard** as formatted
     HTML and open the OS's default mail-handler with a `mailto:` link
     (subject pre-filled). The editor presses Ctrl+V in the message body.

Public API
----------
    detect_default_mail_handler() -> MailHandler
    compose(html, *, subject, backend="auto", preview_path=None) -> str
"""

from __future__ import annotations

import logging
import platform
import subprocess
import urllib.parse
import webbrowser
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class MailHandler:
    """Identifies the user's default email client."""

    kind: str        # "outlook" | "apple_mail" | "thunderbird" | "browser" | "other" | "unknown"
    name: str        # human-readable name from the OS, e.g. "Microsoft Outlook"
    raw_id: str = "" # OS-level identifier (registry ProgId, bundle id, .desktop file)

    @property
    def is_outlook_desktop(self) -> bool:
        return self.kind == "outlook"


# ---------- Detection ----------
def detect_default_mail_handler() -> MailHandler:
    system = platform.system()
    try:
        if system == "Windows":
            return _detect_windows()
        if system == "Darwin":
            return _detect_macos()
        return _detect_linux()
    except Exception as e:
        log.debug("Default-mail detection failed: %s", e)
        return MailHandler(kind="unknown", name="unknown")


def _detect_windows() -> MailHandler:
    """Read HKCU\\...\\UrlAssociations\\mailto\\UserChoice."""
    import winreg  # stdlib on Windows
    key_path = (
        r"Software\Microsoft\Windows\Shell\Associations"
        r"\UrlAssociations\mailto\UserChoice"
    )
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            prog_id, _ = winreg.QueryValueEx(key, "ProgId")
    except FileNotFoundError:
        return MailHandler(kind="unknown", name="unknown")

    pid = (prog_id or "").lower()
    if "outlook" in pid:
        return MailHandler(kind="outlook", name="Microsoft Outlook",
                           raw_id=prog_id)
    if "thunderbird" in pid:
        return MailHandler(kind="thunderbird", name="Mozilla Thunderbird",
                           raw_id=prog_id)
    if "windowslivemail" in pid:
        return MailHandler(kind="other", name="Windows Live Mail",
                           raw_id=prog_id)
    if any(b in pid for b in ("chrome", "firefox", "edge", "msedge",
                              "browser", "html")):
        return MailHandler(kind="browser",
                           name="Web browser (Gmail / Outlook Web / etc.)",
                           raw_id=prog_id)
    return MailHandler(kind="other", name=prog_id, raw_id=prog_id)


def _detect_macos() -> MailHandler:
    """Use LaunchServices (via `defaults read`) to find the default mailto handler."""
    try:
        out = subprocess.run(
            ["defaults", "read",
             "com.apple.LaunchServices/com.apple.launchservices.secure"],
            capture_output=True, text=True, timeout=5, check=False,
        ).stdout
    except Exception:
        out = ""
    bundle = ""
    for line in out.splitlines():
        if "mailto" in line.lower():
            # bundle ids appear in surrounding lines; grab the most recent.
            bundle = line.strip()
            break
    blow = bundle.lower()
    if "com.apple.mail" in blow:
        return MailHandler(kind="apple_mail", name="Apple Mail",
                           raw_id="com.apple.mail")
    if "com.microsoft.outlook" in blow:
        return MailHandler(kind="outlook", name="Microsoft Outlook (macOS)",
                           raw_id="com.microsoft.outlook")
    if "thunderbird" in blow:
        return MailHandler(kind="thunderbird", name="Mozilla Thunderbird",
                           raw_id="thunderbird")
    if any(b in blow for b in ("chrome", "firefox", "safari", "edge",
                               "browser")):
        return MailHandler(kind="browser",
                           name="Web browser (Gmail / Outlook Web / etc.)",
                           raw_id=bundle)
    return MailHandler(kind="unknown", name="unknown", raw_id=bundle)


def _detect_linux() -> MailHandler:
    """`xdg-mime query default x-scheme-handler/mailto`."""
    try:
        out = subprocess.run(
            ["xdg-mime", "query", "default", "x-scheme-handler/mailto"],
            capture_output=True, text=True, timeout=5, check=False,
        ).stdout.strip().lower()
    except FileNotFoundError:
        return MailHandler(kind="unknown", name="unknown")
    if "thunderbird" in out:
        return MailHandler(kind="thunderbird", name="Mozilla Thunderbird",
                           raw_id=out)
    if "outlook" in out:
        return MailHandler(kind="outlook", name="Microsoft Outlook",
                           raw_id=out)
    if any(b in out for b in ("chrome", "firefox", "browser")):
        return MailHandler(kind="browser",
                           name="Web browser (Gmail / Outlook Web / etc.)",
                           raw_id=out)
    return MailHandler(kind="other", name=out or "unknown", raw_id=out)


# ---------- Outlook COM (Windows) ----------
def _outlook_com_available() -> bool:
    if platform.system() != "Windows":
        return False
    try:
        import win32com.client  # noqa: F401
        return True
    except ImportError:
        return False


def compose_outlook(html: str, subject: str) -> None:
    """Open a new Outlook mail item with HTMLBody pre-populated."""
    import win32com.client
    outlook = win32com.client.Dispatch("Outlook.Application")
    mail = outlook.CreateItem(0)  # 0 = olMailItem
    mail.Subject = subject
    mail.HTMLBody = html
    mail.Display(False)  # non-modal: editor can keep working


# ---------- Clipboard (Windows / macOS / Linux) ----------
def copy_html_to_clipboard(html: str) -> bool:
    system = platform.system()
    try:
        if system == "Windows":
            return _copy_html_windows(html)
        if system == "Darwin":
            return _copy_html_macos(html)
        return _copy_html_linux(html)
    except Exception as e:
        log.warning("Clipboard copy failed: %s", e)
        return False


def _copy_html_windows(html: str) -> bool:
    try:
        import win32clipboard
    except ImportError:
        return False
    fragment = "<!--StartFragment-->" + html + "<!--EndFragment-->"
    payload = "<html><body>" + fragment + "</body></html>"
    header = (
        "Version:0.9\r\n"
        "StartHTML:{:010d}\r\n"
        "EndHTML:{:010d}\r\n"
        "StartFragment:{:010d}\r\n"
        "EndFragment:{:010d}\r\n"
    )
    template_len = len(header.format(0, 0, 0, 0).encode("utf-8"))
    start_html = template_len
    start_frag = start_html + len("<html><body>".encode("utf-8")) \
        + len("<!--StartFragment-->".encode("utf-8"))
    end_frag = start_frag + len(html.encode("utf-8"))
    end_html = end_frag + len(
        "<!--EndFragment--></body></html>".encode("utf-8"))
    blob = (header.format(start_html, end_html, start_frag, end_frag)
            + payload).encode("utf-8")
    cf_html = win32clipboard.RegisterClipboardFormat("HTML Format")
    win32clipboard.OpenClipboard()
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(cf_html, blob)
    finally:
        win32clipboard.CloseClipboard()
    return True


def _copy_html_macos(html: str) -> bool:
    """Set the macOS clipboard to HTML.

    Uses a temp-file + AppleScript hand-off so the HTML never enters
    the shell command line -- avoids string-injection (backticks,
    backslashes, double-quotes, AppleScript continuation chars) and
    keeps the implementation safe for arbitrary editor content.
    """
    import tempfile
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".html", delete=False, encoding="utf-8",
        ) as tf:
            tf.write(html)
            tf_path = tf.name
        script = (
            'set theFile to POSIX file "' + tf_path + '"\n'
            'set theHTML to read theFile as «class utf8»\n'
            'set the clipboard to theHTML as «class HTML»\n'
        )
        proc = subprocess.run(
            ["osascript", "-"],
            input=script.encode("utf-8"),
            capture_output=True, timeout=10,
        )
        return proc.returncode == 0
    except Exception as e:
        log.debug("macOS HTML clipboard failed: %s", e)
        return False
    finally:
        try:
            Path(tf_path).unlink(missing_ok=True)
        except Exception:
            pass


def _copy_html_linux(html: str) -> bool:
    for cmd in (["xclip", "-selection", "clipboard", "-t", "text/html"],
                ["wl-copy", "--type", "text/html"]):
        try:
            proc = subprocess.run(cmd, input=html.encode("utf-8"), check=False)
            if proc.returncode == 0:
                return True
        except FileNotFoundError:
            continue
    return False


# ---------- Default-handler launch via mailto ----------
def compose_via_default(html: str, subject: str, *,
                        preview_path: Path | None = None,
                        handler: MailHandler | None = None) -> None:
    """Copy HTML to clipboard, then launch the OS default mail handler."""
    copied = copy_html_to_clipboard(html)
    mailto = "mailto:?subject=" + urllib.parse.quote(subject)
    webbrowser.open(mailto)  # delegates to whichever app the OS has set
    if preview_path is not None and preview_path.exists():
        webbrowser.open(preview_path.as_uri())
    handler_label = f"({handler.name})" if handler else ""
    if copied:
        log.info("HTML copied to clipboard %s — paste with Ctrl+V into the email body.",
                 handler_label)
    else:
        log.warning(
            "Could not copy HTML to clipboard automatically %s. "
            "Copy from the preview window: Ctrl+A then Ctrl+C.",
            handler_label,
        )


# ---------- Top-level dispatch ----------
def compose(html: str, *, subject: str, backend: str = "auto",
            preview_path: Path | None = None) -> str:
    """Open an email draft. Returns the backend used.

    backend="auto" (default): detect the default mail handler and route
    accordingly. backend="outlook" or "default" forces the choice.
    """
    if backend not in ("auto", "outlook", "default"):
        raise ValueError(
            f"backend must be 'auto', 'outlook' or 'default' — got {backend!r}")

    handler = detect_default_mail_handler()
    log.info("Default mail handler: %s [%s]", handler.name, handler.kind)

    use_outlook = (
        backend == "outlook"
        or (backend == "auto" and handler.is_outlook_desktop
            and _outlook_com_available())
    )
    if use_outlook:
        try:
            compose_outlook(html, subject)
            return "outlook"
        except Exception as e:
            log.warning("Outlook draft failed (%s) — falling back to default handler.", e)
            if backend == "outlook":
                raise

    compose_via_default(html, subject, preview_path=preview_path,
                        handler=handler)
    return f"default:{handler.kind}"


__all__ = [
    "MailHandler",
    "detect_default_mail_handler",
    "compose",
    "compose_outlook",
    "compose_via_default",
    "copy_html_to_clipboard",
]
