# License Notes

Generated as part of the Thadou-Kuki (THADBSI) ↔ English (NIV) parallel corpus
project. **This file deliberately contains no license grant for the source
texts.** Nothing here should be read as permission to reuse, redistribute, or
republish the Bible text captured by this project.

## What this project is

- **Code** (`bible_scraper/`, `tests/`): authored for this project. See
  `LICENSE_PROJECT.md` in the parent repository if present; otherwise treat the
  code license as unset until a license file is explicitly added.
- **Data** (`data/`, `reports/`): *derived copies of text published by third
  parties* on bible.com. The data files are an index/extraction of what the
  source site serves; they carry whatever rights the original publishers hold.

## What the sources are (facts observed during collection, not license terms)

| Side | Version id | Code | Publisher (as published on the source site) | Version page |
| --- | ---: | --- | --- | --- |
| Thadou-Kuki | 1879 | `THADBSI` | Bible Society of India (BSI) | <https://www.bible.com/versions/1879-thadbsi-pathen-thutheng-bu-bsi> |
| English | 111 | `NIV` | Biblica | <https://www.bible.com/versions/111-niv-new-international-version> |

- The site's footer links its terms at <https://www.bible.com/terms> and its
  privacy policy at <https://www.bible.com/privacy>. These were **not** treated
  as a grant of redistribution rights, and no license text was found or
  inferred during collection.
- The NIV is a copyrighted translation; its publisher (Biblica) is identified
  on the version page.
- THADBSI ("Pathen Thutheng BU (BSI)") is attributed to the Bible Society of
  India on the version page. Whether any portion is openly licensed (e.g., by
  a translation's own policy) was **not verified** in this project.

## What is explicitly *not* claimed here

1. **Public accessibility ≠ redistribution permission.** The pages were
   readable without login; that fact says nothing about whether the text may
   be copied, republished, bundled into a dataset, or served to third parties.
2. **No license is invented.** If a license for either text is not stated on
   the source site, none is stated here. "Unknown" is the correct value, not a
   guess.
3. **No warranty.** Text is reproduced as published, including any errors in
   the source. No translation, correction, or verification against print
   editions was performed.
4. **Internal research use only until reviewed.** Treat the corpora under
   `data/` as read-only research artifacts. Do not publish, redistribute, or
   use them as training data until you have reviewed:
   - <https://www.bible.com/terms>,
   - the publishers' stated policies for NIV (Biblica) and THADBSI (BSI),
   - and any license that the THADBSI translation itself may carry.
   **An owner-directed exception was taken for the two aligned corpus files —
   see _Publication status_ below. The review listed here has *not* been
   completed for them.**

## Publication status (recorded 2026-09-28)

Two files in this repository contain the full text of both source editions:

- `data/aligned/thadou_kuki_niv_parallel.jsonl` (31,087 verse pairs)
- `data/aligned/thadou_kuki_niv_ml.jsonl` (31,087 id/source/target rows)

They were published at the explicit direction of the repository owner, after the
rights position in this file was reviewed and flagged. **No permission from
Biblica or the Bible Society of India has been established, no license is
granted or implied by their presence here, and `rights_status` for both sources
in `metadata/sources.json` remains `PERMISSION_REQUIRED`.**

This is a decision recorded, not a decision made correct: it does not satisfy
the review list under point 4 or under *What you should do before
redistributing* below. Readers and downstream users should treat the text as
unlicensed third-party material until that review is completed.

Still local-only (blocked by `.gitignore`): `data/raw/`, `data/normalized/` and
the three `data/aligned/splits/*.jsonl` files.

## What you should do before redistributing

- Read the site's Terms of Service and confirm what they allow for automated
  extraction and redistribution.
- Contact the publishers: Biblica (NIV) and the Bible Society of India
  (THADBSI) for explicit written permission for your intended use.
- If either text is later confirmed to be under an open license, record the
  exact license name, version, URL, and date **in this file**, then re-run
  `python -m bible_scraper report` so the manifest reflects it.

## Reminder about verification status

`data/audit/verification.json` and `reports/quality_report.md` state exactly
which chapters and verses were verified and which were withheld as
`LANGUAGE_UNCERTAIN` or recorded as acquisition failures. Never cite corpus
counts from memory: re-run

```bash
python -m bible_scraper verify
python -m bible_scraper report
```

and quote the numbers those commands print.
