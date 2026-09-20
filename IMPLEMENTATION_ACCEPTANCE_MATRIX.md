# Implementation Acceptance Matrix — Yash Trade (brief 2026-09-20, R00–R17)

Maintained during the run. States per surface: `NOT STARTED` · `IN PROGRESS` · `IMPLEMENTED - NOT VERIFIED` · `VERIFIED` · `BLOCKED` · `NOT APPLICABLE (reason)`.
`VERIFIED` is never given from code inspection alone. A web-preview pass never implies an Android/iOS pass.

Baseline (recorded before editing, 20 Sep 2026):
- App/backend repo HEAD `0530ebd5753eb75c9b3f489aefe60013c368f178` (dirty tree carried from the previous session: backend `auth/catalog/commerce/core/install/media_lifecycle/pdf_authoring/pdf_jobs/people/queries/readiness/server.py`, new `discovery.py`, `notifications.py`, `queue_reset.py`, three new pytest files; frontend `_layout`, `(tabs)/_layout`, `index`, `login`, `verify-otp`, `api.ts`, `AuthContext.tsx`, `app.json`, `package.json`, new `src/navigation.ts`, `src/push.ts`). Nothing overwritten.
- Website repository: **no remote, checkout, credentials or project access exist in this environment** (`git remote -v` empty, no website env variables). All R16 rows are therefore BLOCKED (handoff only).
- Root `/app/package-lock.json` (82 bytes, `"packages": {}`) confirmed an empty accidental artifact → removed. `frontend/package-lock.json` (npm lockfile in the Yarn-only project, contradicting settled decision #1) → `git rm --cached`, ignored via `.gitignore`. `frontend/yarn.lock` preserved.
- Baseline pytest `tests/shared`: 104 passed then **1 failure** `test_refresh_rotation_and_reuse_revokes_family` (expects 401 on immediate replay; new 30 s refresh-race grace returns 409) — see R01-B. Baseline `tsc`: 1 error in `src/__tests__/dataCache.test.ts` (pre-existing).

Surfaces: **AND** = app Android, **IOS** = app iOS, **BE** = backend, **WEB** = website (BFF/UI). Native columns can only reach VERIFIED with native runtime evidence (device/simulator), which this container does not have.

| ID | Sub-requirement | AND | IOS | BE | WEB | Files / tests / evidence | Remaining blocker |
| --- | --- | --- | --- | --- | --- | --- | --- |
| R00-A | Staff phone preview/commit, customer promotion, same-key replay, partial-write recovery, stale preview binding, owner protection | IMPLEMENTED - NOT VERIFIED | IMPLEMENTED - NOT VERIFIED | VERIFIED | BLOCKED | `shared/people.py` (`staff_phone_preview`, `staff_phone_change`, `convert`, `operation_replay`), `src/components/panel/StaffPhoneChange.tsx`; pytest `test_operations_iteration.py`, `test_shared_auth_identity.py` | Native UI run; website access |
| R00-B | International formatting/paste, call/WhatsApp links normalised | IMPLEMENTED - NOT VERIFIED | IMPLEMENTED - NOT VERIFIED | VERIFIED | BLOCKED | `src/phone.ts`, `PhoneField.tsx`, `queries.contact_links`; Jest `phone.test.ts`, `phoneField.test.tsx` | Native paste test; provider delivery is only observable with a real SMS (not run) |
| R00-C | Thumbnail-first, bounded/private-safe cache, invalidation, dry-run backfill, cold/warm measurements | IMPLEMENTED - NOT VERIFIED | IMPLEMENTED - NOT VERIFIED | VERIFIED | NOT APPLICABLE (native media stack) | `src/dataCache.ts`, `ProtectedMedia.tsx`, `commerce.py /files`, `media_cache.py`; Jest `dataCache.test.ts` | Device cold/warm measurement not possible here (web timings only) |
| R01-A | Login/OTP removed from back history; Home back stays; other screens back; deep link fallback to role home | IN PROGRESS | IN PROGRESS | NOT APPLICABLE | BLOCKED | `src/navigation.ts`, `app/(tabs)/_layout.tsx`, `app/verify-otp.tsx` | Hardware back can only be exercised natively |
| R01-B | Durable session, offline/5xx keeps credentials, single-flight refresh, race grace, replay revocation, expiry, logout + revocation | IMPLEMENTED - NOT VERIFIED | IMPLEMENTED - NOT VERIFIED | IN PROGRESS | BLOCKED | `shared/auth.py` (`rotate_refresh`, `REFRESH_RACE_SECONDS`, `SESSION_IDLE_DAYS`), `src/api.ts`, `src/context/AuthContext.tsx` | Failing baseline test to be re-specified honestly (see notes) |
| R02 | Cross-platform pinch/pan viewer from every photo entry point; image switching resets; thumbnail while HD loads | NOT STARTED | NOT STARTED | NOT APPLICABLE | BLOCKED | `app/image-viewer.tsx` still ScrollView (iOS-only zoom) | Library compatibility check pending |
| R03 | Unseen-first Home refresh, real viewability, stable paging, exhaustion fallback, account isolation | NOT STARTED | NOT STARTED | IMPLEMENTED - NOT VERIFIED | BLOCKED | `shared/discovery.py`; no frontend consumer yet | — |
| R04 | Calculator continuous decimal typing, stable field identity, iOS Done | NOT STARTED | NOT STARTED | NOT APPLICABLE | NOT APPLICABLE | `app/(tabs)/calculator.tsx:92` nested `InputField` | — |
| R05 | Silver INR/kg & gold INR/10 g display/edit, canonical INR/g, conversions, old-client compat | NOT STARTED | NOT STARTED | IMPLEMENTED - NOT VERIFIED | BLOCKED | `shared/commerce.py` (`MCX_DISPLAY_UNITS`, `mcx_display_rate`, `MCX_UNIT_AMBIGUOUS`) | Frontend consumers, deterministic unit tests |
| R06 | Keyboard avoidance on every input screen family + critical modals | IN PROGRESS | IN PROGRESS | NOT APPLICABLE | BLOCKED | `KeyboardProvider` in `app/_layout.tsx`; 14 screens covered, audit pending | Native keyboard-open screenshots impossible here |
| R07 | Four-box OTP autofill/paste/manual/backspace, single submission | IN PROGRESS | IN PROGRESS | NOT APPLICABLE | BLOCKED | `app/verify-otp.tsx` | OS suggestion acceptance needs a device |
| R08 | Server-driven 15 s resend across every purpose; abuse limits retained | IMPLEMENTED - NOT VERIFIED | IMPLEMENTED - NOT VERIFIED | IMPLEMENTED - NOT VERIFIED | BLOCKED | `shared/auth.py:60-91` (`RESEND_COOLDOWN_SECONDS`, `resend_timing`) | Boundary/concurrency tests to add |
| R09-A | Admin notification composer: title/body/image/link/preview/audience/count/test/draft/send/history | NOT STARTED | NOT STARTED | IMPLEMENTED - NOT VERIFIED | BLOCKED | `shared/notifications.py` admin routes; screen file missing | — |
| R09-B | Permission prompt, marketing preference, token lifecycle, logout unlink, deep links, inbox | IN PROGRESS | IN PROGRESS | IMPLEMENTED - NOT VERIFIED | BLOCKED | `src/push.ts`, `/api/notifications/*`; inbox screen missing | — |
| R09-C | Real image push Android + iOS (Notification Service Extension) | IMPLEMENTED - NOT VERIFIED | IN PROGRESS | IMPLEMENTED - NOT VERIFIED | NOT APPLICABLE | `app.json` plugins `expo-notifications`, `expo-rich-notifications`; `richContent.image` in `expo_send` | Needs native build + push credentials + test devices |
| R09-D | Durable outbox, retries, receipts, invalid-token cleanup, no unauthorized audience | NOT APPLICABLE | NOT APPLICABLE | IMPLEMENTED - NOT VERIFIED | NOT APPLICABLE | `notifications.py` (`enqueue`, `fan_out`, `process_job`, `check_receipts`) | Tests with fake transport to add |
| R10-A | Upload Executive sign-in + every Contents/PDF capability inventoried and usable | NOT STARTED | NOT STARTED | IMPLEMENTED - NOT VERIFIED | BLOCKED | `core.content` gate on catalog/pdf_jobs/pdf_authoring/media routes; no frontend gating | Inventory + tests |
| R10-B | Negative authorization across generic staff routes | NOT APPLICABLE | NOT APPLICABLE | IN PROGRESS | BLOCKED | audit of every `c.staff` usage pending | — |
| R11-A | One central pending workspace, all-time pagination, filters, full detail | IN PROGRESS | IN PROGRESS | IMPLEMENTED - NOT VERIFIED | BLOCKED | `queries.listing/detail`, `RequestsWorkspace.tsx`; presets missing; duplicate Panel tab | — |
| R11-B | Heads/notes/follow-ups preserved, create→complete journey, old telecaller inventory | IN PROGRESS | IN PROGRESS | IMPLEMENTED - NOT VERIFIED | BLOCKED | `queries.mutate`, `telecaller.tsx` leads retained | — |
| R12-A | Query notification wired to every creation path, durable retry | NOT APPLICABLE | NOT APPLICABLE | IMPLEMENTED - NOT VERIFIED | NOT APPLICABLE | `queries.notify_created`, `server.py cart/submit`, `notifications.query_created` | Legacy creation paths audit |
| R12-B | Atomic first claim, ownership-enforced mutations, live updates | IN PROGRESS | IN PROGRESS | IMPLEMENTED - NOT VERIFIED | BLOCKED | `queries.claim` (find_one_and_update predicate); `test_central_queries.py` | Concurrency test evidence to record |
| R13-A | Completed list, immutable completion events, IST daily/range report | IN PROGRESS | IN PROGRESS | IMPLEMENTED - NOT VERIFIED | BLOCKED | `queries.record_completion`, `/requests/reports/completions` | Admin UI |
| R13-B | 03:00 IST release of every non-terminal head, no cutoff, history retained | NOT APPLICABLE | NOT APPLICABLE | IMPLEMENTED - NOT VERIFIED | NOT APPLICABLE | `shared/queue_reset.py`; `test_daily_release.py` | Boundary tests at 02:59:59/03:00:00 |
| R13-C | Deployed scheduler, catch-up, multi-worker idempotency, races | NOT APPLICABLE | NOT APPLICABLE | IN PROGRESS | NOT APPLICABLE | `install.py` starts `queue_reset.worker_loop`; readiness exposure pending | Evidence that the worker is registered in the deployed process |
| R14 | Admin/billing on the same central workspace, role-action matrix | IN PROGRESS | IN PROGRESS | IMPLEMENTED - NOT VERIFIED | BLOCKED | `c.operations` / `c.query_workers` gates | Retire Panel duplicate tab |
| R15-A | Distinct disable / re-enable / delete for customers and staff, clear UI errors | NOT STARTED | NOT STARTED | IMPLEMENTED - NOT VERIFIED | BLOCKED | `people.staff_disable`, `people.admin_delete`, `/customers/{uid}/delete` | Frontend actions |
| R15-B | Sessions/tokens/assignments/erasure cleanup, protected owner/last admin, retry | NOT APPLICABLE | NOT APPLICABLE | IMPLEMENTED - NOT VERIFIED | BLOCKED | `people.admin_delete` → `release_assignments`, `detach_devices`, `erase()` | Tests |
| R16-A | Website code changes + compatibility tests | NOT APPLICABLE | NOT APPLICABLE | NOT APPLICABLE | BLOCKED | No website repository access in this environment | **WEBSITE IMPLEMENTATION/DEPLOYMENT BLOCKED** |
| R16-B | Shared contract/handoff, deploy order, website deployment status | NOT APPLICABLE | NOT APPLICABLE | IN PROGRESS | BLOCKED | `WEBSITE_HANDOFF.md`, `YASH_SHARED_API_CONTRACT.md`, OpenAPI | Website deploy needs the website project |
| R17-A | Store metadata / privacy / data-safety / reviewer-access docs | NOT STARTED | NOT STARTED | NOT APPLICABLE | NOT APPLICABLE | `APP_STORE_SUBMISSION.md` to create | — |
| R17-B | Authentic native screenshots + verified build IDs | BLOCKED | BLOCKED | NOT APPLICABLE | NOT APPLICABLE | Existing PNGs are Expo-web captures | No native build tooling/devices here |
| R17-C | Docs, final tests, commits, migrations/rollback, release-state report | IN PROGRESS | IN PROGRESS | IN PROGRESS | BLOCKED | PRD, RELEASE_READINESS, this file | — |

## Test-run log (command · environment · timestamp · result · artefact)
| # | Command | Env | Timestamp (UTC) | Result | Artefact |
| --- | --- | --- | --- | --- | --- |
| 1 | `pytest tests/shared -q -x` (baseline, dirty tree) | preview container, local mongod | 2026-09-20 | 104 passed, 1 failed (`test_refresh_rotation_and_reuse_revokes_family`: 409 ≠ 401) | `/tmp/pytest_baseline.log` |
| 2 | `npx tsc --noEmit` (baseline) | preview container | 2026-09-20 | 1 error `src/__tests__/dataCache.test.ts(45,12)` | `/tmp/tsc_baseline.log` |

## Notes / assumptions
- R01-B baseline failure: the new grace window (`REFRESH_RACE_SECONDS=30`) answers an immediate replay of a just-rotated refresh token with `409 REFRESH_IN_PROGRESS` and keeps the family alive so two concurrent app calls cannot revoke each other. Replay OUTSIDE the window must still revoke the family (401). The test will be re-specified to cover both cases with a fake clock rather than relaxed.
- Release states are tracked separately at the end of this file.

## Release states (kept separate, never merged)
| State | Value |
| --- | --- |
| Code Complete | IN PROGRESS |
| Tests Passed | IN PROGRESS |
| Native Verified | NOT VERIFIED (no device/simulator in this environment) |
| Website Deployed | BLOCKED (no website project access) |
| Build Uploaded | NOT DONE (owner: Publish → store builds) |
| Submitted for Review | NOT DONE |
| Store Live | NOT DONE |
