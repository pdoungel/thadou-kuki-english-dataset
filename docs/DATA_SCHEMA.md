# Data schema — Thadou-Kuki (THADBSI) ↔ English (NIV) Bible alignment

Every JSON Lines file is UTF-8, one JSON object per line, `\n`-terminated, keys in
the order shown. `null` is JSON `null`, never the string `"null"`.

Field documentation below is transcribed from the artifacts themselves, not from
intent. Where a field is absent from a row it is absent from the schema.

Files are split into two classes:

| Class | In this repository? | Files |
|---|---|---|
| **Metadata / audit / reports** (no verse text) | yes | `data/audit/*`, `data/manifests/*`, `data/discovery/*`, `data/aligned/splits/split_manifest.json`, `reports/*`, `logs/*` |
| **Verse text** (restricted — never committed) | no, local only | `data/aligned/*.jsonl`, `data/aligned/splits/{train,validation,test}.jsonl`, `data/normalized/*.jsonl`, `data/raw/**` |

See [`DATA_ACCESS.md`](DATA_ACCESS.md) for the redistribution rationale, expected
local paths, sizes and SHA-256 digests.

---

## 1. `data/aligned/thadou_kuki_niv_parallel.jsonl` — *(local only)*

The aligned parallel corpus: one row per aligned verse reference.

```jsonc
{
  "id": "GEN.1.1",                  // == reference; unique across the file
  "reference": "GEN.1.1",           // canonical reference: BOOK.CH.VERSE
  "book_code": "GEN",               // canonical 3-letter book code
  "book_name_thadou_kuki": "Semtilbu",   // book name as THADBSI publishes it
  "book_name_english": "Genesis",        // book name as NIV publishes it
  "chapter": 1,
  "verse": 1,
  "thadou_kuki": "…",               // published THADBSI verse text
  "english": "…",                   // published NIV verse text
  "source": {                       // provenance of both sides, per row
    "thadou_kuki": {
      "version_id": 1879,
      "version_code": "THADBSI",
      "url": "https://www.bible.com/bible/1879/GEN.1.THADBSI"
    },
    "english": {
      "version_id": 111,
      "version_code": "NIV",
      "url": "https://www.bible.com/bible/111/GEN.1.NIV"
    }
  },
  "split": "train",                 // train | validation | test (whole-book)
  "identical_text_flag": false      // true if both sides are byte-identical
}
```

* `identical_text_flag` is a contamination signal, not a content change. Rows are
  never altered or dropped because of it; the flag exists so a downstream user can
  filter cross-version leakage if they choose.
* Rows are unique by `id`. 31,087 rows.

## 2. `data/aligned/thadou_kuki_niv_ml.jsonl` — *(local only)*

Training view of the same corpus: only the fields an MT/SFT loader needs.

```jsonc
{
  "id": "GEN.1.1",
  "source": "…",    // Thadou-Kuki (THADBSI) text
  "target": "…"     // English (NIV) text
}
```

31,087 rows, same order as file 1, same `id` on every row.

## 3. `data/aligned/splits/{train,validation,test}.jsonl` — *(local only)*

Identical schema to file 1, partitioned by book. Row counts:
`train` 27,279 / `validation` 2,869 / `test` 939.

## 4. `data/aligned/splits/split_manifest.json` — *committed*

```jsonc
{
  "generated_at": "2026-09-27T14:10:10+00:00",
  "method": "whole-book split; bucket = int(sha256(book_code)[:8], 16) mod 10",
  "buckets": {
    "train": "0-7 (target ~80%)",
    "validation": "8 (target ~10%)",
    "test": "9 (target ~10%)"
  },
  "books": { "train": ["1CH", "1CO", …], "validation": [...], "test": [...] },
  "counts": {
    "train":      { "verses": 27279, "books": 55 },
    "validation": { "verses": 2869,  "books": 7 },
    "test":       { "verses": 939,   "books": 4 }
  },
  "total_parallel_verses": 31087
}
```

Book-level assignment only: no verse text, no per-verse records. The assignment is
a pure function of `book_code`, so it is reproducible without any verse text and
is stable across reruns.

## 5. `data/audit/alignment_audit.jsonl` — *committed* (12,154,063 bytes)

One record for **every** canonical reference considered — aligned or not. This is
why the file has 31,104 records while the corpus has 31,087 pairs: the audit keeps
a row for the 17 references that could not be aligned, so nothing is silently
dropped.

```jsonc
{
  "reference": "REV.12.18",
  "book_code": "REV",
  "chapter": 12,
  "verse": 18,
  "thadou_status": "present",       // present | missing | present_no_text | ...
  "niv_status": "missing",          // present | missing | present_no_text | ...
  "alignment_status": "missing_niv",// aligned | missing_niv | missing_thadou |
                                    // duplicate_thadou | duplicate_niv |
                                    // language_uncertain | extraction_error
  "thadou_text_hash": "…64 hex…",   // sha256 of the normalized text, or null
  "niv_text_hash": null,
  "reason": "reference present in the capture but the source publishes no verse text for it (label '[11]'; verse bracketed/omitted in this edition)",
  "recorded_at": "2026-09-27T14:10:10+00:00"
}
```

* **There is no text field in this file.** Both sides are represented by sha256
  content hashes, so the record is verifiable against a local copy without
  republishing either text.
* `reason` is an operator explanation, max 134 characters, never verse text.
* 19 distinct `reason` values across the whole file.

## 6. `data/audit/alignment_summary.json` — *committed*

Run-level counters: `counts` (`aligned`, `missing_thadou`, `missing_niv`,
`duplicate_thadou`, `duplicate_niv`, `language_uncertain`, `extraction_error`),
`parallel_verses`, `ml_verses`, `audit_records`, `contaminated_chapters`, and the
local `files` paths of the generated artifacts.

## 7. `data/audit/verification.json` — *committed*

The output of `python -m bible_scraper verify`. Gates the release: the project is
only "complete" when `ok` and `complete` are both `true`.

```jsonc
{
  "generated_at": "…", "ok": true, "complete": true,
  "checks": {                    // named boolean/string gates
    "manifests_THADBSI": "pass", "manifests_NIV": "pass", "book_mapping": "pass",
    "raw_captures": "pass", "normalized_deduplicated": "pass",
    "parallel_schema": "pass", "ml_schema": "pass", "no_duplicate_ids": "pass",
    "audit_reconciles": "pass", "split_whole_books": "pass",
    "uncertain_excluded_from_corpus": "pass", "spot_checks": "pass"
  },
  "counts": { "aligned_pairs": 31087, "audit_records": 31104, … },
  "uncertain_chapters": [],
  "empty_verses_in_raw": [ … ],
  "spot_checks": [                // 7 rows: both texts + both URLs
    { "reference": "GEN.1.1", "found": true, "thadou_kuki": "…",
      "english": "…", "thadou_url": "…", "niv_url": "…" }
  ],
  "problems": []
}
```

> **Excerpt notice:** `spot_checks` embeds 7 verse pairs (both languages) as live
> verification evidence. `reports/quality_report.json` carries the same 7-entry array and
> `reports/quality_report.md` renders the same 7 as its `## Manual spot checks` table. These
> excerpts are retained deliberately as part of the audit record; the corpora themselves are
> withheld. See [`DATA_ACCESS.md`](DATA_ACCESS.md) §4.

## 8. `data/manifests/progress.json` — *committed* (877,075 bytes)

Resumable collection state, keyed by version then chapter.

```jsonc
{
  "generated_at": "…",
  "versions": {
    "THADBSI": {
      "GEN.1": {
        "status": "verified",      // pending | extracted | verified | failed
        "url": "https://www.bible.com/bible/1879/GEN.1.THADBSI",
        "attempts": 1,
        "error": null,
        "updated_at": "2026-09-27T10:51:05+00:00",
        "verses": 31,
        "language_status": "verified",
        "content_hash": "db03a510…"
      }, …
    }, "NIV": { … }
  }
}
```

2,378 chapter entries, all `status: "verified"`.

## 9. `data/manifests/book_mapping.json` — *committed*

```jsonc
{
  "generated_at": "…",
  "source": "…",                   // how the mapping was derived
  "canonical_order": ["GEN", "EXO", …],   // 66 codes
  "books": {
    "GEN": { "thadbsi_name": "Semtilbu", "english_name": "Genesis", … }
  }
}
```

Keyed on the canonical code from the URL (`…/GEN.1.THADBSI`), never on a display
name — the THADBSI display names are localized and would not round-trip.

## 10. `data/manifests/{thadbsi,niv}_{books,chapters}.jsonl|json` — *committed*

Discovery output: version identity (`version_id`, `version_code`, `version_name`,
`version_url`, `publisher`), book counts, and one line per discovered chapter:

```jsonc
{
  "version": "THADBSI", "book": "Semtilbu", "book_code": "GEN", "chapter": 1,
  "url": "https://www.bible.com/bible/1879/GEN.1.THADBSI",
  "discovered_at": "2026-09-27T10:50:53+00:00", "status": "discovered"
}
```

66 books and 1,189 chapters per version. No verse text.

## 11. `data/discovery/{thadbsi,niv}_version_page.json` — *committed*

Captured version-page evidence: `page` (`title`, `url`, `h1`, `canonical`, `lang`)
plus the ordered `books` array (code + display name) used to build the mapping.

## 12. `reports/*` — *committed*

| File | Content |
|---|---|
| `quality_report.md` | Human-readable release report (statistics, alignment states, missing-verse policy, spot-check evidence) |
| `quality_report.json` | Same content, machine-readable (`sources`, `metrics`, `verification`, `spot_checks`, `split_manifest`, `checksums`) |
| `quality_report.csv` | Counter / value / description table |
| `checksums.sha256` | 2,386 `sha256sum`-format lines: 2,378 raw chapter captures + 8 final JSONL artifacts |

## 13. `logs/*` — *committed*

`scraper.log`, `audit.log`, `errors.log` — UTC-timestamped events carrying URLs,
attempt numbers, verse counts, status transitions and content hashes.
`errors.log` is empty (0 lines, 0 `ERROR` entries) for this run. Console captures
(`logs/*.out`) are ignored: `*.log` is the record of truth.

---

### Reference formats

* **Canonical reference** — `BOOK.CH.VERSE`, e.g. `GEN.1.1`, `REV.22.21`.
  Book is the canonical 3-letter code; chapter and verse are decimal, no padding.
* **Book codes** — the 66 codes in `book_mapping.json → canonical_order`.
* **Timestamps** — ISO 8601 with offset (`…+00:00`), always UTC for this run.
* **Content hashes** — lowercase hex sha256 of the whitespace-normalized text
  (`normalize_text`: collapse runs of whitespace to one space, trim ends).
