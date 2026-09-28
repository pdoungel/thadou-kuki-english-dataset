# Data access — what is published here, what stays local, and why

**Short version:** this repository publishes the *metadata, audit trail, reports,
checksums and code* for the Thadou-Kuki (THADBSI) ↔ English (NIV) alignment. It
does **not** publish either Bible text. The verse-text artifacts exist only in the
local project directory, and `.gitignore` enforces that they cannot be committed
by accident.

No legal determination is made or implied here. Where permission is not
*clearly* established, the text is withheld.

---

## 1. Rights position

| Side | Edition | Rights holder | Status in this repository |
|---|---|---|---|
| Thadou-Kuki | THADBSI — *Pathen Thutheng BU (BSI)*, bible.com version 1879 | Bible Society of India | Permission not established → **text withheld** |
| English | NIV — *New International Version*, bible.com version 111 | Biblica, Inc.® | Permission not established → **text withheld** |

Supporting records:

* [`../LICENSE_NOTES.md`](../LICENSE_NOTES.md) — states plainly that no license
  for either text is known, that none has been invented, and that accessibility
  is not permission to redistribute.
* [`../metadata/sources.json`](../metadata/sources.json) — both sources are
  registered with `rights_status: PERMISSION_REQUIRED` and
  `repository_policy: "metadata-only"`.
* [`../NOTICE`](../NOTICE) — the repository-wide rule: *restricted or uncertain
  sources are represented by metadata and acquisition instructions, not copied
  into the public dataset*, and *the public build must not add restricted text
  merely because it is technically downloadable.*

The repository's own README has always carried the same instruction for this
exact source ("© Bible Society of India — ask BSI for permission"). This
integration keeps that position: what is new is that the **alignment**, which can
be expressed without text, is now published.

## 2. Published here (no verse text)

```
data/audit/alignment_audit.jsonl     31,104 records, sha256 content hashes only
data/audit/alignment_summary.json    run counters
data/audit/verification.json         release gate + 7 live spot checks (see §4)
data/aligned/splits/split_manifest.json   whole-book split assignment + counts
data/manifests/                      book mapping, chapter manifests, progress.json
data/discovery/                      captured version-page identity + book lists
reports/quality_report.{md,json,csv} full release statistics
reports/checksums.sha256             2,386 sha256 entries
logs/{scraper,audit,errors}.log      URLs, attempts, counts, hashes (no text)
bible_scraper/                       the pipeline (MIT-licensed project code)
tests/                               107 offline tests (synthetic fixture text)
docs/                                schema, pipeline, this document
SOURCE_MANIFEST.md, LICENSE_NOTES.md provenance and rights notes
```

Every file above was scanned before commit for verse text, credentials, cookies,
tokens and browser state. The alignment audit in particular contains **no text
field at all** — both sides are represented by sha256 hashes.

## 3. Local only — never committed

| Artifact | Size (bytes) | SHA-256 |
|---|---:|---|
| `data/aligned/thadou_kuki_niv_parallel.jsonl` | 22,957,154 | `587e55fc710f29f19cad93c0caf7774fb5f7655f25fc488db0cd330781a6aeea` |
| `data/aligned/thadou_kuki_niv_ml.jsonl` | 9,397,373 | `16cd91752534b017ec1a8ae2da0baa6a46c1e53941bc60c441df86aa38bbed86` |
| `data/aligned/splits/train.jsonl` | 20,047,721 | `e58c0fceb0a39f0f6f48a0943e8072ecaed596ceb8343c495b411dbbfff48554` |
| `data/aligned/splits/validation.jsonl` | 2,183,019 | `04e1aaa34293bce6052fdea65d590fc6299e3daa15a68b1cbcd3a4690073e4e2` |
| `data/aligned/splits/test.jsonl` | 726,414 | `ba6769bf0958470bb2044dce87b8f1bb137af871c2316da94121753a38aecf24` |
| `data/normalized/thadbsi_verses.jsonl` | 16,251,038 | `e1997982c67a6866eaabe572769fa97535f031a5ce92357cdf3aff3e2e9bad74` |
| `data/normalized/niv_verses.jsonl` | 15,524,795 | `1dcf8cadcbeabffa95ce0f3535e6ff4138ed02000db0dd90278e7ca0ce01f3dc` |
| `data/raw/thad_bible/**` + `data/raw/niv/**` | 2,378 files, ~628 MB total | per file: `reports/checksums.sha256` |
| `logs/*.out` | — | console capture; `logs/*.log` is the record of truth |

Expected location: the local project directory,
`/Volumes/New Volume/thkvoice/bible/`, with exactly the relative paths shown —
those are the paths recorded in `reports/checksums.sha256`, so the manifest
verifies against a local copy as-is.

`.gitignore` blocks all of them (`data/raw/`, `data/normalized/`,
`data/aligned/*.jsonl`, `data/aligned/splits/*.jsonl`, `logs/*.out`).

**Corpus digest:** sha256 of `thadou_kuki_niv_parallel.jsonl` =
`587e55fc710f29f19cad93c0caf7774fb5f7655f25fc488db0cd330781a6aeea`, matching
`reports/quality_report.md`.

## 4. Excerpt notice (deliberate, limited)

Three published artifacts contain a *small* amount of verse text, retained because
they are the evidence for recorded statistics and the audit trail is a
first-class artifact of this project. All three carry the **same 7 reference
spot-check pairs** — both languages plus both source URLs — covering `GEN.1.1`,
`GEN.3.16`, `PSA.23.1`, `MAT.1.1`, `JHN.3.16`, `ROM.8.28`, `REV.22.21`:

| Artifact | Where |
|---|---|
| `data/audit/verification.json` | `spot_checks` array (7 entries) |
| `reports/quality_report.json` | `spot_checks` array (same 7) |
| `reports/quality_report.md` | `## Manual spot checks` table (same 7) |

7 of 31,087 pairs — excerpt-level evidence that the stored corpus still matches
the live pages, not the corpus. The 31,087-pair corpus, the ML file, the three
splits and both normalized files are withheld in full.

If you would rather publish no text at all, delete the `spot_checks` fields and
the `## Manual spot checks` section. The statistics in all three files are
computed independently of those fields and do not change.

## 5. Reproducing the dataset locally

The text is reproducible from the public pages by the committed code:

```bash
git clone https://github.com/pdoungel/thadou-kuki-english-dataset
cd thadou-kuki-english-dataset
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium

python -m bible_scraper all            # discover → collect → normalize → align → verify → report
```

or stage by stage, as documented in [`PIPELINE.md`](PIPELINE.md). Results land in
the `data/` paths listed in §3; `reports/checksums.sha256` tells you whether you
reproduced the release byte-for-byte (subject to any changes upstream publishers
make after the retrieval window):

```bash
shasum -a 256 -c reports/checksums.sha256      # macOS
sha256sum    -c reports/checksums.sha256       # GNU coreutils
# -> 2,386 OK, 0 FAILED   (the 7 '#' header lines are skipped automatically)
```

Collection for this release ran `2026-09-27T10:51:05Z → 2026-09-27T14:09:22Z`.

Alternative for a text-free reproduction of everything published here:
`python -m bible_scraper report` regenerates reports and checksums from the
committed audit and manifests alone — no verse text is required.

## 6. If permission is obtained

To publish the text, in this order:

1. Record the written permission in `LICENSE_NOTES.md` and set
   `rights_status` / `repository_policy` for both entries in
   `metadata/sources.json`.
2. Remove the five `data/…` block entries in `.gitignore`.
3. Commit the text artifacts (each is ≤ 23 MB, no LFS needed) and re-run
   `python -m bible_scraper verify` — it must report `ok` / `complete`.

Until step 1 exists, the answer is no.

## 7. Public metadata vs restricted text — one-line summary

| | Published | Withheld |
|---|---|---|
| References, book/chapter structure, URLs | ✅ | |
| Alignment statuses, reasons, sha256 hashes | ✅ | |
| Statistics, quality report, verification, checksums | ✅ | |
| Split assignment (book codes) | ✅ | |
| Code, tests, docs, logs | ✅ | |
| Thadou-Kuki (THADBSI) verse text | | ❌ |
| English (NIV) verse text | | ❌ |
| Raw chapter captures | | ❌ |
