# Pipeline — how this dataset is produced

Reproducible, resumable, browser-driven collection → normalization → alignment →
validation → audit → split → checksum → release.

Everything runs from the repository root:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium

python -m bible_scraper discover              # both versions, writes book/chapter manifests
python -m bible_scraper collect --headed      # resumable capture of all chapters
python -m bible_scraper normalize             # per-verse records + language checks
python -m bible_scraper align                 # reference-keyed alignment + audit + splits
python -m bible_scraper verify                # release gate  -> data/audit/verification.json
python -m bible_scraper report                # reports + checksums
python -m bible_scraper all                   # the whole sequence

pytest -q                                     # 107 offline tests (needs Chromium)
```

Useful flags: `--headed` / `--headless` (default `--headed`), `--version THADBSI|NIV`,
`--book GEN [--chapter 1]`, `--min-delay` / `--max-delay` / `--max-retries`.

## Stage → module map

Each stage names the module that implements it. There is exactly one
implementation per stage; nothing lives in two places.

| Stage | Module | Reads | Writes |
|---|---|---|---|
| Source discovery | `bible_scraper/discovery.py` | version page URLs | `data/manifests/book_mapping.json`, `data/manifests/*_books.json`, `data/manifests/*_chapters.jsonl`, `data/discovery/*_version_page.json` |
| Browser session / politeness | `bible_scraper/browser.py` | — | `logs/scraper.log` |
| Chapter capture + validation gates | `bible_scraper/extraction.py` | live pages | `data/raw/**/NNN.json`, `data/manifests/progress.json` |
| Normalization + language verification | `bible_scraper/normalization.py` | raw captures | `data/normalized/*.jsonl` |
| Reference-keyed alignment, audit, splits | `bible_scraper/alignment.py` | normalized | `data/aligned/*.jsonl`, `data/aligned/splits/*`, `data/audit/alignment_audit.jsonl`, `data/audit/alignment_summary.json` |
| Release verification | `bible_scraper/validation.py` | everything above | `data/audit/verification.json` |
| Reports + checksums | `bible_scraper/reporting.py` | everything above | `reports/quality_report.*`, `reports/checksums.sha256`, `SOURCE_MANIFEST.md` |
| CLI, progress, resume | `bible_scraper/cli.py` | — | `logs/audit.log`, `data/manifests/progress.json` |
| Types, constants, reference parsing | `bible_scraper/models.py` | — | — |
| Tests (offline) | `tests/` | fixture HTML | — |

`pyproject.toml` wires `pytest` (`testpaths = ["tests"]`, `pythonpath = ["."]`).
Tests never touch the network: pages are served from in-memory HTML through
Playwright route interception, so the real extraction/validation code runs against
fixture DOM that mirrors the live site.

## Acquisition rules

* **Playwright only.** No `requests`, `urllib`, `curl` or `wget` anywhere in the
  pipeline. The DOM is read as a browser renders it.
* **No auth, no CAPTCHA, no DRM, no paywall bypass.** The two versions are public
  pages. Pages that cannot be read are recorded as failures, never worked around.
* **Polite pacing.** Delay uniformly sampled between `MIN_DELAY` 0.5 s and
  `MAX_DELAY` 2.0 s between requests, `MAX_RETRIES` 3 attempts, all configurable.
* **Resumable.** `data/manifests/progress.json` records per-chapter state
  (`pending → extracted → verified`, or `failed`). Re-running `collect` skips
  chapters already in a completed state and retries only what is missing.

## Methodology

### Extraction and per-chapter validation

A chapter is accepted only if all hard gates pass:

1. `version_id` matches the target version (1879 / 111) and the page's version
   code association matches (`THADBSI` / `NIV`).
2. `title_version_consistent` — the page title must not name a *different*
   version. Neutral chapter-intro titles (e.g. a heading that names no version)
   pass; a title that names a foreign version withholds the chapter.
3. `has_text_content` and `text_coverage_ok` — ≥ 90 % of expected verses carry
   text (`MIN_TEXT_COVERAGE = 0.90`), so genuinely broken extraction is withheld
   rather than published.
4. Target-language text is present (heuristics are **supplementary**: they may
   only withhold a chapter, never promote one), and the page is not UI chrome.

Chapter identity is proven by URL + canonical link + `og:` metadata + `h1`, with
an `h1` book-name fallback when the title carries no "Book Chapter" shape.

Anything that cannot be established is marked `LANGUAGE_UNCERTAIN`, withheld from
the corpus, and reported. It is never guessed into the data.

### Normalization

Published text is preserved exactly. The only permitted transformation is
**technical whitespace normalization**: collapse runs of whitespace to a single
space and trim the ends. No translation, no paraphrase, no spelling or
orthography fixes, no LLM cleanup, no de-duplication by similarity. Headings,
footnotes, cross-references and UI chrome are excluded from verse text.

Duplicate verse spans carrying the same `data-usfm` reference are merged in
document order. Version-level contamination is guarded by
`IDENTICAL_RATIO_WITHHOLD = 0.5`: if more than half of a chapter's verses are
byte-identical across the two versions, the chapter is withheld for review.

### Alignment

Alignment is **strictly by canonical reference** (`GEN.1.1`), never by position,
offset or fuzzy matching. Both sides are keyed on the canonical book code from
the URL.

* Reference present on both sides with text → aligned pair.
* Reference present but the source publishes no verse text → audit record with
  `present_no_text` and an explanatory `reason` (label + why).
* Reference absent on one side → `missing_niv` / `missing_thadou` audit record.
* Present on one side only in a way that indicates capture failure →
  `extraction_error`.

Nothing is imputed, back-filled, interpolated or dropped silently.

### Splits

Whole-book assignment, so no book leaks across splits and the assignment is
reproducible from book codes alone:

```
bucket = int(sha256(book_code)[:8], 16) mod 10
0-7 → train, 8 → validation, 9 → test
```

### Verification (release gate)

`verify` recomputes counts from the files, checks manifest completeness, schema,
uniqueness, audit↔corpus reconciliation, whole-book splits, exclusion of
`LANGUAGE_UNCERTAIN` rows, and performs live spot checks (both texts + both URLs).
The release is `complete` only when every check passes with `ok` and
`complete` both `true`; otherwise the run exits non-zero.

### Checksums

`reports/checksums.sha256` holds **2,386 entries** covering all 2,378 raw chapter
captures plus the 8 final JSONL artifacts (5 aligned + 2 normalized + 1 audit),
in `sha256sum` format. A 7-line `#` provenance header (generated_at, version,
source and chapter URL templates, entry counts) sits above them, so the file is
2,393 lines long — `wc -l` counts the header, `sha256sum -c` skips it.

Verify a local copy:

```bash
shasum -a 256 -c reports/checksums.sha256      # macOS
sha256sum    -c reports/checksums.sha256       # GNU coreutils
# -> 2,386 OK, 0 FAILED  (verified for this release)
```

The corpus digest is the sha256 of `data/aligned/thadou_kuki_niv_parallel.jsonl`:

```
587e55fc710f29f19cad93c0caf7774fb5f7655f25fc488db0cd330781a6aeea
```

Checksums are regenerated only when a covered file actually changes.

## Recovery and judgment calls (this run)

Recorded exactly as they happened; see `reports/quality_report.md` and
`logs/` for the primary evidence.

1. **Playwright driver `EPIPE` at chapter 1467/2378.** A background collection
   process died mid-run. Collection resumed from `data/manifests/progress.json`;
   only pending chapters were re-fetched — 911 collected, 0 failed, and the 1,467
   already verified chapters were skipped.
2. **20 NIV chapters initially withheld for false positives**, corrected only
   after re-checking the live pages:
   * `MAT.1`–`MAT.5` use an alternate page `<title>`. Identity was still proven
     by URL/canonical/`og`/`h1`, so rigid title equality was replaced by the
     `title_version_consistent` check, and an `h1` book-name fallback was added.
     A title naming a foreign version still withholds.
   * 16 verses are intentionally omitted by the NIV edition and appear only as
     bracketed/footnote material. This is an edition property, not a language
     failure, so they became recorded warnings — and the `text_coverage ≥ 0.90`
     gate was added so genuinely broken extraction remains withheld.
3. **Empty published verses reclassified.** A present record with empty text was
   counted as `extraction_error`; it is now `missing_thadou` / `missing_niv` with
   the source label in the `reason` and status `present_no_text`.
   `extraction_error` is reserved for both-sides-empty.
4. **macOS AppleDouble sidecars.** `._*.json` files on the volume crashed an
   unfiltered read. Raw enumeration now ignores AppleDouble files and
   `normalization.load_raw_chapter` tolerates unreadable files instead of
   aborting the run.

## Runtime

* Python ≥ 3.9 (`3.12` used for this release)
* `playwright>=1.40` + Chromium (`playwright install chromium`)
* `pytest>=7.0` for the test suite
