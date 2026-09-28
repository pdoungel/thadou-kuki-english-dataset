"""Corpus verification: schema, provenance, language status, spot checks.

``verify`` re-checks everything the pipeline claimed:

- manifests, raw captures, normalized files, aligned outputs all exist and parse;
- every aligned row carries both texts, canonical reference, book names, and
  both source URLs/versions;
- no duplicate canonical IDs in the verified corpus;
- per-version verse/reference counts reconcile with the audit log;
- language verification status of every chapter is re-asserted from raw
  captures (a chapter that cannot be confidently verified must not be silently
  present as verified);
- the required manual spot-check references are reported with both texts.

Nothing here fetches the network; it only reads files produced by the
pipeline, so it is deterministic and safe to re-run.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from .alignment import load_jsonl
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
from .normalization import parse_reference, raw_chapter_paths

log = logging.getLogger("bible_scraper.validation")

SPOT_CHECKS = ["GEN.1.1", "GEN.3.16", "PSA.23.1", "MAT.1.1", "JHN.3.16", "ROM.8.28", "REV.22.21"]

PARALLEL_REQUIRED_FIELDS = (
    "id", "reference", "book_code", "book_name_thadou_kuki", "book_name_english",
    "chapter", "verse", "thadou_kuki", "english", "source",
)
ML_REQUIRED_FIELDS = ("id", "source", "target")


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def verify(
    thadou_cfg: VersionConfig,
    niv_cfg: VersionConfig,
    require_complete: bool = True,
) -> dict:
    """Run every verification check. Returns a structured report dict."""
    checks: Dict[str, dict] = {}
    problems: List[str] = []

    # ---- 1. manifests ----------------------------------------------------
    manifest_files = {
        cfg.key: {
            "books": MANIFESTS_DIR / f"{cfg.manifest_prefix}_books.json",
            "chapters": MANIFESTS_DIR / f"{cfg.manifest_prefix}_chapters.jsonl",
        }
        for cfg in (thadou_cfg, niv_cfg)
    }
    mapping_path = MANIFESTS_DIR / "book_mapping.json"
    manifest_ok = mapping_path.exists()
    chapter_totals: Dict[str, int] = {}
    for key, files in manifest_files.items():
        ok = files["books"].exists() and files["chapters"].exists()
        total = 0
        if ok:
            with files["chapters"].open(encoding="utf-8") as fh:
                for line in fh:
                    if line.strip():
                        total += 1
        chapter_totals[key] = total
        manifest_ok = manifest_ok and ok
        checks[f"manifests_{key}"] = {
            "ok": ok,
            "detail": f"chapters={total}" if ok else "missing book/chapter manifest",
        }
    checks["book_mapping"] = {"ok": manifest_ok, "detail": str(mapping_path)}

    # ---- 2. raw captures -------------------------------------------------
    raw_counts: Dict[str, dict] = {}
    uncertain_chapters: List[dict] = []
    empty_raw: List[dict] = []
    raw_keys: Dict[str, set] = {}
    manifest_keys: Dict[str, set] = {}
    for cfg in (thadou_cfg, niv_cfg):
        # keys declared in the manifest
        mpath = MANIFESTS_DIR / f"{cfg.manifest_prefix}_chapters.jsonl"
        mkeys = set()
        if mpath.exists():
            with mpath.open(encoding="utf-8") as fh:
                for line in fh:
                    if line.strip():
                        rec = json.loads(line)
                        mkeys.add(f"{rec['book_code']}.{rec['chapter']}")
        manifest_keys[cfg.key] = mkeys

        paths = raw_chapter_paths(cfg)
        verse_total = 0
        bad = []
        keys = set()
        for p in paths:
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                bad.append({"file": str(p), "error": str(exc)})
                continue
            keys.add(f"{data.get('book_code')}.{data.get('chapter')}")
            lang = data.get("language_verification") or {}
            if lang.get("status") != "verified":
                uncertain_chapters.append(
                    {
                        "version": cfg.key,
                        "book": data.get("book_code"),
                        "chapter": data.get("chapter"),
                        "status": lang.get("status"),
                        "failing": lang.get("failing"),
                    }
                )
            verses = data.get("verses") or []
            verse_total += len(verses)
            empties = [v.get("reference") for v in verses if not (v.get("text") or "").strip()]
            if empties:
                empty_raw.append({"file": str(p), "empty_verses": empties})
        raw_keys[cfg.key] = keys
        raw_counts[cfg.key] = {
            "chapters": len(paths),
            "verses": verse_total,
            "unreadable": bad,
        }
    coverage = {}
    for cfg in (thadou_cfg, niv_cfg):
        missing = sorted(manifest_keys[cfg.key] - raw_keys[cfg.key])
        coverage[cfg.key] = {"missing_chapters": missing, "count": len(missing)}
    checks["raw_captures"] = {
        "ok": all(not v["unreadable"] and coverage[v_key]["count"] == 0
                  for v_key, v in raw_counts.items()),
        "detail": {k: {"chapters": v["chapters"], "verses": v["verses"],
                       "missing_from_manifest": coverage[k]["count"]}
                   for k, v in raw_counts.items()},
    }
    failed_chapters = {
        k: coverage[k]["missing_chapters"] for k in coverage if coverage[k]["count"]
    }

    # ---- 3. normalized files --------------------------------------------
    norm_counts: Dict[str, int] = {}
    for cfg in (thadou_cfg, niv_cfg):
        path = NORMALIZED_DIR / f"{cfg.manifest_prefix}_verses.jsonl"
        n = 0
        refs = set()
        dup = 0
        if path.exists():
            with path.open(encoding="utf-8") as fh:
                for line in fh:
                    if not line.strip():
                        continue
                    n += 1
                    rec = json.loads(line)
                    ref = rec.get("reference")
                    if ref in refs:
                        dup += 1
                    refs.add(ref)
        norm_counts[cfg.key] = {"verses": n, "unique": len(refs), "duplicates": dup}
    checks["normalized_deduplicated"] = {
        "ok": all(v["duplicates"] == 0 and v["verses"] == v["unique"]
                  for v in norm_counts.values()),
        "detail": norm_counts,
    }

    # ---- 4. aligned outputs ----------------------------------------------
    parallel_path = ALIGNED_DIR / "thadou_kuki_niv_parallel.jsonl"
    ml_path = ALIGNED_DIR / "thadou_kuki_niv_ml.jsonl"
    audit_path = AUDIT_DIR / "alignment_audit.jsonl"
    parallel = load_jsonl(parallel_path)
    ml = load_jsonl(ml_path)
    audit = load_jsonl(audit_path)

    schema_errors: List[dict] = []
    seen_ids: Dict[str, int] = {}
    for i, row in enumerate(parallel, 1):
        missing = [f for f in PARALLEL_REQUIRED_FIELDS if f not in row]
        if missing:
            schema_errors.append({"line": i, "missing_fields": missing})
            continue
        ref = row.get("reference")
        try:
            book, ch, verse = parse_reference(ref)
        except ValueError:
            schema_errors.append({"line": i, "bad_reference": ref})
            continue
        if row.get("id") != ref:
            schema_errors.append({"line": i, "id_reference_mismatch": ref})
        if book != row.get("book_code"):
            schema_errors.append({"line": i, "book_code_mismatch": ref})
        if not str(row.get("thadou_kuki") or "").strip():
            schema_errors.append({"line": i, "empty_thadou": ref})
        if not str(row.get("english") or "").strip():
            schema_errors.append({"line": i, "empty_english": ref})
        src = row.get("source") or {}
        for side in ("thadou_kuki", "english"):
            if not (src.get(side) or {}).get("url"):
                schema_errors.append({"line": i, "missing_source_url": f"{ref}:{side}"})
        seen_ids[ref] = seen_ids.get(ref, 0) + 1

    duplicate_ids = sorted([r for r, c in seen_ids.items() if c > 1])
    ml_schema_errors = []
    for i, row in enumerate(ml, 1):
        missing = [f for f in ML_REQUIRED_FIELDS if f not in row]
        if missing:
            ml_schema_errors.append({"line": i, "missing_fields": missing})
        if not str(row.get("source") or "").strip() or not str(row.get("target") or "").strip():
            ml_schema_errors.append({"line": i, "empty_text": row.get("id")})

    checks["parallel_schema"] = {
        "ok": not schema_errors and bool(parallel),
        "detail": {"rows": len(parallel), "errors": schema_errors[:20],
                   "error_count": len(schema_errors)},
    }
    checks["ml_schema"] = {
        "ok": not ml_schema_errors and len(ml) == len(parallel),
        "detail": {"rows": len(ml), "errors": ml_schema_errors[:20],
                   "error_count": len(ml_schema_errors)},
    }
    checks["no_duplicate_ids"] = {
        "ok": not duplicate_ids,
        "detail": {"duplicates": duplicate_ids[:20], "count": len(duplicate_ids)},
    }

    # ---- 5. audit reconciliation -----------------------------------------
    audit_status_counts: Dict[str, int] = {}
    for rec in audit:
        s = rec.get("alignment_status") or "unknown"
        audit_status_counts[s] = audit_status_counts.get(s, 0) + 1
    aligned_audit = audit_status_counts.get("aligned", 0)
    checks["audit_reconciles"] = {
        "ok": aligned_audit == len(parallel) or not parallel,
        "detail": {"audit_status_counts": audit_status_counts,
                   "aligned_in_audit": aligned_audit, "parallel_rows": len(parallel)},
    }

    # ---- 6. split integrity ----------------------------------------------
    split_path = ALIGNED_DIR / "splits" / "split_manifest.json"
    split_ok = False
    split_detail: dict = {}
    if split_path.exists() and parallel:
        manifest = json.loads(split_path.read_text(encoding="utf-8"))
        split_books = manifest.get("books") or {}
        all_books = sorted({r["book_code"] for r in parallel})
        assigned = sorted(b for v in split_books.values() for b in v)
        overlap = [b for b in all_books if sum(1 for v in split_books.values() if b in v) > 1]
        split_ok = assigned == all_books and not overlap
        split_detail = {"books": len(all_books), "assigned": len(assigned),
                        "overlap": overlap,
                        "counts": manifest.get("counts")}
    checks["split_whole_books"] = {"ok": split_ok, "detail": split_detail}

    # ---- 7. language uncertainty must be visible, not silent -------------
    uncertain_refs = [
        rec for rec in audit if rec.get("alignment_status") == "language_uncertain"
    ]
    uncertain_ref_set = {rec.get("reference") for rec in uncertain_refs}
    uncertain_in_corpus = [
        row for row in parallel if row["reference"] in uncertain_ref_set
    ]
    checks["uncertain_excluded_from_corpus"] = {
        "ok": not uncertain_in_corpus,
        "detail": {
            "uncertain_audit_records": len(uncertain_refs),
            "uncertain_chapters": len(uncertain_chapters),
            "uncertain_rows_leaked_into_corpus": len(uncertain_in_corpus),
        },
    }

    # ---- 8. spot checks ---------------------------------------------------
    by_ref = {row["reference"]: row for row in parallel}
    spot = []
    for ref in SPOT_CHECKS:
        row = by_ref.get(ref)
        spot.append(
            {
                "reference": ref,
                "found": row is not None,
                "thadou_kuki": row.get("thadou_kuki") if row else None,
                "english": row.get("english") if row else None,
                "thadou_url": (row.get("source", {}).get("thadou_kuki") or {}).get("url") if row else None,
                "niv_url": (row.get("source", {}).get("english") or {}).get("url") if row else None,
            }
        )
    spot_missing = [s["reference"] for s in spot if not s["found"]]
    checks["spot_checks"] = {
        "ok": not spot_missing,
        "detail": {"expected": SPOT_CHECKS, "missing": spot_missing},
    }

    # ---- 9. completion gate ----------------------------------------------
    failed_raw = sum(len(v["unreadable"]) for v in raw_counts.values())
    failed_chapter_total = sum(len(v) for v in failed_chapters.values())
    all_ok = all(c["ok"] for c in checks.values())
    complete = (
        all_ok and not uncertain_chapters and failed_raw == 0 and failed_chapter_total == 0
    )
    if require_complete and not complete:
        problems.append(
            "corpus is NOT fully verified; see failing checks and "
            "uncertain chapters before claiming completeness"
        )

    report = {
        "generated_at": utcnow(),
        "ok": all_ok,
        "complete": complete,
        "checks": checks,
        "counts": {
            "discovered_chapters": chapter_totals,
            "extracted_chapters": {k: v["chapters"] for k, v in raw_counts.items()},
            "normalized_verses": {k: v["verses"] for k, v in norm_counts.items()},
            "aligned_pairs": len(parallel),
            "ml_pairs": len(ml),
            "audit_records": len(audit),
            "missing_thadou": audit_status_counts.get("missing_thadou", 0),
            "missing_niv": audit_status_counts.get("missing_niv", 0),
            "duplicate_thadou": audit_status_counts.get("duplicate_thadou", 0),
            "duplicate_niv": audit_status_counts.get("duplicate_niv", 0),
            "language_uncertain": audit_status_counts.get("language_uncertain", 0),
            "extraction_error": audit_status_counts.get("extraction_error", 0),
            "failed_raw_files": failed_raw,
            "failed_chapters": {k: sorted(v) for k, v in failed_chapters.items()},
            "uncertain_chapters": len(uncertain_chapters),
            "empty_verses_in_raw": sum(len(e["empty_verses"]) for e in empty_raw),
        },
        "uncertain_chapters": uncertain_chapters,
        "empty_verses_in_raw": empty_raw,
        "spot_checks": spot,
        "problems": problems,
    }
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    atomic_write_json(AUDIT_DIR / "verification.json", report)
    log.info(
        "verify ok=%s complete=%s aligned=%d uncertain_chapters=%d failing=%s",
        all_ok, complete, len(parallel), len(uncertain_chapters),
        [k for k, c in checks.items() if not c["ok"]],
    )
    return report


def print_spot_checks(report: dict) -> None:
    print("\nManual spot checks (both texts + both URLs):")
    for s in report.get("spot_checks", []):
        if s["found"]:
            print(f"  {s['reference']}")
            print(f"    THADOU-KUKI : {s['thadou_kuki']}")
            print(f"    NIV         : {s['english']}")
            print(f"    THADBSI URL : {s['thadou_url']}")
            print(f"    NIV URL     : {s['niv_url']}")
        else:
            print(f"  {s['reference']}: NOT ALIGNED (see data/audit/alignment_audit.jsonl)")
