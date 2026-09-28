# Thadou-Kuki (tcz) ↔ English Dataset

Two verse-aligned corpora live in this repository, each with one authoritative location:

| Corpus | Location | Verse text in this repo? |
|---|---|---|
| eBible Chongthu + English WEB/KJV + GospelGo Thadou | `out/` — rebuild: `python build_dataset.py` (reads `raw/`) | yes — open-licence / public-domain sources |
| THADBSI ↔ NIV Bible alignment (66 books, 31,087 verse pairs) | `data/` + `reports/` + `bible_scraper/` | **no** — metadata, audit, checksums and code only ([why?](docs/DATA_ACCESS.md)) |

## Current contents (from eBible corpus)
| File | What |
|---|---|
| `out/parallel.tsv` | 30,814 verse-aligned rows: ref, Thadou (Chongthu), English (WEB), English (KJV), Thadou (gospelgo, 13k verses) |
| `out/train.jsonl` | 95,241 chat-format SFT examples, both directions |
| `out/val.jsonl` / `out/test.jsonl` | held-out BOOKS (Obad, Titus, Phlm, 2Jn, Nah / Ruth, Jonah, Phil, Jude, 3Jn) |
| `out/rag_corpus.jsonl` | one doc per verse with both languages, for embeddings |
| `out/lexicon_candidates.tsv` | auto word-alignment hints (mostly proper nouns; needs human review) |

Thadou text = **Pathen Lekhabu Theng, Chongthu dialect**, © 2020 Chongthu Bible Translation Team,
licensed **CC BY-SA 4.0** (attribution + share-alike; derived datasets/models must credit it and use the same license).
English = World English Bible + KJV (public domain).

## Other sources (collect manually / with permission)
| Source | Notes |
|---|---|
| YouVersion `THADBSI` Pathen Thutheng BU (BSI 2015), bible.com/versions/1879 | Standard Thadou + audio. © Bible Society of India — ask BSI for permission, don't scrape |
| bibliamundi.com Chin-Thado-All-Bible.pdf | Same BSI text as PDF |
| scriptureearth.org (iso=tcz) | text/audio/video index |
| globalrecordings.net/en/language/tcz | audio (good for STT) |
| gospelgo.com/a/kuki_bible.htm | Unicode Thadou Bible |
| Google Play "Thadou Kuki English Bible" (jaqer) | parallel app |
| UNT Digital Library: *Thadou-Kuki for Students, Teachers and Writers* | orthography, grammar, wordlists |
| *Grammar of Thadou-Kuki* (dokumen.pub), khalvontawi.in | grammar/oral literature |
| CIIL Bhasha Sanchika – Thadou collection | govt. language corpus |
| omniglot.com/writing/thadou.htm, Wikipedia | phrases, alphabet |
| Local bilingual papers (e.g. *The Hills Today*), church hymnals, Facebook/YouTube Kuki pages | modern everyday language — biggest gap |

Two Bibles (Chongthu + BSI) aligned on the same verses = extra target variety for free.
Not found: no Thadou in FLORES-200, NLLB, or any HF dataset yet → a published dataset would be the first.

> **Update.** A verse-aligned **THADBSI ↔ NIV** corpus has since been produced from the
> YouVersion pages listed above. It is published here as metadata + audit + code only — the
> text itself stays local. See
> [THADBSI ↔ NIV Bible alignment](#thadou-kuki-thadbsi--english-niv-bible-alignment) below.

## Limitation
Bible-only data gives archaic/religious register. For conversational quality add everyday sentences
(native-speaker written, or recorded speech transcribed with STT, then corrected).

## Collected files (`sources/`)
| File | From |
|---|---|
| `ebible_usfm/`, `tczchongthu_usfm.zip` | ebible.org Chongthu Bible, USFM (with footnotes/headings) |
| `ebible_readaloud/` | same, plain text per chapter (1,192 files), good for TTS scripts |
| `gospelgo_kuki_bible.html` → `raw/tcz-gospelgo.txt` | older standard Thadou Bible, parsed by `parse_gospelgo.py` (13,106 verses aligned) |
| `omniglot_thadou.html`, `wikipedia_thadou_language.html` | alphabet, phonology |
| `dimasa_basic_kuki_phrases.html` | everyday phrases |
| `khalvontawi_oral_literature.html` | oral literature article |
| `scriptureearth_tcz.html`, `unt_thadou_for_students.html` | index pages (links only) |

Could not auto-download (do by hand in a browser): BSI PDF on bibliamundi (503/SSL), mchip PDF (dead),
globalrecordings.net (403), UNT book (viewer only), YouVersion THADBSI (copyright, ask BSI).


## Language AI Studio

A local application is included under `app/` for corpus curation and future model development. It is designed from the start for both **Thadou-Kuki → English** and **English → Thadou-Kuki**.

See [app/README.md](app/README.md) for setup. The MVP provides dataset browsing, human review/correction, source-rights metadata, safe import, reviewed-data export, and a translation-workspace scaffold.

---

## THADBSI ↔ NIV Bible alignment

A verse-aligned parallel corpus pairing the Thadou-Kuki **THADBSI** edition
(*Pathen Thutheng BU (BSI)*, Bible Society of India, bible.com version **1879**) with the
English **NIV** (*New International Version*, Biblica, bible.com version **111**) across the
whole Bible: 66 books, 1,189 chapters, **31,087 aligned verse pairs**.

Produced by the browser-driven pipeline in [`bible_scraper/`](bible_scraper/)
and verified by its own release gate. The authoritative statistics record is
**[`reports/quality_report.md`](reports/quality_report.md)** (also
[`.json`](reports/quality_report.json) / [`.csv`](reports/quality_report.csv)) — the numbers
below were copied from it, not re-derived.

> **Text is not redistributed in this repository.** No license for either edition has been
> established, so no verse text is committed. What is published is the audit trail, reports,
> checksums, manifests and the code that rebuilds the corpus locally.
> See [`docs/DATA_ACCESS.md`](docs/DATA_ACCESS.md) and [`LICENSE_NOTES.md`](LICENSE_NOTES.md).

### Dataset statistics

| Metric | Value |
|---|---|
| Books / chapters per version | 66 / 1,189 → 2,378 chapter captures |
| Captures failed or unreadable | 0 |
| Normalized verses (THADBSI / NIV) | 31,104 / 31,103 |
| **Aligned verse pairs** | **31,087** |
| **Audit records** | **31,104** |
| Missing in THADBSI | 0 |
| Missing in NIV | 17 |
| Duplicates (THADBSI / NIV) | 0 / 0 |
| `language_uncertain` | 0 |
| `extraction_error` | 0 |
| Corpus SHA-256 (`thadou_kuki_niv_parallel.jsonl`) | `587e55fc710f29f19cad93c0caf7774fb5f7655f25fc488db0cd330781a6aeea` |
| Checksums | 2,386 entries (2,378 raw chapters + 8 final JSONL), 12 randomly re-verified, 0 mismatches |
| Retrieval window | `2026-09-27T10:51:05Z` → `2026-09-27T14:09:22Z` |
| `logs/errors.log` | 0 `ERROR` entries |
| Verification | 7/7 spot checks had both texts + both URLs; 6/6 independently sampled rows re-fetched byte-exact; all 2,378 chapter manifests marked `verified` |

### Why 31,104 audit records but 31,087 pairs

The audit keeps **one record for every canonical reference considered**, aligned or not, so the
17 non-aligned references are explicit rather than missing from the file:

* **16** are edition-level bracketed/footnote-only omissions — verses the NIV edition
  intentionally does not print as verse text.
* **1** is `REV.12.18`, which is absent from the NIV edition.
* All 17 are `missing_niv`; `missing_thadou` is **0**.

Nothing was imputed, interpolated or silently removed. Every record carries `thadou_status`,
`niv_status`, `alignment_status`, sha256 content hashes for both sides, a `reason` naming the
source label, and a timestamp — and **no text field at all**:

* [`data/audit/alignment_audit.jsonl`](data/audit/alignment_audit.jsonl) — 31,104 records
* [`data/audit/verification.json`](data/audit/verification.json) — release gate
* [`data/audit/alignment_summary.json`](data/audit/alignment_summary.json) — run counters

### Train / validation / test split

Whole-book, so no book leaks across splits:

| Split | Examples | Books |
|---|---:|---:|
| train | 27,279 | 55 |
| validation | 2,869 | 7 |
| test | 939 | 4 |

`bucket = int(sha256(book_code)[:8], 16) mod 10` → 0-7 train, 8 validation, 9 test. The
assignment is a pure function of the book code, so it is reproducible without any verse text:
[`data/aligned/splits/split_manifest.json`](data/aligned/splits/split_manifest.json).

### Methodology

* **Acquisition** — Playwright only (no `requests`/`curl`), public pages only, no auth, CAPTCHA
  or DRM handling; 0.5–2.0 s random delay, 3 retries, all configurable. Unreadable pages are
  recorded as failures, never worked around. Resumable through
  [`data/manifests/progress.json`](data/manifests/progress.json).
* **Alignment** — strictly by canonical reference (`GEN.1.1`), keyed on the book code from the
  URL. Never positional, never fuzzy, never fabricated.
* **Text fidelity** — published text preserved verbatim; the only change is collapsing
  whitespace runs and trimming ends. No translation, paraphrase, spelling or orthography
  fixes, no LLM cleanup. Headings, footnotes, cross-references and UI chrome are excluded.
* **Validation** — per-chapter gates (version id + version-consistent title + ≥ 90 % text
  coverage + target-language presence). Language heuristics are supplementary: they may only
  withhold a chapter, never promote one. Unverifiable → `LANGUAGE_UNCERTAIN`, excluded from the
  corpus and reported.
* **Audit** — every non-alignment is recorded with status and reason (see above).

Full stage-by-stage documentation: [`docs/PIPELINE.md`](docs/PIPELINE.md).
Field-by-field documentation: [`docs/DATA_SCHEMA.md`](docs/DATA_SCHEMA.md).

### Recovery and judgment calls

Recorded as they happened; primary evidence is in `logs/` and `reports/quality_report.md`.

1. A background collection run terminated with an `EPIPE` in the Playwright driver at chapter
   1467/2378. It resumed from `progress.json`, re-fetching **only** pending chapters:
   **911 collected, 0 failed**, with already-verified chapters skipped.
2. **20 NIV chapters were initially withheld for two false-positive reasons**, each checked
   against the live site before the extraction logic was corrected:
   * `MAT.1–5` publish an alternate `<title>`. Identity is nevertheless proven through
     URL/canonical/`og`/`h1`, so rigid title checking became a *consistency* check (a title
     naming a foreign version still withholds) plus an `h1` book-name fallback.
   * **16 verses are intentionally omitted by the NIV edition** (bracketed/footnote-only).
     This is an edition property, not a language failure: they became recorded warnings, and a
     `text_coverage ≥ 0.90` guard was added so genuinely broken extraction is still withheld.
3. Empty published verses were reclassified from `extraction_error` to
   `missing_thadou`/`missing_niv`, with the source label in the reason and status
   `present_no_text`. `extraction_error` is now reserved for both-sides-empty.
4. macOS AppleDouble `._*.json` sidecars on the volume crashed an unfiltered read; raw
   enumeration and loading were hardened to ignore them.

### Reproducing

```bash
pip install -r requirements.txt && playwright install chromium
python -m bible_scraper all        # discover → collect → normalize → align → verify → report
pytest -q                          # 107 tests, fully offline (fixture HTML, no network)
```

Stage-by-stage CLI:

```bash
python -m bible_scraper {discover,collect,normalize,align,verify,report,all} \
    [--headed | --headless] [--version THADBSI|NIV] [--book GEN [--chapter 1]] \
    [--min-delay 0.5] [--max-delay 2.0] [--max-retries 3]
```

`verify` is the release gate: it recomputes counts, checks schema, uniqueness, audit↔corpus
reconciliation, whole-book splits and exclusion of uncertain rows, and runs live spot checks.
It exits non-zero unless `ok` and `complete` are both true. `report` then writes the quality
reports and `reports/checksums.sha256` (7 provenance comment lines + 2,386 entries).
Checksums are regenerated only when a covered file actually changes. Verify any copy with:

```bash
sha256sum -c reports/checksums.sha256    # or: shasum -a 256 -c …  -> 2,386 OK, 0 FAILED
```

### Directory structure

```
bible_scraper/            pipeline (discover, collect, normalize, align, verify, report)
tests/                    107 offline tests (synthetic fixture text)
data/
  audit/                  alignment_audit.jsonl, alignment_summary.json, verification.json
  discovery/              captured version-page identity (books, canonical URLs)
  manifests/              book_mapping.json, *_books.json, *_chapters.jsonl, progress.json
  aligned/splits/         split_manifest.json   (train/validation/test JSONL: local only)
  raw/                    raw chapter captures  (local only — .gitignore)
  normalized/             per-verse records     (local only — .gitignore)
  aligned/                parallel + ML JSONL   (local only — .gitignore)
docs/                     DATA_ACCESS.md, DATA_SCHEMA.md, PIPELINE.md
reports/                  quality_report.{md,json,csv}, checksums.sha256
logs/                     scraper.log, audit.log, errors.log
SOURCE_MANIFEST.md        provenance of every captured source
LICENSE_NOTES.md          rights notes (no licence invented)
```

### Known limitations

* Biblical register only — archaic/religious domain, not everyday Thadou-Kuki speech.
* THADBSI and NIV are independent translations: rows are verse-aligned, not sentence-aligned
  or interlinear, so literal word-order correspondence should not be assumed.
* 17 references have no NIV side and are absent from the corpus (audit records exist for all
  of them); none were filled in.
* `identical_text_flag` marks byte-identical rows as a cross-version leakage signal. Rows are
  never altered or dropped because of it — filter downstream if you need to.
* Verification is 7 spot checks plus 6 independently sampled rows, not an exhaustive
  human re-read of all 31,087 pairs.

### Licensing and copyright

* **Project code** (`bible_scraper/`, `tests/`): MIT (declared in `pyproject.toml`).
* **THADBSI text**: © Bible Society of India — permission not established.
* **NIV text**: © Biblica, Inc.® — permission not established.
* Published metadata, audit records, reports and checksums contain no verse text. Three
  artifacts (`data/audit/verification.json`, `reports/quality_report.json`,
  `reports/quality_report.md`) retain the same 7-verse spot-check excerpt as audit evidence —
  see [`docs/DATA_ACCESS.md`](docs/DATA_ACCESS.md) §4.
* The full corpora are **local-only release artifacts**; `.gitignore` blocks them.
  Do not treat this repository as an open-licence Bible corpus — see
  [`LICENSE_NOTES.md`](LICENSE_NOTES.md), [`metadata/sources.json`](metadata/sources.json) and
  [`NOTICE`](NOTICE).