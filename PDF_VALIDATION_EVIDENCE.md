# PDF validation evidence — follow-up, 11 September2026

Build `shared-v1-followup-2026-09-11`. Workspace implementation only; no production rollout. Baseline30796997d3484594c6c5f53965e1c71dd5ed1c86 is verified in GitHub. New commit/pinned links await user-controlled Save to GitHub.

## Current artifacts (all in this repository)

- `backend/fixtures/catalog-v1/sample.pdf` — actual admin download `GET /api/pdf-template/sample.pdf`, attachment Yash-Catalog-Template-v1.pdf.
- `backend/fixtures/catalog-v1/sample.manifest.json` — regenerated field/geometry fixture manifest.
- `backend/fixtures/catalog-v1/authoring.json` — advanced editable companion, downloadable `/api/pdf-template/authoring.json`.
- `backend/tools/generate_catalog.py`, `backend/shared/pdf_schema.py`, `backend/shared/pdf_parser.py`, `backend/tools/parse_catalog_page.py` — SAME version1 generator/schema/parser.
- `frontend/app/catalog-author.tsx`, `backend/shared/pdf_authoring.py` — labelled photo/field form and POST /api/pdf-template/export. No Python/JSON required for ordinary staff.
- `frontend/app/pdf-import.tsx`, `frontend/src/components/staff/{ProductFields,SquareCrop,PrivateImage}.tsx` — labelled correction, private page preview, drag+resize crop.
- `backend/tests/shared/pdf_measure_followup.py`, `pdf_parser_benchmark_followup.py` — executed non-live evidence generators.

Template layout is unchanged: A4,2 square80mm photograph regions per PRODUCTS page, guide pages ignored, same version markers/field reference. Guide text now explains the app form and grams-per-pair compatibility. No silent new PDF layout/version. Form export max20 entries,32MiB input photos, output within importer cap; form drafts are session-local. Export alone does not publish inventory.

## Exact sample/parser evidence

`test_reports/followup_pdf_measurements.json`:3 products (silver/gold/diamond),0 row errors, all masters1024×1024 PNG and thumbnails320×320 PNG. Four document pages: guide,2 products,1 product,field-reference guide. Crop mean absolute pixel differences versus contained source references: silver2.4390, gold1.6606, diamond1.2307; mean1.7768. Independent baseline parser/crop check supplied by owner reported the same three typed rows and supports this happy path, not provider/native/release claims.

Aggregate3-photo bytes: masters3,616,707; thumbnails384,365; total4,001,072. Offline JPEG92 master+thumb507,598; WebP92 master+thumb304,986. These are sizing experiments, not approved image replacements or claims of equal jewellery-detail quality. Originals and served PNG formats retained. See STORAGE_CAPACITY.md for projections including source/preview/backup exclusions.

Automated visual PDF inspection found readable/unclipped guide/field reference and three separated square photographs. This is rendered-document inspection, NOT manual Acrobat/Apple Preview/device validation. Common PDF viewer/device sharing checks remain unverified.

## Executed regression coverage

Final combined command: `/opt/plugins-venv/bin/python -m pytest /app/backend/tests/shared -q --tb=short --junitxml=/app/test_reports/pytest/followup_combined_after_races.xml` -> **54 passed,0 failed,0 skipped**. Earlier iteration15–17 failures are retained as history, superseded by the final run after fixes; iteration18 adds five controlled race tests. TypeScript `npx tsc --noEmit` passed; final lint/compile evidence is recorded in RELEASE_READINESS.md.

Included cases:
- Exact three-product parsing, guide exclusion, no analysis-time products, hidden commit/exclusion, idempotent repeated commit, duplicate SKU/update-version handling.
- Legacy raw grams/per-pair image/title-only edits, ambiguous unchanged optional fields preserved; new ambiguous input rejected. Slab currency/basis/version/role handling.
- Full chunked upload/status, private owner access, different-owner/customer rejection, private source chunks blocked via /files, source reconstruction after local assembled cache deletion.
- Crop square/bounds/text protection and90/180/270 normalization comparisons; actual mobile-web PanResponder MOVE and RESIZE changed persisted rectangle while retaining square geometry.
- Labelled title correction then crop, versioned save, hidden two-row commit; preview read locks no longer conflict with row mutations.
- Wrong hash/retry/idempotency baseline cases; injected storage outage then successful retry; provider402/generic503 writes recorded unknown; quota/high-watermark and retained references/candidate states.
- Encrypted PDF safe failure; truncated PDF no worker crash (test allows safe failure OR repaired reviewable output, not unconditional truncation rejection).
- Form photo upload/entry/export download and text parse, duplicate/unknown field/other-owner photo rejection; catalog navigation/back and media accounting screen.
- Existing external HTTPS photograph renders without bearer headers while canonical private photo preview uses bearer; external request is intercepted synthetic data (no real third-party call).
- Concurrent identical chunk uploads preserve one manifest entry/bytecount; concurrent same-version commits create exactly three unique sample products; commit/cancel race has one consistent terminal result. Simulated thumbnail failure after successful master write leaves zero products for that row, recorded unknown thumbnail, then retry produces exactly one complete product. Expired-lease worker-claim-equivalent harness resumes after two checkpointed product rows without duplicating them (not a real OS/process/cloud restart).

**Test transport boundaries:** isolated Mongo fixture; MSG91/storage are test doubles. Five authenticated browser journeys route to real ASGI logic. Chromium omitted multipart File payload in post_data_buffer; test init instrumentation captures the selected File via Request.arrayBuffer and forwards identical multipart bytes (native captured184 bytes vs forwarded695080). This validates UI/backend handling with a controlled transport, not live web upload networking or a real file-provider. No universal OTP/reviewer bypass exists in production.

## Current subprocess/RAM benchmark

Artifact `test_reports/followup_parser_benchmark_20260911T133224Z.json`:60 generated products,32pages,4,128,423bytes. Sequential current per-page subprocess path54.641s;0.5856pages/s,1.0981products/s. Imported-backend parent baseline111,775,744bytes; parent peak112,250,880; child peak123,473,920; sampled COMBINED peak235,646,976bytes (~224.73MiB). Sampling50ms/1086samples; concurrency1. Test container cgroup8GiB/4CPU, NOT production entitlement.

This parent imports backend modules but is not a complete concurrent HTTP+PDF-export+Mongo+provider workload. One import worker loop per backend process; preview/crop/export work may add concurrency. Additional replicas can process more jobs. Full service concurrent/RAM acceptance against actual production CPU/RAM remains a release gate. Historical447,312KB (~437MiB) in-process benchmark is not the current worker limit or a production sizing proof.

## Configured, estimated and unverified limits

- CONFIGURED:64MiB PDF,1MiB chunks,200pages,25second page timeout,512MiB child address-space ceiling,22second CPU limit;4 active imports/admin. Client reads capabilities. No1GB upload claim.
- MEASURED: sample and60-row fixture above. NOT a measured64MiB/200page maximum or10k-image PDF ingestion promise.
- SIMULATED: source-cache reconstruction, injected storage failure/retry, isolated concurrency/idempotency cases. No real cloud outage, process kill/restart under load, network partition, worker lease expiry across real replicas or provider key rotation test.
- UNAVAILABLE: physical Android/iOS builds/file-provider lifetime, background/reopen/OS kill, share/open handoff, gesture/three-button navigation/home indicator, genuine Play reviewer access, actual provider writes/deletion and release-resource load test. Mobile-web screenshots are not native validation.
- BLOCKED: remote managed storage DELETE/lifecycle completion. Candidate audit does not erase bytes. Active/referenced source chunks remain retained; unreferenced candidates record blocked_provider_unsupported. No source PDF is made public to bypass the gate.