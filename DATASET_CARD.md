# Dataset Card — Thadou-Kuki ↔ English Dataset

## Summary

This repository is a research-oriented collection for Thadou-Kuki (ISO 639-3: tcz) ↔ English translation, lexicon, retrieval-augmented generation, and future speech/NLP work.

The existing corpus is Bible-centered parallel data plus collected source metadata. The expansion plan separates reusable data from sources that require permission.

## Current scope

The existing generated corpus is built from eBible Chongthu Thadou Bible material and English Bible references, plus a second Thadou Bible source collected from GospelGo.

Do not interpret the presence of a source file as proof that its contents may be redistributed or used for every downstream purpose. Rights are tracked per source.

## THADBSI ↔ NIV alignment (metadata-only)

A second corpus lives under `data/`: 31,087 verse pairs aligning the Thadou-Kuki **THADBSI**
edition (bible.com version 1879, Bible Society of India) with the English **NIV** (bible.com
version 111, Biblica), across 66 books and 1,189 chapters. Collection, normalization,
alignment, verification and reporting are implemented in `bible_scraper/` and documented in
`docs/PIPELINE.md`; fields are described in `docs/DATA_SCHEMA.md`.

Under the data-governance rule above, this source is classified
`rights_status: PERMISSION_REQUIRED`, `repository_policy: metadata-only` in
`metadata/sources.json`. Therefore:

- **Published:** references and canonical structure, alignment statuses and reasons, sha256
  content hashes, the 31,104-record audit trail, verification results, quality reports,
  checksums, manifests, split assignment (book codes), code and tests.
- **Withheld:** THADBSI verse text, NIV verse text, raw chapter captures, normalized records,
  the aligned/ML JSONL files and the three split files. These are local-only release
  artifacts, blocked by `.gitignore`.
- The alignment itself is publishable because it contains no text: every audit record carries
  hashes and a reason instead of verse content.

Three artifacts retain the same 7-verse spot-check excerpt as verification evidence —
`data/audit/verification.json`, `reports/quality_report.json` and the `## Manual spot checks`
table in `reports/quality_report.md`. This is documented explicitly in `docs/DATA_ACCESS.md` §4.

The corpus remains usable for research on a local copy, and can be rebuilt from the public
pages with `python -m bible_scraper all` subject to the same rights position as any other
restricted source.

## Expansion priorities

1. LDC-IL Mother Tongue Parallel Text Corpus of India Vol. I — Thado/Thadou component.
2. Bharatavani/CIIL Thadou dictionaries, grammar, textbooks and literature.
3. Government and educational Thadou-Kuki materials.
4. Public-domain historical and linguistic works.
5. Openly licensed modern text and speech resources.
6. Native-speaker contributed conversational data.

## Data governance

Each source should record source URL, retrieval date, author/publisher/content partner, language/variety, data type, license, redistribution status, model-training status and checksum when an artifact is retained.

Rights statuses:
- OPEN_LICENSE
- PUBLIC_DOMAIN
- PERMITTED_RESEARCH
- PERMISSION_REQUIRED
- METADATA_ONLY
- UNKNOWN

The public build must not add restricted text merely because it is technically downloadable.

## Intended uses

- Low-resource machine translation research
- Thadou-Kuki lexicon development
- RAG and language-learning resources
- Evaluation of Thadou-Kuki NLP systems
- Future speech/ASR/TTS research when audio rights permit

## Known limitations

The existing corpus is strongly dominated by religious/scriptural register. Verse-aligned evaluation is in-domain and should not be presented as general conversational translation evaluation. Lexicon candidates are automatically generated and require native-speaker review. Orthographic and dialect/register variation require explicit annotation.

See CITATION.cff and NOTICE for attribution and rights policy.
