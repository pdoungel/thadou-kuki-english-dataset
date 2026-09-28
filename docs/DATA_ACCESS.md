# Data access — what is published here, what stays local, and why

**Short version:** this repository publishes the metadata, audit trail, reports,
checksums and code for the Thadou-Kuki (THADBSI) ↔ English (NIV) alignment, and
since 2026-09-28 it also publishes the two aligned corpus files themselves
(`data/aligned/thadou_kuki_niv_{parallel,ml}.jsonl`). The raw chapter captures,
the per-version normalized records and the three split files remain local only.

No legal determination is made or implied here. **No permission from Biblica
(NIV) or the Bible Society of India (THADBSI) has been established, and no
license is granted or implied by the presence of the text in this repository.**
The corpus was published at the explicit direction of the repository owner after
the rights position below was reviewed and flagged; the underlying rights status
has not changed.

---

## 1. Rights position

| Side | Edition | Rights holder | Status in this repository |
|---|---|---|---|
| Thadou-Kuki | THADBSI — *Pathen Thutheng BU (BSI)*, bible.com version 1879 | Bible Society of India | Permission **not** established — text published at owner's direction, no license claimed |
| English | NIV — *New International Version*, bible.com version 111 | Biblica, Inc.® | Permission **not** established — text published at owner's direction, no license claimed |

Supporting records:

* [`../LICENSE_NOTES.md`](../LICENSE_NOTES.md) — states plainly that no license
  for either text is known, that none has been invented, and that accessibility
  is not permission to redistribute. Its *Publication status* section records
  what was published here and on what basis.
* [`../metadata/sources.json`](../metadata/sources.json) — both sources are
  registered with `rights_status: PERMISSION_REQUIRED` (unchanged) and
  `repository_policy: "included-rights-unconfirmed"` (now reflecting that the
  text is present).
* [`../NOTICE`](../NOTICE) — the repository-wide rule: *restricted or uncertain
  sources are represented by metadata and acquisition instructions, not copied
  into the public dataset*. **The two aligned corpus files are a deliberate,
  owner-directed exception to that rule**, recorded here rather than left for a
  reader to discover.

Before any redistribution, model training or derivative release, complete the
review listed in [`../LICENSE_NOTES.md`](../LICENSE_NOTES.md) → *What you should
do before redistributing*: the site's terms, and written permission from Biblica
and the Bible Society of India.

## 2. Published here

```
data/aligned/thadou_kuki_niv_parallel.jsonl  31,087 verse pairs (both texts) — 22,957,154 B
data/aligned/thadou_kuki_niv_ml.jsonl        31,087 id/source/target rows  — 9,397,373 B
data/audit/alignment_audit.jsonl             31,104 records, sha256 content hashes only
data/audit/alignment_summary.json            run counters
data/audit/verification.json                 release gate + 7 spot checks (see §4)
data/aligned/splits/split_manifest.json      whole-book split assignment + counts
data/manifests/                              book mapping, chapter manifests, progress.json
data/discovery/                              captured version-page identity + book lists
reports/quality_report.{md,json,csv}         full release statistics
reports/checksums.sha256                     2,386 sha256 entries
logs/{scraper,audit,errors}.log              URLs, attempts, counts, hashes (no text)
bible_scraper/                               the pipeline (MIT-licensed project code)
tests/                                       107 offline tests (synthetic fixture text)
docs/                                        schema, pipeline, this document
SOURCE_MANIFEST.md, LICENSE_NOTES.md         provenance and rights notes
```

Digests of the two corpus files:

| File | Bytes | SHA-256 |
|---|---:|---|
| `data/aligned/thadou_kuki_niv_parallel.jsonl` | 22,957,154 | `587e55fc710f29f19cad93c0caf7774fb5f7655f25fc488db0cd330781a6aeea` |
| `data/aligned/thadou_kuki_niv_ml.jsonl` | 9,397,373 | `16cd91752534b017ec1a8ae2da0baa6a46c1e53941bc60c441df86aa38bbed86` |

The first digest is the corpus SHA-256 quoted in `reports/quality_report.md`.
Both entries also appear in `reports/checksums.sha256`, so anyone can confirm
the published files are the verified release artifacts:

```bash
sha256sum -c reports/checksums.sha256 2>/dev/null | grep data/aligned/
```

All other files listed above were scanned before commit for credentials,
cookies, tokens and browser state. The alignment audit in particular contains
**no text field at all** — both sides are represented by sha256 hashes.

## 3. Local only — not committed

| Artifact | Size (bytes) | SHA-256 |
|---|---:|---|
| `data/aligned/splits/train.jsonl` | 20,047,721 | `e58c0fceb0a39f0f6f48a0943e8072ecaed596ceb8343c495b411dbbfff48554` |
| `data/aligned/splits/validation.jsonl` | 2,183,019 | `04e1aaa34293bce6052fdea65d590fc6299e3daa15a68b1cbcd3a4690073e4e2` |
| `data/aligned/splits/test.jsonl` | 726,414 | `ba6769bf0958470bb2044dce87b8f1bb137af871c2316da94121753a38aecf24` |
| `data/normalized/thadbsi_verses.jsonl` | 16,251,038 | `e1997982c67a6866eaabe572769fa97535f031a5ce92357cdf3aff3e2e9bad74` |
| `data/normalized/niv_verses.jsonl` | 15,524,795 | `1dcf8cadcbeabffa95ce0f3535e6ff4138ed02000db0dd90278e7ca0ce01f3dc` |
| `data/raw/thad_bible/**` + `data/raw/niv/**` | 2,378 files, ~628 MB total | per file: `reports/checksums.sha256` |
| `logs/*.out` | — | console capture; `logs/*.log` is the record of truth |

Why these stay local: the splits are an exact repartition of the published
corpus (reproducible from `split_manifest.json`), the normalized files are a
near-duplicate of it, and the raw captures are 628 MB of browser output that no
repository should carry. None of them add information the published files lack.

Expected location for a local copy: the project directory
`/Volumes/New Volume/thkvoice/bible/`, with exactly the relative paths shown —
those are the paths recorded in `reports/checksums.sha256`, so the manifest
verifies against a local copy as-is.

`.gitignore` blocks them (`data/raw/`, `data/normalized/`,
`data/aligned/splits/*.jsonl`, `logs/*.out`).

## 4. Excerpt notice (deliberate, limited)

Three report artifacts contain small verse excerpts retained as verification
evidence. Now that the full corpus is published, this is no longer an
exposure question — the note is kept so the provenance of those strings is
understood. All three carry the **same 7 reference spot-check pairs** — both
languages plus both source URLs — covering `GEN.1.1`, `GEN.3.16`, `PSA.23.1`,
`MAT.1.1`, `JHN.3.16`, `ROM.8.28`, `REV.22.21`:

| Artifact | Where |
|---|---|
| `data/audit/verification.json` | `spot_checks` array (7 entries) |
| `reports/quality_report.json` | `spot_checks` array (same 7) |
| `reports/quality_report.md` | `## Manual spot checks` table (same 7) |

If you ever need the reports without them, delete the `spot_checks` fields and
the `## Manual spot checks` section. The statistics in all three files are
computed independently of those fields and do not change.

## 5. Reproducing the dataset

```bash
git clone https://github.com/pdoungel/thadou-kuki-english-dataset
cd thadou-kuki-english-dataset
sha256sum -c reports/checksums.sha256     # verifies the published corpus
                                           # (raw/normalized entries need a local capture)

# Full rebuild from the public pages:
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
python -m bible_scraper all            # discover → collect → normalize → align → verify → report
```

or stage by stage, as documented in [`PIPELINE.md`](PIPELINE.md). Results land in
the `data/` paths; `reports/checksums.sha256` tells you whether you reproduced
the release byte-for-byte (subject to any changes upstream publishers make after
the retrieval window):

```bash
shasum -a 256 -c reports/checksums.sha256      # macOS
sha256sum    -c reports/checksums.sha256       # GNU coreutils
# -> 2,386 OK, 0 FAILED   (the 7 '#' header lines are skipped automatically;
#    entries for data/raw/ and data/normalized/ need those files locally)
```

Collection for this release ran `2026-09-27T10:51:05Z → 2026-09-27T14:09:22Z`.

## 6. If permission is obtained

If written permission from Biblica and/or the Bible Society of India arrives:

1. Record it in `LICENSE_NOTES.md` — exact license name, version, URL, date —
   and set `rights_status` for both entries in `metadata/sources.json`.
2. Update the tables in this document.
3. Optionally publish the remaining artifacts by removing the `data/raw/`,
   `data/normalized/` and `data/aligned/splits/*.jsonl` entries from
   `.gitignore`, then re-run `python -m bible_scraper verify` (it must report
   `ok` / `complete`).

The two aligned corpus files are already published, so nothing needs unblocking
for them.

## 7. Public vs local — one-line summary

| | Published | Local only |
|---|---|---|
| References, book/chapter structure, URLs | ✅ | |
| Alignment statuses, reasons, sha256 hashes | ✅ | |
| Statistics, quality report, verification, checksums | ✅ | |
| Split assignment (book codes) | ✅ | |
| Code, tests, docs, logs | ✅ | |
| Thadou-Kuki (THADBSI) + English (NIV) aligned corpus | ✅ — *no permission established, no license claimed* | |
| Train/validation/test split files | | ❌ reproducible from the corpus + manifest |
| Per-version normalized records | | ❌ duplicate of the corpus |
| Raw chapter captures (2,378) | | ❌ |
