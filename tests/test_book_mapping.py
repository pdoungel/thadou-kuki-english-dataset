"""Book mapping and discovery: identity comes from canonical URL codes.

Covers the persistence contract: mapping keyed by canonical book codes (never
display names), chapter manifests with correct version URLs, duplicate chapter
link deduplication, and discovery validation.
"""

from __future__ import annotations

import json

import pytest

import bible_scraper.models as models
from bible_scraper.discovery import (
    DISCOVERY_JS,
    load_book_mapping,
    load_chapter_tasks,
    validate_discovery,
    write_discovery_outputs,
)
from bible_scraper.models import (
    CANONICAL_BOOK_ORDER,
    CANONICAL_CHAPTERS,
    VERSIONS,
)
from tests.conftest import (
    THADBSI_BOOK_NAMES,
    NIV_BOOK_NAMES,
    full_book_payload,
    mocked_site,
    version_page_html,
)


def test_mapping_is_keyed_by_canonical_codes(project):
    """Localized THADBSI names must never become mapping keys."""
    payloads = {
        "THADBSI": full_book_payload(VERSIONS["THADBSI"], THADBSI_BOOK_NAMES),
        "NIV": full_book_payload(VERSIONS["NIV"], NIV_BOOK_NAMES),
    }
    write_discovery_outputs(payloads)

    mapping = load_book_mapping()
    assert mapping["canonical_order"] == CANONICAL_BOOK_ORDER
    assert set(mapping["books"]) == set(CANONICAL_BOOK_ORDER)

    gen = mapping["books"]["GEN"]
    # display names recorded as labels only
    assert gen["thadbsi_name"] == "Semtilbu"
    assert gen["english_name"] == "Genesis"
    # localized names are NOT keys anywhere
    assert "Semtilbu" not in mapping["books"]
    assert gen["testament"] == "Old Testament"
    assert gen["chapters"] == {"THADBSI": 50, "NIV": 50}
    assert gen["intro_urls"]["THADBSI"].endswith("GEN.INTRO1.THADBSI")


def test_chapter_manifests_carry_version_urls(project):
    payloads = {
        "THADBSI": full_book_payload(VERSIONS["THADBSI"], THADBSI_BOOK_NAMES),
        "NIV": full_book_payload(VERSIONS["NIV"], NIV_BOOK_NAMES),
    }
    write_discovery_outputs(payloads)

    thad = load_chapter_tasks("THADBSI", "thadbsi")
    niv = load_chapter_tasks("NIV", "niv")
    assert len(thad) == sum(CANONICAL_CHAPTERS.values()) == 1189
    assert len(niv) == 1189

    gen1_thad = next(t for t in thad if t["book_code"] == "GEN" and t["chapter"] == 1)
    gen1_niv = next(t for t in niv if t["book_code"] == "GEN" and t["chapter"] == 1)
    assert gen1_thad["url"] == "https://www.bible.com/bible/1879/GEN.1.THADBSI"
    assert gen1_niv["url"] == "https://www.bible.com/bible/111/GEN.1.NIV"
    assert gen1_thad["book"] == "Semtilbu"  # label only; code decides identity
    assert gen1_thad["status"] == "discovered"


def test_version_page_js_groups_by_canonical_code(project):
    """DISCOVERY_JS on a fixture version page: codes from URLs, not names."""
    cfg = VERSIONS["THADBSI"]
    html = version_page_html(cfg, THADBSI_BOOK_NAMES)
    pages = {cfg.url: html}

    with mocked_site(pages) as site:
        site.session.goto(cfg.url, selector='a[href*="/bible/1879/"]')
        payload = site.session.evaluate(DISCOVERY_JS, cfg.version_id)

    codes = [b["code"] for b in payload["books"]]
    assert codes == CANONICAL_BOOK_ORDER
    assert payload["version_codes_seen"] == ["THADBSI"]

    gen = next(b for b in payload["books"] if b["code"] == "GEN")
    # duplicate "Read Now" link for chapter 1 is deduplicated, not dropped
    assert gen["chapters"] == list(range(1, 51))
    assert gen["name"] == "Semtilbu"
    assert gen["testament"] == "Old Testament"
    assert gen["intro_url"] == "/bible/1879/GEN.INTRO1.THADBSI"
    assert payload["duplicate_chapter_urls"]  # recorded, not silently ignored
    # every book publishes a duplicated chapter-1 "Read Now" link
    assert all(u.startswith("/bible/1879/") and ".1." in u
               for u in payload["duplicate_chapter_urls"])
    assert "/bible/1879/GEN.1.THADBSI" in payload["duplicate_chapter_urls"]
    assert "/bible/1879/REV.1.THADBSI" in payload["duplicate_chapter_urls"]

    rev = next(b for b in payload["books"] if b["code"] == "REV")
    assert rev["name"] == "Thuphon"
    assert rev["testament"] == "New Testament"
    assert rev["chapters"] == list(range(1, 23))

    validation = validate_discovery(payload, cfg)
    assert validation["status"] == "verified"
    assert validation["missing_canonical_books"] == []
    assert validation["chapter_count_mismatches"] == []


def test_discovery_validation_flags_missing_books(project):
    cfg = VERSIONS["NIV"]
    payload = full_book_payload(cfg, NIV_BOOK_NAMES)
    payload["books"] = [b for b in payload["books"] if b["code"] != "GEN"]
    payload["duplicate_chapter_urls"] = []
    payload["version_codes_seen"] = [cfg.version_code]

    validation = validate_discovery(payload, cfg)
    assert validation["status"] == "UNCERTAIN"
    assert validation["missing_canonical_books"] == ["GEN"]
    assert not validation["checks"]["canonical_books_present"]


def test_manifest_files_exist_on_disk(project):
    payloads = {"NIV": full_book_payload(VERSIONS["NIV"], NIV_BOOK_NAMES)}
    write_discovery_outputs(payloads)

    books_path = models.MANIFESTS_DIR / "niv_books.json"
    chapters_path = models.MANIFESTS_DIR / "niv_chapters.jsonl"
    assert books_path.exists() and chapters_path.exists()

    books = json.loads(books_path.read_text(encoding="utf-8"))
    assert books["book_count"] == 66
    assert books["version_code"] == "NIV"

    with chapters_path.open(encoding="utf-8") as fh:
        first = json.loads(fh.readline())
    assert set(first) >= {"version", "book", "book_code", "chapter", "url",
                          "discovered_at", "status"}
    assert ".INTRO" not in json.dumps(first)  # intros are not chapters
