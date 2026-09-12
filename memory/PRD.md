# Yash Trade — owner login recovery, 12 September 2026

## Current user request and scope
User reports website staff-login unavailable after demo OTP removal and explicitly authorises promoting existing app phone9999813334 CUSTOMER to ADMIN in production; preserve canonical ID/history and supply a website handoff prompt. No role bypass, duplicate admin, fixed OTP, or bulk identity merge. Website settings are a distinct pre-role blocker.

## Current architecture / implementation
Existing ExpoSDK54 + FastAPI + Mongo + MSG91 remain unchanged. New backend/shared/admin_recovery.py and tools/recover_owner_admin.py are OPERATOR-ONLY, never HTTP/startup imported. Dry-run no writes, exact database/ID/phone, unique-identity and active/deleted guards, snapshot hash, backup/maintenance/operator approval, intent audit then atomic same-user role+sv+event update. Recovery bookkeeping only revokes families referenced by old-version refresh tokens; completed or partial replay does not touch fresh sessions. No production repair executed.
New shared/readiness.py replaces misleading health status with per-flow mobile/staff/enrollment/deletion config+DB readiness; /health/live separate. Protected non-phone/no-SMS staff/enrollment readiness verifies key matching. Trimmed equal staff/enrollment credentials now fail consistently. OpenAPI120paths regenerated. frontend/app.config.js uses EXPO_DEVTOOLS_ORIGIN only with NODE_ENV=development for supported Expo Router preview-origin allowlisting; production native origin untouched.

## Live evidence / remaining P0
- Fresh production GET12September: app shared-v1-followup-2026-09-11, STAFF_SERVICE_KEY absent. Both website domains website-shared-v1-auth-readiness-v1 missing CANONICAL_API_BASE_URL/ENROLLMENT_INTEGRATION_KEY/STAFF_SERVICE_KEY. New live endpoint404 until new code activated.
- Authenticated production READ ONLY customer lookup confirms9999813334 active/verified/CUSTOMER, idbcdf18c9-dc87-4d46-b580-30cf519103df. Current local app database empty; no production settings writer/Mongo connection/admin session. No OTP dispatched or account changed.
- User approval now covers ONLY this same-ID role repair, NOT all identity merges. Full website export does not block this scoped recovery. Need authorised live operator to review dry-run/backup and apply, privately configure matching distinct keys on both projects, and verify both website origin allowlists. See PRODUCTION_ADMIN_RECOVERY.md; copy/paste WEBSITE_AUTH_FIX_PROMPT.md.
- Iteration21 final testing-agent verification:19/19 focused recovery/readiness tests,29/29 shared regressions (additional12/12 auth/people run overlaps), preview smartphone smoke and allowed/rejected embedded origins pass. Partial replay protects fresh access+refresh; completed replay idempotent. No local implementation issues remain; production /health/live404 is an unresolved gate. Fixture SMS/storage intercepted; no production login success claimed. Removed duplicate EXPO_PUBLIC_ENROLLMENT_URL; canonical register.yashsilver.com is now the sole configured registration URL.

## Backlog priorities
P0: authorised live configuration+single-account role repair and genuine owner OTP acceptance on app and both domains. P1: complete separately approved full identity mapping/cutover, storage plan and original release gates. P2: physical native camera/notifications/sharing acceptance. Historical follow-up below remains otherwise preserved.

# Previous phase record — 11 September2026

## Problem / constraints
Finish shared backend integration and prepare for10000photos without redoing architecture, duplicating database/media authority, losing genuine records, exposing secrets or premature rollout. Preserve owner9999813334 canonical ID/history. No9711881372 password-admin creation, no universal OTP, no production merge without specific report-hash approval/restored backup. Website private export must not block independent app work.

## Architecture and implementation
Expo SDK54 React Native app + canonical FastAPI/Motor Mongo; existing Emergent managed binary storage. Shared core/auth/people/queries/commerce/catalog/units/pdf_jobs/pdf_authoring/media_lifecycle/media_cache modules replace relevant legacy routes; remaining server/panel functionality preserved.
- Baseline OTP/grants/revocable15minute access/30day refresh families, same-subject staff exchange, role/last-admin guards, local deletion/tombstones/outbox preserved. STAFF_SERVICE_KEY remains absent and now must also differ from enrollment credential.
- Legacy grams/per-pair normalize only on explicit valid writes; unchanged historical optional fields do not block title/photo updates. Structured INR labour amount/basis with old labelled adapter; ambiguity flagged, no implicit scaling; old slab controls versions/display corrected.
- Catalog limit<=100, stable created_at/id order from page1, indexed words/exact SKU, separate discovery. Admin product-catalog FlatList40/page; thumbnail-first/private images. New catalog-author form accepts photos/fields, saves hidden product or exports exact v1 PDF. Same generator/schema/sample; no second PDF layout.
- Owner-only upright source page geometry/PNG, labelled review, actual drag/resize crop. Fixed GET-preview mutation-lock contention and new-screen back stack duplication. Source assembly independently locked.
- Managed-write intent/bytes/hash ledger, unknown outcomes, budgets/high-watermarks, media-usage UI; candidate audit protects referenced/shared/source media. Provider DELETE unavailable; remote_deleted never true. Byte-bounded16MiB/60second internal public-byte cache with authorization before EVERY fetch and HTTP private,no-store.
- Customer date/assignment controls, named telecaller/assignee/resolver options, daily/range drilldowns. Canonical analytics/dashboard retained. No admin-targeted customer phone change; self-service subject only.

## Verification / evidence
54 shared tests passed together,5 routed mobile-web journeys; final JUnit test_reports/pytest/followup_combined_after_races.xml. Isolated SMS/storage doubles; browser File multipart capture fixes test bridge omission, not production bypass. Actual crop move/resize and rotatedPDF tests pass. Added controlled PDFchunk/commit/cancel races, master-success/thumb-fail recovery and simulated expired-lease checkpoint resume. Six real read-only managed-storage reads total608598bytes; no livewrite/SMS/deletion/rotation.
10000synthetic metadata rows/100pages/unique IDs,100rowpayload62040bytes; exacttimings test_reports/catalog_10k_benchmark_iteration16.json. Browser scrolling metrics test_reports/mobile_web_catalog_scroll_metrics_iteration16.json (not native RAM). Sample3products/noerrors1024master320thumb, MAE2.439/1.6606/1.2307. Current60product/32page4,128,423byte subprocess fixture54.641s; parent+child235,646,976byte peak/concurrency1 excludes fullserviceworkload. TypeScript/lint/compile checked. Physical devices/provider failure chaos unavailable.

## P0 release gates
1. Save to GitHub is user-controlled/unavailable to agent; branchmain local baseline30796997d3484594c6c5f53965e1c71dd5ed1c86 publicly verified beforeediting, NOT newimplementationcommit. Follow-upSHA/pinnedlinks pending action. No productiondeploy; previewbuildshared-v1-followup-2026-09-11 commitunrecorded; production independent lastv7 commitunknown.
2. Authorized production+website secrets, separate staffkey/rotation, genuine MSG91dispatch+receipt.
3. Account-specific storage/DB/bandwidth/readwrite/CPU/RAM/backup costs unknown; supportedDELETE or owner-approved single-store plan required. No purchase/migration authorized. Complete production inventory/controlledproviderwrite+readback/recovery testpending.
4. Minimal private identityexport, verifiedrestorablebackup, conflict/hashmappingapproval; later websiteBFF/UIstaging, coordinatedcutover/reauthentication. No actualreconciliation.
5. Privatelyprovisioned isolated Playreview roles/data; externaldeletion/privacyretention verification; physicalAndroid/iOSfiles/sharing/background/navigation; fullservice/resourcechaos tests.

## P1/P2
P1: finish genuine-provider/device/full-serviceacceptance when inputs available; durableauthoringdrafts if needed. Cleanup dormant legacy panel sections without breaking preserved flows. P2: optional optimizedservingvariants after detailreview, stablelogicalmedia-ID migration onlyifapproved, furthercursor/snapshotpaging if livecatalogeditvolume requires it. No recommendation to expand paidresources without actualentitlement/inventory.

## Handoff
All five rootdocs updated: YASH_SHARED_API_CONTRACT.md, WEBSITE_HANDOFF.md, IDENTITY_EXPORT_CONTRACT.md, PDF_VALIDATION_EVIDENCE.md, RELEASE_READINESS.md. Additional STORAGE_CAPACITY.md. Regenerated contracts/openapi.shared-v1.json and sample.pdf/sample.manifest.json. WEBSITE_HANDOFF includes endpoint/body/header/response maps, nonsecretconfigurationnames, minimalread-onlyexportinstructions and stagebothclients-beforelivecutover sequence. No privateexports/backups/reviewcredentials inGit.