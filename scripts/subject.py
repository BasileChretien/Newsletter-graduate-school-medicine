"""Derive the email subject line from a parsed masthead.

A module of its own so that the CLI and the browser build can share one
implementation without either depending on the other. It briefly lived
in `scripts/webapp.py`, which made `build_newsletter.py` import the
web-build module just to name an email -- backwards layering, and a
surprise for anyone reading the CLI's imports.

Two implementations of "what is this issue's subject?" would eventually
disagree, and the subject is both what recipients see in their inbox
preview and what `manifest.py` records for the audit trail. A mismatch
between those two is exactly what `sanitize_subject` exists to prevent.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from scripts.config import TITLE
from scripts.text_utils import sanitize_subject

# Type-only import: there is no import cycle here (docx_parser reaches
# only config/text_utils/html_utils). The reason is cost -- importing
# docx_parser pulls in python-docx and lxml, which is real time in
# Pyodide for a module that only needs the name for an annotation.
if TYPE_CHECKING:
    from scripts.docx_parser import Masthead

log = logging.getLogger(__name__)


def subject_from_masthead(issue: int, masthead: Masthead | None) -> str:
    """Build the email subject from an already-parsed masthead.

    Runs the issue line through `sanitize_subject` so Word-pasted
    invisibles (ZWSP, NBSP, BOM, RLO) never reach the wire -- otherwise
    the inbox preview shows one string while the logs and the audit
    trail show another.

    Total by construction: a non-string `issue_line` arriving from
    schema drift falls back to the generic subject rather than raising.
    A `TypeError` here used to short-circuit the validate-before-write
    guard upstream, which is a bad place to discover a type bug.
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


__all__ = ["subject_from_masthead"]
