"""Conservative Unicode normalization for Thadou-Kuki preprocessing.

This operates on copies of source data and deliberately avoids spelling correction.
"""
from __future__ import annotations
import re
import unicodedata

SPACE_RE = re.compile(r"[ \t\r\f\v]+")

def normalize(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\u00a0", " ").replace("\u200b", "")
    return SPACE_RE.sub(" ", text).strip()

def normalize_lines(lines: list[str]) -> list[str]:
    return [normalize(x) if x else "" for x in lines]
