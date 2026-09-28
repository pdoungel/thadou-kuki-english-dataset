"""Final output schemas: parallel JSONL, ML JSONL, audit JSONL, checksums."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest

from bible_scraper.models import (
    ALIGNED_DIR,
    AUDIT_DIR,
    NORMALIZED_DIR,
    REPORTS_DIR,
    SPLITS_DIR,
    VERSIONS,
)
from bible_scraper.alignment import load_jsonl
from bible_scraper.reporting import report
from bible_scraper.validation import verify
from tests.conftest import MINI_SPECS

PARALLEL_FIELDS = {
    "id", "reference", "book_code", "book_name_thadou_kuki", "book_name_english",
    "chapter", "verse", "thadou_kuki", "english", "source", "split",
    "identical_text_flag",
}
ML_FIELDS = {"id", "source", "target"}
AUDIT_FIELDS = {
    "reference", "book_code", "chapter", "verse", "thadou_status", "niv_status",
    "alignment_status", "thadou_text_hash", "niv_text_hash", "reason",
    "recorded_at",
}
ALLOWED_ALIGN_STATES = {
    "aligned", "missing_thadou", "missing_niv", "duplicate_thadou",
    "duplicate_niv", "language_uncertain", "extraction_error",
}
SPOT_REFS = {"GEN.1.1", "GEN.3.16", "PSA.23.1", "MAT.1.1", "JHN.3.16",
             "ROM.8.28", "REV.22.21"}


@pytest.fixture
def corpus(mini_corpus):
    """mini_corpus with the offline pipeline already run by the fixture."""
    return mini_corpus


def test_parallel_jsonl_schema(corpus):
    rows = load_jsonl(ALIGNED_DIR / "thadou_kuki_niv_parallel.jsonl")
    assert rows
    for row in rows:
        assert set(row) == PARALLEL_FIELDS, set(row) ^ PARALLEL_FIELDS
        assert row["id"] == row["reference"]
        assert row["reference"].count(".") == 2
        assert row["id"] == f"{row['book_code']}.{row['chapter']}.{row['verse']}"
        assert isinstance(row["chapter"], int) and row["chapter"] >= 1
        assert isinstance(row["verse"], int) and row["verse"] >= 1
        assert isinstance(row["thadou_kuki"], str) and row["thadou_kuki"].strip()
        assert isinstance(row["english"], str) and row["english"].strip()
        assert row["book_name_thadou_kuki"] and row["book_name_english"]
        assert row["split"] in {"train", "validation", "test"}
        assert isinstance(row["identical_text_flag"], bool)

        src = row["source"]
        assert set(src) == {"thadou_kuki", "english"}
        assert src["thadou_kuki"]["version_id"] == 1879
        assert src["thadou_kuki"]["version_code"] == "THADBSI"
        assert src["english"]["version_id"] == 111
        assert src["english"]["version_code"] == "NIV"
        assert src["thadou_kuki"]["url"] == \
            f"https://www.bible.com/bible/1879/{row['book_code']}.{row['chapter']}.THADBSI"
        assert src["english"]["url"] == \
            f"https://www.bible.com/bible/111/{row['book_code']}.{row['chapter']}.NIV"

    # ids unique, sorted canonically by the align stage
    ids = [r["id"] for r in rows]
    assert len(ids) == len(set(ids))
    total = sum(count for _c, _ch, count in MINI_SPECS)
    assert len(rows) == total


def test_parallel_contains_all_spot_checks(corpus):
    rows = load_jsonl(ALIGNED_DIR / "thadou_kuki_niv_parallel.jsonl")
    ids = {r["id"] for r in rows}
    assert SPOT_REFS <= ids
    by_id = {r["id"]: r for r in rows}
    for ref in SPOT_REFS:
        assert by_id[ref]["thadou_kuki"] and by_id[ref]["english"]
        assert by_id[ref]["source"]["thadou_kuki"]["url"]
        assert by_id[ref]["source"]["english"]["url"]


def test_texts_pass_through_verbatim(corpus):
    """Corpus text equals the raw capture text byte-for-byte (post-join)."""
    rows = {r["id"]: r for r in
            load_jsonl(ALIGNED_DIR / "thadou_kuki_niv_parallel.jsonl")}

    raw_thad = json.loads(
        (corpus.RAW_DIR / "thad_bible" / "GEN" / "001.json").read_text(encoding="utf-8")
    )
    for v in raw_thad["verses"]:
        assert rows[v["reference"]]["thadou_kuki"] == v["text"]

    raw_niv = json.loads(
        (corpus.RAW_DIR / "niv" / "GEN" / "001.json").read_text(encoding="utf-8")
    )
    for v in raw_niv["verses"]:
        assert rows[v["reference"]]["english"] == v["text"]


def test_ml_jsonl_schema(corpus):
    rows = load_jsonl(ALIGNED_DIR / "thadou_kuki_niv_ml.jsonl")
    parallel = load_jsonl(ALIGNED_DIR / "thadou_kuki_niv_parallel.jsonl")
    assert len(rows) == len(parallel)
    for m, p in zip(rows, parallel):
        assert set(m) == ML_FIELDS
        assert m["id"] == p["id"]
        assert m["source"] == p["thadou_kuki"]
        assert m["target"] == p["english"]
        assert m["source"].strip() and m["target"].strip()
    ids = [r["id"] for r in rows]
    assert len(ids) == len(set(ids))


def test_audit_jsonl_schema(corpus):
    rows = load_jsonl(AUDIT_DIR / "alignment_audit.jsonl")
    assert rows
    refs = set()
    for row in rows:
        assert set(row) == AUDIT_FIELDS, set(row) ^ AUDIT_FIELDS
        assert row["alignment_status"] in ALLOWED_ALIGN_STATES
        assert row["reference"].count(".") == 2
        if row["alignment_status"] == "aligned":
            refs.add(row["reference"])
            assert row["thadou_text_hash"] and row["niv_text_hash"]
            assert len(row["thadou_text_hash"]) == 64
            assert len(row["niv_text_hash"]) == 64
            assert row["thadou_status"] == "present" and row["niv_status"] == "present"
        else:
            assert row["reason"]  # every non-aligned state explains itself
    # audit's aligned set exactly equals the corpus
    corpus_ids = {r["id"] for r in
                  load_jsonl(ALIGNED_DIR / "thadou_kuki_niv_parallel.jsonl")}
    assert refs == corpus_ids


def test_audit_covers_every_reference_once(corpus):
    rows = load_jsonl(AUDIT_DIR / "alignment_audit.jsonl")
    aligned_refs = [r["reference"] for r in rows if r["alignment_status"] == "aligned"]
    assert len(aligned_refs) == len(set(aligned_refs))
    # every normalized reference appears in the audit
    norm_refs = set()
    for prefix in ("thadbsi", "niv"):
        for line in (NORMALIZED_DIR / f"{prefix}_verses.jsonl").read_text(
            encoding="utf-8"
        ).splitlines():
            if line.strip():
                norm_refs.add(json.loads(line)["reference"])
    audited = {r["reference"] for r in rows}
    assert norm_refs <= audited


def test_split_files_and_manifest(corpus):
    manifest = json.loads((SPLITS_DIR / "split_manifest.json").read_text(encoding="utf-8"))
    assert set(manifest) >= {"generated_at", "method", "buckets", "books",
                             "counts", "total_parallel_verses"}
    books = manifest["books"]
    assigned = [b for v in books.values() for b in v]
    assert len(assigned) == len(set(assigned))
    for split in ("train", "validation", "test"):
        assert split in books and split in manifest["counts"]
        rows = load_jsonl(SPLITS_DIR / f"{split}.jsonl")
        assert all(set(r) == PARALLEL_FIELDS for r in rows)
        assert len(rows) == manifest["counts"][split]["verses"]
    # partition: split rows = full corpus
    all_rows = load_jsonl(ALIGNED_DIR / "thadou_kuki_niv_parallel.jsonl")
    split_ids = [r["id"] for s in ("train", "validation", "test")
                 for r in load_jsonl(SPLITS_DIR / f"{s}.jsonl")]
    assert sorted(split_ids) == sorted(r["id"] for r in all_rows)


def test_report_outputs_and_checksums(corpus):
    result = report(VERSIONS["THADBSI"], VERSIONS["NIV"])

    assert result["verification_ok"] is True
    assert result["verification_complete"] is True

    for name in ("md", "json", "csv"):
        assert (corpus.root / result["paths"][name]).exists(), result["paths"][name]
    quality = json.loads((REPORTS_DIR / "quality_report.json").read_text(encoding="utf-8"))
    metrics = {m["metric"]: m["value"] for m in quality["metrics"]}
    total = sum(count for _c, _ch, count in MINI_SPECS)
    assert metrics["aligned_verse_pairs"] == total
    assert metrics["books_discovered_thadbsi"] == 66
    assert metrics["books_discovered_niv"] == 66
    assert metrics["missing_in_thadbsi"] == 0
    assert metrics["missing_in_niv"] == 0
    assert metrics["language_uncertain_verses"] == 0
    assert metrics["verification_complete"] == "true"
    assert sum(metrics[k] for k in ("train_verses", "validation_verses",
                                    "test_verses")) == total

    # CSV is a well-formed two-column table
    with (REPORTS_DIR / "quality_report.csv").open(encoding="utf-8") as fh:
        table = list(csv.reader(fh))
    assert table[0] == ["metric", "value"]
    assert ("aligned_verse_pairs", str(total)) in [(a, b) for a, b in table[1:]]
    assert len(table) == len(quality["metrics"]) + 1

    # markdown report exists and mentions the corpus hash
    md = (REPORTS_DIR / "quality_report.md").read_text(encoding="utf-8")
    assert "# Quality Report" in md
    assert str(total) in md

    # checksums: one line per raw chapter + every final JSONL, digests correct
    checksums_path = corpus.root / result["paths"]["checksums"]
    lines = [l for l in checksums_path.read_text(encoding="utf-8").splitlines()
             if l and not l.startswith("#")]
    raw_count = sum(1 for _v in ("thad_bible", "niv")
                    for _ in (corpus.RAW_DIR / _v).glob("*/*.json"))
    final_jsonl = [
        NORMALIZED_DIR / "thadbsi_verses.jsonl",
        NORMALIZED_DIR / "niv_verses.jsonl",
        AUDIT_DIR / "alignment_audit.jsonl",
        ALIGNED_DIR / "thadou_kuki_niv_parallel.jsonl",
        ALIGNED_DIR / "thadou_kuki_niv_ml.jsonl",
        SPLITS_DIR / "train.jsonl",
        SPLITS_DIR / "validation.jsonl",
        SPLITS_DIR / "test.jsonl",
    ]
    assert len(lines) == raw_count + len(final_jsonl)

    for line in lines:
        digest, relpath = line.split("  ", 1)
        assert len(digest) == 64
        target = corpus.root / relpath
        assert target.exists(), relpath
        actual = hashlib.sha256(target.read_bytes()).hexdigest()
        assert actual == digest, relpath

    # header documents provenance
    header = checksums_path.read_text(encoding="utf-8")
    assert "# scraper_version:" in header
    assert "# source_version_pages:" in header
    assert "bible.com/versions/1879" in header
    assert "bible.com/versions/111" in header


def test_source_manifest_written(corpus):
    report(VERSIONS["THADBSI"], VERSIONS["NIV"])
    manifest = (corpus.root / "SOURCE_MANIFEST.md").read_text(encoding="utf-8")
    assert "# Source Manifest" in manifest
    assert "https://www.bible.com/versions/1879" in manifest
    assert "https://www.bible.com/versions/111" in manifest
    assert "bible.com/robots.txt" in manifest or "robots.txt" in manifest
    assert "book_mapping.json" in manifest
    assert "LICENSE_NOTES.md" in manifest
    assert "no translation" in manifest or "No translation" in manifest


def test_verification_json_spot_checks_include_urls(corpus):
    verify(VERSIONS["THADBSI"], VERSIONS["NIV"])
    payload = json.loads((AUDIT_DIR / "verification.json").read_text(encoding="utf-8"))
    for spot in payload["spot_checks"]:
        assert set(spot) >= {"reference", "found", "thadou_kuki", "english",
                             "thadou_url", "niv_url"}
        assert spot["found"] is True
        assert "/bible/1879/" in spot["thadou_url"]
        assert "/bible/111/" in spot["niv_url"]
