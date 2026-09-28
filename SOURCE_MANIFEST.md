# Source Manifest — Thadou-Kuki (THADBSI) ↔ English (NIV) Parallel Corpus

Generated 2026-09-27T14:16:09+00:00 by `bible_scraper` 1.0.0.

## What this corpus is

A verse-aligned parallel corpus pairing the Thadou-Kuki Bible (**Pathen Thutheng BU (BSI)**, version id `1879`, code `THADBSI`, publisher Bible Society of India) with the English **New International Version** (version id `111`, code `NIV`, publisher Biblica), both read from bible.com by automated browser.

## Sources

| Side | Version id | Code | Language | Version page |
| --- | ---: | --- | --- | --- |
| Thadou-Kuki | 1879 | `THADBSI` | Thadou Kuki (`tcz`) | https://www.bible.com/versions/1879-thadbsi-pathen-thutheng-bu-bsi |
| English | 111 | `NIV` | English (`eng`) | https://www.bible.com/versions/111-niv-new-international-version |

Chapter URLs follow `https://www.bible.com/bible/{versionId}/{BOOK}.{CHAPTER}.{CODE}`,
e.g. https://www.bible.com/bible/1879/GEN.1.THADBSI and https://www.bible.com/bible/111/GEN.1.NIV.

## How it was obtained

- Playwright + Chromium, one chapter page at a time, headed by default for development (`--headless` for production runs).
- Polite delays between requests (default `MIN_DELAY=0.5s`, `MAX_DELAY=2.0s`) and retries with exponential backoff (default `MAX_RETRIES=3`).
- `robots.txt` on bible.com allows `/bible/*`; notes and search paths are disallowed and were not accessed.
- No login, CAPTCHA, paywall or access control was bypassed; pages that could not be read normally are recorded as acquisition failures.
- Text is copied exactly as published: only technical whitespace normalization (runs of whitespace → single space, trim). No translation, paraphrase, spelling, punctuation or segmentation changes.
- Headings, verse numbers, footnotes, cross-references and other UI chrome are excluded from verse text.

## Discovery and identity

- Book identity comes from the canonical codes inside Bible.com URLs, never from display names (THADBSI shows localized names such as `Semtilbu`, `Potdohbu`, `Thempudan`, `Minbu`, `Thuphon`).
- Persistent mapping: `data/manifests/book_mapping.json` (66 THADBSI books × 66 NIV books, keyed by canonical code).
- Alignment is strictly by canonical reference (`GEN.1.1`); never by position or text similarity.
- Chapter manifests: `data/manifests/thadbsi_chapters.jsonl` and `data/manifests/niv_chapters.jsonl`.

## Retrieval summary

| Item | THADBSI | NIV |
| --- | ---: | ---: |
| Chapters discovered | 1189 | 1189 |
| Chapters captured | 1189 | 1189 |
| Verses normalized | 31104 | 31103 |

- Retrieval time range (raw captures): 2026-09-27T10:51:05+00:00 → 2026-09-27T14:09:22+00:00 (UTC)
- Raw captures: `data/raw/thad_bible/`, `data/raw/niv/`

## Outputs

| File | Rows / notes | SHA-256 |
| --- | --- | --- |
| `data/aligned/thadou_kuki_niv_parallel.jsonl` | 31087 rows | `587e55fc710f29f19cad93c0caf7774fb5f7655f25fc488db0cd330781a6aeea` |
| `data/aligned/thadou_kuki_niv_ml.jsonl` | 31087 rows | `16cd91752534b017ec1a8ae2da0baa6a46c1e53941bc60c441df86aa38bbed86` |
| `data/audit/alignment_audit.jsonl` | 31104 rows | `c2b9a8c6f0a803a77c503b23c164051d25bd1283a7c3f5916d0d5a45e011a7c6` |
| `reports/checksums.sha256` | 2378 raw + 8 final files | `3a9681476a87d1dc87bc9aa0aa75f9f4f7b686a299a748221ccc9f2d2b74796e` |

## Integrity status

- Verification: **OK**; complete: **YES**
- Language-uncertain chapters withheld from the verified corpus: 0
- Missing-in-NIV verses: 17; missing-in-THADBSI verses: 0; extraction errors: 0
- Re-run any time: `python -m bible_scraper verify` then `python -m bible_scraper report`.

## Provenance notes

- Thadou-Kuki language provenance: bible.com language page `https://www.bible.com/languages/tcz` ("The Bible in Thado Chin - Thadou Kuki") links `/versions/1879-…` with `THADBSI` as the abbreviation.
- Accessibility of the text does **not** establish permission to redistribute it; see `LICENSE_NOTES.md`.
