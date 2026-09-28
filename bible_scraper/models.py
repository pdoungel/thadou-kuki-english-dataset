"""Configuration, paths, canonical Bible tables, and small data models."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

# --------------------------------------------------------------------------
# Paths — everything this project writes lives under the bible/ project root.
# --------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DISCOVERY_DIR = DATA_DIR / "discovery"
RAW_DIR = DATA_DIR / "raw"
NORMALIZED_DIR = DATA_DIR / "normalized"
ALIGNED_DIR = DATA_DIR / "aligned"
SPLITS_DIR = ALIGNED_DIR / "splits"
AUDIT_DIR = DATA_DIR / "audit"
MANIFESTS_DIR = DATA_DIR / "manifests"
REPORTS_DIR = ROOT / "reports"
LOGS_DIR = ROOT / "logs"
TESTS_DIR = ROOT / "tests"

ALL_DIRS = (
    DISCOVERY_DIR,
    RAW_DIR / "thad_bible",
    RAW_DIR / "niv",
    NORMALIZED_DIR,
    ALIGNED_DIR,
    SPLITS_DIR,
    AUDIT_DIR,
    MANIFESTS_DIR,
    REPORTS_DIR,
    LOGS_DIR,
)


def ensure_dirs() -> None:
    for d in ALL_DIRS:
        d.mkdir(parents=True, exist_ok=True)


def atomic_write_json(path: Path, payload) -> None:
    """Write JSON atomically so an interrupted run never truncates state files."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


# --------------------------------------------------------------------------
# Version configuration (facts taken from the live site during investigation)
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class VersionConfig:
    key: str  # THADBSI | NIV
    version_id: int
    version_code: str
    version_name: str
    language: str
    language_code: str  # ISO 639-3 as used by bible.com (tcz / eng)
    publisher: str
    url: str  # version page URL
    raw_dirname: str  # data/raw/<raw_dirname>/
    manifest_prefix: str  # data/manifests/<manifest_prefix>_*

    def chapter_url(self, book_code: str, chapter: int) -> str:
        return f"https://www.bible.com/bible/{self.version_id}/{book_code}.{chapter}.{self.version_code}"


VERSIONS: Dict[str, VersionConfig] = {
    "THADBSI": VersionConfig(
        key="THADBSI",
        version_id=1879,
        version_code="THADBSI",
        version_name="Pathen Thutheng BU (BSI)",
        language="Thadou Kuki",
        language_code="tcz",
        publisher="Bible Society of India",
        url="https://www.bible.com/versions/1879-thadbsi-pathen-thutheng-bu-bsi",
        raw_dirname="thad_bible",
        manifest_prefix="thadbsi",
    ),
    "NIV": VersionConfig(
        key="NIV",
        version_id=111,
        version_code="NIV",
        version_name="New International Version",
        language="English",
        language_code="eng",
        publisher="Biblica",
        url="https://www.bible.com/versions/111-niv-new-international-version",
        raw_dirname="niv",
        manifest_prefix="niv",
    ),
}


def get_version(key: str) -> VersionConfig:
    k = (key or "").strip().upper()
    if k not in VERSIONS:
        raise KeyError(f"unknown version {key!r}; expected one of {sorted(VERSIONS)}")
    return VERSIONS[k]


# --------------------------------------------------------------------------
# Canonical Protestant book order and chapter counts.
# Used ONLY as an independent expectation for quality control. Discovery is
# always driven by the live site; these tables never generate chapter lists.
# --------------------------------------------------------------------------
CANONICAL_BOOK_ORDER: List[str] = [
    "GEN", "EXO", "LEV", "NUM", "DEU", "JOS", "JDG", "RUT", "1SA", "2SA",
    "1KI", "2KI", "1CH", "2CH", "EZR", "NEH", "EST", "JOB", "PSA", "PRO",
    "ECC", "SNG", "ISA", "JER", "LAM", "EZK", "DAN", "HOS", "JOL", "AMO",
    "OBA", "JON", "MIC", "NAM", "HAB", "ZEP", "HAG", "ZEC", "MAL",
    "MAT", "MRK", "LUK", "JHN", "ACT", "ROM", "1CO", "2CO", "GAL", "EPH",
    "PHP", "COL", "1TH", "2TH", "1TI", "2TI", "TIT", "PHM", "HEB", "JAS",
    "1PE", "2PE", "1JN", "2JN", "3JN", "JUD", "REV",
]

CANONICAL_CHAPTERS: Dict[str, int] = {
    "GEN": 50, "EXO": 40, "LEV": 27, "NUM": 36, "DEU": 34, "JOS": 24,
    "JDG": 21, "RUT": 4, "1SA": 31, "2SA": 24, "1KI": 22, "2KI": 25,
    "1CH": 29, "2CH": 36, "EZR": 10, "NEH": 13, "EST": 10, "JOB": 42,
    "PSA": 150, "PRO": 31, "ECC": 12, "SNG": 8, "ISA": 66, "JER": 52,
    "LAM": 5, "EZK": 48, "DAN": 12, "HOS": 14, "JOL": 3, "AMO": 9,
    "OBA": 1, "JON": 4, "MIC": 7, "NAM": 3, "HAB": 3, "ZEP": 3,
    "HAG": 2, "ZEC": 14, "MAL": 4,
    "MAT": 28, "MRK": 16, "LUK": 24, "JHN": 21, "ACT": 28, "ROM": 16,
    "1CO": 16, "2CO": 13, "GAL": 6, "EPH": 6, "PHP": 4, "COL": 4,
    "1TH": 5, "2TH": 3, "1TI": 6, "2TI": 4, "TIT": 3, "PHM": 1,
    "HEB": 13, "JAS": 5, "1PE": 5, "2PE": 3, "1JN": 5, "2JN": 1,
    "3JN": 1, "JUD": 1, "REV": 22,
}

CANONICAL_TOTAL_CHAPTERS = sum(CANONICAL_CHAPTERS.values())  # 1189

# --------------------------------------------------------------------------
# Progress states for data/manifests/progress.json
# --------------------------------------------------------------------------
STATUS_DISCOVERED = "discovered"
STATUS_QUEUED = "queued"
STATUS_FETCHING = "fetching"
STATUS_EXTRACTED = "extracted"
STATUS_VERIFIED = "verified"
STATUS_FAILED = "failed"

PROGRESS_STATES = (
    STATUS_DISCOVERED,
    STATUS_QUEUED,
    STATUS_FETCHING,
    STATUS_EXTRACTED,
    STATUS_VERIFIED,
    STATUS_FAILED,
)

# A chapter counts as complete only when extraction AND validation succeeded.
COMPLETE_STATES = (STATUS_EXTRACTED, STATUS_VERIFIED)


@dataclass
class ChapterTask:
    """One chapter to collect."""

    version: str
    book_code: str
    chapter: int
    url: str
    discovered_at: str
    status: str = STATUS_DISCOVERED

    @property
    def key(self) -> str:
        return f"{self.book_code}.{self.chapter}"

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "book_code": self.book_code,
            "chapter": self.chapter,
            "url": self.url,
            "discovered_at": self.discovered_at,
            "status": self.status,
        }
