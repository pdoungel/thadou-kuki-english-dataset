# Thadou-Kuki Language AI Studio

A local-first dataset curation and translation-development application for **Thadou-Kuki ↔ English**.

## MVP

- Dataset statistics
- Search/browse parallel segments
- Human review and correction
- Approval/rejection status
- Train/validation/test split fields
- Source/rights register
- Safe import of authorized TSV data
- Reviewed-data export
- Translation workspace scaffold for both directions

The app deliberately does **not** assume that downloadable material is reusable. The repository's source/rights metadata remains authoritative.

## Run locally

From the repository root:

```bash
python -m venv .venv
# macOS/Linux
source .venv/bin/activate
# Windows PowerShell
# .venv\Scripts\Activate.ps1

pip install -r app/requirements.txt
python -m uvicorn app.backend.main:app --reload
```

Open:

- http://127.0.0.1:8000
- http://127.0.0.1:8000/docs

FastAPI provides automatic interactive API documentation. The current architecture can later serve a built React/Vite frontend from the same backend; for the first MVP the UI is a dependency-light static frontend served directly by FastAPI.

## Import the current corpus

Use the UI button or:

```bash
curl -X POST http://127.0.0.1:8000/api/import-existing
```

This imports `out/parallel.tsv` into the local SQLite database at `app/data/studio.db`. The database is local runtime state and should not be committed.

## Next development phases

1. Native-speaker review workflow with reviewer identities and audit history.
2. Authorized source import wizard with manifest/checksum validation.
3. Better deduplication and near-duplicate detection.
4. Controlled train/validation/test split generation.
5. SentencePiece/tokenizer experiments.
6. Baseline Thadou-Kuki ↔ English model training and evaluation.
7. Model-backed translation API.
8. React/Vite production UI and authentication for collaborative annotation.

## Important bilingual design

Every training record should be usable in either direction:

```text
Thadou-Kuki → English
English → Thadou-Kuki
```

Direction-specific evaluation sets must be maintained separately so quality in one direction is not assumed to represent the other.
