"""Normalization: technical whitespace normalization + per-version deduplication.

No translation, paraphrase, spelling fixes, punctuation changes, or text
cleanup of any kind happens here. Only runs of whitespace are collapsed to a
single space and the string is trimmed, so poetry line splits and stray
indentation do not leak into the corpus. Duplicates are removed *by canonical
reference within each version* (first occurrence wins); identical text across
different references is never treated as a duplicate.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .models import (
    NORMALIZED_DIR,
    RAW_DIR,
    ROOT,
    STATUS_FAILED,
    VersionConfig,
    atomic_write_json,
)

log = logging.getLogger("bible_scraper.normalization")

_WS_RE = re.compile(r"\s+")


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normalize_text(text: str) -> str:
    """Collapse runs of whitespace to single spaces and trim the ends.

    This is the *only* transformation applied to published verse text.
    """
    if not text:
        return ""
    return _WS_RE.sub(" ", text).strip()


def parse_reference(reference: str) -> Tuple[str, int, str]:
    """Split ``GEN.1.1`` into ``('GEN', 1, '1')``. Raises ValueError."""
    m = re.fullmatch(r"([0-9A-Z]{3})\.(\d+)\.(\d+[a-z]?)", reference or "")
    if not m:
        raise ValueError(f"invalid canonical reference: {reference!r}")
    return m.group(1), int(m.group(2)), m.group(3)


def format_reference(book_code: str, chapter: int, verse: str) -> str:
    return f"{book_code}.{chapter}.{verse}"


def raw_chapter_paths(cfg: VersionConfig) -> List[Path]:
    """All raw chapter captures for a version, in stable book/chapter order."""
    root = RAW_DIR / cfg.raw_dirname
    if not root.is_dir():
        return []
    paths = sorted(root.glob("*/*.json"))
    return [p for p in paths if not p.name.startswith(".") and "._" not in p.name]


def load_raw_chapter(path: Path) -> Optional[dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:  # incl. decode/JSON errors
        log.error("unreadable raw capture %s: %s", path, exc)
        return None
    if not isinstance(data, dict):
        log.error("raw capture %s is not an object", path)
        return None
    return data


def normalize_version(
    cfg: VersionConfig,
    progress: Optional[dict] = None,
) -> dict:
    """Normalize every raw capture of one version into a deduplicated JSONL.

    Writes ``data/normalized/{prefix}_verses.jsonl`` and returns a summary
    including every duplicate reference that was dropped (with its source
    file, so the removal is auditable).
    """
    out_path = NORMALIZED_DIR / f"{cfg.manifest_prefix}_verses.jsonl"
    records: List[dict] = []
    seen: Dict[str, dict] = {}
    duplicates: List[dict] = []
    empty_verses: List[dict] = []
    unreadable: List[str] = []
    uncertain_chapters: List[str] = []
    failed_chapters: List[str] = []
    chapter_hashes: Dict[str, str] = {}
    duplicate_content_hashes: List[dict] = []

    paths = raw_chapter_paths(cfg)
    for path in paths:
        raw = load_raw_chapter(path)
        if raw is None:
            unreadable.append(str(path))
            continue
        rel = str(path.relative_to(ROOT))
        ch_key = f"{raw.get('book_code')}.{raw.get('chapter')}"
        lang = raw.get("language_verification") or {}
        lang_status = lang.get("status") or "UNKNOWN"
        if lang_status != "verified":
            uncertain_chapters.append(ch_key)
        if progress is not None:
            pstate = (progress.get(cfg.key) or {}).get(ch_key) or {}
            if pstate.get("status") == STATUS_FAILED:
                failed_chapters.append(ch_key)
        chash = raw.get("content_hash")
        if chash:
            if chash in chapter_hashes:
                duplicate_content_hashes.append(
                    {"content_hash": chash, "chapters": [chapter_hashes[chash], ch_key]}
                )
            else:
                chapter_hashes[chash] = ch_key

        for v in raw.get("verses") or []:
            ref = v.get("reference")
            try:
                book_code, chapter, verse = parse_reference(ref)
            except ValueError:
                log.error("invalid reference in %s: %r", rel, ref)
                continue
            text = normalize_text(v.get("text") or "")
            rec = {
                "reference": ref,
                "book_code": book_code,
                "book_name": raw.get("book_name"),
                "chapter": chapter,
                "verse": verse,
                "text": text,
                "label": v.get("label"),
                "version": cfg.key,
                "version_id": cfg.version_id,
                "url": raw.get("url"),
                "source_file": rel,
                "language_status": lang_status,
                "content_hash": chash,
            }
            if not text:
                empty_verses.append({"reference": ref, "source_file": rel})
                # still recorded so the audit can distinguish empty from missing
            if ref in seen:
                duplicates.append(
                    {
                        "reference": ref,
                        "version": cfg.key,
                        "kept_file": seen[ref]["source_file"],
                        "dropped_file": rel,
                    }
                )
                continue
            seen[ref] = rec
            records.append(rec)

    records.sort(
        key=lambda r: (
            _book_order_key(r["book_code"]),
            r["chapter"],
            _verse_sort_key(r["verse"]),
        )
    )

    NORMALIZED_DIR.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_name(out_path.name + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    tmp.replace(out_path)

    summary = {
        "version": cfg.key,
        "generated_at": utcnow(),
        "raw_chapters": len(paths),
        "verses": len(records),
        "unique_references": len(seen),
        "duplicate_references": len(duplicates),
        "duplicates": duplicates,
        "empty_verses": empty_verses,
        "unreadable_raw_files": unreadable,
        "uncertain_chapters": sorted(set(uncertain_chapters)),
        "failed_chapters": sorted(set(failed_chapters)),
        "duplicate_chapter_pages": duplicate_content_hashes,
        "output": str(out_path.relative_to(ROOT)),
    }
    atomic_write_json(NORMALIZED_DIR / f"{cfg.manifest_prefix}_summary.json", summary)
    log.info(
        "normalized version=%s chapters=%d verses=%d duplicates=%d empty=%d uncertain=%d",
        cfg.key, len(paths), len(records), len(duplicates),
        len(empty_verses), len(set(uncertain_chapters)),
    )
    return summary


def load_normalized(cfg: VersionConfig) -> List[dict]:
    path = NORMALIZED_DIR / f"{cfg.manifest_prefix}_verses.jsonl"
    if not path.exists():
        return []
    out = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def _verse_sort_key(verse: str) -> Tuple[int, str]:
    m = re.fullmatch(r"(\d+)([a-z]*)", str(verse))
    if not m:
        return (999999, str(verse))
    return (int(m.group(1)), m.group(2))


def _book_order_key(book_code: str) -> int:
    from .models import CANONICAL_BOOK_ORDER

    try:
        return CANONICAL_BOOK_ORDER.index(book_code)
    except ValueError:
        return 999
