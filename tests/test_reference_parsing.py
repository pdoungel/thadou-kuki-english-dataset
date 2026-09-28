"""Canonical reference parsing and ordering (never text similarity)."""

from __future__ import annotations

import pytest

from bible_scraper.alignment import _ref_sort_key, split_bucket, split_for_book
from bible_scraper.extraction import USFM_RE, split_usfm, _verse_order_key, group_spans
from bible_scraper.normalization import format_reference, parse_reference


@pytest.mark.parametrize(
    "usfm,expected",
    [
        ("GEN.1.1", ("GEN", 1, "1")),
        ("REV.22.21", ("REV", 22, "21")),
        ("1SA.2.10", ("1SA", 2, "10")),
        ("2KI.1.1", ("2KI", 1, "1")),
        ("1JN.1.9", ("1JN", 1, "9")),
        ("PSA.119.1", ("PSA", 119, "1")),
        ("GEN.1.1a", ("GEN", 1, "1a")),  # split-verse suffix (USFM 3.0)
        ("GEN.1", None),
        ("GEN.1.1.2", None),
        ("", None),
        ("gen.1.1", None),  # codes are uppercase
    ],
)
def test_split_usfm(usfm, expected):
    assert split_usfm(usfm) == expected


def test_split_usfm_accepts_three_letter_codes_only():
    assert split_usfm("SON.1.1") is not None  # structurally valid USFM ref
    assert split_usfm("GENESIS.1.1") is None
    assert split_usfm("G1N.1.1") is not None  # shape check, not a canon check


@pytest.mark.parametrize("bad", ["", "GEN", "GEN.1", "GEN.1.", "GEN..1", "GEN.1.1.", "abc.1.1"])
def test_parse_reference_rejects_malformed(bad):
    with pytest.raises(ValueError):
        parse_reference(bad)


def test_parse_reference_round_trip():
    for ref in ("GEN.1.1", "1SA.2.10", "PSA.119.176", "REV.22.21", "JHN.3.16"):
        book, chapter, verse = parse_reference(ref)
        assert format_reference(book, chapter, verse) == ref


def test_usfm_regex_matches_reference_only():
    assert USFM_RE.match("GEN.1.1")
    assert not USFM_RE.match("GEN.INTRO1")
    assert not USFM_RE.match("GEN.1")


def test_verse_order_key_is_numeric_not_lexicographic():
    refs = ["GEN.1.10", "GEN.1.2", "GEN.1.1", "GEN.1.21", "GEN.2.1", "GEN.1.3a"]
    ordered = sorted(refs, key=_verse_order_key)
    assert ordered == [
        "GEN.1.1", "GEN.1.2", "GEN.1.3a", "GEN.1.10", "GEN.1.21", "GEN.2.1",
    ]


def test_reference_sort_key_uses_canonical_book_order():
    refs = ["REV.1.1", "GEN.1.1", "1SA.1.1", "PSA.1.1", "MAT.1.1", "ZZZ.1.1"]
    ordered = sorted(refs, key=_ref_sort_key)
    assert ordered == ["GEN.1.1", "1SA.1.1", "PSA.1.1", "MAT.1.1", "REV.1.1", "ZZZ.1.1"]


def test_group_spans_rejects_foreign_references():
    """Spans from another chapter are reported as anomalies, never merged."""
    spans = [
        {"usfm": "GEN.1.1", "label": "1", "parts": [{"text": "first", "note_before": False}]},
        {"usfm": "EXO.1.1", "label": "1", "parts": [{"text": "foreign", "note_before": False}]},
        {"usfm": "garbage", "label": None, "parts": [{"text": "x", "note_before": False}]},
    ]
    verses, anomalies = group_spans(spans, "GEN", 1)
    assert [v["reference"] for v in verses] == ["GEN.1.1"]
    assert verses[0]["text"] == "first"
    assert sorted(anomalies) == ["unexpected_usfm:EXO.1.1", "unexpected_usfm:garbage"]


def test_split_bucket_is_stable_and_covers_all_books():
    from bible_scraper.models import CANONICAL_BOOK_ORDER

    first = {code: split_bucket(code) for code in CANONICAL_BOOK_ORDER}
    # deterministic across calls (same process; hash input is just the code)
    assert first == {code: split_bucket(code) for code in CANONICAL_BOOK_ORDER}
    assert all(0 <= b <= 9 for b in first.values())
    # whole-book assignment: one label per book
    labels = {code: split_for_book(code) for code in CANONICAL_BOOK_ORDER}
    assert set(labels) == set(CANONICAL_BOOK_ORDER)
    assert set(labels.values()) <= {"train", "validation", "test"}
    # books landing in different buckets must not share a split label collision
    by_bucket = {}
    for code, b in first.items():
        by_bucket.setdefault(b, set()).add(labels[code])
    assert all(len(s) == 1 for s in by_bucket.values())
