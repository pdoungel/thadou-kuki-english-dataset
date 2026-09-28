"""Normalization: technical whitespace only + per-version deduplication."""

from __future__ import annotations

import json

import pytest

from bible_scraper.models import NORMALIZED_DIR, VERSIONS, atomic_write_json
from bible_scraper.normalization import (
    load_normalized,
    normalize_text,
    normalize_version,
    parse_reference,
    raw_chapter_paths,
)
from tests.conftest import write_raw_chapter


def test_normalize_text_is_whitespace_only():
    assert normalize_text("  a   b \n\t c  ") == "a b c"
    assert normalize_text("\n\nIn the beginning\r\n") == "In the beginning"
    # nothing else changes: case, punctuation, diacritics, quotes, digits
    tricky = "Ahi \"the\" pathen's (jin) … naïve 100% 1:1"
    assert normalize_text(tricky) == tricky
    # non-breaking space collapses too (technical whitespace)
    assert normalize_text("a\u00a0b") == "a b"
    assert normalize_text("") == ""
    assert normalize_text("   ") == ""


def test_normalize_text_preserves_published_unicode():
    published = "Thadou: thutheng ahi kha."
    assert normalize_text(published) == published
    # no unicode normalization applied (composed vs combining accents kept)
    combining = "e\u0301cole"
    assert normalize_text(combining) == combining
    # straight quotes and ellipsis stay exactly as published
    quoted = 'Ahi "the" pathen\u2019s \u2026 kha.'
    assert normalize_text(quoted) == quoted


def test_normalize_version_dedupes_by_reference(project):
    """Same canonical reference twice in one version -> first wins, logged."""
    cfg = VERSIONS["THADBSI"]
    write_raw_chapter(cfg, "GEN", "Semtilbu", 1, ["first text.", "second text."])

    from bible_scraper.models import RAW_DIR

    # a second capture file containing an overlapping reference
    other = RAW_DIR / cfg.raw_dirname / "GEN" / "002.json"
    payload = {
        "version": cfg.key, "version_id": cfg.version_id,
        "version_code": cfg.version_code, "book_code": "GEN",
        "book_name": "Semtilbu", "chapter": 2,
        "url": cfg.chapter_url("GEN", 2),
        "retrieved_at": "2026-09-27T00:00:00+00:00",
        "content_hash": "x", "page": {}, "chapter_label": "2", "heading": None,
        "selector_fallback": False, "navigation_attempts": 1, "anomalies": [],
        "language_verification": {"status": "verified", "failing": []},
        "verse_count": 2,
        "verses": [
            # duplicate of GEN.1.1 (different text): dropped, recorded
            {"reference": "GEN.1.1", "verse": "1", "label": "1",
             "text": "DUPLICATE text.", "span_count": 1,
             "parts": [{"text": "DUPLICATE text.", "note_before": False}]},
            {"reference": "GEN.2.1", "verse": "1", "label": "1",
             "text": "chap two.", "span_count": 1,
             "parts": [{"text": "chap two.", "note_before": False}]},
        ],
    }
    other.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(other, payload)

    summary = normalize_version(cfg)
    # references kept: GEN.1.1 + GEN.1.2 (file 001) and GEN.2.1 (file 002)
    assert summary["verses"] == 3
    assert summary["unique_references"] == 3
    assert summary["duplicate_references"] == 1
    dup = summary["duplicates"][0]
    assert dup["reference"] == "GEN.1.1"
    assert dup["version"] == "THADBSI"
    assert dup["kept_file"].endswith("GEN/001.json")
    assert dup["dropped_file"].endswith("GEN/002.json")

    rows = load_normalized(cfg)
    by_ref = {r["reference"]: r for r in rows}
    assert by_ref["GEN.1.1"]["text"] == "first text."  # first capture wins
    assert "DUPLICATE" not in json.dumps(rows)
    assert set(by_ref) == {"GEN.1.1", "GEN.1.2", "GEN.2.1"}


def test_normalize_version_records_language_status(project):
    cfg = VERSIONS["THADBSI"]
    write_raw_chapter(cfg, "GEN", "Semtilbu", 1, ["text one."])
    write_raw_chapter(cfg, "EXO", "Potdohbu", 1, ["text two."],
                      language_status="LANGUAGE_UNCERTAIN",
                      failing=["english_stopword_ratio_out_of_range"])

    summary = normalize_version(cfg)
    assert summary["uncertain_chapters"] == ["EXO.1"]
    rows = {r["reference"]: r for r in load_normalized(cfg)}
    assert rows["GEN.1.1"]["language_status"] == "verified"
    assert rows["EXO.1.1"]["language_status"] == "LANGUAGE_UNCERTAIN"


def test_normalize_version_records_empty_verses(project):
    cfg = VERSIONS["NIV"]
    write_raw_chapter(cfg, "GEN", "Genesis", 1, ["kept.", "   "])
    summary = normalize_version(cfg)
    assert [e["reference"] for e in summary["empty_verses"]] == ["GEN.1.2"]
    rows = {r["reference"]: r for r in load_normalized(cfg)}
    assert rows["GEN.1.2"]["text"] == ""  # recorded, not hidden


def test_normalize_version_skips_malformed_references(project):
    cfg = VERSIONS["NIV"]
    write_raw_chapter(cfg, "GEN", "Genesis", 1, ["ok text."])
    # inject a malformed reference into the raw capture
    from bible_scraper.models import RAW_DIR

    path = RAW_DIR / cfg.raw_dirname / "GEN" / "001.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["verses"].append({"reference": "GEN.1", "verse": "1", "label": "1",
                           "text": "bad ref", "span_count": 1, "parts": []})
    atomic_write_json(path, data)

    summary = normalize_version(cfg)
    assert summary["verses"] == 1
    assert load_normalized(cfg)[0]["reference"] == "GEN.1.1"


def test_normalized_output_is_jsonl_with_expected_fields(project):
    cfg = VERSIONS["THADBSI"]
    write_raw_chapter(cfg, "GEN", "Semtilbu", 1, ["text one.", "text two."])
    normalize_version(cfg)

    out = NORMALIZED_DIR / "thadbsi_verses.jsonl"
    assert out.exists()
    lines = out.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    row = json.loads(lines[0])
    assert set(row) >= {"reference", "book_code", "chapter", "verse", "text",
                        "version", "version_id", "url", "source_file",
                        "language_status", "content_hash"}
    assert row["version"] == "THADBSI"
    assert row["version_id"] == 1879
    assert row["url"] == cfg.chapter_url("GEN", 1)


def test_normalized_output_is_sorted_canonically(project):
    cfg = VERSIONS["NIV"]
    write_raw_chapter(cfg, "REV", "Revelation", 2, ["rev two one.", "rev two two."])
    write_raw_chapter(cfg, "GEN", "Genesis", 10, ["gen ten one."])
    write_raw_chapter(cfg, "GEN", "Genesis", 2, ["gen two one."])
    normalize_version(cfg)

    refs = [r["reference"] for r in load_normalized(cfg)]
    assert refs == ["GEN.2.1", "GEN.10.1", "REV.2.1", "REV.2.2"]


def test_raw_chapter_paths_stable_order(project):
    cfg = VERSIONS["NIV"]
    write_raw_chapter(cfg, "GEN", "Genesis", 1, ["a"])
    write_raw_chapter(cfg, "EXO", "Exodus", 1, ["b"])
    paths = raw_chapter_paths(cfg)
    assert len(paths) == 2
    assert paths == sorted(paths)
