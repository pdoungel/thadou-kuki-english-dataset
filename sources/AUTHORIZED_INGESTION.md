# Authorized ingestion workflow

This repository separates source discovery from corpus ingestion.

## Rule

Do not add text from a source merely because a web page or PDF can be viewed or downloaded. Add source text only when the source record documents permission for redistribution in this repository and, separately, permission for the intended model-training use.

## Current high-value targets

- LDC-IL Mother Tongue Parallel Text Corpus Vol. I: the official catalogue includes Thado/Thadou as one of the 147 mother tongues and describes 5,332 sentences per language component. Obtain the Thado component through LDC-IL's authorized commercial or non-commercial route before ingestion.
- Bharatavani Thadou dictionaries/Bhashakosha: valuable lexicon and grammar resources, but portal availability does not by itself establish a redistribution or AI-training license.
- WALS/Glottolog: openly licensed metadata/reference material can support language profiling, but their licenses do not automatically license the publications they cite.

## Required source manifest fields

For every acquired source record:

- source_id
- title
- provider/author
- canonical URL
- retrieval date
- SHA-256 of original file
- language/variety
- data type/register
- exact license or permission statement
- redistribution permission
- model-training permission
- attribution requirement
- transformation performed
- accepted/rejected record counts
- reviewer notes

## Ingestion

Use scripts/ingest_authorized_parallel.py for an authorized TSV with:

ref<TAB>thadou<TAB>english

The script performs conservative NFC/whitespace normalization and exact duplicate-pair removal. It does not download sources or bypass access controls.

After ingestion, merge accepted records with the main build using explicit source IDs so source-level provenance survives into every training and evaluation record.
