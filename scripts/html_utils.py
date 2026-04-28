"""Small HTML / BeautifulSoup helpers shared across the toolkit.

The validator (deciding which text the recipient actually sees, for
the unfilled-masthead guard), the plaintext alternative generator
(deciding which content survives into the multipart/text body), and
the renderer all need a couple of shared primitives:

* `parse_html(html)`              -- one place to choose the BS4 parser.
* `remove_hidden_elements(soup)`  -- single source of truth for "what
                                     the recipient cannot see".
* `visible_text(html)`            -- shorthand combining the two for
                                     the masthead-guard / spam-filter
                                     ratio computations.

Centralising these eliminates the round-9 hidden-element selector
duplication AND the round-10 architect M1 finding that
`BeautifulSoup(html, "html.parser")` was instantiated independently in
4 places (`validator.py:121,137,219`, `plaintext.py:89`). Switching
the parser later (e.g. to `lxml` for speed) becomes a one-line change.
"""

from __future__ import annotations

from bs4 import BeautifulSoup


# Single source of truth for the BS4 parser the toolkit uses. Pinned
# to the stdlib parser because it ships everywhere -- editors don't
# need to install lxml. Switch here if performance ever justifies it.
_PARSER = "html.parser"


# CSS selectors that match an element the recipient cannot see in the
# rendered HTML body. Order doesn't matter; BS4 unions selectors when
# they're comma-separated.
_HIDDEN_SELECTORS: tuple[str, ...] = (
    "[style*='display:none']",
    "[style*='display: none']",
    "[style*='visibility:hidden']",
    "[style*='visibility: hidden']",
    "[hidden]",
)


def parse_html(html: str) -> BeautifulSoup:
    """Parse `html` with the toolkit's chosen BS4 parser.

    Wraps `BeautifulSoup(html, "html.parser")` so callers don't need
    to remember the parser name AND so a future migration to `lxml`
    is a single-file edit.
    """
    return BeautifulSoup(html, _PARSER)


def remove_hidden_elements(soup: BeautifulSoup) -> None:
    """In-place: drop every element a recipient wouldn't see.

    Mutates `soup`. Returns None. Intentionally aggressive -- if a
    template legitimately needs an off-screen-only element to survive
    text extraction, that's a future requirement worth solving with
    a more nuanced selector then.
    """
    for hidden in soup.select(",".join(_HIDDEN_SELECTORS)):
        hidden.decompose()


def visible_text(html: str, separator: str = " ") -> str:
    """Return the text a recipient can actually read.

    Strips hidden elements before pulling text, so a `display:none`
    preheader fallback (e.g. an inbox-list teaser hidden in the body)
    doesn't leak into the result. Used by both the validator's
    masthead-token guard and any future plaintext-ratio calculations.
    """
    soup = parse_html(html)
    remove_hidden_elements(soup)
    return soup.get_text(separator, strip=True)


__all__ = ["parse_html", "remove_hidden_elements", "visible_text"]
