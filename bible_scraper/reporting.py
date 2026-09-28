"""Reporting: quality report (md/json/csv), checksums, source manifest.

Everything in this module is offline and deterministic: it reads files the
pipeline already produced (manifests, raw captures, aligned outputs,
verification report) and never touches the network.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from . import __version__
from .models import (
    ALIGNED_DIR,
    AUDIT_DIR,
    MANIFESTS_DIR,
    NORMALIZED_DIR,
    RAW_DIR,
    REPORTS_DIR,
    ROOT,
    VersionConfig,
    atomic_write_json,
)
from .validation import SPOT_CHECKS, verify

log = logging.getLogger("bible_scraper.reporting")

QUALITY_MD = REPORTS_DIR / "quality_report.md"
QUALITY_JSON = REPORTS_DIR / "quality_report.json"
QUALITY_CSV = REPORTS_DIR / "quality_report.csv"
CHECKSUMS = REPORTS_DIR / "checksums.sha256"
SOURCE_MANIFEST = ROOT / "SOURCE_MANIFEST.md"

# Final JSONL outputs covered by reports/checksums.sha256 (raw chapter
# captures are hashed individually as well).
FINAL_JSONL = (
    NORMALIZED_DIR / "thadbsi_verses.jsonl",
    NORMALIZED_DIR / "niv_verses.jsonl",
    AUDIT_DIR / "alignment_audit.jsonl",
    ALIGNED_DIR / "thadou_kuki_niv_parallel.jsonl",
    ALIGNED_DIR / "thadou_kuki_niv_ml.jsonl",
    ALIGNED_DIR / "splits" / "train.jsonl",
    ALIGNED_DIR / "splits" / "validation.jsonl",
    ALIGNED_DIR / "splits" / "test.jsonl",
)


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def rel(path: Path) -> str:
    try:
        return str(Path(path).resolve().relative_to(ROOT.resolve()))
    except ValueError:
        return str(path)


# ---------------------------------------------------------------------------
# Checksums
# ---------------------------------------------------------------------------
def write_checksums(
    thadou_cfg: VersionConfig,
    niv_cfg: VersionConfig,
) -> dict:
    """SHA-256 for every raw chapter capture + every final JSONL output."""
    entries: List[str] = []
    raw_files: List[Path] = []
    for cfg in (thadou_cfg, niv_cfg):
        root = RAW_DIR / cfg.raw_dirname
        if root.is_dir():
            raw_files.extend(
                p for p in sorted(root.glob("*/*.json"))
                if not p.name.startswith(".") and "._" not in p.name
            )
    missing_final = [str(rel(p)) for p in FINAL_JSONL if not p.exists()]

    digests: Dict[str, str] = {}
    for p in raw_files:
        digests[rel(p)] = sha256_file(p)
    for p in FINAL_JSONL:
        if p.exists():
            digests[rel(p)] = sha256_file(p)

    # stable order: raw first (sorted), then final JSONL in declared order
    for p in raw_files:
        entries.append(digests[rel(p)] + "  " + rel(p))
    for p in FINAL_JSONL:
        if p.exists():
            entries.append(digests[rel(p)] + "  " + rel(p))

    header = [
        "# SHA-256 checksums for the Thadou-Kuki <-> NIV parallel corpus",
        f"# generated_at: {utcnow()}",
        f"# scraper_version: {__version__}",
        f"# source_version_pages: {thadou_cfg.url} ; {niv_cfg.url}",
        f"# chapter_url_templates: {thadou_cfg.chapter_url('GEN', 1)} ; {niv_cfg.chapter_url('GEN', 1)}",
        f"# raw_chapter_files: {len(raw_files)}",
        f"# final_jsonl_files: {sum(1 for p in FINAL_JSONL if p.exists())}",
    ]
    if missing_final:
        header.append("# missing_final_jsonl: " + " ; ".join(missing_final))
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    tmp = CHECKSUMS.with_name(CHECKSUMS.name + ".tmp")
    tmp.write_text("\n".join(header + entries) + "\n", encoding="utf-8")
    tmp.replace(CHECKSUMS)

    out = {
        "path": rel(CHECKSUMS),
        "raw_chapter_files": len(raw_files),
        "final_jsonl_files": sum(1 for p in FINAL_JSONL if p.exists()),
        "missing_final_jsonl": missing_final,
        "checksums_sha256": sha256_file(CHECKSUMS),
        "corpus_sha256": digests.get(
            rel(ALIGNED_DIR / "thadou_kuki_niv_parallel.jsonl")
        ),
        "digests": digests,
    }
    log.info(
        "checksums written files=%d raw=%d final=%d",
        len(entries), len(raw_files), out["final_jsonl_files"],
    )
    return out


# ---------------------------------------------------------------------------
# Quality report
# ---------------------------------------------------------------------------
def _read_json(path: Path) -> Optional[dict]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _manifest_book_count(prefix: str) -> int:
    data = _read_json(MANIFESTS_DIR / f"{prefix}_books.json")
    return int(data.get("book_count", 0)) if data else 0


def _count_lines(path: Path) -> int:
    if not path.exists():
        return 0
    n = 0
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                n += 1
    return n


def build_quality_report(
    verification: dict,
    checksum_info: dict,
    thadou_cfg: VersionConfig,
    niv_cfg: VersionConfig,
) -> dict:
    """Assemble every required QC metric into one payload."""
    counts = dict(verification.get("counts") or {})
    split_manifest = _read_json(ALIGNED_DIR / "splits" / "split_manifest.json") or {}
    split_counts = split_manifest.get("counts") or {}

    metrics: List[dict] = [
        {"metric": "books_discovered_thadbsi", "value": _manifest_book_count(thadou_cfg.manifest_prefix)},
        {"metric": "books_discovered_niv", "value": _manifest_book_count(niv_cfg.manifest_prefix)},
        {"metric": "chapters_discovered_thadbsi", "value": (counts.get("discovered_chapters") or {}).get(thadou_cfg.key, 0)},
        {"metric": "chapters_discovered_niv", "value": (counts.get("discovered_chapters") or {}).get(niv_cfg.key, 0)},
        {"metric": "chapters_extracted_thadbsi", "value": (counts.get("extracted_chapters") or {}).get(thadou_cfg.key, 0)},
        {"metric": "chapters_extracted_niv", "value": (counts.get("extracted_chapters") or {}).get(niv_cfg.key, 0)},
        {"metric": "verses_normalized_thadbsi", "value": (counts.get("normalized_verses") or {}).get(thadou_cfg.key, 0)},
        {"metric": "verses_normalized_niv", "value": (counts.get("normalized_verses") or {}).get(niv_cfg.key, 0)},
        {"metric": "aligned_verse_pairs", "value": counts.get("aligned_pairs", 0)},
        {"metric": "ml_pairs", "value": counts.get("ml_pairs", 0)},
        {"metric": "missing_in_thadbsi", "value": counts.get("missing_thadou", 0)},
        {"metric": "missing_in_niv", "value": counts.get("missing_niv", 0)},
        {"metric": "duplicate_thadbsi", "value": counts.get("duplicate_thadou", 0)},
        {"metric": "duplicate_niv", "value": counts.get("duplicate_niv", 0)},
        {"metric": "language_uncertain_verses", "value": counts.get("language_uncertain", 0)},
        {"metric": "language_uncertain_chapters", "value": counts.get("uncertain_chapters", 0)},
        {"metric": "extraction_error_verses", "value": counts.get("extraction_error", 0)},
        {"metric": "extraction_failures_chapters", "value": sum(len(v) for v in (counts.get("failed_chapters") or {}).values())},
        {"metric": "unreadable_raw_files", "value": counts.get("failed_raw_files", 0)},
        {"metric": "empty_verses_in_raw", "value": counts.get("empty_verses_in_raw", 0)},
        {"metric": "audit_records", "value": counts.get("audit_records", 0)},
        {"metric": "train_verses", "value": (split_counts.get("train") or {}).get("verses", 0)},
        {"metric": "train_books", "value": (split_counts.get("train") or {}).get("books", 0)},
        {"metric": "validation_verses", "value": (split_counts.get("validation") or {}).get("verses", 0)},
        {"metric": "validation_books", "value": (split_counts.get("validation") or {}).get("books", 0)},
        {"metric": "test_verses", "value": (split_counts.get("test") or {}).get("verses", 0)},
        {"metric": "test_books", "value": (split_counts.get("test") or {}).get("books", 0)},
        {"metric": "checksummed_files", "value": checksum_info.get("raw_chapter_files", 0) + checksum_info.get("final_jsonl_files", 0)},
        {"metric": "verification_ok", "value": str(verification.get("ok")).lower()},
        {"metric": "verification_complete", "value": str(verification.get("complete")).lower()},
    ]

    payload = {
        "generated_at": utcnow(),
        "scraper_version": __version__,
        "sources": {
            "thadou_kuki": {
                "version_id": thadou_cfg.version_id,
                "version_code": thadou_cfg.version_code,
                "version_name": thadou_cfg.version_name,
                "url": thadou_cfg.url,
                "publisher": thadou_cfg.publisher,
                "language": thadou_cfg.language,
            },
            "english": {
                "version_id": niv_cfg.version_id,
                "version_code": niv_cfg.version_code,
                "version_name": niv_cfg.version_name,
                "url": niv_cfg.url,
                "publisher": niv_cfg.publisher,
                "language": niv_cfg.language,
            },
        },
        "metrics": metrics,
        "verification": {
            "ok": verification.get("ok"),
            "complete": verification.get("complete"),
            "checks": {
                k: {"ok": v.get("ok"), "detail": v.get("detail")}
                for k, v in (verification.get("checks") or {}).items()
            },
            "problems": verification.get("problems") or [],
        },
        "uncertain_chapters": verification.get("uncertain_chapters") or [],
        "spot_checks": verification.get("spot_checks") or [],
        "split_manifest": {
            "method": split_manifest.get("method"),
            "buckets": split_manifest.get("buckets"),
            "counts": split_counts,
        },
        "checksums": {
            "file": checksum_info.get("path"),
            "raw_chapter_files": checksum_info.get("raw_chapter_files"),
            "final_jsonl_files": checksum_info.get("final_jsonl_files"),
            "checksums_sha256": checksum_info.get("checksums_sha256"),
            "corpus_sha256": checksum_info.get("corpus_sha256"),
            "missing_final_jsonl": checksum_info.get("missing_final_jsonl"),
        },
    }
    return payload


def render_quality_md(payload: dict) -> str:
    m = {row["metric"]: row["value"] for row in payload["metrics"]}
    src = payload["sources"]
    lines: List[str] = []
    lines.append("# Quality Report — Thadou-Kuki (THADBSI) ↔ English (NIV) Parallel Corpus")
    lines.append("")
    lines.append(f"- Generated: {payload['generated_at']}")
    lines.append(f"- Scraper version: `{payload['scraper_version']}`")
    lines.append(
        f"- THADBSI: version {src['thadou_kuki']['version_id']} / "
        f"`{src['thadou_kuki']['version_code']}` — {src['thadou_kuki']['version_name']} "
        f"({src['thadou_kuki']['publisher']}) — {src['thadou_kuki']['url']}"
    )
    lines.append(
        f"- NIV: version {src['english']['version_id']} / `{src['english']['version_code']}` — "
        f"{src['english']['version_name']} ({src['english']['publisher']}) — {src['english']['url']}"
    )
    lines.append(
        f"- Verification: **{'OK' if payload['verification']['ok'] else 'FAIL'}**, "
        f"complete: **{'YES' if payload['verification']['complete'] else 'NO'}**"
    )
    lines.append("")
    lines.append("## Counts")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("| --- | ---: |")
    for row in payload["metrics"]:
        lines.append(f"| {row['metric']} | {row['value']} |")
    lines.append("")
    lines.append("## Alignment states (from data/audit/alignment_audit.jsonl)")
    lines.append("")
    lines.append("| State | Count |")
    lines.append("| --- | ---: |")
    for state in (
        "aligned", "missing_thadou", "missing_niv", "duplicate_thadou",
        "duplicate_niv", "language_uncertain", "extraction_error",
    ):
        val = next(
            (r["value"] for r in payload["metrics"]
             if r["metric"] == _state_metric(state)), None
        )
        if val is None:
            val = 0
        lines.append(f"| {state} | {val} |")
    lines.append("")
    lines.append("## Splits (whole books, deterministic)")
    lines.append("")
    sm = payload.get("split_manifest") or {}
    lines.append(f"- Method: {sm.get('method')}")
    lines.append(f"- Buckets: {sm.get('buckets')}")
    lines.append("")
    lines.append("| Split | Verses | Books |")
    lines.append("| --- | ---: | ---: |")
    for name in ("train", "validation", "test"):
        c = (sm.get("counts") or {}).get(name) or {}
        lines.append(f"| {name} | {c.get('verses', 0)} | {c.get('books', 0)} |")
    lines.append("")
    lines.append("## Verification checks")
    lines.append("")
    lines.append("| Check | Result |")
    lines.append("| --- | --- |")
    for name, chk in payload["verification"]["checks"].items():
        lines.append(f"| {name} | {'PASS' if chk['ok'] else 'FAIL'} |")
    problems = payload["verification"].get("problems") or []
    if problems:
        lines.append("")
        lines.append("### Problems")
        lines.append("")
        for p in problems:
            lines.append(f"- {p}")
    uncertain = payload.get("uncertain_chapters") or []
    lines.append("")
    lines.append(f"## Language-uncertain chapters: {len(uncertain)}")
    lines.append("")
    if uncertain:
        lines.append("| Version | Book | Chapter | Status |")
        lines.append("| --- | --- | ---: | --- |")
        for u in uncertain:
            lines.append(f"| {u.get('version')} | {u.get('book')} | {u.get('chapter')} | {u.get('status')} |")
    lines.append("")
    lines.append("## Manual spot checks")
    lines.append("")
    lines.append("| Reference | Thadou-Kuki (THADBSI) | English (NIV) |")
    lines.append("| --- | --- | --- |")
    for s in payload.get("spot_checks") or []:
        if s.get("found"):
            lines.append(
                f"| {s['reference']} | {_md_cell(s['thadou_kuki'])} | {_md_cell(s['english'])} |"
            )
        else:
            lines.append(f"| {s['reference']} | NOT ALIGNED | NOT ALIGNED |")
    lines.append("")
    if payload.get("spot_checks"):
        lines.append("Spot-check source URLs are in `data/audit/verification.json`.")
        lines.append("")
    lines.append("## Checksums")
    lines.append("")
    ck = payload.get("checksums") or {}
    lines.append(f"- Checksums file: `{ck.get('file')}`")
    lines.append(f"- Raw chapter files hashed: {ck.get('raw_chapter_files')}")
    lines.append(f"- Final JSONL files hashed: {ck.get('final_jsonl_files')}")
    lines.append(f"- SHA-256 of checksums file: `{ck.get('checksums_sha256')}`")
    lines.append(f"- SHA-256 of `thadou_kuki_niv_parallel.jsonl`: `{ck.get('corpus_sha256')}`")
    if ck.get("missing_final_jsonl"):
        lines.append(f"- Missing outputs: {', '.join(ck['missing_final_jsonl'])}")
    lines.append("")
    return "\n".join(lines)


def _state_metric(state: str) -> str:
    return {
        "aligned": "aligned_verse_pairs",
        "missing_thadou": "missing_in_thadbsi",
        "missing_niv": "missing_in_niv",
        "duplicate_thadou": "duplicate_thadbsi",
        "duplicate_niv": "duplicate_niv",
        "language_uncertain": "language_uncertain_verses",
        "extraction_error": "extraction_error_verses",
    }[state]


def _md_cell(text: Optional[str]) -> str:
    if not text:
        return ""
    return str(text).replace("|", "\\|").replace("\n", " ")


def write_quality_report(payload: dict) -> Dict[str, str]:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    atomic_write_json(QUALITY_JSON, payload)

    md_tmp = QUALITY_MD.with_name(QUALITY_MD.name + ".tmp")
    md_tmp.write_text(render_quality_md(payload), encoding="utf-8")
    md_tmp.replace(QUALITY_MD)

    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(["metric", "value"])
    for row in payload["metrics"]:
        writer.writerow([row["metric"], row["value"]])
    csv_tmp = QUALITY_CSV.with_name(QUALITY_CSV.name + ".tmp")
    csv_tmp.write_text(buf.getvalue(), encoding="utf-8")
    csv_tmp.replace(QUALITY_CSV)

    log.info("quality report written md/json/csv")
    return {"md": rel(QUALITY_MD), "json": rel(QUALITY_JSON), "csv": rel(QUALITY_CSV)}


# ---------------------------------------------------------------------------
# SOURCE_MANIFEST.md
# ---------------------------------------------------------------------------
def write_source_manifest(
    verification: dict,
    checksum_info: dict,
    thadou_cfg: VersionConfig,
    niv_cfg: VersionConfig,
) -> str:
    counts = verification.get("counts") or {}
    discovered = counts.get("discovered_chapters") or {}
    extracted = counts.get("extracted_chapters") or {}
    normalized = counts.get("normalized_verses") or {}
    retrieved = _retrieval_range()

    lines: List[str] = []
    lines.append("# Source Manifest — Thadou-Kuki (THADBSI) ↔ English (NIV) Parallel Corpus")
    lines.append("")
    lines.append(f"Generated {utcnow()} by `bible_scraper` {__version__}.")
    lines.append("")
    lines.append("## What this corpus is")
    lines.append("")
    lines.append(
        "A verse-aligned parallel corpus pairing the Thadou-Kuki Bible "
        f"(**{thadou_cfg.version_name}**, version id `{thadou_cfg.version_id}`, "
        f"code `{thadou_cfg.version_code}`, publisher {thadou_cfg.publisher}) with the "
        f"English **{niv_cfg.version_name}** (version id `{niv_cfg.version_id}`, "
        f"code `{niv_cfg.version_code}`, publisher {niv_cfg.publisher}), both read from "
        "bible.com by automated browser."
    )
    lines.append("")
    lines.append("## Sources")
    lines.append("")
    lines.append("| Side | Version id | Code | Language | Version page |")
    lines.append("| --- | ---: | --- | --- | --- |")
    lines.append(
        f"| Thadou-Kuki | {thadou_cfg.version_id} | `{thadou_cfg.version_code}` | "
        f"{thadou_cfg.language} (`{thadou_cfg.language_code}`) | {thadou_cfg.url} |"
    )
    lines.append(
        f"| English | {niv_cfg.version_id} | `{niv_cfg.version_code}` | "
        f"{niv_cfg.language} (`{niv_cfg.language_code}`) | {niv_cfg.url} |"
    )
    lines.append("")
    lines.append("Chapter URLs follow `https://www.bible.com/bible/{versionId}/{BOOK}.{CHAPTER}.{CODE}`,")
    lines.append(f"e.g. {thadou_cfg.chapter_url('GEN', 1)} and {niv_cfg.chapter_url('GEN', 1)}.")
    lines.append("")
    lines.append("## How it was obtained")
    lines.append("")
    lines.append(
        "- Playwright + Chromium, one chapter page at a time, headed by default for "
        "development (`--headless` for production runs)."
    )
    lines.append(
        "- Polite delays between requests (default `MIN_DELAY=0.5s`, `MAX_DELAY=2.0s`) and "
        "retries with exponential backoff (default `MAX_RETRIES=3`)."
    )
    lines.append(
        "- `robots.txt` on bible.com allows `/bible/*`; notes and search paths are disallowed "
        "and were not accessed."
    )
    lines.append(
        "- No login, CAPTCHA, paywall or access control was bypassed; pages that could not be "
        "read normally are recorded as acquisition failures."
    )
    lines.append(
        "- Text is copied exactly as published: only technical whitespace normalization "
        "(runs of whitespace → single space, trim). No translation, paraphrase, spelling, "
        "punctuation or segmentation changes."
    )
    lines.append(
        "- Headings, verse numbers, footnotes, cross-references and other UI chrome are "
        "excluded from verse text."
    )
    lines.append("")
    lines.append("## Discovery and identity")
    lines.append("")
    lines.append(
        "- Book identity comes from the canonical codes inside Bible.com URLs, never from "
        "display names (THADBSI shows localized names such as `Semtilbu`, `Potdohbu`, "
        "`Thempudan`, `Minbu`, `Thuphon`)."
    )
    lines.append(
        "- Persistent mapping: `data/manifests/book_mapping.json` "
        f"({_manifest_book_count(thadou_cfg.manifest_prefix)} THADBSI books × "
        f"{_manifest_book_count(niv_cfg.manifest_prefix)} NIV books, keyed by canonical code)."
    )
    lines.append("- Alignment is strictly by canonical reference (`GEN.1.1`); never by position or text similarity.")
    lines.append(f"- Chapter manifests: `data/manifests/{thadou_cfg.manifest_prefix}_chapters.jsonl` "
                 f"and `data/manifests/{niv_cfg.manifest_prefix}_chapters.jsonl`.")
    lines.append("")
    lines.append("## Retrieval summary")
    lines.append("")
    lines.append("| Item | THADBSI | NIV |")
    lines.append("| --- | ---: | ---: |")
    lines.append(
        f"| Chapters discovered | {discovered.get(thadou_cfg.key, 0)} | {discovered.get(niv_cfg.key, 0)} |"
    )
    lines.append(
        f"| Chapters captured | {extracted.get(thadou_cfg.key, 0)} | {extracted.get(niv_cfg.key, 0)} |"
    )
    lines.append(
        f"| Verses normalized | {normalized.get(thadou_cfg.key, 0)} | {normalized.get(niv_cfg.key, 0)} |"
    )
    lines.append("")
    lines.append(f"- Retrieval time range (raw captures): {retrieved}")
    lines.append(f"- Raw captures: `data/raw/{thadou_cfg.raw_dirname}/`, `data/raw/{niv_cfg.raw_dirname}/`")
    lines.append("")
    lines.append("## Outputs")
    lines.append("")
    lines.append("| File | Rows / notes | SHA-256 |")
    lines.append("| --- | --- | --- |")
    for path in (
        ALIGNED_DIR / "thadou_kuki_niv_parallel.jsonl",
        ALIGNED_DIR / "thadou_kuki_niv_ml.jsonl",
        AUDIT_DIR / "alignment_audit.jsonl",
    ):
        if path.exists():
            lines.append(
                f"| `{rel(path)}` | {_count_lines(path)} rows | "
                f"`{checksum_info.get('digests', {}).get(rel(path))}` |"
            )
    lines.append(
        f"| `{checksum_info.get('path')}` | {checksum_info.get('raw_chapter_files', 0)} raw + "
        f"{checksum_info.get('final_jsonl_files', 0)} final files | "
        f"`{checksum_info.get('checksums_sha256')}` |"
    )
    lines.append("")
    lines.append("## Integrity status")
    lines.append("")
    lines.append(
        f"- Verification: **{'OK' if verification.get('ok') else 'FAIL'}**; "
        f"complete: **{'YES' if verification.get('complete') else 'NO'}**"
    )
    lines.append(
        f"- Language-uncertain chapters withheld from the verified corpus: "
        f"{len(verification.get('uncertain_chapters') or [])}"
    )
    lines.append(
        f"- Missing-in-NIV verses: {counts.get('missing_niv', 0)}; "
        f"missing-in-THADBSI verses: {counts.get('missing_thadou', 0)}; "
        f"extraction errors: {counts.get('extraction_error', 0)}"
    )
    lines.append(
        "- Re-run any time: `python -m bible_scraper verify` then `python -m bible_scraper report`."
    )
    lines.append("")
    lines.append("## Provenance notes")
    lines.append("")
    lines.append(
        f"- Thadou-Kuki language provenance: bible.com language page `https://www.bible.com/languages/tcz` "
        f"(\"The Bible in Thado Chin - Thadou Kuki\") links `/versions/{thadou_cfg.version_id}-…` "
        f"with `THADBSI` as the abbreviation."
    )
    lines.append(
        "- Accessibility of the text does **not** establish permission to redistribute it; "
        "see `LICENSE_NOTES.md`."
    )
    lines.append("")

    tmp = SOURCE_MANIFEST.with_name(SOURCE_MANIFEST.name + ".tmp")
    tmp.write_text("\n".join(lines), encoding="utf-8")
    tmp.replace(SOURCE_MANIFEST)
    log.info("source manifest written %s", rel(SOURCE_MANIFEST))
    return rel(SOURCE_MANIFEST)


def _retrieval_range() -> str:
    stamps: List[str] = []
    for sub in ("thad_bible", "niv"):
        root = RAW_DIR / sub
        if not root.is_dir():
            continue
        for p in sorted(root.glob("*/*.json")):
            if p.name.startswith("."):
                continue  # AppleDouble/AppleResourceFork sidecar, not a capture
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, ValueError):  # incl. JSONDecodeError/UnicodeDecodeError
                continue
            ts = data.get("retrieved_at")
            if ts:
                stamps.append(ts)
    if not stamps:
        return "n/a"
    return f"{min(stamps)} → {max(stamps)} (UTC)"


# ---------------------------------------------------------------------------
# report command
# ---------------------------------------------------------------------------
def report(
    thadou_cfg: VersionConfig,
    niv_cfg: VersionConfig,
    verification: Optional[dict] = None,
) -> dict:
    """Produce checksums, quality report and source manifest (offline)."""
    if verification is None:
        verification = verify(thadou_cfg, niv_cfg)
    checksum_info = write_checksums(thadou_cfg, niv_cfg)
    payload = build_quality_report(verification, checksum_info, thadou_cfg, niv_cfg)
    paths = write_quality_report(payload)
    paths["source_manifest"] = write_source_manifest(
        verification, checksum_info, thadou_cfg, niv_cfg
    )
    paths["checksums"] = checksum_info["path"]
    return {
        "paths": paths,
        "metrics": {row["metric"]: row["value"] for row in payload["metrics"]},
        "verification_ok": verification.get("ok"),
        "verification_complete": verification.get("complete"),
        "checksums": checksum_info,
    }
