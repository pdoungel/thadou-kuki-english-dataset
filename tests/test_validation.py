"""Validation: chapter-level language verification and corpus verification."""

from __future__ import annotations

import json

import pytest

from bible_scraper.alignment import align, load_jsonl
from bible_scraper.models import (
    AUDIT_DIR,
    MANIFESTS_DIR,
    NORMALIZED_DIR,
    VERSIONS,
    atomic_write_json,
)
from bible_scraper.normalization import load_normalized, normalize_version
from bible_scraper.validation import SPOT_CHECKS, verify
from tests.conftest import (
    MINI_SPECS,
    THADBSI_VERSE_TEMPLATE,
    NIV_VERSE_TEMPLATE,
    mini_book_names,
    write_mini_discovery,
    write_mini_raw_corpus,
    write_raw_chapter,
)


def run_offline_pipeline():
    """normalize -> align for the already-written mini corpus."""
    thad, niv = VERSIONS["THADBSI"], VERSIONS["NIV"]
    normalize_version(thad)
    normalize_version(niv)
    return align(load_normalized(thad), load_normalized(niv), thad, niv)


def test_verify_passes_on_complete_mini_corpus(mini_corpus):
    result = verify(VERSIONS["THADBSI"], VERSIONS["NIV"])

    assert result["ok"] is True
    assert result["complete"] is True
    assert result["problems"] == []
    assert all(chk["ok"] for chk in result["checks"].values()), {
        k: v["detail"] for k, v in result["checks"].items() if not v["ok"]
    }
    # every spot-check reference is present with both texts and both URLs
    for spot in result["spot_checks"]:
        assert spot["found"], spot["reference"]
        assert spot["thadou_kuki"]
        assert spot["english"]
        assert "/bible/1879/" in spot["thadou_url"]   # THADBSI version id
        assert spot["thadou_url"].endswith(".THADBSI")
        assert "/bible/111/" in spot["niv_url"]       # NIV version id
        assert spot["niv_url"].endswith(".NIV")


def test_verify_counts_reconcile(mini_corpus):
    result = verify(VERSIONS["THADBSI"], VERSIONS["NIV"])
    counts = result["counts"]

    total_expected = sum(count for _c, _ch, count in MINI_SPECS)
    assert counts["aligned_pairs"] == total_expected
    assert counts["ml_pairs"] == total_expected
    assert counts["missing_thadou"] == 0
    assert counts["missing_niv"] == 0
    assert counts["language_uncertain"] == 0
    assert counts["extraction_error"] == 0
    assert counts["uncertain_chapters"] == 0
    assert counts["discovered_chapters"] == {"THADBSI": 7, "NIV": 7}
    assert counts["extracted_chapters"] == {"THADBSI": 7, "NIV": 7}
    # audit covers every reference exactly once as aligned
    assert counts["audit_records"] == total_expected


def test_verify_fails_when_chapter_is_unverifiable(mini_corpus):
    """A LANGUAGE_UNCERTAIN chapter blocks completion and never enters corpus."""
    thad = VERSIONS["THADBSI"]
    write_raw_chapter(thad, "GEN", mini_book_names("THADBSI")["GEN"], 1,
                      [THADBSI_VERSE_TEMPLATE.format(ch=1, i=i) for i in range(1, 4)],
                      language_status="LANGUAGE_UNCERTAIN",
                      failing=["english_stopword_ratio_out_of_range"])
    run_offline_pipeline()
    result = verify(thad, VERSIONS["NIV"])

    # structure stays intact: schema/audit/split checks still pass
    for name in ("parallel_schema", "ml_schema", "no_duplicate_ids",
                 "audit_reconciles", "split_whole_books",
                 "uncertain_excluded_from_corpus", "normalized_deduplicated",
                 "raw_captures"):
        assert result["checks"][name]["ok"], name
    # withheld GEN.1.1 is a spot-check reference, so overall verification fails
    assert result["checks"]["spot_checks"]["ok"] is False
    assert result["ok"] is False
    assert result["complete"] is False     # never claimed complete
    assert result["problems"]              # never silently claimed complete
    assert len(result["uncertain_chapters"]) == 1
    assert result["uncertain_chapters"][0]["status"] == "LANGUAGE_UNCERTAIN"
    assert result["counts"]["language_uncertain"] == 3  # GEN.1.1-1.3 withheld

    # withheld verses are absent from the corpus, present in the audit
    from bible_scraper.models import ALIGNED_DIR

    refs = {r["reference"] for r in load_jsonl(ALIGNED_DIR / "thadou_kuki_niv_parallel.jsonl")}
    assert not any(r.startswith("GEN.1.") for r in refs)
    audit = {a["reference"]: a["alignment_status"]
             for a in load_jsonl(AUDIT_DIR / "alignment_audit.jsonl")}
    assert audit["GEN.1.1"] == "language_uncertain"


def test_verify_detects_missing_chapter_capture(mini_corpus):
    """A chapter in the manifest with no raw capture = acquisition failure."""
    from bible_scraper.models import RAW_DIR

    path = RAW_DIR / "niv" / "REV" / "022.json"
    path.unlink()
    run_offline_pipeline()
    result = verify(VERSIONS["THADBSI"], VERSIONS["NIV"])

    assert result["complete"] is False
    assert result["checks"]["raw_captures"]["ok"] is False
    assert "REV.22" in result["counts"]["failed_chapters"]["NIV"]
    assert result["checks"]["audit_reconciles"]["ok"] is True
    # every NIV-only reference of REV.22 is audited as missing, not invented
    audit = {a["reference"]: a["alignment_status"]
             for a in load_jsonl(AUDIT_DIR / "alignment_audit.jsonl")}
    assert audit["REV.22.21"] == "missing_niv"


def test_verify_detects_duplicate_ids(mini_corpus):
    from bible_scraper.models import ALIGNED_DIR

    run_offline_pipeline()
    path = ALIGNED_DIR / "thadou_kuki_niv_parallel.jsonl"
    rows = path.read_text(encoding="utf-8").splitlines()
    path.write_text(rows[0] + "\n" + "\n".join(rows) + "\n", encoding="utf-8")

    result = verify(VERSIONS["THADBSI"], VERSIONS["NIV"])
    assert result["checks"]["no_duplicate_ids"]["ok"] is False
    assert result["checks"]["parallel_schema"]["ok"] is True  # rows themselves fine
    assert result["ok"] is False


def test_verify_detects_tampered_row(mini_corpus):
    from bible_scraper.models import ALIGNED_DIR

    run_offline_pipeline()
    path = ALIGNED_DIR / "thadou_kuki_niv_parallel.jsonl"
    rows = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()]
    rows[0]["english"] = "   "  # emptied text
    with path.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    result = verify(VERSIONS["THADBSI"], VERSIONS["NIV"])
    assert result["checks"]["parallel_schema"]["ok"] is False
    assert result["ok"] is False


def test_verify_detects_wrong_source_url(mini_corpus):
    from bible_scraper.models import ALIGNED_DIR

    run_offline_pipeline()
    path = ALIGNED_DIR / "thadou_kuki_niv_parallel.jsonl"
    rows = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()]
    rows[0]["source"]["thadou_kuki"]["url"] = ""
    with path.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    result = verify(VERSIONS["THADBSI"], VERSIONS["NIV"])
    assert result["checks"]["parallel_schema"]["ok"] is False
    assert any("missing_source_url" in str(e)
               for e in result["checks"]["parallel_schema"]["detail"]["errors"])


def test_verify_reports_spot_check_table(mini_corpus):
    run_offline_pipeline()
    result = verify(VERSIONS["THADBSI"], VERSIONS["NIV"])
    assert [s["reference"] for s in result["spot_checks"]] == SPOT_CHECKS
    assert result["checks"]["spot_checks"]["ok"] is True


def test_verify_writes_verification_json(mini_corpus):
    run_offline_pipeline()
    verify(VERSIONS["THADBSI"], VERSIONS["NIV"])
    path = AUDIT_DIR / "verification.json"
    assert path.exists()
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert set(payload) >= {"generated_at", "ok", "complete", "checks", "counts",
                            "uncertain_chapters", "spot_checks", "problems"}
