"""Copy HTML to the system clipboard as formatted HTML.

Cross-platform: CF_HTML on Windows, AppleScript «class HTML» via temp
file on macOS, xclip / wl-copy with text/html target on Linux.
"""

from __future__ import annotations

import logging
import platform
import subprocess
from pathlib import Path

log = logging.getLogger(__name__)


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

    Writes the HTML to a temp file and asks AppleScript to read it as
    «class HTML» -- avoids string injection (backticks, backslashes,
    AppleScript continuation chars) for arbitrary editor content.
    """
    import tempfile
    tf_path = ""
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
        if tf_path:
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


__all__ = ["copy_html_to_clipboard"]
