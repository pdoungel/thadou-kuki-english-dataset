"""Chapter extraction against fixture DOM (offline, real EXTRACT_JS).

Verifies: verse text preserved verbatim, labels/headings/notes/cross-refs
excluded, poetry spans merged, page metadata captured, chapter validation
status, and the missing-container (invalid chapter) path.
"""

from __future__ import annotations

import pytest

from bible_scraper.extraction import (
    EXTRACT_JS,
    content_hash,
    english_stopword_ratio,
    extract_chapter,
    group_spans,
    merge_parts,
    validate_chapter,
)
from bible_scraper.models import VERSIONS
from tests.conftest import chapter_html, mocked_site


def _thad_page(**kwargs) -> str:
    cfg = VERSIONS["THADBSI"]
    defaults = dict(
        url=cfg.chapter_url("GEN", 1),
        version_code=cfg.version_code,
        version_id=cfg.version_id,
        version_name=cfg.version_name,
        book_code="GEN",
        book_name="Semtilbu",
        chapter=1,
        verses=[
            "Pathen ahi hong hong ahi.",
            "Vai ding ahi kha a lam ahi jing.",
            "Mawhna le ahi a kha ni.",
        ],
        notes={2: "Na piang a ni. "},
        split_verses={3},
    )
    defaults.update(kwargs)
    return chapter_html(**defaults)


def test_extract_chapter_preserves_published_text(project):
    cfg = VERSIONS["THADBSI"]
    pages = {cfg.chapter_url("GEN", 1): _thad_page()}

    with mocked_site(pages) as site:
        raw = extract_chapter(site.session, cfg, "GEN", 1, "Semtilbu")

    assert raw["verse_count"] == 3
    texts = {v["reference"]: v["text"] for v in raw["verses"]}
    # exact published text, no normalization beyond whitespace collapsing
    assert texts["GEN.1.1"] == "Pathen ahi hong hong ahi."
    assert texts["GEN.1.2"] == "Vai ding ahi kha a lam ahi jing."
    # poetry split spans merge back with source spacing intact
    assert texts["GEN.1.3"] == "Mawhna le ahi a kha ni."
    # footnote text and cross-reference never leak into the verse
    assert "Na piang a ni." not in " ".join(texts.values())
    assert "v.1" not in " ".join(texts.values())
    # chapter label and heading are never verse text
    assert "Chapter heading (must be excluded)" not in " ".join(texts.values())


def test_extract_chapter_metadata_and_validation(project):
    cfg = VERSIONS["THADBSI"]
    url = cfg.chapter_url("GEN", 1)
    pages = {url: _thad_page()}

    with mocked_site(pages) as site:
        raw = extract_chapter(site.session, cfg, "GEN", 1, "Semtilbu")

    assert raw["page"]["title"] == "Semtilbu 1 | THADBSI Bible - Bible App"
    assert raw["page"]["canonical"] == url
    assert raw["version_code"] == "THADBSI"
    assert raw["book_code"] == "GEN"
    assert raw["chapter"] == 1
    assert raw["url"] == url
    assert raw["selector_fallback"] is False
    assert raw["anomalies"] == []
    assert raw["language_verification"]["status"] == "verified"
    assert raw["language_verification"]["method"] == [
        "version_metadata", "page_metadata", "DOM_context",
    ]
    assert raw["heading"] == "Chapter heading (must be excluded)"
    assert raw["content_hash"] == content_hash(raw["verses"])
    # cross-reference spans are not counted as verses
    assert [v["reference"] for v in raw["verses"]] == ["GEN.1.1", "GEN.1.2", "GEN.1.3"]


def test_extract_niv_chapter_validates_as_english(project):
    cfg = VERSIONS["NIV"]
    # Synthetic English standing in for the NIV: the public repository must
    # not carry NIV verse text (see NOTICE and LICENSE_NOTES.md).
    verses = [
        "At the start the maker set the broad sky over the dry ground.",
        "The ground had no shape and nothing was there, and shade lay on the deep.",
        "And a breath from the maker was moving over the waters.",
    ]
    url = cfg.chapter_url("GEN", 1)
    page = chapter_html(
        url=url, version_code=cfg.version_code, version_id=cfg.version_id,
        version_name=cfg.version_name, book_code="GEN", book_name="Genesis",
        chapter=1, verses=verses,
    )
    with mocked_site({url: page}) as site:
        raw = extract_chapter(site.session, cfg, "GEN", 1, "Genesis")

    assert raw["language_verification"]["status"] == "verified"
    assert [v["text"] for v in raw["verses"]] == verses
    assert raw["language_verification"]["supplementary"]["english_stopword_ratio"] >= 0.25


def test_missing_container_is_detected(project):
    """Invalid chapter: page loads but no chapter container -> not extracted."""
    cfg = VERSIONS["THADBSI"]
    url = cfg.chapter_url("GEN", 51)
    page = chapter_html(
        url=url, version_code=cfg.version_code, version_id=cfg.version_id,
        version_name=cfg.version_name, book_code="GEN", book_name="Semtilbu",
        chapter=51, verses=[], with_container=False,
    )
    from bible_scraper.browser import BrowserError

    with mocked_site({url: page}) as site:
        with pytest.raises(BrowserError):
            # selector wait fails because the container never appears
            extract_chapter(site.session, cfg, "GEN", 51, "Semtilbu")


def test_selector_fallback_when_class_names_change(project):
    """CSS-module hash rotation must not break extraction."""
    cfg = VERSIONS["THADBSI"]
    url = cfg.chapter_url("GEN", 1)
    page = _thad_page().replace("AbC1x__verse", "Zz9Qq__verse")
    with mocked_site({url: page}) as site:
        raw = extract_chapter(site.session, cfg, "GEN", 1, "Semtilbu")
    assert raw["verse_count"] == 3
    assert raw["selector_fallback"] is False  # suffix match still works

    # now remove the suffix pattern entirely: fallback selector must kick in
    page2 = _thad_page().replace("AbC1x__verse", "verseSpan")
    with mocked_site({url: page2}) as site:
        raw2 = extract_chapter(site.session, cfg, "GEN", 1, "Semtilbu")
    assert raw2["selector_fallback"] is True
    assert raw2["verse_count"] == 3
    assert {v["reference"]: v["text"] for v in raw2["verses"]}["GEN.1.2"] == \
        "Vai ding ahi kha a lam ahi jing."


def test_wrong_version_is_not_silently_verified(project):
    """Serve an NIV page for a THADBSI request: validation must withhold."""
    cfg = VERSIONS["THADBSI"]
    other = VERSIONS["NIV"]
    url = cfg.chapter_url("GEN", 1)
    # NIV-shaped page at the THADBSI URL (title/version code mismatch)
    page = chapter_html(
        url=url, version_code=other.version_code, version_id=other.version_id,
        version_name=other.version_name, book_code="GEN", book_name="Genesis",
        chapter=1,
        verses=["At the start the maker set the broad sky over the dry ground.",
                "The ground had no shape and nothing was there, and shade lay on the deep."],
    )
    with mocked_site({url: page}) as site:
        raw = extract_chapter(site.session, cfg, "GEN", 1, "Semtilbu")

    status = raw["language_verification"]
    assert status["status"] == "LANGUAGE_UNCERTAIN"
    assert "title_version_consistent" in status["failing"] or \
           "version_link_present" in status["failing"] or \
           "book_name_matches" in status["failing"]


def test_chapter_intro_title_variant_still_verifies(project):
    """The site sometimes serves a chapter-intro <title> with no version code
    (observed live for MAT.1-MAT.5): 'The Genealogy of Jesus Christ - Bible
    App'. Identity is still proven by URL, canonical link, version link and
    h1, so the chapter must verify — with the variant surfaced as a warning,
    not hidden."""
    cfg = VERSIONS["NIV"]
    url = cfg.chapter_url("MAT", 1)
    page = chapter_html(
        url=url, version_code=cfg.version_code, version_id=cfg.version_id,
        version_name=cfg.version_name, book_code="MAT", book_name="Matthew",
        chapter=1,
        verses=["Here is the record of the man, the son of David.",
                "Here is the record of the son of Abraham, the father of Isaac."],
        full_title="The Genealogy of Jesus Christ - Bible App",
    )
    with mocked_site({url: page}) as site:
        raw = extract_chapter(site.session, cfg, "MAT", 1, "Matthew")

    status = raw["language_verification"]
    assert raw["page"]["title"] == "The Genealogy of Jesus Christ - Bible App"
    assert status["status"] == "verified"
    assert status["checks"]["title_version_consistent"] is True   # title neutral
    assert status["checks"]["book_name_matches"] is True          # via h1 fallback
    assert status["checks"]["url_matches_expected"] is True
    assert "title_without_version_code" in status["warnings"]
    assert status["failing"] == []


def test_title_declaring_a_foreign_version_is_withheld(project):
    """A title that names a *different* version contradicts the request."""
    cfg = VERSIONS["THADBSI"]
    url = cfg.chapter_url("GEN", 1)
    page = chapter_html(
        url=url, version_code="KJV", version_id=cfg.version_id,
        version_name="King James Version", book_code="GEN", book_name="Genesis",
        chapter=1,
        verses=["In the beginning God created the heaven and the earth."],
        full_title="Genesis 1 | KJV Bible - Bible App",
    )
    with mocked_site({url: page}) as site:
        raw = extract_chapter(site.session, cfg, "GEN", 1, "Semtilbu")
    status = raw["language_verification"]
    assert status["status"] == "LANGUAGE_UNCERTAIN"
    assert "title_version_consistent" in status["failing"]


def test_omitted_verse_is_reported_but_does_not_withhold(project):
    """A verse the publisher omits (empty text) is a content fact recorded in
    warnings; it must not withhold a chapter whose identity is proven."""
    cfg = VERSIONS["NIV"]
    url = cfg.chapter_url("JHN", 5)
    verses = [f"This is verse number {i} of the chapter and it is here."
              for i in range(1, 11)]
    verses[3] = ""  # JHN.5.4: label + footnote only in the source edition
    page = chapter_html(
        url=url, version_code=cfg.version_code, version_id=cfg.version_id,
        version_name=cfg.version_name, book_code="JHN", book_name="John",
        chapter=5, verses=verses,
    )
    with mocked_site({url: page}) as site:
        raw = extract_chapter(site.session, cfg, "JHN", 5, "John")

    status = raw["language_verification"]
    assert status["status"] == "verified"
    assert status["empty_verse_count"] == 1
    assert status["warnings"]["empty_verses"]["references"] == ["JHN.5.4"]
    assert status["checks"]["text_coverage_ok"] is True
    assert status["failing"] == []


def test_mostly_empty_chapter_is_withheld(project):
    """Silent extraction breakage looks like empty verses: when most of a
    chapter has no text, withhold rather than trust it."""
    cfg = VERSIONS["NIV"]
    url = cfg.chapter_url("MRK", 9)
    verses = [f"This is verse {i} and it is the text of the chapter here."
              for i in range(1, 11)]
    verses = verses + [""] * 6  # 10 written of 16 -> 0.625 coverage
    page = chapter_html(
        url=url, version_code=cfg.version_code, version_id=cfg.version_id,
        version_name=cfg.version_name, book_code="MRK", book_name="Mark",
        chapter=9, verses=verses,
    )
    with mocked_site({url: page}) as site:
        raw = extract_chapter(site.session, cfg, "MRK", 9, "Mark")

    status = raw["language_verification"]
    assert status["status"] == "LANGUAGE_UNCERTAIN"
    assert "text_coverage_ok" in status["failing"]
    assert status["checks"]["has_text_content"] is True  # text exists, just not enough


# ---------------------------------------------------------------------------
# Pure-Python join rules
# ---------------------------------------------------------------------------
def test_merge_parts_rules():
    # empty parts contribute nothing
    assert merge_parts([{"text": ""}, {"text": "a"}, {"text": None}]) == "a"
    # plain concatenation with source whitespace preserved
    assert merge_parts([{"text": "line one "}, {"text": "line two"}]) == "line one line two"
    # no-space fragments (poetry) get exactly one space
    assert merge_parts([{"text": "word"}, {"text": "word2"}]) == "word word2"
    # a note boundary means raw concatenation (source spacing authoritative)
    assert merge_parts([
        {"text": "kept ", "note_before": False},
        {"text": "going", "note_before": True},
    ]) == "kept going"
    assert merge_parts([
        {"text": "kept", "note_before": False},
        {"text": "'s mark", "note_before": True},
    ]) == "kept's mark"
    # first non-empty part starts the text even if a note precedes it
    assert merge_parts([{"text": "", "note_before": True},
                        {"text": "start"}]) == "start"


def test_merge_parts_never_edits_text():
    published = "Ahi \"the\" pathen's  (jin) … na  100% a kha."
    out = merge_parts([{"text": published, "note_before": False}])
    assert out == published  # verbatim: no smart quotes, no re-spacing inside


def test_english_stopword_ratio_heuristic():
    assert english_stopword_ratio("the and of to in that it is was") == pytest.approx(1.0)
    assert english_stopword_ratio("Pathen ahi hong ahi mawhna le ahi ni") == 0.0
    assert english_stopword_ratio("") == 0.0
    assert english_stopword_ratio("a a a the") == pytest.approx(1.0)  # "a" is a stopword
    assert english_stopword_ratio("the and cat dog") == pytest.approx(0.5)


def test_validate_chapter_withholds_on_english_thadbsi():
    """Heuristics may only withhold confidence, never grant it."""
    cfg = VERSIONS["THADBSI"]
    payload = {
        "page": {
            "title": "Semtilbu 1 | THADBSI Bible - Bible App",
            "url": cfg.chapter_url("GEN", 1),
            "canonical": cfg.chapter_url("GEN", 1),
            "versionLinks": [f"/versions/{cfg.version_id}-x"],
        },
        "containerFound": True,
    }
    englishish = [{"reference": "GEN.1.1", "text": "In the beginning it was the "
                   "way that they had been of the people and the land"}]
    result = validate_chapter(payload, englishish, cfg, "GEN", 1,
                              cfg.chapter_url("GEN", 1), "Semtilbu", "Semtilbu")
    assert result["status"] == "LANGUAGE_UNCERTAIN"
    assert "english_stopword_ratio_out_of_range" in result["failing"]
    # structural checks all passed — the heuristic alone withheld it
    assert all(result["checks"].values())
    assert result["supplementary"]["english_stopword_ratio"] > 0.55
