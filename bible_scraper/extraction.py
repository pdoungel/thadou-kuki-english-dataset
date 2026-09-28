"""Chapter extraction.

The in-page script (EXTRACT_JS) captures *structure* only: for every verse
span it returns the ordered content/note parts exactly as published. Joining
those parts into verse text happens in Python (``merge_parts``) so the merge
rules are unit-testable offline without a browser.

DOM facts this is built on (verified against the live site):

- chapter container: ``[data-usfm="GEN.1"]`` (class ``*__chapter``)
- verse spans: class token ending in ``__verse``, ``data-usfm="GEN.1.1"``
- verse number: ``*__label`` child (never part of the text)
- verse text: ``*__content`` children (multiple spans = poetry/spacers)
- footnotes: ``*__note`` children (never part of the text); a note *between*
  two content parts means the parts join raw (source spacing is authoritative)
- cross references: ``*__ref`` spans inside notes, also carrying ``data-usfm``
  — excluded
- headings: ``*__heading``/``*__s``/``*__s1`` are chapter-level, outside verse
  spans — excluded
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import datetime, timezone
from typing import Dict, List, Optional, Sequence, Tuple

log = logging.getLogger("bible_scraper.extraction")

# --------------------------------------------------------------------------
# In-page extraction (returns structure; no text manipulation)
# --------------------------------------------------------------------------
EXTRACT_JS = r"""
(args) => {
  const book = args.bookCode;
  const chapter = args.chapter;
  const expectedUsfm = book + '.' + chapter;
  const verseRe = new RegExp('^' + book + '\\.' + chapter + '\\.\\d+[a-z]?$');

  const page = {
    title: document.title,
    url: location.href,
    canonical: null,
    ogUrl: null,
    lang: document.documentElement.lang || null,
    h1: null,
    versionLinks: [],
  };
  const canonEl = document.querySelector('link[rel="canonical"]');
  if (canonEl) page.canonical = canonEl.href;
  const ogEl = document.querySelector('meta[property="og:url"]');
  if (ogEl) page.ogUrl = ogEl.getAttribute('content');
  const h1El = document.querySelector('h1');
  if (h1El) page.h1 = (h1El.textContent || '').trim();
  const linkSet = new Set();
  document.querySelectorAll('a[href*="/versions/"]').forEach((a) => {
    const h = a.getAttribute('href') || '';
    if (/^\/versions\/\d+/.test(h)) linkSet.add(h);
  });
  page.versionLinks = Array.from(linkSet).slice(0, 10);

  const hasClassSuf = (el, suf) => {
    const cls = el.getAttribute('class') || '';
    return cls.split(/\s+/).some((t) => t === suf || t.endsWith('__' + suf));
  };
  const insideNote = (el, root) => {
    let n = el.parentElement;
    while (n && n !== root) {
      if ((n.getAttribute('class') || '').includes('__note')) return true;
      n = n.parentElement;
    }
    return false;
  };

  // Chapter container: an element carrying data-usfm="BOOK.CH" that has
  // data-usfm descendants (verses). Prefer class *__chapter if several match.
  const candidates = Array.from(
    document.querySelectorAll('[data-usfm="' + expectedUsfm + '"]')
  );
  let container = null;
  for (const c of candidates) {
    if (c.querySelector('[data-usfm]')) { container = c; break; }
  }

  const result = { ok: false, containerFound: !!container, page, verses: [],
                   chapterLabel: null, heading: null, selectorFallback: false };
  if (!container) return result;

  // Chapter-level label + heading (recorded, never part of verse text).
  for (const child of container.children) {
    if (hasClassSuf(child, 'label') && !result.chapterLabel) {
      result.chapterLabel = (child.textContent || '').trim();
    }
    if (!result.heading &&
        (hasClassSuf(child, 'heading') || hasClassSuf(child, 's') ||
         hasClassSuf(child, 's1'))) {
      result.heading = (child.textContent || '').replace(/\s+/g, ' ').trim();
    }
  }

  const all = Array.from(container.querySelectorAll('[data-usfm]'));
  let verseEls = all.filter((el) =>
    verseRe.test(el.getAttribute('data-usfm') || '') && hasClassSuf(el, 'verse')
  );
  let fallback = false;
  if (verseEls.length === 0) {
    // Fallback: module class naming changed — accept any in-chapter element
    // with a 3-part USFM that is not a note/cross-reference.
    fallback = true;
    verseEls = all.filter((el) => {
      const u = el.getAttribute('data-usfm') || '';
      if (!verseRe.test(u)) return false;
      if (insideNote(el, container)) return false;
      const cls = el.getAttribute('class') || '';
      if (cls.split(/\s+/).some((t) => t === 'ref' || t.endsWith('__ref'))) return false;
      return true;
    });
  }
  result.selectorFallback = fallback;

  for (const el of verseEls) {
    const usfm = el.getAttribute('data-usfm');
    let label = null;
    const labelEl = Array.from(el.children).find((c) => hasClassSuf(c, 'label'));
    if (labelEl) label = (labelEl.textContent || '').trim();

    // Ordered parts: content spans (with a note-boundary flag), notes skipped.
    const parts = [];
    let pendingNote = false;
    const nodes = el.querySelectorAll('[class*="__content"], [class*="__note"]');
    for (const node of nodes) {
      const cls = node.getAttribute('class') || '';
      if (cls.includes('__note')) { pendingNote = true; continue; }
      if (!cls.includes('__content')) continue;
      if (insideNote(node, el)) continue;
      parts.push({ text: node.textContent || '', note_before: pendingNote });
      pendingNote = false;
    }
    result.verses.push({ usfm, label, parts });
  }

  result.ok = result.verses.length > 0;
  return result;
}
"""

USFM_RE = re.compile(r"^([0-9A-Z]{3})\.(\d+)\.(\d+[a-z]?)$")
VERSION_LINK_RE = re.compile(r"^/versions/(\d+)")


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --------------------------------------------------------------------------
# Pure-Python join rules (unit tested)
# --------------------------------------------------------------------------
def merge_parts(parts: Sequence[dict]) -> str:
    """Join ordered content parts into verse text.

    Rules (derived from the published DOM):
    - empty parts contribute nothing;
    - the first non-empty part starts the text;
    - a part that follows a footnote/cross-reference (``note_before``) is
      concatenated raw — the source already carries its own spacing;
    - otherwise, if either side already has whitespace at the boundary,
      concatenate raw; two non-adjacent-looking fragments (poetry lines split
      into separate spans) are joined with exactly one space;
    - no other modification is performed.
    """
    out = ""
    for p in parts:
        text = p.get("text")
        if text is None or text == "":
            continue
        if not out:
            out = text
        elif p.get("note_before"):
            out += text
        elif out[-1].isspace() or text[0].isspace():
            out += text
        else:
            out += " " + text
    return out


def split_usfm(usfm: str) -> Optional[Tuple[str, int, str]]:
    m = USFM_RE.match(usfm or "")
    if not m:
        return None
    return m.group(1), int(m.group(2)), m.group(3)


def _verse_order_key(reference: str) -> Tuple[int, int, str]:
    parsed = split_usfm(reference)
    if not parsed:
        return (9999, 999999, reference)
    book, chapter, verse = parsed
    m = re.match(r"(\d+)([a-z]*)$", verse)
    if not m:
        return (chapter, 999999, verse)
    return (chapter, int(m.group(1)), m.group(2))


def group_spans(spans: Sequence[dict], book_code: str, chapter: int) -> Tuple[List[dict], List[str]]:
    """Group verse spans by USFM (poetry lines / spacers) and merge parts.

    Returns (verses, anomalies). Anomalies list every span whose USFM does
    not belong to this chapter — they are reported, never silently dropped
    without a trace.
    """
    prefix = f"{book_code}.{chapter}."
    grouped: Dict[str, dict] = {}
    order: List[str] = []
    anomalies: List[str] = []
    for span in spans:
        usfm = span.get("usfm") or ""
        if not usfm.startswith(prefix) or not USFM_RE.match(usfm):
            anomalies.append(f"unexpected_usfm:{usfm}")
            continue
        g = grouped.get(usfm)
        if g is None:
            g = {"reference": usfm, "parts": [], "labels": [], "span_count": 0}
            grouped[usfm] = g
            order.append(usfm)
        g["parts"].extend(span.get("parts") or [])
        label = span.get("label")
        if label:
            g["labels"].append(str(label))
        g["span_count"] += 1

    verses: List[dict] = []
    for usfm in order:
        g = grouped[usfm]
        parsed = split_usfm(usfm)
        verse_num = parsed[2] if parsed else usfm.rsplit(".", 1)[-1]
        verses.append({
            "verse": verse_num,
            "reference": usfm,
            "label": g["labels"][0] if g["labels"] else None,
            "text": merge_parts(g["parts"]),
            "span_count": g["span_count"],
            "parts": g["parts"],
        })
    verses.sort(key=lambda v: _verse_order_key(v["reference"]))
    return verses, anomalies


# --------------------------------------------------------------------------
# Language heuristics (supplementary only — never the sole authority)
# --------------------------------------------------------------------------
ENGLISH_STOPWORDS = frozenset("""
a about above after again against all am an and any are as at be because been
before being below between both but by can did do does doing down during each
few for from further had has have having he her here hers herself him himself
his how i if in into is it its itself just me more most my myself no nor not
now of off on once only or other our ours ourselves out over own same she should
so some such than that the their theirs them themselves then there these they
this those through to too under until up very was we were what when where which
while who whom why will with you your yours yourself yourselves
""".split())

# Ratio above which English-like stopword density flags a THADBSI chapter as
# not confidently verifiable; below which an NIV chapter looks suspicious.
THADBSI_ENGLISH_RATIO_MAX = 0.55
NIV_ENGLISH_RATIO_MIN = 0.25

# Minimum share of a chapter's verses that must carry text. Guards against a
# silently broken extraction (e.g. content spans no longer matched) without
# punishing verses the publisher omits: bible.com brackets omitted verses
# (label "[37]") and publishes only a footnote for them, which legitimately
# leaves their text empty on that side.
MIN_TEXT_COVERAGE = 0.90

# Titles come in two live variants: "Matthew 17 | NIV Bible - Bible App" and
# chapter-intro titles such as "The Genealogy of Jesus Christ - Bible App"
# (observed for MAT.1-MAT.5). Only the first declares a version code.
TITLE_VERSION_RE = re.compile(r"\|\s*([A-Za-z0-9]+)\s+Bible\b")


def english_stopword_ratio(text: str) -> float:
    """Share of whitespace-delimited tokens that are English stopwords.

    Supplementary diagnostic only. Thadou-Kuki is low-resource, so this can
    neither confirm nor refute the target language on its own; it is recorded
    in every chapter's ``language_verification`` block.
    """
    tokens = [t for t in re.split(r"\s+", (text or "").strip()) if t]
    if not tokens:
        return 0.0
    hits = sum(1 for t in tokens if t.lower().strip(".,;:!?\"'()[]") in ENGLISH_STOPWORDS)
    return round(hits / len(tokens), 4)


# --------------------------------------------------------------------------
# Validation of one extracted chapter (decisive signals = metadata/DOM)
# --------------------------------------------------------------------------
def validate_chapter(
    payload: dict,
    verses: Sequence[dict],
    cfg,
    book_code: str,
    chapter: int,
    expected_url: str,
    page_book_name: Optional[str],
    mapping_book_name: Optional[str],
) -> dict:
    """Verify that the captured page is the requested version/chapter.

    Heuristics (stopword ratio) are supplementary: they can only *withhold*
    confidence, never grant it. Structural signals — URL, canonical link,
    title, version link, container, reference pattern, book name — decide.
    """
    page = payload.get("page") or {}
    url = page.get("url") or ""
    title = page.get("title") or ""
    canonical = page.get("canonical")
    version_links = page.get("versionLinks") or []

    refs_ok = all(
        split_usfm(v["reference"]) is not None
        and v["reference"].startswith(f"{book_code}.{chapter}.")
        for v in verses
    ) and bool(verses)
    empty_refs = [v["reference"] for v in verses if not v["text"].strip()]
    non_empty = len(verses) - len(empty_refs)
    coverage = round(non_empty / len(verses), 4) if verses else 0.0

    stopword_ratio = english_stopword_ratio(" ".join(v["text"] for v in verses))

    # Version actually named by the <title>, if any: None means the title
    # carries no version code at all (chapter-intro variant), which is neutral
    # — identity still has to be proven by URL, canonical, and version link.
    title_code = None
    title_match = TITLE_VERSION_RE.search(title)
    if title_match:
        title_code = title_match.group(1)

    structural = {
        "url_version_id": url.startswith(f"https://www.bible.com/bible/{cfg.version_id}/"),
        "url_matches_expected": url.rstrip("/") == expected_url.rstrip("/"),
        "canonical_matches": (canonical or "").rstrip("/") == expected_url.rstrip("/"),
        "title_version_consistent": title_code in (None, cfg.version_code),
        "version_link_present": any(
            (VERSION_LINK_RE.match(l) or [None, None])[1] == str(cfg.version_id)
            for l in version_links
        ),
        "container_found": bool(payload.get("containerFound")),
        "verses_extracted": bool(verses),
        "references_match_chapter": refs_ok,
        "book_name_matches": bool(page_book_name)
        and bool(mapping_book_name)
        and page_book_name.casefold() == mapping_book_name.casefold(),
        # target-language text is actually present, and not just for a token
        # number of verses: a chapter that is almost entirely empty means the
        # extraction failed, not that the publisher omitted those verses.
        "has_text_content": non_empty > 0,
        "text_coverage_ok": coverage >= MIN_TEXT_COVERAGE,
    }

    # Non-gating observations: recorded so the QC report can surface them, but
    # they say nothing about *which* version/language/chapter this is.
    warnings: Dict[str, object] = {}
    if empty_refs:
        warnings["empty_verses"] = {
            "count": len(empty_refs),
            "references": empty_refs,
            "note": "reference present in the capture with no verse text "
                    "(publisher omits/brackets the verse in this edition); "
                    "recorded as a missing verse downstream, never filled in",
        }
    if title_code is None:
        warnings["title_without_version_code"] = {
            "title": title,
            "note": "chapter-intro title variant; version proven by URL, "
                    "canonical link, og:url, version link and h1",
        }
    warnings["verse_text_coverage"] = coverage

    # Supplementary heuristics: only able to downgrade confidence.
    if cfg.key == "THADBSI":
        heur_ok = stopword_ratio <= THADBSI_ENGLISH_RATIO_MAX
    else:
        heur_ok = stopword_ratio >= NIV_ENGLISH_RATIO_MIN
    heuristics = {
        "english_stopword_ratio": stopword_ratio,
        "within_expected_range": heur_ok,
        "thresholds": {
            "thadbsi_max": THADBSI_ENGLISH_RATIO_MAX,
            "niv_min": NIV_ENGLISH_RATIO_MIN,
        },
    }

    methods = []
    if all(structural[k] for k in
           ("url_version_id", "url_matches_expected", "title_version_consistent",
            "version_link_present")):
        methods.append("version_metadata")
    if structural["canonical_matches"]:
        methods.append("page_metadata")
    if all(structural[k] for k in
           ("container_found", "verses_extracted", "references_match_chapter",
            "book_name_matches")):
        methods.append("DOM_context")

    structural_ok = all(structural.values())
    status = "verified" if structural_ok and heur_ok else "LANGUAGE_UNCERTAIN"
    failing = [k for k, v in structural.items() if not v]
    if not heur_ok:
        failing.append("english_stopword_ratio_out_of_range")

    return {
        "expected": "thadou-kuki" if cfg.key == "THADBSI" else "english",
        "status": status,
        "method": methods,
        "checks": structural,
        "failing": failing,
        "supplementary": heuristics,
        "warnings": warnings,
        "empty_verse_count": len(empty_refs),
        "verse_text_coverage": coverage,
        "validated_at": utcnow(),
    }


# --------------------------------------------------------------------------
# Raw capture assembly
# --------------------------------------------------------------------------
def content_hash(verses: Sequence[dict]) -> str:
    """SHA-256 over the canonical reference/text pairs of one chapter."""
    payload = [{"reference": v["reference"], "text": v["text"]} for v in verses]
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def extract_chapter(session, cfg, book_code: str, chapter: int,
                    book_name: Optional[str]) -> dict:
    """Navigate to one chapter and return its raw capture payload."""
    url = cfg.chapter_url(book_code, chapter)
    selector = f'[data-usfm="{book_code}.{chapter}"]'
    attempts = session.goto(url, selector=selector)
    payload = session.evaluate(
        EXTRACT_JS, {"bookCode": book_code, "chapter": chapter}
    )
    payload["navigation_attempts"] = attempts
    verses, anomalies = group_spans(payload.get("verses") or [], book_code, chapter)
    page = payload.get("page") or {}
    page_book_name = None
    title_prefix = (page.get("title") or "").split("|")[0].strip()
    for candidate in (title_prefix, (page.get("h1") or "").strip()):
        # "Matthew 17" -> "Matthew"; the h1 fallback covers titles that carry
        # a chapter-intro name instead of the book ("The Genealogy of ...").
        m = re.match(r"^(.*)\s+\d+[a-z]?$", candidate)
        if m and m.group(1).strip():
            page_book_name = m.group(1).strip()
            break
    validation = validate_chapter(
        payload, verses, cfg, book_code, chapter, url, page_book_name, book_name
    )
    raw = {
        "version": cfg.key,
        "version_id": cfg.version_id,
        "version_code": cfg.version_code,
        "book_code": book_code,
        "book_name": book_name,
        "chapter": chapter,
        "url": url,
        "retrieved_at": utcnow(),
        "content_hash": content_hash(verses),
        "page": {
            "title": page.get("title"),
            "url": page.get("url"),
            "canonical": page.get("canonical"),
            "og_url": page.get("ogUrl"),
            "lang": page.get("lang"),
            "h1": page.get("h1"),
            "version_links": page.get("versionLinks"),
        },
        "chapter_label": payload.get("chapterLabel"),
        "heading": payload.get("heading"),
        "selector_fallback": bool(payload.get("selectorFallback")),
        "navigation_attempts": attempts,
        "anomalies": anomalies,
        "language_verification": validation,
        "verse_count": len(verses),
        "verses": verses,
    }
    log.info(
        "extracted version=%s %s.%d url=%s verses=%d status=%s fallback=%s",
        cfg.key, book_code, chapter, url, len(verses),
        validation["status"], raw["selector_fallback"],
    )
    return raw
