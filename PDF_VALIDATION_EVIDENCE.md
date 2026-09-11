# PDF Validation Evidence (shared-v1-2026-09-11)

## Fixture under test
- PDF: `/app/backend/fixtures/catalog-v1/sample.pdf`
- Manifest: `/app/backend/fixtures/catalog-v1/sample.manifest.json`
- Parser tests: `/app/backend/tests/shared/test_shared_pdf_media_reconcile.py`

## Structural verification
- Parsed template pages validated with `analyze_page(..., mode="template_v1")`
- GUIDE pages return empty rows (page 1 and page 4 in sample)
- Extracted product codes are exactly:
  - `SAMPLE-SILVER-001`
  - `SAMPLE-GOLD-001`
  - `SAMPLE-DIAMOND-001`

## Crop dimension verification
- All extracted masters are exactly `1024 x 1024`
- Thumbnail generation path is tested by parser thumbnail utility and importer flow tests

## Pixel-comparison evidence (fixture JPEG vs parsed crop)
Measured using `/app/backend/tests/shared/pdf_measure_report.py`.

| Product code | Mean absolute pixel diff | Parsed crop | Expected fixture crop |
|---|---:|---|---|
| SAMPLE-SILVER-001 | 2.4390 | `/app/test_reports/pdf_crops/SAMPLE-SILVER-001-parsed.png` | `/app/test_reports/pdf_crops/SAMPLE-SILVER-001-expected.png` |
| SAMPLE-GOLD-001 | 1.6606 | `/app/test_reports/pdf_crops/SAMPLE-GOLD-001-parsed.png` | `/app/test_reports/pdf_crops/SAMPLE-GOLD-001-expected.png` |
| SAMPLE-DIAMOND-001 | 1.2307 | `/app/test_reports/pdf_crops/SAMPLE-DIAMOND-001-parsed.png` | `/app/test_reports/pdf_crops/SAMPLE-DIAMOND-001-expected.png` |

Threshold used in pytest: mean absolute diff `< 8.0` (all pass with large margin).

## Malformed/layout rejection evidence
- Cropbox-altered PDF is rejected (`CatalogError`)
- Blank/unknown layout PDF is rejected (`CatalogError`)

## Notes
- This report validates correctness of sample fixture extraction and crop fidelity.
- It does **not** claim configured max throughput/memory limits as measured production performance.

## Benchmark evidence (iter12, production generator+parser path)
- Script: `/app/backend/tests/shared/pdf_benchmark_report.py`
- Output JSON: `/app/test_reports/pdf_benchmark_iter12.json`
- Generated PDF: `/app/test_reports/benchmark_catalog_60.pdf`
- Measured run:
  - bytes: `4,127,720`
  - pages: `32`
  - products: `60`
  - parser elapsed: `39.321s`
  - process peak RSS: `447,312 KB`
- Unproven maxima:
  - >32 pages / >60 products with mixed-quality real supplier scans
  - concurrent import-job contention under multi-worker production load
  - end-to-end storage retry behavior against real object-storage transient failures

## Final combined verification
- `/app/test_reports/pytest/shared_final.xml`: 31 tests passed together (27 backend + 4 authenticated browser journeys).
- Browser PDF regression now waits for phase `queued` AND the full acknowledged byte count before invoking the test worker. The earlier chunk409 was caused by the test forcibly starting analysis while upload was still running; it was not reproduced after correcting the test. Backend source reconstruction now independently rejects an incomplete manifest even if a local source cache exists.
- Exact sample download, browser chooser/chunk upload, preview, field correction, exclusion and hidden commit exercised through actual ASGI logic and isolated Mongo. SMS/storage transport are fixture-stubbed; no production customer/financial records were changed and no real SMS was sent.
- Main fullscreen customer gallery regression now selects an added photograph explicitly; original scan remains a separate selectable photograph.
- Physical Android/iOS and release-build execution, full negative parser matrix, actual process-kill recovery and live storage outage testing remain unverified.