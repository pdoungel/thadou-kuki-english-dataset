"""Command-line interface for the parallel-corpus pipeline.

Commands
--------
discover   version page -> book/chapter manifests + book mapping
collect    fetch + extract chapters (resumable, browser-driven)
normalize  whitespace normalization + per-version deduplication
align      strict reference-based alignment, audit log, splits
verify     offline corpus verification + spot-check report
report     quality report (md/json/csv), checksums, source manifest
all        discover -> collect -> normalize -> align -> verify -> report

The browser is used for ``discover`` and ``collect`` only; every other step is
offline and re-runnable. State lives in ``data/manifests/progress.json`` so an
interrupted collection resumes where it stopped.
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from . import __version__
from .alignment import align
from .browser import BrowserSession
from .discovery import discover_version, load_book_mapping, load_chapter_tasks, write_discovery_outputs
from .extraction import extract_chapter
from .models import (
    COMPLETE_STATES,
    LOGS_DIR,
    MANIFESTS_DIR,
    RAW_DIR,
    STATUS_DISCOVERED,
    STATUS_EXTRACTED,
    STATUS_FAILED,
    STATUS_FETCHING,
    STATUS_VERIFIED,
    VERSIONS,
    VersionConfig,
    atomic_write_json,
    ensure_dirs,
    get_version,
)
from .normalization import load_normalized, normalize_version
from .reporting import report as run_report
from .validation import print_spot_checks, verify

log = logging.getLogger("bible_scraper.cli")
audit = logging.getLogger("bible_scraper.audit")

# --------------------------------------------------------------------------
# Logging: logs/scraper.log (info+), logs/errors.log (warning+), logs/audit.log
# --------------------------------------------------------------------------
LOG_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"


def setup_logging(level: str = "INFO") -> None:
    ensure_dirs()
    root = logging.getLogger("bible_scraper")
    root.setLevel(logging.DEBUG)
    for h in list(root.handlers):
        root.removeHandler(h)
        try:
            h.close()
        except Exception:  # pragma: no cover
            pass
    formatter = logging.Formatter(LOG_FORMAT)

    stream = logging.StreamHandler(sys.stderr)
    stream.setFormatter(formatter)
    stream.setLevel(getattr(logging, level.upper(), logging.INFO))
    root.addHandler(stream)

    scraper_fh = logging.FileHandler(LOGS_DIR / "scraper.log", encoding="utf-8")
    scraper_fh.setFormatter(formatter)
    scraper_fh.setLevel(logging.INFO)
    root.addHandler(scraper_fh)

    errors_fh = logging.FileHandler(LOGS_DIR / "errors.log", encoding="utf-8")
    errors_fh.setFormatter(formatter)
    errors_fh.setLevel(logging.WARNING)
    root.addHandler(errors_fh)

    audit_logger = logging.getLogger("bible_scraper.audit")
    audit_logger.setLevel(logging.INFO)
    for h in list(audit_logger.handlers):
        audit_logger.removeHandler(h)
        try:
            h.close()
        except Exception:  # pragma: no cover
            pass
    audit_fh = logging.FileHandler(LOGS_DIR / "audit.log", encoding="utf-8")
    audit_fh.setFormatter(formatter)
    audit_logger.addHandler(audit_fh)


# --------------------------------------------------------------------------
# Progress state (data/manifests/progress.json)
# --------------------------------------------------------------------------
PROGRESS_PATH = MANIFESTS_DIR / "progress.json"


def load_progress() -> dict:
    if PROGRESS_PATH.exists():
        try:
            data = json.loads(PROGRESS_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("versions"), dict):
                return data
        except (OSError, json.JSONDecodeError):
            log.warning("progress.json unreadable; starting a fresh one")
    return {"generated_at": None, "versions": {}}


def save_progress(progress: dict) -> None:
    from datetime import datetime, timezone

    progress["generated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    atomic_write_json(PROGRESS_PATH, progress)


def progress_state(progress: dict, version_key: str, chapter_key: str) -> str:
    return ((progress.get("versions") or {}).get(version_key) or {}).get(chapter_key, {}).get("status", "discovered")


def set_progress(progress: dict, version_key: str, chapter_key: str, **fields) -> None:
    from datetime import datetime, timezone

    versions = progress.setdefault("versions", {})
    entry = versions.setdefault(version_key, {}).setdefault(chapter_key, {})
    entry.update(fields)
    entry["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    save_progress(progress)


def audit_event(**fields) -> None:
    audit.info("AUDIT " + " ".join(f"{k}={v}" for k, v in fields.items()))


# --------------------------------------------------------------------------
# shared helpers
# --------------------------------------------------------------------------
def selected_versions(version_arg: Optional[str]) -> List[VersionConfig]:
    if version_arg:
        return [get_version(version_arg)]
    return [VERSIONS["THADBSI"], VERSIONS["NIV"]]


def raw_capture_path(cfg: VersionConfig, book_code: str, chapter: int) -> Path:
    return RAW_DIR / cfg.raw_dirname / book_code / f"{chapter:03d}.json"


def filter_tasks(tasks: Sequence[dict], book: Optional[str], chapter: Optional[int]) -> List[dict]:
    out = list(tasks)
    if book:
        out = [t for t in out if t["book_code"].upper() == book.upper()]
    if chapter is not None:
        out = [t for t in out if int(t["chapter"]) == int(chapter)]
    return out


def book_display_name(cfg: VersionConfig, book_code: str) -> Optional[str]:
    mapping = load_book_mapping()
    entry = mapping.get("books", {}).get(book_code) or {}
    if cfg.key == "THADBSI":
        return entry.get("thadbsi_name")
    return entry.get("english_name")


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------
def cmd_discover(args) -> int:
    """Visit each selected version page and persist discovery outputs."""
    progress = load_progress()
    results: Dict[str, dict] = {}
    for cfg in selected_versions(args.version):
        with BrowserSession(
            headed=args.headed,
            min_delay=args.min_delay,
            max_delay=args.max_delay,
            max_retries=args.max_retries,
        ) as session:
            payload = discover_version(session, cfg)
        payload["validation"] = payload.get("validation") or {}
        results[cfg.key] = payload
        if payload["validation"].get("status") != "verified":
            log.warning(
                "discovery for %s is UNCERTAIN: %s",
                cfg.key, json.dumps(payload["validation"], ensure_ascii=False)[:500],
            )
            audit_event(event="discovery_uncertain", version=cfg.key)
        else:
            audit_event(event="discovery_verified", version=cfg.key,
                        books=len(payload.get("books", [])),
                        chapters=sum(len(b.get("chapters", [])) for b in payload.get("books", [])))

    write_discovery_outputs(results)

    # seed progress entries (preserve everything already collected)
    for cfg in selected_versions(args.version):
        for task in load_chapter_tasks(cfg.key, cfg.manifest_prefix):
            versions = progress.setdefault("versions", {})
            entry = versions.setdefault(cfg.key, {}).setdefault(task["book_code"] + "." + str(task["chapter"]), {})
            entry.setdefault("status", STATUS_DISCOVERED)
            entry.setdefault("url", task["url"])
            entry.setdefault("attempts", 0)
    save_progress(progress)
    print(f"discovery complete for: {', '.join(results)} -> {MANIFESTS_DIR}")
    return 0


def cmd_collect(args) -> int:
    """Fetch + extract chapters; resumable and polite."""
    progress = load_progress()
    configs = selected_versions(args.version)

    plan: List[tuple] = []
    skipped = 0
    for cfg in configs:
        tasks = load_chapter_tasks(cfg.key, cfg.manifest_prefix)
        if not tasks:
            log.error("no chapter manifest for %s; run `discover` first", cfg.key)
            return 2
        tasks = filter_tasks(tasks, getattr(args, "book", None), getattr(args, "chapter", None))
        if getattr(args, "book", None) and not tasks:
            log.error("no chapters match book=%s chapter=%s for %s",
                      args.book, args.chapter, cfg.key)
            return 2
        for t in tasks:
            key = f"{t['book_code']}.{t['chapter']}"
            state = progress_state(progress, cfg.key, key)
            raw_path = raw_capture_path(cfg, t["book_code"], int(t["chapter"]))
            if state in COMPLETE_STATES and raw_path.exists():
                skipped += 1  # already collected on a previous run
                continue
            plan.append((cfg, t))

    print(f"collect plan: {len(plan)} chapter(s) pending "
          f"(headless={not args.headed}, delays={args.min_delay}-{args.max_delay}s, "
          f"retries={args.max_retries})")
    if not plan:
        print("nothing to do; all requested chapters are already collected")
        return 0

    collected = failed = 0
    with BrowserSession(
        headed=args.headed,
        min_delay=args.min_delay,
        max_delay=args.max_delay,
        max_retries=args.max_retries,
    ) as session:
        for cfg, task in plan:
            book_code = task["book_code"]
            chapter = int(task["chapter"])
            key = f"{book_code}.{chapter}"
            name = book_display_name(cfg, book_code)
            raw_path = raw_capture_path(cfg, book_code, chapter)

            last_error = None
            raw = None
            attempts = args.max_retries + 1
            for attempt in range(1, attempts + 1):
                set_progress(progress, cfg.key, key, status=STATUS_FETCHING,
                             url=task["url"], attempts=attempt, error=None)
                audit_event(event="fetch", version=cfg.key, chapter=key,
                            attempt=attempt, url=task["url"])
                try:
                    session.pause()
                    raw = extract_chapter(session, cfg, book_code, chapter, name)
                    if raw["verse_count"] == 0:
                        raise RuntimeError("no verses extracted (container/selector not found)")
                    last_error = None
                    break
                except Exception as exc:  # noqa: BLE001 - recorded, retried, never hidden
                    last_error = f"{type(exc).__name__}: {exc}"
                    raw = None
                    log.warning("extract failed %s %s attempt=%d/%d: %s",
                                cfg.key, key, attempt, attempts, last_error)
                    if attempt < attempts:
                        time.sleep((2 ** (attempt - 1)) + random.random())

            if raw is None:
                failed += 1
                set_progress(progress, cfg.key, key, status=STATUS_FAILED,
                             url=task["url"], error=last_error)
                audit_event(event="chapter_failed", version=cfg.key, chapter=key,
                            error=last_error)
                continue

            raw_path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_json(raw_path, raw)

            lang = (raw.get("language_verification") or {}).get("status")
            state = STATUS_VERIFIED if lang == "verified" else STATUS_EXTRACTED
            set_progress(
                progress, cfg.key, key,
                status=state, url=task["url"], error=None,
                verses=raw.get("verse_count"), language_status=lang,
                content_hash=raw.get("content_hash"),
            )
            audit_event(
                event="chapter_collected", version=cfg.key, chapter=key,
                status=state, language=lang, verses=raw.get("verse_count"),
                content_hash=raw.get("content_hash"), url=task["url"],
            )
            collected += 1
            print(f"  [{cfg.key}] {key}: {raw.get('verse_count')} verses -> {lang}")

    # a task blocked by a failed earlier chapter counts as not attempted
    pending_left = 0
    for cfg, task in plan:
        key = f"{task['book_code']}.{task['chapter']}"
        if progress_state(progress, cfg.key, key) in (STATUS_FETCHING, STATUS_DISCOVERED, STATUS_FAILED):
            pending_left += 1

    print(f"collect done: collected={collected} skipped={skipped} failed={failed} "
          f"unresolved={pending_left}")
    audit_event(event="collect_summary", collected=collected, skipped=skipped,
                failed=failed, unresolved=pending_left)
    return 1 if failed else 0


def cmd_normalize(args) -> int:
    """Technical whitespace normalization + per-version deduplication."""
    progress = load_progress()
    exit_code = 0
    for cfg in selected_versions(args.version):
        summary = normalize_version(cfg, progress=progress)
        if summary["raw_chapters"] == 0:
            log.error("no raw captures for %s; run `collect` first", cfg.key)
            exit_code = 2
            continue
        audit_event(
            event="normalized", version=cfg.key,
            chapters=summary["raw_chapters"], verses=summary["verses"],
            duplicates=summary["duplicate_references"],
            empty=len(summary["empty_verses"]),
            uncertain=len(summary["uncertain_chapters"]),
        )
        print(f"  [{cfg.key}] chapters={summary['raw_chapters']} verses={summary['verses']} "
              f"duplicates={summary['duplicate_references']} empty={len(summary['empty_verses'])}")
    return exit_code


def cmd_align(args) -> int:
    """Strict canonical-reference alignment + audit + whole-book splits."""
    thadou_cfg = get_version("THADBSI")
    niv_cfg = get_version("NIV")
    thadou = load_normalized(thadou_cfg)
    niv = load_normalized(niv_cfg)
    if not thadou or not niv:
        log.error("missing normalized data (thadbsi=%d niv=%d); run `normalize` first",
                  len(thadou), len(niv))
        return 2

    duplicates: List[dict] = []
    from .models import NORMALIZED_DIR

    for cfg in (thadou_cfg, niv_cfg):
        path = NORMALIZED_DIR / f"{cfg.manifest_prefix}_summary.json"
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            duplicates.extend(data.get("duplicates") or [])

    summary = align(thadou, niv, thadou_cfg, niv_cfg, duplicates=duplicates)
    counts = summary["counts"]
    print("align done:")
    for state in ("aligned", "missing_thadou", "missing_niv", "duplicate_thadou",
                  "duplicate_niv", "language_uncertain", "extraction_error"):
        print(f"  {state:20s} {counts.get(state, 0)}")
    for split, c in summary["split_counts"].items():
        print(f"  split {split:11s} verses={c['verses']} books={c['books']}")
    if summary["contaminated_chapters"]:
        print(f"  withheld contaminated chapters: {len(summary['contaminated_chapters'])}")
    audit_event(event="align_summary", **{k: v for k, v in counts.items()})
    return 0


def cmd_verify(args) -> int:
    """Offline verification of the whole corpus (never fetches)."""
    thadou_cfg = get_version("THADBSI")
    niv_cfg = get_version("NIV")
    result = verify(thadou_cfg, niv_cfg, require_complete=True)

    print("\nverification checks:")
    for name, chk in result["checks"].items():
        mark = "PASS" if chk["ok"] else "FAIL"
        print(f"  [{mark}] {name}")
        if not chk["ok"]:
            detail = chk.get("detail")
            print(f"         detail: {json.dumps(detail, ensure_ascii=False)[:400]}")

    counts = result["counts"]
    print("\ncounts:")
    for k in ("discovered_chapters", "extracted_chapters", "normalized_verses",
              "aligned_pairs", "ml_pairs", "audit_records", "missing_thadou",
              "missing_niv", "duplicate_thadou", "duplicate_niv",
              "language_uncertain", "extraction_error", "uncertain_chapters",
              "failed_chapters", "failed_raw_files"):
        if k in counts:
            print(f"  {k:24s} {counts[k]}")

    print_spot_checks(result)

    if result["problems"]:
        print("\nPROBLEMS:")
        for p in result["problems"]:
            print(f"  - {p}")
    print(f"\nverification ok={result['ok']} complete={result['complete']}")
    audit_event(event="verify", ok=result["ok"], complete=result["complete"],
                aligned=counts.get("aligned_pairs"),
                uncertain_chapters=counts.get("uncertain_chapters"))
    return 0 if result["ok"] else 1


def cmd_report(args) -> int:
    """Quality report + checksums + source manifest (offline)."""
    thadou_cfg = get_version("THADBSI")
    niv_cfg = get_version("NIV")
    result = run_report(thadou_cfg, niv_cfg)
    print("report written:")
    for k, v in result["paths"].items():
        print(f"  {k:16s} {v}")
    print("\nkey metrics:")
    for k in ("aligned_verse_pairs", "missing_in_thadbsi", "missing_in_niv",
              "duplicate_thadbsi", "duplicate_niv", "language_uncertain_verses",
              "language_uncertain_chapters", "extraction_error_verses",
              "extraction_failures_chapters", "train_verses", "validation_verses",
              "test_verses", "verification_ok", "verification_complete"):
        if k in result["metrics"]:
            print(f"  {k:32s} {result['metrics'][k]}")
    print(f"  {'corpus_sha256':32s} {result['checksums'].get('corpus_sha256')}")
    audit_event(event="report", aligned=result["metrics"].get("aligned_verse_pairs"),
                complete=result["verification_complete"])
    return 0 if result["verification_ok"] else 1


def cmd_all(args) -> int:
    """Full pipeline: discover -> collect -> normalize -> align -> verify -> report."""
    codes = [
        ("discover", cmd_discover),
        ("collect", cmd_collect),
        ("normalize", cmd_normalize),
        ("align", cmd_align),
        ("verify", cmd_verify),
        ("report", cmd_report),
    ]
    worst = 0
    for name, fn in codes:
        print(f"\n=== {name} ===")
        code = fn(args)
        if code:
            worst = max(worst, code) if code != 2 else 2
            if code == 2:  # hard precondition failure: stop the pipeline
                print(f"stopping pipeline: {name} failed with exit code {code}")
                return 2
    return worst


# --------------------------------------------------------------------------
# argument parsing
# --------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m bible_scraper",
        description=(
            "Reproducible Thadou-Kuki (THADBSI) <-> English (NIV) verse-aligned "
            "parallel corpus collector (Playwright-based)."
        ),
    )
    parser.add_argument("--version-info", action="version",
                        version=f"bible_scraper {__version__}")

    common = argparse.ArgumentParser(add_help=False)
    mode = common.add_mutually_exclusive_group()
    mode.add_argument("--headed", dest="headed", action="store_true",
                      help="show the browser window (default; best for development)")
    mode.add_argument("--headless", dest="headed", action="store_false",
                      help="run without a visible browser window")
    common.set_defaults(headed=True)
    common.add_argument("--min-delay", type=float, default=0.5,
                        help="minimum polite delay between chapter requests in seconds (default 0.5)")
    common.add_argument("--max-delay", type=float, default=2.0,
                        help="maximum polite delay between chapter requests in seconds (default 2.0)")
    common.add_argument("--max-retries", type=int, default=3,
                        help="retries per navigation with exponential backoff (default 3)")
    common.add_argument("--version", choices=["THADBSI", "NIV"],
                        help="restrict to one version (default: both)")
    common.add_argument("--log-level", default="INFO",
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"])

    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("discover", parents=[common],
                   help="version page -> books -> chapters manifests")
    collect_p = sub.add_parser("collect", parents=[common],
                               help="fetch + extract chapters (resumable)")
    collect_p.add_argument("--book", help="canonical book code, e.g. GEN")
    collect_p.add_argument("--chapter", type=int, help="chapter number (requires --book)")

    norm_p = sub.add_parser("normalize", parents=[common],
                            help="whitespace normalization + deduplication")

    sub.add_parser("align", parents=[common],
                   help="strict reference alignment + audit + splits")
    sub.add_parser("verify", parents=[common], help="offline corpus verification")
    sub.add_parser("report", parents=[common], help="quality report + checksums")
    sub.add_parser("all", parents=[common],
                   help="discover -> collect -> normalize -> align -> verify -> report")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if getattr(args, "chapter", None) is not None and not getattr(args, "book", None):
        parser.error("--chapter requires --book")
    if getattr(args, "min_delay", 1) < 0 or getattr(args, "max_delay", 1) < 0:
        parser.error("delays must be >= 0")
    if getattr(args, "max_retries", 3) < 0:
        parser.error("--max-retries must be >= 0")
    if getattr(args, "min_delay", 0) > getattr(args, "max_delay", 0):
        parser.error("--min-delay must be <= --max-delay")

    ensure_dirs()
    setup_logging(getattr(args, "log_level", "INFO"))
    log.info("bible_scraper %s command=%s", __version__, args.command)

    commands = {
        "discover": cmd_discover,
        "collect": cmd_collect,
        "normalize": cmd_normalize,
        "align": cmd_align,
        "verify": cmd_verify,
        "report": cmd_report,
        "all": cmd_all,
    }
    try:
        return commands[args.command](args)
    except KeyboardInterrupt:
        print("\ninterrupted; progress saved in data/manifests/progress.json", file=sys.stderr)
        return 130
