"""Detect the user's default email client per OS."""

from __future__ import annotations

import logging
import platform
import subprocess

from scripts.mail.base import MailHandler

log = logging.getLogger(__name__)


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
    """Use LaunchServices (via `defaults read`) to find the mailto handler."""
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


__all__ = ["detect_default_mail_handler"]
