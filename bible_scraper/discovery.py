"""Discovery: version page -> books -> chapters manifests.

Book identity comes from the canonical codes embedded in Bible.com URLs
(``/bible/{versionId}/{BOOK}.{chapter}.{VERSION}``), never from display names,
which mix Thadou and English on the THADBSI page. Display names are recorded
only as labels, taken from the ``H3`` heading that precedes each book's
chapter links on the version page.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

from .browser import BrowserSession
from .models import (
    CANONICAL_BOOK_ORDER,
    CANONICAL_CHAPTERS,
    MANIFESTS_DIR,
    DISCOVERY_DIR,
    STATUS_DISCOVERED,
    VersionConfig,
    atomic_write_json,
)

log = logging.getLogger("bible_scraper.discovery")

# Runs in the page. Collects every /bible/{id}/... anchor, grouped by the
# canonical book code that appears in the URL. Book display names come from
# the nearest preceding H3 heading; testaments from the H2 headings.
DISCOVERY_JS = r"""
(versionId) => {
  const hrefRe = /^\/bible\/(\d+)\/([0-9A-Z]{3})\.([0-9]+|[A-Z]+\d*)\.([A-Z]+)$/;
  const books = new Map();
  const order = [];
  const duplicateChapterUrls = [];
  let testament = null;
  let bookName = null;

  const nodes = document.querySelectorAll('h2, h3, a[href]');
  for (const n of nodes) {
    if (n.tagName === 'H2') {
      const t = (n.textContent || '').trim();
      if (t === 'Old Testament' || t === 'New Testament') {
        testament = t;
        bookName = null;
      }
      continue;
    }
    if (n.tagName === 'H3') {
      bookName = (n.textContent || '').trim();
      continue;
    }
    const href = n.getAttribute('href') || '';
    const m = hrefRe.exec(href);
    if (!m) continue;
    if (m[1] !== String(versionId)) continue;
    const code = m[2], mid = m[3], vcode = m[4];
    let b = books.get(code);
    if (!b) {
      b = { code, name: null, testament: null, chapters: [], seen: new Set(),
            intro_url: null, version_code: vcode, anchor_sample: [] };
      books.set(code, b);
      order.push(code);
    }
    if (!b.name && bookName) b.name = bookName;
    if (!b.testament && testament) b.testament = testament;
    if (/^[0-9]+$/.test(mid)) {
      const ch = parseInt(mid, 10);
      if (b.seen.has(ch)) { duplicateChapterUrls.push(href); }
      else { b.seen.add(ch); b.chapters.push(ch); }
    } else if (/^INTRO/.test(mid)) {
      b.intro_url = href;
    }
    if (b.anchor_sample.length < 2) b.anchor_sample.push(href);
  }

  const h1 = document.querySelector('h1');
  const canonical = document.querySelector('link[rel="canonical"]');
  return {
    page: {
      title: document.title,
      url: location.href,
      h1: h1 ? (h1.textContent || '').trim() : null,
      canonical: canonical ? canonical.href : null,
      lang: document.documentElement.lang || null,
    },
    books: order.map((c) => {
      const b = books.get(c);
      b.chapters.sort((x, y) => x - y);
      return { code: c, name: b.name, testament: b.testament, chapters: b.chapters,
               intro_url: b.intro_url, version_code: b.version_code,
               anchor_sample: b.anchor_sample };
    }),
    duplicate_chapter_urls: duplicateChapterUrls,
    version_codes_seen: Array.from(new Set(order.map((c) => books.get(c).version_code))),
  };
}
"""


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def discover_version(session: BrowserSession, cfg: VersionConfig) -> dict:
    """Visit the version page and return its raw discovery payload."""
    log.info("discovering version=%s url=%s", cfg.key, cfg.url)
    selector = f'a[href*="/bible/{cfg.version_id}/"]'
    attempts = session.goto(cfg.url, selector=selector, selector_timeout_ms=20_000)
    payload = session.evaluate(DISCOVERY_JS, cfg.version_id)
    payload["discovered_at"] = utcnow()
    payload["version"] = cfg.key
    payload["version_id"] = cfg.version_id
    payload["version_code"] = cfg.version_code
    payload["version_name"] = cfg.version_name
    payload["version_url"] = cfg.url
    payload["publisher"] = cfg.publisher
    payload["manifest_prefix"] = cfg.manifest_prefix
    payload["navigation_attempts"] = attempts
    payload["validation"] = validate_discovery(payload, cfg)
    log.info(
        "discovered version=%s books=%d chapters=%d status=%s",
        cfg.key, len(payload.get("books", [])),
        sum(len(b.get("chapters", [])) for b in payload.get("books", [])),
        payload["validation"]["status"],
    )
    return payload


def validate_discovery(payload: dict, cfg: VersionConfig) -> dict:
    """Structure-level sanity checks for a discovery payload (never guessed)."""
    books = payload.get("books", [])
    codes = [b["code"] for b in books]
    checks = {
        "books_non_empty": bool(books),
        "book_codes_unique": len(codes) == len(set(codes)),
        "version_codes_uniform": payload.get("version_codes_seen") == [cfg.version_code],
        "expected_book_count": len(books) == len(CANONICAL_BOOK_ORDER),
        "all_chapters_positive": all(
            all(isinstance(ch, int) and ch >= 1 for ch in b.get("chapters", [])) for b in books
        ),
        "display_names_present": all(b.get("name") for b in books),
    }
    # Chapter-count mismatches vs. the canonical table are reported, not fatal:
    # the live site is authoritative for what exists.
    chapter_mismatches = []
    for b in books:
        expected = CANONICAL_CHAPTERS.get(b["code"])
        actual = len(b.get("chapters", []))
        if expected is not None and expected != actual:
            chapter_mismatches.append(
                {"book": b["code"], "canonical": expected, "discovered": actual}
            )
    missing_canonical = [c for c in CANONICAL_BOOK_ORDER if c not in codes]
    extra = [c for c in codes if c not in CANONICAL_BOOK_ORDER]
    checks["canonical_books_present"] = not missing_canonical
    status = "verified" if all(checks.values()) else "UNCERTAIN"
    return {
        "status": status,
        "checks": checks,
        "chapter_count_mismatches": chapter_mismatches,
        "missing_canonical_books": missing_canonical,
        "unexpected_books": extra,
        "duplicate_chapter_urls": payload.get("duplicate_chapter_urls", []),
    }


def write_discovery_outputs(results: Dict[str, dict]) -> dict:
    """Persist discovery payloads, book/chapter manifests, book mapping.

    Existing progress entries are preserved so collect runs stay resumable.
    """
    generated_at = utcnow()
    mapping_books: Dict[str, dict] = {
        code: {
            "thadbsi_name": None,
            "english_name": None,
            "testament": None,
            "chapters": {},
            "intro_urls": {},
        }
        for code in CANONICAL_BOOK_ORDER
    }

    for version_key, payload in results.items():
        cfg_version_id = payload["version_id"]
        prefix = payload["manifest_prefix"]
        # raw discovery payload
        atomic_write_json(DISCOVERY_DIR / f"{prefix}_version_page.json", payload)

        books = payload["books"]
        book_manifest = {
            "version": version_key,
            "version_id": cfg_version_id,
            "version_code": payload["version_code"],
            "version_name": payload.get("version_name"),
            "version_url": payload.get("version_url"),
            "publisher": payload.get("publisher"),
            "discovered_at": payload["discovered_at"],
            "book_count": len(books),
            "validation": payload["validation"],
            "books": [
                {
                    "code": b["code"],
                    "name": b.get("name"),
                    "testament": b.get("testament"),
                    "chapter_count": len(b.get("chapters", [])),
                    "intro_url": b.get("intro_url"),
                }
                for b in books
            ],
        }
        atomic_write_json(MANIFESTS_DIR / f"{prefix}_books.json", book_manifest)

        chapters_path = MANIFESTS_DIR / f"{prefix}_chapters.jsonl"
        with chapters_path.open("w", encoding="utf-8") as fh:
            for b in books:
                for ch in b.get("chapters", []):
                    rec = {
                        "version": version_key,
                        "book": b.get("name"),
                        "book_code": b["code"],
                        "chapter": ch,
                        "url": (
                            f"https://www.bible.com/bible/{cfg_version_id}/"
                            f"{b['code']}.{ch}.{payload['version_code']}"
                        ),
                        "discovered_at": payload["discovered_at"],
                        "status": STATUS_DISCOVERED,
                    }
                    fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

        # merge into the shared book mapping
        for b in books:
            entry = mapping_books.setdefault(b["code"], {
                "thadbsi_name": None, "english_name": None,
                "testament": None, "chapters": {}, "intro_urls": {},
            })
            if version_key == "THADBSI":
                entry["thadbsi_name"] = b.get("name")
            else:
                entry["english_name"] = b.get("name")
            entry["testament"] = b.get("testament") or entry["testament"]
            entry["chapters"][version_key] = len(b.get("chapters", []))
            if b.get("intro_url"):
                entry["intro_urls"][version_key] = b["intro_url"]

    # canonical order, filtered to books that were actually discovered
    ordered = {
        code: mapping_books[code]
        for code in CANONICAL_BOOK_ORDER
        if code in mapping_books
    }
    atomic_write_json(MANIFESTS_DIR / "book_mapping.json", {
        "generated_at": generated_at,
        "source": "canonical book codes from Bible.com URLs; display names are labels only",
        "canonical_order": [c for c in CANONICAL_BOOK_ORDER if c in mapping_books],
        "books": ordered,
    })
    log.info("wrote discovery outputs for versions=%s", sorted(results))
    return {"book_mapping": str(MANIFESTS_DIR / "book_mapping.json"),
            "books": len(ordered)}


def load_book_mapping() -> dict:
    path = MANIFESTS_DIR / "book_mapping.json"
    if not path.exists():
        return {"canonical_order": [], "books": {}}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {"canonical_order": data.get("canonical_order", []),
            "books": data.get("books", {})}


def load_chapter_tasks(version_key: str, prefix: str) -> List[dict]:
    """Read a chapters manifest back as a list of records."""
    path = MANIFESTS_DIR / f"{prefix}_chapters.jsonl"
    if not path.exists():
        return []
    out = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out
