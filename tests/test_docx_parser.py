"""Tests for the DOCX parser using the actual MERIDIAN template."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.config import MERIDIAN_TEMPLATE
from scripts.docx_parser import (
    BodyParagraph, BulletList, Heading, Newsletter, Section, TableBlock,
    parse,
)


pytestmark = pytest.mark.skipif(
    not MERIDIAN_TEMPLATE.exists(),
    reason="MERIDIAN template not built yet",
)


@pytest.fixture(scope="module")
def newsletter() -> Newsletter:
    return parse(MERIDIAN_TEMPLATE)


def test_seven_sections_parsed(newsletter):
    assert len(newsletter.sections) == 7
    assert [s.number for s in newsletter.sections] == [1, 2, 3, 4, 5, 6, 7]


def test_section_titles_preserved(newsletter):
    titles = [s.title for s in newsletter.sections]
    assert "MESSAGE FROM THE DEAN" in titles[0].upper()
    assert "FEATURED HIGHLIGHTS" in titles[1].upper()
    assert "RESEARCH" in titles[2].upper()
    assert "INTERNATIONAL" in titles[3].upper()
    assert "EDUCATION" in titles[4].upper()
    assert "EVENTS" in titles[5].upper()
    assert "CONTACT" in titles[6].upper()


def test_masthead_extracted(newsletter):
    assert newsletter.masthead.title == "MERIDIAN"
    assert "medicine" in newsletter.masthead.tagline.lower()
    assert "Nagoya" in newsletter.masthead.subtitle


def test_research_section_has_subheads(newsletter):
    research = newsletter.sections[2]  # Section 3
    headings = [b.text for b in research.blocks if isinstance(b, Heading)]
    assert "Notable Publications" in headings
    assert "Grants & Funding Awarded" in headings


def test_research_has_bullet_list(newsletter):
    research = newsletter.sections[2]
    bullets = [b for b in research.blocks if isinstance(b, BulletList)]
    assert bullets, "Expected at least one bullet list in Research section"
    assert all(len(b.items) > 0 for b in bullets)


def test_international_section_has_table(newsletter):
    intl = newsletter.sections[3]
    tables = [b for b in intl.blocks if isinstance(b, TableBlock)]
    assert tables, "Expected visiting-scholars table in International section"
    t = tables[0]
    assert t.has_header
    assert len(t.rows) >= 2  # header + at least one data row


def test_events_section_has_event_table(newsletter):
    events = newsletter.sections[5]
    tables = [b for b in events.blocks if isinstance(b, TableBlock)]
    assert tables
    assert tables[0].has_header
    # event table starts with Date / Time & Venue / Event headers
    headers = " ".join(tables[0].rows[0]).lower()
    assert "date" in headers


def test_body_paragraphs_html_escaped(newsletter):
    for section in newsletter.sections:
        for block in section.blocks:
            if isinstance(block, BodyParagraph):
                # No raw < or > except inside our generated tags
                assert "<script" not in block.html.lower()
