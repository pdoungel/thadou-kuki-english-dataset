"""Shared fixtures: isolated project root + offline mocked Bible.com pages.

No test ever touches the network: pages are served from in-memory HTML via
Playwright route interception, so the *real* BrowserSession / extraction /
validation code paths run against fixture DOM that mirrors the live site's
structure (CSS-module class names, data-usfm attributes, notes, headings).
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Dict, Iterable, List, Optional, Sequence

import pytest

import bible_scraper.alignment as alignment_mod
import bible_scraper.cli as cli_mod
import bible_scraper.discovery as discovery_mod
import bible_scraper.models as models_mod
import bible_scraper.normalization as normalization_mod
import bible_scraper.reporting as reporting_mod
import bible_scraper.validation as validation_mod
from bible_scraper.alignment import align, load_jsonl
from bible_scraper.models import CANONICAL_BOOK_ORDER, CANONICAL_CHAPTERS, VERSIONS
from bible_scraper.normalization import load_normalized, normalize_version

# ---------------------------------------------------------------------------
# Isolated project root: every module keeps its own binding of the path
# constants, so each one must be redirected for tests to stay hermetic.
# ---------------------------------------------------------------------------
PATH_ATTRS = (
    "ROOT", "DATA_DIR", "DISCOVERY_DIR", "RAW_DIR", "NORMALIZED_DIR",
    "ALIGNED_DIR", "SPLITS_DIR", "AUDIT_DIR", "MANIFESTS_DIR", "REPORTS_DIR",
    "LOGS_DIR", "TESTS_DIR",
)

MODULES = (
    models_mod, discovery_mod, normalization_mod, alignment_mod,
    validation_mod, reporting_mod, cli_mod,
)


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """Redirect all package paths into an isolated temporary project root."""
    import sys as _sys

    root = tmp_path / "bible"
    dirs = {
        "ROOT": root,
        "DATA_DIR": root / "data",
        "DISCOVERY_DIR": root / "data" / "discovery",
        "RAW_DIR": root / "data" / "raw",
        "NORMALIZED_DIR": root / "data" / "normalized",
        "ALIGNED_DIR": root / "data" / "aligned",
        "SPLITS_DIR": root / "data" / "aligned" / "splits",
        "AUDIT_DIR": root / "data" / "audit",
        "MANIFESTS_DIR": root / "data" / "manifests",
        "REPORTS_DIR": root / "reports",
        "LOGS_DIR": root / "logs",
        "TESTS_DIR": root / "tests",
    }
    for path in dirs.values():
        path.mkdir(parents=True, exist_ok=True)

    # Patch every loaded module that binds a path constant: the package
    # modules (they import names with ``from .models import ...``) and the
    # test modules (they import constants at collection time).
    for name, mod in list(_sys.modules.items()):
        if mod is None:
            continue
        if not (name == "bible_scraper" or name.startswith("bible_scraper.")
                or name == "tests" or name.startswith("tests.")):
            continue
        for attr, value in dirs.items():
            if hasattr(mod, attr):
                monkeypatch.setattr(mod, attr, value)

    # derived constants computed at import time
    aligned = dirs["ALIGNED_DIR"]
    norm = dirs["NORMALIZED_DIR"]
    audit = dirs["AUDIT_DIR"]
    monkeypatch.setattr(reporting_mod, "QUALITY_MD", dirs["REPORTS_DIR"] / "quality_report.md")
    monkeypatch.setattr(reporting_mod, "QUALITY_JSON", dirs["REPORTS_DIR"] / "quality_report.json")
    monkeypatch.setattr(reporting_mod, "QUALITY_CSV", dirs["REPORTS_DIR"] / "quality_report.csv")
    monkeypatch.setattr(reporting_mod, "CHECKSUMS", dirs["REPORTS_DIR"] / "checksums.sha256")
    monkeypatch.setattr(reporting_mod, "SOURCE_MANIFEST", root / "SOURCE_MANIFEST.md")
    monkeypatch.setattr(reporting_mod, "FINAL_JSONL", (
        norm / "thadbsi_verses.jsonl",
        norm / "niv_verses.jsonl",
        audit / "alignment_audit.jsonl",
        aligned / "thadou_kuki_niv_parallel.jsonl",
        aligned / "thadou_kuki_niv_ml.jsonl",
        aligned / "splits" / "train.jsonl",
        aligned / "splits" / "validation.jsonl",
        aligned / "splits" / "test.jsonl",
    ))
    monkeypatch.setattr(
        cli_mod, "PROGRESS_PATH", dirs["MANIFESTS_DIR"] / "progress.json"
    )

    return SimpleNamespace(root=root, **dirs)


# ---------------------------------------------------------------------------
# Offline browser: real BrowserSession with all requests answered locally.
# ---------------------------------------------------------------------------
class MockedSite:
    """Serves fixture HTML for bible.com URLs without any network access."""

    def __init__(self, pages: Dict[str, str], session):
        self.pages = pages
        self.session = session
        self.requests: List[str] = []

    def _handler(self, route) -> None:
        url = route.request.url
        self.requests.append(url)
        html = self.pages.get(url)
        if html is None:
            route.fulfill(status=404, content_type="text/html",
                          body="<html><body>not found</body></html>")
        else:
            route.fulfill(status=200, content_type="text/html; charset=utf-8",
                          body=html)

    def __enter__(self) -> "MockedSite":
        self.session.start()
        self.session._context.route("**/*", self._handler)
        return self

    def __exit__(self, *exc) -> None:
        self.session.stop()


def mocked_site(pages: Dict[str, str], **session_kwargs) -> MockedSite:
    """Build a MockedSite wrapping a headless BrowserSession (offline)."""
    kwargs = dict(headed=False, min_delay=0.0, max_delay=0.0,
                  max_retries=1, timeout_ms=10_000, selector_timeout_ms=2_000)
    kwargs.update(session_kwargs)
    return MockedSite(pages, models_session(**kwargs))


def models_session(**kwargs):
    from bible_scraper.browser import BrowserSession

    return BrowserSession(**kwargs)


# ---------------------------------------------------------------------------
# HTML fixtures mirroring bible.com's DOM
# ---------------------------------------------------------------------------
# NOTE: all fixture verse text below is SYNTHETIC (never published text);
# tests only verify structure and that published text passes through verbatim.

CHAPTER_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>{title_text}</title>
<link rel="canonical" href="{url}"/>
<meta property="og:url" content="{url}"/>
</head>
<body>
<nav><a href="{version_link}">{version_name}</a></nav>
<h1>{h1}</h1>
{body}
<footer><a href="/terms">Terms</a></footer>
</body>
</html>
"""


def _split_at_space(text: str) -> "tuple[str, str]":
    """Split *text* just after a whitespace run near the middle, so a
    poetry-style split span preserves the source spacing exactly."""
    mid = len(text) // 2
    best = None
    best_dist = None
    for i, ch in enumerate(text):
        if ch.isspace():
            dist = abs(i - mid)
            if best is None or dist < best_dist:
                best, best_dist = i, dist
    if best is None:
        return text, ""
    return text[: best + 1], text[best + 1 :]


def chapter_html(
    *,
    url: str,
    version_code: str,
    version_id: int,
    version_name: str,
    book_code: str,
    book_name: str,
    chapter: int,
    verses: Sequence[str],
    heading: str = "Chapter heading (must be excluded)",
    notes: Optional[Dict[str, str]] = None,
    split_verses: Iterable[int] = (),
    with_container: bool = True,
    title_prefix: Optional[str] = None,
    full_title: Optional[str] = None,
) -> str:
    """Render one chapter page in bible.com's structural shape.

    ``verses[i]`` is the published text of verse ``i+1`` (kept verbatim).
    ``notes`` maps 1-based verse number -> footnote text placed *inside* that
    verse span (must never leak into the verse text). ``split_verses`` lists
    verse numbers rendered as two ``__content`` spans split at a space, the
    way poetry lines are published. ``full_title`` sets the exact ``<title>``
    text (the live site sometimes serves a chapter-intro title with no
    version code); by default the title is "<book> <ch> | <code> Bible - Bible
    App" as observed on the site.
    """
    notes = dict(notes or {})
    body_parts: List[str] = []
    for i, text in enumerate(verses, start=1):
        ref = f"{book_code}.{chapter}.{i}"
        parts: List[str] = [f'<span class="AbC1x__label">{i}</span>']
        if i in split_verses:
            left, right = _split_at_space(text)
            parts.append(f'<span class="AbC1x__content">{left}</span>')
            if right:
                parts.append(f'<span class="AbC1x__content">{right}</span>')
        else:
            parts.append(f'<span class="AbC1x__content">{text}</span>')
        if i in notes:
            # cross-reference inside the note also carries data-usfm (USFM 3.0)
            parts.append(
                f'<span class="AbC1x__note">{notes[i]}'
                f'<a class="AbC1x__ref" data-usfm="{ref}">v.1</a></span>'
            )
        body_parts.append(
            f'  <span class="AbC1x__verse hover" data-usfm="{ref}">'
            + "".join(parts) + "</span>"
        )
    if with_container:
        body = (
            f'<div class="AbC1x__chapter" data-usfm="{book_code}.{chapter}">\n'
            f'  <div class="AbC1x__label">{chapter}</div>\n'
            f'  <div class="AbC1x__heading">{heading}</div>\n'
            + "\n".join(body_parts)
            + "\n</div>"
        )
    else:
        body = '<div class="AbC1x__placeholder">This chapter does not exist.</div>'
    base_title = title_prefix or f"{book_name} {chapter}"
    title_text = full_title or f"{base_title} | {version_code} Bible - Bible App"
    return CHAPTER_TEMPLATE.format(
        title_text=title_text,
        version_code=version_code,
        url=url,
        version_link=f"/versions/{version_id}-fixture-{version_code.lower()}",
        version_name=version_name,
        h1=f"{book_name} {chapter}",
        body=body,
    )


VERSION_PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"/>
<title>{title}</title>
<link rel="canonical" href="{url}"/>
</head>
<body>
<h1>{title}</h1>
{sections}
</body>
</html>
"""


def version_page_html(cfg, book_names: Dict[str, str]) -> str:
    """Render a version page with all 66 books (testament H2 + book H3)."""
    sections: List[str] = []
    for testament, codes in (
        ("Old Testament", CANONICAL_BOOK_ORDER[:39]),
        ("New Testament", CANONICAL_BOOK_ORDER[39:]),
    ):
        sections.append(f"<h2>{testament}</h2>")
        for code in codes:
            name = book_names.get(code, code)
            sections.append(f"<h3>{name}</h3>")
            sections.append('<div class="chapters">')
            for ch in range(1, CANONICAL_CHAPTERS[code] + 1):
                href = f"/bible/{cfg.version_id}/{code}.{ch}.{cfg.version_code}"
                label = "Read Now" if ch == 1 else str(ch)
                sections.append(f'<a href="{href}">{label}</a>')
                if ch == 1:  # duplicate "Read Now" link as on the live page
                    sections.append(f'<a href="{href}">{label}</a>')
            href = f"/bible/{cfg.version_id}/{code}.INTRO1.{cfg.version_code}"
            sections.append(f'<a href="{href}">Intro</a>')
            sections.append("</div>")
    return VERSION_PAGE_TEMPLATE.format(
        title=cfg.version_name, url=cfg.url, sections="\n".join(sections)
    )


# THADBSI display names observed on the live site (labels only; codes decide).
THADBSI_BOOK_NAMES = {
    "GEN": "Semtilbu", "EXO": "Potdohbu", "LEV": "Thempudan", "NUM": "Minbu",
    "DEU": "Danbu", "PSA": "Labu", "JHN": "John", "ACT": "Solchah",
    "ROM": "Rome", "REV": "Thuphon",
}

NIV_BOOK_NAMES = {
    "GEN": "Genesis", "EXO": "Exodus", "LEV": "Leviticus", "NUM": "Numbers",
    "DEU": "Deuteronomy", "PSA": "Psalms", "JHN": "John", "ACT": "Acts",
    "ROM": "Romans", "REV": "Revelation",
}


@pytest.fixture
def thad_cfg():
    return models_mod.VERSIONS["THADBSI"]


@pytest.fixture
def niv_cfg():
    return models_mod.VERSIONS["NIV"]


# ---------------------------------------------------------------------------
# Raw capture + discovery payload builders (offline, mirror extractor output)
# ---------------------------------------------------------------------------
def make_raw_chapter(
    cfg,
    book_code: str,
    book_name: str,
    chapter: int,
    verses: Sequence[str],
    *,
    language_status: str = "verified",
    failing: Optional[Sequence[str]] = None,
    title: Optional[str] = None,
) -> dict:
    """Build one raw capture exactly like ``extraction.extract_chapter``."""
    from bible_scraper.extraction import content_hash

    verse_records = [
        {"reference": f"{book_code}.{chapter}.{i}", "verse": str(i),
         "label": str(i), "text": text, "span_count": 1,
         "parts": [{"text": text, "note_before": False}]}
        for i, text in enumerate(verses, start=1)
    ]
    url = cfg.chapter_url(book_code, chapter)
    return {
        "version": cfg.key,
        "version_id": cfg.version_id,
        "version_code": cfg.version_code,
        "book_code": book_code,
        "book_name": book_name,
        "chapter": chapter,
        "url": url,
        "retrieved_at": "2026-09-27T00:00:00+00:00",
        "content_hash": content_hash(verse_records),
        "page": {
            "title": title or f"{book_name} {chapter} | {cfg.version_code} Bible - Bible App",
            "url": url,
            "canonical": url,
            "og_url": url,
            "lang": "en",
            "h1": f"{book_name} {chapter}",
            "version_links": [f"/versions/{cfg.version_id}-fixture"],
        },
        "chapter_label": str(chapter),
        "heading": None,
        "selector_fallback": False,
        "navigation_attempts": 1,
        "anomalies": [],
        "language_verification": {
            "expected": "thadou-kuki" if cfg.key == "THADBSI" else "english",
            "status": language_status,
            "method": ["version_metadata", "page_metadata", "DOM_context"],
            "checks": {}, "failing": list(failing or []),
            "supplementary": {}, "empty_verse_count": 0,
            "validated_at": "2026-09-27T00:00:00+00:00",
        },
        "verse_count": len(verse_records),
        "verses": verse_records,
    }


def write_raw_chapter(cfg, book_code: str, book_name: str, chapter: int,
                      verses: Sequence[str], **kwargs) -> Path:
    """Persist one raw capture where ``collect`` would write it."""
    payload = make_raw_chapter(cfg, book_code, book_name, chapter, verses, **kwargs)
    path = models_mod.RAW_DIR / cfg.raw_dirname / book_code / f"{chapter:03d}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    models_mod.atomic_write_json(path, payload)
    return path


def full_book_payload(cfg, book_names: Dict[str, str], discovered_at: str = "2026-09-27T00:00:00+00:00") -> dict:
    """A discovery payload with all 66 books (canonical chapter counts)."""
    books = []
    for code in CANONICAL_BOOK_ORDER:
        books.append({
            "code": code,
            "name": book_names.get(code, code),
            "testament": "Old Testament" if CANONICAL_BOOK_ORDER.index(code) < 39 else "New Testament",
            "chapters": list(range(1, CANONICAL_CHAPTERS[code] + 1)),
            "intro_url": f"/bible/{cfg.version_id}/{code}.INTRO1.{cfg.version_code}",
            "version_code": cfg.version_code,
            "anchor_sample": [f"/bible/{cfg.version_id}/{code}.1.{cfg.version_code}"],
        })
    payload = {
        "page": {"title": cfg.version_name, "url": cfg.url, "h1": cfg.version_name,
                 "canonical": cfg.url, "lang": "en"},
        "books": books,
        "duplicate_chapter_urls": [],
        "version_codes_seen": [cfg.version_code],
        "discovered_at": discovered_at,
        "version": cfg.key,
        "version_id": cfg.version_id,
        "version_code": cfg.version_code,
        "version_name": cfg.version_name,
        "version_url": cfg.url,
        "publisher": cfg.publisher,
        "manifest_prefix": cfg.manifest_prefix,
        "navigation_attempts": 1,
    }
    payload["validation"] = discovery_mod.validate_discovery(payload, cfg)
    return payload


# Miniature corpus used by alignment/validation/schema tests: seven chapters
# across six books, covering every manual spot-check reference. All text is
# synthetic fixture text (never published source text).
# (book_code, chapter, verse_count) — same verse numbers on both versions.
MINI_SPECS = [
    ("GEN", 1, 3),
    ("GEN", 3, 16),
    ("PSA", 23, 3),
    ("MAT", 1, 2),
    ("JHN", 3, 16),
    ("ROM", 8, 28),
    ("REV", 22, 21),
]

# THADBSI display labels: observed on the live site where known (GEN, PSA,
# JHN, ROM, REV), test fixture label otherwise. Names are labels only.
THADBSI_MINI_NAMES = {
    "GEN": "Semtilbu", "PSA": "Labu", "MAT": "Matthew",
    "JHN": "John", "ROM": "Rome", "REV": "Thuphon",
}
NIV_MINI_NAMES = {
    "GEN": "Genesis", "PSA": "Psalms", "MAT": "Matthew",
    "JHN": "John", "ROM": "Romans", "REV": "Revelation",
}

# THADBSI side: synthetic pseudo-text with low English stopword density so
# the supplementary heuristic stays within range.
THADBSI_VERSE_TEMPLATE = "Chinha {ch} pathen {i} hong ahi mawhna le ahi."
# NIV side: synthetic English with high stopword density.
NIV_VERSE_TEMPLATE = (
    "In the book of the Lord this is verse {i} of chapter {ch}, and the word "
    "of God was with the people of the land."
)


def mini_verses(version_key: str, chapter: int, count: int) -> List[str]:
    template = THADBSI_VERSE_TEMPLATE if version_key == "THADBSI" else NIV_VERSE_TEMPLATE
    return [template.format(ch=chapter, i=i) for i in range(1, count + 1)]


def mini_book_names(version_key: str) -> Dict[str, str]:
    return THADBSI_MINI_NAMES if version_key == "THADBSI" else NIV_MINI_NAMES


def write_mini_discovery(project) -> None:
    """Write book/chapter manifests + book_mapping for the mini corpus.

    ``MINI_SPECS`` applies to both versions (same chapters on each side).
    """
    payloads = {}
    for key in ("THADBSI", "NIV"):
        cfg = models_mod.VERSIONS[key]
        wanted = {code for (code, _ch, _count) in MINI_SPECS}
        payload = full_book_payload(cfg, mini_book_names(key))
        for book in payload["books"]:
            if book["code"] not in wanted:
                book["chapters"] = []
            else:
                book["chapters"] = sorted(
                    ch for (code, ch, _count) in MINI_SPECS if code == book["code"]
                )
        payload["validation"] = discovery_mod.validate_discovery(payload, cfg)
        payloads[key] = payload
    discovery_mod.write_discovery_outputs(payloads)


def write_mini_raw_corpus(project) -> None:
    """Write raw captures for every mini chapter, both versions."""
    for key in ("THADBSI", "NIV"):
        cfg = models_mod.VERSIONS[key]
        names = mini_book_names(key)
        for code, chapter, count in MINI_SPECS:
            write_raw_chapter(
                cfg, code, names[code], chapter,
                mini_verses(key, chapter, count),
            )

@pytest.fixture
def mini_corpus(project):
    """Isolated project with discovery + raw corpus + normalized/aligned data.

    Tests can mutate the raw captures and re-run ``run_offline_pipeline()`` to
    observe how downstream stages react.
    """
    write_mini_discovery(project)
    write_mini_raw_corpus(project)
    normalize_version(VERSIONS["THADBSI"])
    normalize_version(VERSIONS["NIV"])
    align(load_normalized(VERSIONS["THADBSI"]),
          load_normalized(VERSIONS["NIV"]),
          VERSIONS["THADBSI"], VERSIONS["NIV"])
    return project
