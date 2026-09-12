# Release readiness — follow-up NOT production-ready

## Owner-login recovery update — 12 September 2026

**Production login remains blocked; NOT restored.** Fresh GET checks (not cached crawl) show app build `shared-v1-followup-2026-09-11` missing STAFF_SERVICE_KEY; both website domains run `website-shared-v1-auth-readiness-v1` missing canonical base/enrollment/staff configuration. Production `/api/health/live` is currently404 because the new code is not running there. Existing owner9999813334 is active/verified/CUSTOMER, canonical ID confirmed in PRODUCTION_ADMIN_RECOVERY.md. No real role/settings changes or SMS occurred.

Current workspace build `shared-v1-owner-recovery-2026-09-12` adds guarded operator-only recovery, per-flow readiness/no-SMS credential checks, trimmed key separation, and a development-only embedded-preview origin configuration. Generated OpenAPI now120 paths. Full website export is NOT a prerequisite for the owner's newly authorised single-account role repair; full identity merging remains gated. Production Mongo/settings access is not available to this workspace. Exact live maintenance and website coordination instructions: PRODUCTION_ADMIN_RECOVERY.md and WEBSITE_AUTH_FIX_PROMPT.md.

Iteration20 testing found/reproduced a partial-recovery replay edge case; code now revokes only pre-repair version families, protecting fresh sessions. Iteration21 testing-agent retest passed19/19 focused tests and29/29 shared regressions; additional12/12 auth/people run overlaps that regression suite. Mobile preview and development-only allowed/rejected origin checks passed. No local implementation issue remains in that report; production probe still finds old-build /health/live404. Frontend duplicate enrollment URL removed, retaining canonical register.yashsilver.com. The baseline54 result below is historical and not a new production claim.

## Previous phase code, repository and runtime provenance

| Surface | Evidence/status |
|---|---|
| Verified pre-follow-up public main | 30796997d3484594c6c5f53965e1c71dd5ed1c86; public main checked before editing. Prior baseline-sync uncertainty is superseded. |
| New implementation | Workspace branch main. No configured git remote or agent-controlled Save to GitHub operation. New implementation SHA/commit URL/remote sync UNAVAILABLE until that user-controlled action. Never identify the baseline as this implementation. |
| Preview | https://yash-trade-backend.preview.emergentagent.com ; health build shared-v1-followup-2026-09-11, commit unrecorded. Source loaded in preview, exact recorded commit unknown. |
| App production | https://yash-tryon-test.emergent.host ; owner's independent11September check:2026.09.09-integration-v7; exact commit unknown. No production change performed here. |
| Website production | https://register.yashsilver.com and https://yash-register.emergent.host ; independent check2026.09.10-login-v10; commits unknown. No website access/config/code change or rollout performed. |

Code sync is not deployment. Do not stage breaking auth/session/enrollment contracts against the unprepared website. After Save to GitHub, verify the NEW branch/SHA contains all five docs/OpenAPI/artifacts and record that commit separately in staged BUILD_COMMIT. No secrets/real exports/backups/reviewer passwords belong in Git. Existing memory/test_credentials.md contains only isolated-test guidance, not real credentials.

Generated `contracts/openapi.shared-v1.json` contains116 paths; exact JSON equality with the running ingress-accessible `/api/openapi.json` was verified by curl. A final read-only public main check still returned the baseline SHA, so new remote sync is definitively NOT claimed.

## Implemented and verified in workspace

- Preserved canonical Mongo/auth/grants/refresh/revocation/role checks, stable IDs, request ledger/attribution, existing galleries/rates/lead flows; no database replacement or identity migration.
- Shared legacy weight/unit adapters; unchanged historical optional fields no longer block photo/title edits. Structured INR labour basis compatibility and display; versioned old/new slab controls and soft deletion.
- Catalog server cap100, stable first/later pages/id tie-breaker, indexed words/exact SKU and filters; separate random discovery; admin FlatList40/page, thumbnails and private image delivery.
- Labelled PDF review/visual move+resize private source-page crop; owner-only page geometry/PNG; same-v1 form export. Fixed preview/mutation lock contention and Back stack duplication. Regenerated sample instructions/manifest.
- New media write intents/byte/hash/purpose ledger, bounded application write budgets, high-watermark UI, lifecycle candidate audit/reference protection, safe byte cache with authorization on every fetch.
- Legacy external HTTPS images render without Authorization headers; only canonical private-media requests receive bearer credentials. Verified with an intercepted external-host test, not a real third-party request.
- Customer registration/login/assignment date+name controls; named query assignee/resolver and daily/range drilldowns; existing canonical admin dashboard plus scoped metrics. Targeted admin customer phone change NOT implemented; self-service remains explicit.

Final suite: **54 passed,0 failed,0 skipped**, including5 authenticated routed mobile-web journeys, `test_reports/pytest/followup_combined_after_races.xml`. Test provider transports are isolated doubles, not real SMS/write proof. `test_reports/followup_final_summary.json` consolidates final status over historical failures. TypeScript/lint/compile passes. Separate read-only managed storage measurement:6 reads succeeded,608598 aggregate bytes, no live upload/deletion.

Final restarted preview paints successfully with no captured render exception. Non-failing warnings remain:9 Python deprecation warnings; React Native Web shadow/pointerEvents deprecations; Metro suggests SDK54 patch alignment for expo-constants18.0.13→18.0.14, expo-font14.0.11→14.0.12 and expo-router6.0.23→6.0.24. These existing dependency patches were not changed as part of this follow-up; review them with native-build acceptance rather than claiming device compatibility from browser success.

10k synthetic metadata test:100pages,10000unique IDs;100-row response62040bytes; current list/search/concurrency timings in `test_reports/catalog_10k_benchmark_iteration16.json`. Mobile-web300-row fixture held40metadata/page; actual scrollTop0→7072,6→14 rendered cards,248→361DOM nodes,reported20.5MB JS heap unchanged; this is not native memory or10k decoded-image proof. PDF60-row subprocess benchmark combined parent+child224.73MiB, not full service peak or production-resource entitlement. See PDF_VALIDATION_EVIDENCE.md and STORAGE_CAPACITY.md.

## Configuration presence (names/status only)

Workspace JWT_SECRET, MSG91_AUTHKEY, ENROLLMENT_INTEGRATION_KEY and existing managed-storage credential are present. Presence does not prove strength, authorization, rotation or delivery. **STAFF_SERVICE_KEY absent**; portal/exchange fail closed. Code now also rejects use of the same value as enrollment key. Target production private secret tooling and website project are not available here; no production or website key configured.

Authorized owner/operator must privately generate a strong separate staff key (at least32random bytes), configure STAFF_SERVICE_KEY on app backend and matching website BFF variable with the same value, send X-Staff-Service-Key only from BFF, rotate/revoke using the maintenance plan, and verify presence/negative isolation/real portal login without publishing values. Enrollment uses ENROLLMENT_INTEGRATION_KEY -> X-Integration-Key. Do not substitute it. CORS allowlist and managed proxy are environment-configured; protected Expo/Mongo variables were not changed. `.env.example` contains names/application safety defaults only.

## Consolidated release gates

| Affected feature | Exact missing input/approval/environment | Completed despite gate |
|---|---|---|
| Repository handoff | User-controlled Save to GitHub; verify resulting NEW SHA and pinned links | Code, five docs, generated OpenAPI, sample/test evidence prepared locally |
| Staff portal + security rotation | Authorized app/website private secret tooling; separate staff key; approved rotation window | Header/role/same-subject/fail-closed guards and tests |
| Genuine SMS | Authorized current target environment/recipient and receipt confirmation; valid MSG91/DLT routing | Canonical purpose-bound OTP/rate-limit/session tests; no real SMS sent this stage |
| Media capacity/delivery | Account-specific included DB/object GB/object/upload limits, outbound/read/write charges, CPU/RAM/concurrency, backups/restore/overages | Read-only inventory/sample projections,6 real reads,10k metadata load, ledger/alerts/cache |
| Remote deletion/privacy | Provider-supported actual DELETE+verification or separately approved single-store migration; website/provider erasure/retention acknowledgements | Conservative retained/candidate states, unknown PUT accounting; no false deleted flag |
| Production media write/recovery | Explicit approved test budget/object set and production-equivalent credentials; key rotation/readback/checksum/cleanup capability | Isolated write/failure/retry/402/quota tests. NO new live object test uploads |
| Owner reconciliation | Minimal private website+app exports, consistent/restored backup, conflict report and specific hash/per-ID approval | Offline dry-run tool/contract; owner9999813334 target preserved, no9711881372 password admin |
| Play review access | Authorized isolated reusable review environment/data/role identities + secure private delivery approval | Production has no universal OTP or published review credentials; no review accounts provisioned |
| Native acceptance | Appropriate Android/iOS builds and devices/file providers/sharing/background/OS-kill/nav tests | Safe-area/keyboard controls and browser gestures/navigation tested; not native proof |
| Full-service PDF load | Actual production CPU/RAM/concurrency and complete backend+worker+HTTP+authoring/provider test | Current per-page subprocess measurement, configured limits, isolated negative cases |
| Website cutover | Later website implementation reviewed against final contract; both clients staged, backup/admin continuity/secrets/gates cleared; agreed maintenance window | Self-contained handoff and export instructions; no premature rollout |

No production reconciliation, bulk unit migration, provider migration, purchase or billing change was authorized/executed. Current managed storage cannot fulfill required erasure; do not declare production-ready. Source PDFs/chunks/previews remain private even while erasure is blocked.

## UI audit and external deletion boundaries

Implemented controls: registration/last mobile login/last portal login display; account/login/onboarding/search/assignment/date filters; named telecaller assignment; named request filters; age/status/type filters; daily/range attribution drilldown; admin/billing rate permissions; safe-area/keyboard-aware new screens and corrected Back navigation. Optional public preview reload loses in-memory auth by design; native secure-session reopen is a separate unverified device scenario. No admin-targeted phone change is claimed.

Local account deletion/anonymization+tombstones/outbox remains `external_erasure_pending`, not full global deletion. Website drafts/cache/outbox/sessions and provider-held SMS/AI/chat/media/backup retention need scoped acknowledgement and privacy review. Do not answer store Data Safety fields from code alone; source documents, customer fields, requests/rewards, SDK diagnostics and processors must match the actual released binary and operational retention policy. AI Try-On remains removed; existing separate assistant is preserved.