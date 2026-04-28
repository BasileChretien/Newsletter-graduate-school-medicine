"""Small HTML / BeautifulSoup helpers shared across the toolkit.

Both the validator (deciding which text the recipient actually sees,
for the unfilled-masthead guard) and the plaintext alternative
generator (deciding which content survives into the multipart/text
body) need to drop hidden elements before extracting text. Round-9
code-review HIGH: the same 5-selector list lived in
`scripts/validator.py` and `scripts/mail/plaintext.py`. Consolidated
here so adding a new hiding pattern (e.g. `mso-hide:all`,
`opacity:0`) updates both consumers automatically.
"""

from __future__ import annotations

from bs4 import BeautifulSoup

# CSS selectors that match an element the recipient cannot see in the
# rendered HTML body. Order doesn't matter; BS4 selectors are unioned.
_HIDDEN_SELECTORS: tuple[str, ...] = (
    "[style*='display:none']",
    "[style*='display: none']",
    "[style*='visibility:hidden']",
    "[style*='visibility: hidden']",
    "[hidden]",
)


def remove_hidden_elements(soup: BeautifulSoup) -> None:
    """In-place: drop every element a recipient wouldn't see.

    Mutates `soup`. Returns None. Intentionally aggressive -- if a
    template legitimately needs an off-screen-only element to survive
    text extraction, that's a future requirement worth solving with
    a more nuanced selector then.
    """
    for hidden in soup.select(",".join(_HIDDEN_SELECTORS)):
        hidden.decompose()


__all__ = ["remove_hidden_elements"]
