# Yash Trade shared backend — implementation handoff

## Request and constraints
Implement canonical phone OTP identity/roles/profiles for the app and separate enrollment website; secure staff/customer integration, unified queries and IST metrics, billing rates, permanent product photos, privacy/deletion controls, and a reviewed resumable native PDF importer with actual sample/generator/tests. Preserve existing records and working catalog/rewards/banner flows.

No verified website export has been provided. Phone 9999813334 is the intended admin, retaining its existing app ID and history. Production reconciliation is **dry-run only** until a backup, conflict report and owner approval of that exact migration exist. Do not create a password/default admin or infer other roles from website records.

## Architecture and implementation
- New `backend/shared/` modules: core, auth, people, queries, commerce, PDF schema/parser/jobs, route installation. Canonical routes replace unsafe legacy registrations; existing catalog/rewards remain in oversized server.py.
- Auth: persistent purpose-bound hashed four-digit challenges using existing MSG91 Flow sender, cooldown/attempt limits, single use, canonical role/current-user checks, revocable session versions/families, rotating refresh. Old fixed-OTP environment flags cannot enable a bypass. Startup no longer seeds identities or silently backfills verification.
- Identity: grant-backed enrollment, profile whitelist, stable-ID phone change with revocation, admin-only staff directory/conversion, last-admin guard, same-subject service-key exchange; paginated customer directory.
- Requests: full staff queue including unassigned, pagination beyond 200, atomic claims/versioned events, separate resolver/editor, canonical history/status adapters, reopening, IST cohort/throughput metrics and drilldown. Telecaller Requests is primary; CRM remains separate; billing queries read-only.
- Commerce: versioned admin/billing rates/slabs, permanent validated photo upload, original scan plus added-photo selection in both detail and fullscreen gallery. Separate AI assistant retained with owned history and reporting.
- Deletion: local anonymization/revocation, tombstones, website deletion outbox. External provider/website erasure is NOT claimed complete.
- PDF: actual v1 A4 sample, JSON authoring generator, guide ignored, two blocks/page, silver/gold/diamond fields and geometric 1024² masters/320² thumbnails. Chunk manifests/hashes, native-compatible file APIs, durable job leases/checkpoints, review/crop/exclude/duplicate policy, hidden idempotent commit, pause/resume/cancel. No silent whole-page fallback or OCR claim.
- Migration: offline dry-run tool and synthetic linkage fixture; private minimum export contract. No production apply command or live migration run.

## Verification
- 27 backend tests passed together (`iter12_final_results.xml`).
- Four authenticated mobile-web journeys passed (`iter13_authenticated_ui.xml`) using real ASGI logic and isolated Mongo, with test-only SMS/storage interception. Admin PDF test was corrected to wait for acknowledged full upload before worker execution; passes (`iter13_corrected_upload.xml`).
- Sample exactly three products; crop pixel MAE 1.23–2.44. Benchmark 32 pages/60 products, 4,127,720 bytes, 39.321s, 447,312KB peak RSS. Configured 64MiB/200-page maximum is NOT proven.
- TypeScript and Python compile pass. Physical Android/iOS, Expo Go device and release-build tests not run.

## P0 release gates still pending
Final combined suite: **31 passed** (`test_reports/pytest/shared_final.xml`). Idempotent index setup retries only AutoReconnect transport errors; no business tests are retried/suppressed. Authenticated browser startup waits for painted content rather than a short cold-bundle timeout.

1. Website project changes and cross-deployment verification; no identity export/backup/approved reconciliation applied.
2. Secret rotation and separate STAFF_SERVICE_KEY provisioning (missing locally); controlled real SMS verification.
3. Production rollout and repository sync/new implementation commit verification. Current branch main; observed HEAD `1d18a772c6c058e8917d969615f1495ad2c6345d` is pre-change baseline, not this implementation. No remote configured. Observed production build `2026.09.09-integration-v7`, exact deployed commit unknown.
4. Isolated Play-review role identities/sample data and private external credentials handoff; NOT provisioned.
5. Complete cross-system/provider deletion, retention and privacy/Data Safety audit; remote object-storage purge/orphan cleanup confirmation.
6. Remaining PDF negative/chaos/native-device matrix and resource-limit validation under real deployment budget.

## P1/P2
Remove dormant legacy handlers/UI and finish modularizing server/panel. Improve drag-based crop editing and filter UX; admin sync status widget. Future push/WhatsApp fallback, enrollment alerts, analytics and gold calculator remain backlog.

## References
`YASH_SHARED_API_CONTRACT.md`, `WEBSITE_HANDOFF.md`, `IDENTITY_EXPORT_CONTRACT.md`, `RELEASE_READINESS.md`, `PDF_VALIDATION_EVIDENCE.md`, generated `contracts/openapi.shared-v1.json`; `backend/fixtures/catalog-v1/`, `backend/tools/generate_catalog.py`, `backend/tools/reconcile_identities.py`; test reports/JUnit/screenshots iterations 11–13. No production/reviewer credentials belong in this repository.