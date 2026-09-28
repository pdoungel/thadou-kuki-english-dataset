# Quality Report — Thadou-Kuki (THADBSI) ↔ English (NIV) Parallel Corpus

- Generated: 2026-09-27T14:16:09+00:00
- Scraper version: `1.0.0`
- THADBSI: version 1879 / `THADBSI` — Pathen Thutheng BU (BSI) (Bible Society of India) — https://www.bible.com/versions/1879-thadbsi-pathen-thutheng-bu-bsi
- NIV: version 111 / `NIV` — New International Version (Biblica) — https://www.bible.com/versions/111-niv-new-international-version
- Verification: **OK**, complete: **YES**

## Counts

| Metric | Value |
| --- | ---: |
| books_discovered_thadbsi | 66 |
| books_discovered_niv | 66 |
| chapters_discovered_thadbsi | 1189 |
| chapters_discovered_niv | 1189 |
| chapters_extracted_thadbsi | 1189 |
| chapters_extracted_niv | 1189 |
| verses_normalized_thadbsi | 31104 |
| verses_normalized_niv | 31103 |
| aligned_verse_pairs | 31087 |
| ml_pairs | 31087 |
| missing_in_thadbsi | 0 |
| missing_in_niv | 17 |
| duplicate_thadbsi | 0 |
| duplicate_niv | 0 |
| language_uncertain_verses | 0 |
| language_uncertain_chapters | 0 |
| extraction_error_verses | 0 |
| extraction_failures_chapters | 0 |
| unreadable_raw_files | 0 |
| empty_verses_in_raw | 16 |
| audit_records | 31104 |
| train_verses | 27279 |
| train_books | 55 |
| validation_verses | 2869 |
| validation_books | 7 |
| test_verses | 939 |
| test_books | 4 |
| checksummed_files | 2386 |
| verification_ok | true |
| verification_complete | true |

## Alignment states (from data/audit/alignment_audit.jsonl)

| State | Count |
| --- | ---: |
| aligned | 31087 |
| missing_thadou | 0 |
| missing_niv | 17 |
| duplicate_thadou | 0 |
| duplicate_niv | 0 |
| language_uncertain | 0 |
| extraction_error | 0 |

## Splits (whole books, deterministic)

- Method: whole-book split; bucket = int(sha256(book_code)[:8], 16) mod 10
- Buckets: {'train': '0-7 (target ~80%)', 'validation': '8 (target ~10%)', 'test': '9 (target ~10%)'}

| Split | Verses | Books |
| --- | ---: | ---: |
| train | 27279 | 55 |
| validation | 2869 | 7 |
| test | 939 | 4 |

## Verification checks

| Check | Result |
| --- | --- |
| manifests_THADBSI | PASS |
| manifests_NIV | PASS |
| book_mapping | PASS |
| raw_captures | PASS |
| normalized_deduplicated | PASS |
| parallel_schema | PASS |
| ml_schema | PASS |
| no_duplicate_ids | PASS |
| audit_reconciles | PASS |
| split_whole_books | PASS |
| uncertain_excluded_from_corpus | PASS |
| spot_checks | PASS |

## Language-uncertain chapters: 0


## Manual spot checks

| Reference | Thadou-Kuki (THADBSI) | English (NIV) |
| --- | --- | --- |
| GEN.1.1 | Atilin Pathen'in van le leiset aseme. | In the beginning God created the heavens and the earth. |
| GEN.3.16 | Aman numei nu jah-a chun, Keiman nalung gentheina le nanaovopna chu nasatah-a kapunsah ding; nangman nat thoh gim tah-a cha nahin ding; nalung ngaichat chu na inneipu-a ding hiding, chule aman nachunga vai ahomding ahi, ati. | To the woman he said, “I will make your pains in childbearing very severe; with painful labor you will give birth to children. Your desire will be for your husband, and he will rule over you.” |
| PSA.23.1 | Pakai chu kelngoi chinna eichingpa ahin, keima lhasamponge. | The Lord is my shepherd, I lack nothing. |
| MAT.1.1 | Abraham chapa, David chapa, Jesu Christa khangui thubu. | This is the genealogy of Jesus the Messiah the son of David, the son of Abraham: |
| JHN.3.16 | Ajeh chu Pathen'in hibanga hi vannoi angailut jeh-in, Achapa changkhat chu apetan ahi; koi hijongle Ama tahsan chan chun mangthah louva tonsot hinkemlou anei ahitai. | For God so loved the world that he gave his one and only Son, that whoever believes in him shall not perish but have eternal life. |
| ROM.8.28 | Ahin Pathen ngailuho chengse, ama lunggot lam doltah-a kikouho ding vang chun, thiljouse hin aphat nadingu atongkhom sohkeije, ti chu iheuve. | And we know that in all things God works for the good of those who love him, who have been called according to his purpose. |
| REV.22.21 | I-Pakaiyu Jesu Christa milungset nachun, mithengte nabon chaovin umpiuvin, Amen. | The grace of the Lord Jesus be with God’s people. Amen. |

Spot-check source URLs are in `data/audit/verification.json`.

## Checksums

- Checksums file: `reports/checksums.sha256`
- Raw chapter files hashed: 2378
- Final JSONL files hashed: 8
- SHA-256 of checksums file: `3a9681476a87d1dc87bc9aa0aa75f9f4f7b686a299a748221ccc9f2d2b74796e`
- SHA-256 of `thadou_kuki_niv_parallel.jsonl`: `587e55fc710f29f19cad93c0caf7774fb5f7655f25fc488db0cd330781a6aeea`
