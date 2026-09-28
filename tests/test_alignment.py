"""Alignment: strictly by canonical reference, with a full audit trail."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bible_scraper.alignment import (
    IDENTICAL_RATIO_WITHHOLD,
    align,
    chapter_identical_ratios,
    load_jsonl,
    split_for_book,
)
from bible_scraper.models import ALIGNED_DIR, AUDIT_DIR, SPLITS_DIR, VERSIONS
from bible_scraper.normalization import load_normalized, normalize_version
from tests.conftest import (
    MINI_SPECS,
    mini_verses,
    write_mini_discovery,
    write_raw_chapter,
)


def _record(cfg, ref, text, *, status="verified", label=None):
    book_code, chapter, verse = ref.split(".")[0], int(ref.split(".")[1]), ref.split(".")[2]
    return {
        "reference": ref, "book_code": book_code, "chapter": chapter,
        "verse": verse, "text": text, "version": cfg.key,
        "version_id": cfg.version_id, "url": cfg.chapter_url(book_code, chapter),
        "language_status": status, "content_hash": "h",
        "book_name": "Label", "source_file": "x.json", "label": label,
    }


@pytest.fixture
def thad():
    return VERSIONS["THADBSI"]


@pytest.fixture
def niv():
    return VERSIONS["NIV"]


# ---------------------------------------------------------------------------
# Basic alignment
# ---------------------------------------------------------------------------
def test_aligned_pairs_join_on_reference(thad, niv, project):
    t = [_record(thad, "GEN.1.1", "thad text a"), _record(thad, "GEN.1.2", "thad text b")]
    e = [_record(niv, "GEN.1.1", "english text a"), _record(niv, "GEN.1.2", "english text b")]
    summary = align(t, e, thad, niv)

    assert summary["counts"]["aligned"] == 2
    rows = load_jsonl(ALIGNED_DIR / "thadou_kuki_niv_parallel.jsonl")
    assert [r["reference"] for r in rows] == ["GEN.1.1", "GEN.1.2"]
    assert rows[0]["thadou_kuki"] == "thad text a"
    assert rows[0]["english"] == "english text a"
    assert rows[0]["source"]["thadou_kuki"]["version_id"] == 1879
    assert rows[0]["source"]["thadou_kuki"]["url"] == thad.chapter_url("GEN", 1)
    assert rows[0]["source"]["english"]["version_id"] == 111
    assert rows[0]["source"]["english"]["url"] == niv.chapter_url("GEN", 1)


def test_alignment_is_not_positional(thad, niv, project):
    """Different verse ordering / gaps must not shift the pairing."""
    t = [_record(thad, "GEN.1.1", "one"), _record(thad, "GEN.1.3", "three"),
         _record(thad, "GEN.1.10", "ten")]
    e = [_record(niv, "GEN.1.10", "EN ten"), _record(niv, "GEN.1.1", "EN one"),
         _record(niv, "GEN.1.3", "EN three")]
    align(t, e, thad, niv)
    rows = {r["reference"]: r for r in
            load_jsonl(ALIGNED_DIR / "thadou_kuki_niv_parallel.jsonl")}
    assert rows["GEN.1.1"]["english"] == "EN one"
    assert rows["GEN.1.3"]["english"] == "EN three"
    assert rows["GEN.1.10"]["english"] == "EN ten"
    assert rows["GEN.1.1"]["thadou_kuki"] == "one"


def test_missing_verses_get_explicit_audit_records(thad, niv, project):
    t = [_record(thad, "GEN.1.1", "both"), _record(thad, "GEN.1.2", "thad only")]
    e = [_record(niv, "GEN.1.1", "both en"), _record(niv, "GEN.1.3", "niv only")]
    summary = align(t, e, thad, niv)

    assert summary["counts"]["aligned"] == 1
    assert summary["counts"]["missing_thadou"] == 1  # GEN.1.3 absent from THADBSI
    assert summary["counts"]["missing_niv"] == 1     # GEN.1.2 absent from NIV

    audit = {a["reference"]: a for a in load_jsonl(AUDIT_DIR / "alignment_audit.jsonl")}
    assert audit["GEN.1.3"]["alignment_status"] == "missing_thadou"
    assert audit["GEN.1.3"]["thadou_status"] == "missing"
    assert audit["GEN.1.3"]["niv_status"] == "present"
    assert audit["GEN.1.2"]["alignment_status"] == "missing_niv"
    assert audit["GEN.1.2"]["reason"]  # human-readable explanation

    rows = {r["reference"] for r in load_jsonl(ALIGNED_DIR / "thadou_kuki_niv_parallel.jsonl")}
    assert rows == {"GEN.1.1"}  # nothing fabricated for the gap
    ml = load_jsonl(ALIGNED_DIR / "thadou_kuki_niv_ml.jsonl")
    assert len(ml) == 1


def test_uncertain_language_is_excluded_not_silently_included(thad, niv, project):
    t = [_record(thad, "GEN.1.1", "ok", status="verified"),
         _record(thad, "GEN.1.2", "suspect", status="LANGUAGE_UNCERTAIN")]
    e = [_record(niv, "GEN.1.1", "ok en"),
         _record(niv, "GEN.1.2", "suspect en")]
    summary = align(t, e, thad, niv)

    assert summary["counts"]["language_uncertain"] == 1
    rows = load_jsonl(ALIGNED_DIR / "thadou_kuki_niv_parallel.jsonl")
    assert [r["reference"] for r in rows] == ["GEN.1.1"]
    audit = {a["reference"]: a for a in load_jsonl(AUDIT_DIR / "alignment_audit.jsonl")}
    assert audit["GEN.1.2"]["alignment_status"] == "language_uncertain"
    assert "LANGUAGE_UNCERTAIN" in audit["GEN.1.2"]["reason"]


def test_empty_text_is_recorded_as_missing_on_that_side(thad, niv, project):
    """A reference present in the capture but with no published text is
    missing on that side — never a fabricated row, never counted as aligned."""
    t = [_record(thad, "GEN.1.1", "   ")]
    e = [_record(niv, "GEN.1.1", "english")]
    summary = align(t, e, thad, niv)
    assert summary["counts"]["missing_thadou"] == 1
    assert summary["counts"]["aligned"] == 0
    audit = load_jsonl(AUDIT_DIR / "alignment_audit.jsonl")
    assert audit[0]["alignment_status"] == "missing_thadou"
    assert audit[0]["thadou_status"] == "present_no_text"
    assert "no verse text" in audit[0]["reason"]
    rows = load_jsonl(ALIGNED_DIR / "thadou_kuki_niv_parallel.jsonl")
    assert rows == []  # nothing fabricated for the gap


def test_bracketed_niv_verse_is_missing_niv(thad, niv, project):
    """bible.com brackets verses an edition omits ("[37]") and publishes only
    a footnote: that is a missing NIV verse, with the label preserved."""
    t = [_record(thad, "GEN.1.1", "thadou text"),
         _record(thad, "GEN.1.2", "thadou text two")]
    e = [_record(niv, "GEN.1.1", "english text"),
         _record(niv, "GEN.1.2", "  ", label="[2]")]
    summary = align(t, e, thad, niv)
    assert summary["counts"]["missing_niv"] == 1
    audit = {a["reference"]: a for a in load_jsonl(AUDIT_DIR / "alignment_audit.jsonl")}
    rec = audit["GEN.1.2"]
    assert rec["alignment_status"] == "missing_niv"
    assert rec["niv_status"] == "present_no_text"
    assert "[2]" in rec["reason"]
    assert "bracketed/omitted" in rec["reason"]
    rows = load_jsonl(ALIGNED_DIR / "thadou_kuki_niv_parallel.jsonl")
    assert [r["reference"] for r in rows] == ["GEN.1.1"]


def test_empty_on_both_sides_is_extraction_error(thad, niv, project):
    """Only when neither side shows text do we call it an extraction problem."""
    t = [_record(thad, "GEN.1.1", "")]
    e = [_record(niv, "GEN.1.1", "   ")]
    summary = align(t, e, thad, niv)
    assert summary["counts"]["extraction_error"] == 1
    audit = load_jsonl(AUDIT_DIR / "alignment_audit.jsonl")
    assert audit[0]["alignment_status"] == "extraction_error"
    assert "empty verse text" in audit[0]["reason"]


def test_identical_text_contamination_is_withheld(thad, niv, project):
    """A chapter whose THADBSI text equals the NIV text is English leakage."""
    # Identical synthetic text on both sides = English leakage into THADBSI.
    same = ["At the start the maker set the broad sky over the dry ground.",
            "The ground had no shape and nothing was there, and shade lay on the deep.",
            "And a breath from the maker was moving over the waters."]
    t = [_record(thad, f"GEN.1.{i}", txt) for i, txt in enumerate(same, 1)]
    e = [_record(niv, f"GEN.1.{i}", txt) for i, txt in enumerate(same, 1)]
    summary = align(t, e, thad, niv)

    assert summary["counts"]["aligned"] == 0
    assert summary["counts"]["language_uncertain"] == 3
    assert summary["contaminated_chapters"]
    assert summary["contaminated_chapters"][0]["book"] == "GEN"
    assert summary["contaminated_chapters"][0]["chapter"] == 1
    assert summary["contaminated_chapters"][0]["ratio"] >= IDENTICAL_RATIO_WITHHOLD
    assert load_jsonl(ALIGNED_DIR / "thadou_kuki_niv_parallel.jsonl") == []


def test_different_text_is_not_contamination(thad, niv, project):
    t = [_record(thad, f"GEN.1.{i}", f"thadou {i}") for i in range(1, 4)]
    e = [_record(niv, f"GEN.1.{i}", f"english {i}") for i in range(1, 4)]
    ratios = chapter_identical_ratios(
        {r["reference"]: r for r in t}, {r["reference"]: r for r in e}
    )
    assert ratios[("GEN", 1)]["identical"] == 0
    summary = align(t, e, thad, niv)
    assert summary["counts"]["aligned"] == 3
    assert summary["contaminated_chapters"] == []


def test_single_shared_verse_is_not_contamination(thad, niv, project):
    """Ratio needs a meaningful denominator (>=3 common verses)."""
    t = [_record(thad, "GEN.1.1", "same")]
    e = [_record(niv, "GEN.1.1", "same")]
    summary = align(t, e, thad, niv)
    assert summary["counts"]["aligned"] == 1  # flagged but not withheld
    rows = load_jsonl(ALIGNED_DIR / "thadou_kuki_niv_parallel.jsonl")
    assert rows[0]["identical_text_flag"] is True


# ---------------------------------------------------------------------------
# Deduplication passed through from normalization
# ---------------------------------------------------------------------------
def test_duplicate_references_are_audited(thad, niv, project):
    t = [_record(thad, "GEN.1.1", "a"), _record(thad, "GEN.1.2", "b")]
    e = [_record(niv, "GEN.1.1", "a en"), _record(niv, "GEN.1.2", "b en")]
    duplicates = [{"reference": "GEN.1.2", "version": "THADBSI",
                   "kept_file": "data/raw/thad_bible/GEN/001.json",
                   "dropped_file": "data/raw/thad_bible/GEN/009.json"}]
    summary = align(t, e, thad, niv, duplicates=duplicates)

    assert summary["counts"]["duplicate_thadou"] == 1
    assert summary["counts"]["aligned"] == 2  # the surviving copy still aligns
    dup_records = [a for a in load_jsonl(AUDIT_DIR / "alignment_audit.jsonl")
                   if a["alignment_status"] == "duplicate_thadou"]
    assert len(dup_records) == 1
    assert dup_records[0]["reference"] == "GEN.1.2"
    assert "009.json" in dup_records[0]["reason"]


# ---------------------------------------------------------------------------
# Splits
# ---------------------------------------------------------------------------
def test_splits_are_whole_book_and_deterministic(thad, niv, project):
    from tests.conftest import write_mini_raw_corpus

    write_mini_discovery(project)
    write_mini_raw_corpus(project)
    for cfg in (thad, niv):
        normalize_version(cfg)

    t, e = load_normalized(thad), load_normalized(niv)
    summary1 = align(t, e, thad, niv)
    manifest_path = SPLITS_DIR / "split_manifest.json"
    manifest1 = json.loads(manifest_path.read_text(encoding="utf-8"))
    parallel1 = load_jsonl(ALIGNED_DIR / "thadou_kuki_niv_parallel.jsonl")

    # deterministic: same input -> byte-identical assignment on a second run
    align(t, e, thad, niv)
    manifest2 = json.loads(manifest_path.read_text(encoding="utf-8"))
    parallel2 = load_jsonl(ALIGNED_DIR / "thadou_kuki_niv_parallel.jsonl")
    assert manifest1["books"] == manifest2["books"]
    assert [r["id"] for r in parallel1] == [r["id"] for r in parallel2]

    # whole books: each book appears in exactly one split
    books = manifest1["books"]
    all_assigned = [b for v in books.values() for b in v]
    assert len(all_assigned) == len(set(all_assigned))
    corpus_books = sorted({r["book_code"] for r in parallel1})
    assert sorted(all_assigned) == corpus_books

    # split files agree with the manifest and with each row's split label
    for split in ("train", "validation", "test"):
        rows = load_jsonl(SPLITS_DIR / f"{split}.jsonl")
        assert len(rows) == manifest1["counts"][split]["verses"]
        assert all(r["split"] == split for r in rows)
        assert {r["book_code"] for r in rows} == set(books[split])
        assert all(split_for_book(r["book_code"]) == split for r in rows)

    # no verse is lost or duplicated across splits
    split_ids = [r["id"] for s in ("train", "validation", "test")
                 for r in load_jsonl(SPLITS_DIR / f"{s}.jsonl")]
    assert sorted(split_ids) == sorted(r["id"] for r in parallel1)
    assert len(split_ids) == len(set(split_ids)) == summary1["counts"]["aligned"]


def test_ml_dataset_mirrors_parallel_dataset(thad, niv, project):
    t = [_record(thad, "GEN.1.1", "thad one"), _record(thad, "GEN.1.2", "thad two")]
    e = [_record(niv, "GEN.1.1", "en one"), _record(niv, "GEN.1.2", "en two")]
    align(t, e, thad, niv)

    parallel = load_jsonl(ALIGNED_DIR / "thadou_kuki_niv_parallel.jsonl")
    ml = load_jsonl(ALIGNED_DIR / "thadou_kuki_niv_ml.jsonl")
    assert len(ml) == len(parallel)
    for p, m in zip(parallel, ml):
        assert set(m) == {"id", "source", "target"}
        assert m["id"] == p["id"]
        assert m["source"] == p["thadou_kuki"]
        assert m["target"] == p["english"]
