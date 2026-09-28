"""Alignment: join the two normalized versions strictly by canonical reference.

Alignment key is always the canonical reference (``GEN.1.1``). Position in the
file, verse index, and text similarity are never used. Every reference in the
union of both versions gets an audit record; only fully verified, non-empty,
non-contaminated pairs enter the parallel corpus.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .discovery import load_book_mapping
from .models import (
    ALIGNED_DIR,
    AUDIT_DIR,
    SPLITS_DIR,
    VersionConfig,
    atomic_write_json,
)
from .normalization import load_normalized, parse_reference

log = logging.getLogger("bible_scraper.alignment")

# Chapter-level cross-version contamination threshold: if >= this share of a
# chapter's THADBSI verses is byte-identical to the NIV verse, the chapter is
# presumed English contamination and is withheld from the verified corpus.
IDENTICAL_RATIO_WITHHOLD = 0.5

# Deterministic whole-book split: sha256(book_code) mod 10.
#   0..7 -> train (target ~80%), 8 -> validation (~10%), 9 -> test (~10%)
SPLIT_TRAIN_BUCKETS = frozenset({0, 1, 2, 3, 4, 5, 6, 7})
SPLIT_VALIDATION_BUCKETS = frozenset({8})
SPLIT_TEST_BUCKETS = frozenset({9})


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def split_bucket(book_code: str) -> int:
    digest = hashlib.sha256(book_code.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % 10


def split_for_book(book_code: str) -> str:
    b = split_bucket(book_code)
    if b in SPLIT_TRAIN_BUCKETS:
        return "train"
    if b in SPLIT_VALIDATION_BUCKETS:
        return "validation"
    return "test"


def text_hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _index(records: Sequence[dict]) -> Dict[str, dict]:
    idx: Dict[str, dict] = {}
    for rec in records:
        idx.setdefault(rec["reference"], rec)
    return idx


def chapter_identical_ratios(
    thadou_by_ref: Dict[str, dict], niv_by_ref: Dict[str, dict]
) -> Dict[Tuple[str, int], dict]:
    """Per-chapter share of THADBSI verses byte-identical to the NIV verse."""
    stats: Dict[Tuple[str, int], dict] = {}
    for ref, trec in thadou_by_ref.items():
        nrec = niv_by_ref.get(ref)
        if not nrec:
            continue
        key = (trec["book_code"], trec["chapter"])
        s = stats.setdefault(key, {"common": 0, "identical": 0})
        s["common"] += 1
        if trec.get("text") and trec.get("text") == nrec.get("text"):
            s["identical"] += 1
    for s in stats.values():
        s["ratio"] = round(s["identical"] / s["common"], 4) if s["common"] else 0.0
    return stats


def align(
    thadou_records: Sequence[dict],
    niv_records: Sequence[dict],
    thadou_cfg: VersionConfig,
    niv_cfg: VersionConfig,
    duplicates: Optional[Sequence[dict]] = None,
) -> dict:
    """Build the aligned corpus, ML corpus, audit log, and book-level splits."""
    thadou_idx = _index(thadou_records)
    niv_idx = _index(niv_records)
    mapping = load_book_mapping()
    books: Dict[str, dict] = mapping.get("books", {})
    order: List[str] = mapping.get("canonical_order") or sorted(
        set(thadou_idx) | set(niv_idx), key=_ref_sort_key
    )

    identical = chapter_identical_ratios(thadou_idx, niv_idx)
    contaminated_chapters = {
        key for key, s in identical.items()
        if s["ratio"] >= IDENTICAL_RATIO_WITHHOLD and s["common"] >= 3
    }

    all_refs = sorted(set(thadou_idx) | set(niv_idx), key=_ref_sort_key)

    parallel: List[dict] = []
    ml: List[dict] = []
    audit: List[dict] = []
    counts = {
        "aligned": 0,
        "missing_thadou": 0,
        "missing_niv": 0,
        "duplicate_thadou": 0,
        "duplicate_niv": 0,
        "language_uncertain": 0,
        "extraction_error": 0,
    }

    # duplicates discovered during normalization get explicit audit records
    for dup in duplicates or []:
        status = "duplicate_thadou" if dup.get("version") == thadou_cfg.key else "duplicate_niv"
        counts[status] += 1
        audit.append(
            {
                "reference": dup["reference"],
                "book_code": _ref_book(dup["reference"]),
                "chapter": _ref_chapter(dup["reference"]),
                "verse": _ref_verse(dup["reference"]),
                "thadou_status": "duplicate" if status == "duplicate_thadou" else "present_or_missing",
                "niv_status": "duplicate" if status == "duplicate_niv" else "present_or_missing",
                "alignment_status": status,
                "thadou_text_hash": None,
                "niv_text_hash": None,
                "reason": (
                    f"duplicate reference in {dup.get('version')} version; "
                    f"kept {dup.get('kept_file')}, dropped {dup.get('dropped_file')}"
                ),
                "recorded_at": utcnow(),
            }
        )

    for ref in all_refs:
        trec = thadou_idx.get(ref)
        nrec = niv_idx.get(ref)
        book_code, chapter, verse = _ref_parts(ref)
        book = books.get(book_code) or {}
        audit_rec = {
            "reference": ref,
            "book_code": book_code,
            "chapter": chapter,
            "verse": verse,
            "thadou_status": "present" if trec else "missing",
            "niv_status": "present" if nrec else "missing",
            "alignment_status": "aligned",
            "thadou_text_hash": text_hash(trec["text"]) if trec else None,
            "niv_text_hash": text_hash(nrec["text"]) if nrec else None,
            "reason": "",
            "recorded_at": utcnow(),
        }

        uncertain = False
        if trec and trec.get("language_status") != "verified":
            uncertain = True
            audit_rec["reason"] = (
                f"THADBSI chapter language status={trec.get('language_status')}"
            )
        if nrec and nrec.get("language_status") != "verified":
            uncertain = True
            audit_rec["reason"] = (
                (audit_rec["reason"] + "; ") if audit_rec["reason"] else ""
            ) + f"NIV chapter language status={nrec.get('language_status')}"

        if (book_code, chapter) in contaminated_chapters and trec:
            uncertain = True
            s = identical[(book_code, chapter)]
            audit_rec["reason"] = (
                (audit_rec["reason"] + "; ") if audit_rec["reason"] else ""
            ) + (
                f"cross-version identical-text ratio {s['ratio']} "
                f"({s['identical']}/{s['common']}) indicates English contamination"
            )

        if uncertain:
            audit_rec["alignment_status"] = "language_uncertain"
            counts["language_uncertain"] += 1
            audit.append(audit_rec)
            continue

        if trec is None:
            audit_rec["alignment_status"] = "missing_thadou"
            audit_rec["reason"] = "reference published in NIV but not present in THADBSI capture"
            counts["missing_thadou"] += 1
            audit.append(audit_rec)
            continue
        if nrec is None:
            audit_rec["alignment_status"] = "missing_niv"
            audit_rec["reason"] = "reference published in THADBSI but not present in NIV capture"
            counts["missing_niv"] += 1
            audit.append(audit_rec)
            continue

        t_text = trec.get("text") or ""
        n_text = nrec.get("text") or ""
        t_empty = not t_text.strip()
        n_empty = not n_text.strip()
        if t_empty or n_empty:
            # The reference exists in the capture but carries no text. On this
            # site that happens when the publisher omits a verse and brackets
            # its label ("[37]") publishing only a footnote — a fact about the
            # source, never a verse to invent. It is recorded as missing on
            # that side; only when *both* sides are empty do we call it an
            # extraction problem, because then no source has shown its text.
            if t_empty and n_empty:
                audit_rec["thadou_status"] = "present_no_text"
                audit_rec["niv_status"] = "present_no_text"
                audit_rec["alignment_status"] = "extraction_error"
                audit_rec["reason"] = (
                    "empty verse text after extraction on both sides "
                    f"(labels thadou={trec.get('label')!r}, niv={nrec.get('label')!r})"
                )
                counts["extraction_error"] += 1
            else:
                side = "thadou" if t_empty else "niv"
                label = (trec if t_empty else nrec).get("label") or ""
                bracketed = label.startswith("[") and label.endswith("]")
                # record exists, so the reference is present in the capture,
                # but it carries no text: say exactly that, not "present".
                audit_rec[f"{side}_status"] = "present_no_text"
                audit_rec["alignment_status"] = f"missing_{side}"
                audit_rec["reason"] = (
                    "reference present in the capture but the source publishes "
                    f"no verse text for it (label {label!r}"
                    + ("; verse bracketed/omitted in this edition" if bracketed else "")
                    + ")"
                )
                counts[f"missing_{side}"] += 1
            audit.append(audit_rec)
            continue

        ident = t_text == n_text
        if ident:
            audit_rec["reason"] = "verse texts byte-identical across versions (flagged)"

        parallel.append(
            {
                "id": ref,
                "reference": ref,
                "book_code": book_code,
                "book_name_thadou_kuki": book.get("thadbsi_name"),
                "book_name_english": book.get("english_name"),
                "chapter": chapter,
                "verse": _verse_number(verse),
                "thadou_kuki": t_text,
                "english": n_text,
                "source": {
                    "thadou_kuki": {
                        "version_id": trec.get("version_id"),
                        "version_code": thadou_cfg.version_code,
                        "url": trec.get("url"),
                    },
                    "english": {
                        "version_id": nrec.get("version_id"),
                        "version_code": niv_cfg.version_code,
                        "url": nrec.get("url"),
                    },
                },
                "split": split_for_book(book_code),
                "identical_text_flag": ident,
            }
        )
        ml.append({"id": ref, "source": t_text, "target": n_text})
        counts["aligned"] += 1
        audit.append(audit_rec)

    # ---- write outputs -----------------------------------------------------
    ALIGNED_DIR.mkdir(parents=True, exist_ok=True)
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    SPLITS_DIR.mkdir(parents=True, exist_ok=True)

    parallel_path = ALIGNED_DIR / "thadou_kuki_niv_parallel.jsonl"
    _write_jsonl(parallel_path, parallel)
    ml_path = ALIGNED_DIR / "thadou_kuki_niv_ml.jsonl"
    _write_jsonl(ml_path, ml)
    audit_path = AUDIT_DIR / "alignment_audit.jsonl"
    _write_jsonl(audit_path, audit)

    split_counts: Dict[str, dict] = {}
    for split_name in ("train", "validation", "test"):
        rows = [r for r in parallel if r["split"] == split_name]
        split_books = sorted({r["book_code"] for r in rows})
        _write_jsonl(SPLITS_DIR / f"{split_name}.jsonl", rows)
        split_counts[split_name] = {"verses": len(rows), "books": len(split_books)}

    books_by_split: Dict[str, List[str]] = {"train": [], "validation": [], "test": []}
    seen_books = sorted({r["book_code"] for r in parallel}) or list(order)
    for code in seen_books:
        books_by_split[split_for_book(code)].append(code)

    split_manifest = {
        "generated_at": utcnow(),
        "method": "whole-book split; bucket = int(sha256(book_code)[:8], 16) mod 10",
        "buckets": {
            "train": "0-7 (target ~80%)",
            "validation": "8 (target ~10%)",
            "test": "9 (target ~10%)",
        },
        "books": books_by_split,
        "counts": split_counts,
        "total_parallel_verses": len(parallel),
    }
    atomic_write_json(SPLITS_DIR / "split_manifest.json", split_manifest)

    summary = {
        "generated_at": utcnow(),
        "counts": counts,
        "parallel_verses": len(parallel),
        "ml_verses": len(ml),
        "audit_records": len(audit),
        "contaminated_chapters": [
            {"book": b, "chapter": ch, "ratio": identical[(b, ch)]["ratio"],
             "identical": identical[(b, ch)]["identical"],
             "common": identical[(b, ch)]["common"]}
            for (b, ch) in sorted(contaminated_chapters)
        ],
        "files": {
            "parallel": str(parallel_path),
            "ml": str(ml_path),
            "audit": str(audit_path),
        },
        "split_counts": split_counts,
    }
    atomic_write_json(AUDIT_DIR / "alignment_summary.json", summary)
    log.info(
        "aligned pairs=%d missing_thadou=%d missing_niv=%d uncertain=%d "
        "extraction_error=%d duplicates=%d",
        counts["aligned"], counts["missing_thadou"], counts["missing_niv"],
        counts["language_uncertain"], counts["extraction_error"],
        counts["duplicate_thadou"] + counts["duplicate_niv"],
    )
    return summary


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _write_jsonl(path, rows: Iterable[dict]) -> None:
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    tmp.replace(path)


def load_jsonl(path) -> List[dict]:
    if not path.exists():
        return []
    out = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def _verse_number(verse) -> int:
    digits = "".join(c for c in str(verse) if c.isdigit())
    return int(digits or 0)


def _ref_parts(ref: str) -> Tuple[str, int, str]:
    try:
        return parse_reference(ref)
    except ValueError:
        return ("", 0, "0")


def _ref_book(ref: str) -> str:
    return _ref_parts(ref)[0]


def _ref_chapter(ref: str) -> int:
    return _ref_parts(ref)[1]


def _ref_verse(ref: str) -> str:
    return _ref_parts(ref)[2]


def _ref_sort_key(ref: str):
    book, chapter, verse = _ref_parts(ref)
    from .models import CANONICAL_BOOK_ORDER

    try:
        book_i = CANONICAL_BOOK_ORDER.index(book)
    except ValueError:
        book_i = 999
    digits = "".join(c for c in str(verse) if c.isdigit()) or "0"
    suffix = "".join(c for c in str(verse) if not c.isdigit())
    return (book_i, chapter, int(digits), suffix)
