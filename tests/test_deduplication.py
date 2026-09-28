"""Deduplication rules: by canonical reference within a version only."""

from __future__ import annotations

import json

import pytest

from bible_scraper.alignment import align, load_jsonl
from bible_scraper.extraction import group_spans
from bible_scraper.models import ALIGNED_DIR, AUDIT_DIR, VERSIONS, atomic_write_json
from bible_scraper.normalization import load_normalized, normalize_version
from tests.conftest import write_raw_chapter


def test_duplicate_spans_merge_into_one_verse():
    """Poetry/spacer spans repeating a USFM are merged, not double-counted."""
    spans = [
        {"usfm": "PSA.23.1", "label": "1",
         "parts": [{"text": "The Lord is my shepherd; ", "note_before": False}]},
        {"usfm": "PSA.23.1", "label": None,
         "parts": [{"text": "I shall not want.", "note_before": False}]},
        {"usfm": "PSA.23.1", "label": None,
         "parts": [{"text": "", "note_before": False}]},  # spacer
        {"usfm": "PSA.23.2", "label": "2",
         "parts": [{"text": "He makes me lie down.", "note_before": False}]},
    ]
    verses, anomalies = group_spans(spans, "PSA", 23)
    assert [v["reference"] for v in verses] == ["PSA.23.1", "PSA.23.2"]
    assert verses[0]["text"] == "The Lord is my shepherd; I shall not want."
    assert verses[0]["span_count"] == 3
    assert verses[1]["span_count"] == 1
    assert anomalies == []


def test_normalize_dedupes_within_version_only(project):
    cfg = VERSIONS["THADBSI"]
    write_raw_chapter(cfg, "GEN", "Semtilbu", 1, ["kept text."])
    # second file (later in stable path order) repeats GEN.1.1 with different text
    from bible_scraper.models import RAW_DIR

    other = RAW_DIR / cfg.raw_dirname / "GEN" / "002.json"
    payload = json.loads(
        (RAW_DIR / cfg.raw_dirname / "GEN" / "001.json").read_text(encoding="utf-8")
    )
    payload["book_code"] = "GEN"
    payload["book_name"] = "Semtilbu"
    payload["chapter"] = 2
    payload["url"] = cfg.chapter_url("GEN", 2)
    payload["verses"] = [
        {"reference": "GEN.1.1", "verse": "1", "label": "1",
         "text": "other text.", "span_count": 1,
         "parts": [{"text": "other text.", "note_before": False}]}
    ]
    payload["verse_count"] = 1
    other.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(other, payload)

    summary = normalize_version(cfg)
    assert summary["duplicate_references"] == 1
    rows = load_normalized(cfg)
    assert len(rows) == 1
    assert rows[0]["text"] == "kept text."


def test_identical_text_under_different_references_is_kept(project):
    """Repeated wording (e.g. titles) is NOT a duplicate: references decide."""
    cfg = VERSIONS["NIV"]
    write_raw_chapter(cfg, "GEN", "Genesis", 1,
                      ["A book of the generations of Adam.",  # repeated text
                       "A book of the generations of Adam."])
    write_raw_chapter(cfg, "GEN", "Genesis", 2,
                      ["A book of the generations of Adam."])
    summary = normalize_version(cfg)
    assert summary["duplicate_references"] == 0
    assert summary["verses"] == 3
    assert len(load_normalized(cfg)) == 3


def test_same_reference_across_versions_is_not_a_duplicate(thad_cfg, niv_cfg, project):
    """GEN.1.1 exists in both versions by design; pairing is alignment."""
    write_raw_chapter(thad_cfg, "GEN", "Semtilbu", 1, ["thadou text."])
    write_raw_chapter(niv_cfg, "GEN", "Genesis", 1, ["english text."])
    normalize_version(thad_cfg)
    normalize_version(niv_cfg)

    summary = align(load_normalized(thad_cfg), load_normalized(niv_cfg),
                    thad_cfg, niv_cfg)
    assert summary["counts"]["aligned"] == 1
    assert summary["counts"]["duplicate_thadou"] == 0
    assert summary["counts"]["duplicate_niv"] == 0
    # and the "duplicate" audit statuses stay at zero
    statuses = [a["alignment_status"]
                for a in load_jsonl(AUDIT_DIR / "alignment_audit.jsonl")]
    assert statuses == ["aligned"]


def test_ml_and_parallel_have_no_duplicate_ids(thad_cfg, niv_cfg, project):
    write_raw_chapter(thad_cfg, "GEN", "Semtilbu", 1, ["a.", "b."])
    write_raw_chapter(niv_cfg, "GEN", "Genesis", 1, ["A.", "B."])
    normalize_version(thad_cfg)
    normalize_version(niv_cfg)
    align(load_normalized(thad_cfg), load_normalized(niv_cfg), thad_cfg, niv_cfg)

    for name in ("thadou_kuki_niv_parallel.jsonl", "thadou_kuki_niv_ml.jsonl"):
        rows = load_jsonl(ALIGNED_DIR / name)
        ids = [r["id"] for r in rows]
        assert len(ids) == len(set(ids)), f"duplicate ids in {name}"
    audit_refs = [(a["reference"], a["alignment_status"])
                  for a in load_jsonl(AUDIT_DIR / "alignment_audit.jsonl")]
    # one aligned record per pair, no repeated aligned entries
    aligned = [r for r, s in audit_refs if s == "aligned"]
    assert len(aligned) == len(set(aligned))


def test_duplicate_audit_records_carry_both_files(thad_cfg, niv_cfg, project):
    duplicates = [
        {"reference": "GEN.1.1", "version": "NIV",
         "kept_file": "data/raw/niv/GEN/001.json",
         "dropped_file": "data/raw/niv/GEN/002.json"},
        {"reference": "GEN.1.2", "version": "THADBSI",
         "kept_file": "data/raw/thad_bible/GEN/001.json",
         "dropped_file": "data/raw/thad_bible/GEN/007.json"},
    ]
    t = [{"reference": "GEN.1.1", "book_code": "GEN", "chapter": 1, "verse": "1",
          "text": "t1", "language_status": "verified", "url": "u", "version": "THADBSI"}]
    e = [{"reference": "GEN.1.1", "book_code": "GEN", "chapter": 1, "verse": "1",
          "text": "e1", "language_status": "verified", "url": "u", "version": "NIV"}]
    summary = align(t, e, thad_cfg, niv_cfg, duplicates=duplicates)
    assert summary["counts"]["duplicate_niv"] == 1
    assert summary["counts"]["duplicate_thadou"] == 1
    assert summary["counts"]["aligned"] == 1  # surviving copies still align

    dups = [a for a in load_jsonl(AUDIT_DIR / "alignment_audit.jsonl")
            if a["alignment_status"].startswith("duplicate")]
    assert len(dups) == 2
    by_status = {d["alignment_status"]: d for d in dups}
    assert by_status["duplicate_niv"]["reference"] == "GEN.1.1"
    assert by_status["duplicate_thadou"]["reference"] == "GEN.1.2"
    assert "002.json" in by_status["duplicate_niv"]["reason"]
    assert "007.json" in by_status["duplicate_thadou"]["reason"]
