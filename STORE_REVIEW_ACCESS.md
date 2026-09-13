# Store-review access — isolated reviewer accounts (owner-run)

**Build `shared-v1-store-submission-2026-09-13` (13 Sep 2026).** App Store and Play reviewers sign in with a **Reviewer ID + reusable access key** on the hidden *Store reviewer access* screen (login screen → small link under the footer → `/review-access`). Sessions are bound server-side to the **store-review copy**: the `review__*` prefixed collections of the SAME MongoDB database (`DB_NAME`). Isolation is **application-enforced** by the signature-verified session scope (`scope=review` in the JWT), not database-level; the deployment's MongoDB user needs no rights beyond its main database, and the former separate review database / `REVIEW_DB_NAME` setting **no longer exists**. Synthetic customers, products, rates, enquiries and rewards; SMS/calls are simulated and recorded; media uploads are stored inside `review__review_blobs` (5 MiB/file, 256 MiB total); the AI assistant is genuine (after the same AI-consent step real users see) but limited to 600 characters per message and 40 messages per reviewer per UTC day. Real users keep the normal MSG91 OTP flow; nothing about it changed.

Switch: `REVIEW_ACCESS_ENABLED=true` in `backend/.env` (declared with the real value, carried into every deployment). Off/placeholder → reviewer login answers 503 `REVIEW_UNAVAILABLE`, `/api/health` `flows.review.issues=["REVIEW_ACCESS_DISABLED"]`, no `review__` collection is created.

## Isolation guarantees (all covered by tests)

| Guarantee | Enforced by |
|---|---|
| `REVIEW_ACCESS_ENABLED` off/placeholder → `POST /api/auth/review/login` **503 `REVIEW_UNAVAILABLE`**; never falls back to production; nothing created | `core.configure/initialize_review`, `shared/review.py`; `test_review_login_is_denied_when_review_access_is_disabled`, `test_console_is_unavailable_when_review_access_is_disabled` |
| Review storage that refuses initialisation (MongoDB error) → startup continues, review marked unusable for the process (`flows.review.usable=false`, `issues=[REVIEW_STORAGE_UNAVAILABLE]`), reviewer sign-in/sessions 503, workers skip the review scope; a failing **primary** database still aborts startup | `core.initialize_review()`, `core.scopes()`; `test_review_prefixed_storage.py` (real `mongod --auth` with a user restricted to the main database: reviewer sign-in is served from the prefixed collections **without** a second database) |
| Every collection touched in review scope resolves to its `review__` name; `$lookup` targets go through `core.collection_name()`; nothing in production scope ever resolves a prefixed name; `--reset-data`/RESET asserts each target name before emptying it | `core._PrefixedDatabase`, `queries.py`; `test_prefixed_view_resolves_only_review_collections_and_reset_never_touches_unprefixed_data` |
| Scope comes only from the signed session (`scope=review`) or a `review.`-prefixed refresh token; a forged/stripped claim or a production identity in review scope is 401 | `core.current_user`; `test_forged_scope_claims_and_review_phones_cannot_cross_environments` |
| Reviewer sessions cannot read/modify production customers, products, requests, media, staff records, import jobs, outbox or SMS provider | scope-aware `db`/`store_object`/`send_sms` gates; `test_review_sessions_cannot_read_or_modify_production_records`, `test_review_actions_persist…`; live preview iterations 26/27 (`test_reports/iteration_26.json`, `iteration_27.json`: uploads, PDF import job processed by the background worker, exports, deletion — unprefixed counts unchanged) |
| Review phones are not OTP identities in production (404, no SMS) and are invisible to the website integration lookup | same test file |
| Only bcrypt hashes are stored; unknown IDs cost the same as wrong keys; per-IP and per-account rate limits; audit rows only in `review__review_access_log` | `shared/review.py`; `test_reviewer_login_rate_limit_is_per_account` |
| Rotation invalidates the old key **and** live sessions; revocation disables the account (and never regains access through profile recreation); reset wipes synthetic data but keeps the four credentials and signs every reviewer out | `review_seed.rotate/revoke/seed_dataset(reset=True)`; owner-console + CLI suites |
| **Simulated review OTP** is disclosed only in the response to the SAME authenticated review session for ITS OWN challenge (`disclose_to == subject`: account deletion, phone change); bound to phone+purpose+subject, 10-minute expiry, single use, 5 attempts; never logged (the simulated `sms_log` row and the challenge row carry no digits); unauthenticated requests, other accounts' challenges (`/auth/send-otp` with a review bearer), production sessions and signed-out/forged/expired sessions never receive digits | `auth.start_challenge(disclose_to=…)`; `test_simulated_review_otp_is_disclosed_only_to_its_own_authenticated_review_session` |
| **Fresh sample profile after deletion**: a reviewer who deletes the sample account signs in again with the same ENABLED credential and gets a NEW synthetic profile (`profile_recreated: true`); nothing of the old one returns (history, uploads, rewards, AI consent, sessions — `session_version` advances, families revoked); a REVOKED credential never recreates anything; ordinary customers never auto-recreate | `review.review_login` → `review_seed.restore_profile`; `test_reviewer_deletion_then_repeat_login_starts_a_fresh_sample_profile_without_restoring_anything` |
| Background workers (PDF import, deletion retry) iterate production then review **inside separate scopes** | `core.scopes()`; CLI suite background-job test; live iteration 27 B4 |

## Owner console (primary path) — app → Panel → **Store review** (`/review-keys`)

Visible only to the **owner administrator** (`OWNER_ADMIN_PHONE`, decided server-side on the canonical record: `403 OWNER_ADMIN_REQUIRED` for any other admin, `403 REVIEW_SCOPE_FORBIDDEN` for reviewer administrators, whose panel does not even show the tab). Every key operation needs **fresh authentication**: a single-use 4-digit OTP (purpose `review_keys`) sent to the owner's own registered number through the normal MSG91 transport, valid 10 minutes.

| Action | Effect |
|---|---|
| **PROVISION n MISSING ACCOUNTS + SAMPLE DATA** | seeds the synthetic dataset (idempotent) and creates only the missing accounts; existing keys are **never** changed; the new keys are shown **once** (copy per account, COPY PRIVATE NOTE, DOWNLOAD .TXT) — only bcrypt hashes are stored |
| **ROTATE** (per account) | new key shown once; the old key and its live sessions stop working immediately (including in the store forms) |
| **REVOKE** (per account) | account disabled, sessions ended; a later ROTATE re-enables it with a new key |
| **RESET SAMPLE DATA (KEEPS THE 4 KEYS)** | empties and reseeds only the allow-listed `review__` collections (same as CLI `--reset-data`); credentials untouched; every reviewer session/refresh token invalidated; live customer data untouched |

API: `GET /api/admin/review/status`, `POST /api/admin/review/challenge`, `POST /api/admin/review/keys {action: provision|rotate|revoke|reset_data, reviewer_id?, otp, challenge_id, environment, api_base_url}`. The screen also prints the store-form text and sign-in steps, and marks the environment (`PREVIEW · <host>` vs `PRODUCTION · <host>`) from the backend origin it talks to. Health reports only a count: `flows.review.accounts_enabled`.

## CLI (equivalent, owner's PC) — `backend/tools/provision_review_access.py`

Requires `MONGO_URL` and `DB_NAME` as environment variables (the Windows wrapper `Provision-ReviewAccess.ps1 -Environment production -DbName <DB_NAME> …` asks for the connection string with a hidden prompt). `--expected-db <DB_NAME>` must equal `DB_NAME`; the `review__` collections are written into that database. Production issuance/rotation requires `--write-note <private file outside the repo>` (`-NotePath`); keys are never printed for production. `--verify` signs in with every issued key against `--api-base-url`, checks role + `review_environment`, signs out, proves the old session is rejected and repeats the sign-in; `--verify-note` re-verifies a stored note read-only (pre-flight pins environment, database and backend URL). Exit codes: 0 done/verified, 1 blocked before any change, 2 keys issued/kept but verification failed/incomplete (tested).

## Preview accounts vs production accounts

| | Preview (this workspace) | Production (owner-run) |
|---|---|---|
| Backend | `https://trade-app-submit.preview.emergentagent.com/api` | `https://yash-tryon-test.emergent.host/api` after Save to GitHub + republish on this build |
| Review storage | `review__*` collections of `jewellers_app` | `review__*` collections of the production `DB_NAME` (no extra setting, no extra database rights) |
| Who provisioned | agent (CLI), 13 Sep 2026, for the automated PREVIEW E2E run only | **owner**, through the owner console or the CLI |
| Where the keys are | were only in a private `/tmp` note inside the disposable preview container; **all four accounts REVOKED and the note shredded after the run** (`flows.review.accounts_enabled=0`) | private note on the owner's PC / password manager, then the store review forms |
| Status | verified 13 Sep 2026: CLI `--verify` PASS for all four roles + testing-agent iterations 26/27 (PREVIEW, automated) | **not yet provisioned — reviewer access is NOT ready for submission until this is done** |

Preview keys were never the reviewer credentials for store submission.

## Production procedure — A. owner console in the app (primary, no PC tooling)

Prerequisites: this build deployed (`GET https://yash-tryon-test.emergent.host/api/health` → `build=shared-v1-store-submission-2026-09-13`, `flows.review.ready=true`, `flows.owner_admin.ready=true`), and the owner signed in to the production app with the real MSG91 OTP as `OWNER_ADMIN_PHONE` (role `admin` on the canonical record). No extra Secret, database or database right is needed for review storage: the `review__` collections are created inside the production `DB_NAME` on first provisioning.

1. Panel → **Store review** (`/review-keys`). The badge must read **PRODUCTION · yash-tryon-test.emergent.host**; the Environment card shows `ON · usable`, storage `prefixed_collections in database <DB_NAME>`, and all four accounts as `not provisioned`.
2. Tap **PROVISION 4 MISSING ACCOUNTS + SAMPLE DATA** → a 4-digit OTP is sent to the owner's registered number (one real SMS) → enter it → **CONFIRM PROVISION**.
3. The four keys appear **once**. Tap **COPY PRIVATE NOTE** or **DOWNLOAD .TXT** and store the note in a password manager / encrypted drive. The server keeps only bcrypt hashes; a lost key can only be rotated.
4. Verify: sign out, open *Store reviewer access* on the login screen, sign in with `store-review-customer` + its key → gold **STORE-REVIEW ENVIRONMENT** banner, Profile shows *Review Customer (synthetic)*. Repeat for `store-review-admin` (staff panel, no *Store review* tab), `store-review-telecaller` (`/telecaller`) and `store-review-billing` (panel). Sign out after each. Optionally run the read-only CLI re-check below (`-VerifyNote` needs a CLI-written note; for a console-written note use the four manual sign-ins).
5. Paste the note's "TEXT FOR THE STORE REVIEW FORMS" and the Reviewer ID / Access key pairs into the store forms (section "Entering the credentials in the stores" on the screen and below).

Later: **ROTATE** / **REVOKE** per account and **RESET SAMPLE DATA** on the same screen, each with a fresh OTP. Reviewer administrators never see the tab and receive `403 REVIEW_SCOPE_FORBIDDEN`; any other production admin receives `403 OWNER_ADMIN_REQUIRED` (both render as a locked card, never as a login prompt).

## Production procedure — B. CLI on the owner's Windows PC (equivalent)

Prerequisites: `PRODUCTION_ADMIN_RECOVERY.md` section 0 (Python + `Setup-Operator.ps1`), the production `DB_NAME` exactly as shown in **Manage Publishes → Secrets**, the production MongoDB connection string (Manage Publishes → Database). Nothing has to be redeployed: there is no separate review database and no review setting besides `REVIEW_ACCESS_ENABLED=true` (already declared in `backend/.env`).

```powershell
cd C:\Yash\app
.\backend\tools\windows\Provision-ReviewAccess.ps1 -Environment production `
    -DbName <DB_NAME> `
    -ApiBaseUrl https://yash-tryon-test.emergent.host/api `
    -Provision -Seed -Status -Verify `
    -NotePath "$env:USERPROFILE\Private\yash-review-production.txt"
```
Paste the production MongoDB connection string at the hidden prompt. The script:

1. checks that `DB_NAME` equals `-DbName` (the `review__` collections are written into THIS database, unprefixed collections are never touched) and that the note path is outside the repository and does not exist yet (refused **before** any key is created, so a key can never be lost);
2. creates indexes and the synthetic dataset in the `review__` collections only (idempotent; a second run adds nothing);
3. creates the four reviewer accounts (`store-review-customer`, `store-review-admin`, `store-review-telecaller`, `store-review-billing`) and stores only bcrypt hashes;
4. **verifies each new key against the deployed backend**: `POST /auth/review/login` → `GET /auth/me` (role and `review_environment=true`) → `POST /auth/logout` (must answer `logged_out=true`) → a second `GET /auth/me` with the old token must be **401**. A failed logout or a still-usable session is reported as FAIL, never PASS; results appear as `verification` / `verified_all` / `all_four_roles_verified` in the JSON output, without secrets;
5. writes the keys, sign-in steps, store-form text and rotate/revoke commands **only** to the note file (created exclusively with owner-only permissions **before** any key exists, so a refused or unwritable location never loses a key). Nothing secret is printed. Keys are persisted to the note **before** the network verification runs, so a connectivity failure leaves the keys safe and the note marked `NOT COMPLETED`.

**Exit codes (tested, `test_review_provisioning_cli.py::test_cli_verify_against_live_backend_returns_strict_exit_codes`):**

| Code | Meaning | What to do |
|---|---|---|
| **0** | Requested work done; when `-Verify`/`-VerifyNote` was given, **every** key was proved end-to-end | Use the note for the store forms |
| **1** | Blocked **before any change and before any network request** (placeholder/mismatched database, note inside the repository or already existing, wrong `-Environment` for the note, production issuance without a note, `-VerifyNote` whose note pins a **different backend** than `-ApiBaseUrl` — scheme, host, port and path must all match — or records no backend at all) | Fix the argument/setting and re-run; nothing was issued and nothing was sent |
| **2** | Keys were issued/kept but verification **FAILED** (a key was rejected, wrong role/scope, logout not honoured, session reusable) or was **INCOMPLETE** (backend unreachable after a valid pre-flight, or `-Verify` with nothing issued) | The note records the outcome (for a transport failure: a sanitized `NOT COMPLETED - <ErrorType>` line, never a key or payload). Fix the cause, then re-run the **same `-VerifyNote <note> -ApiBaseUrl <pinned backend>`** command (read-only: no connection string, no account change; appends a dated `VERIFICATION RE-RUN` block). Never treat exit 2 as success |

The JSON printed on stdout carries the run result in `outcome` (`ok`, `verification_failed`, `verification_incomplete`); the account table requested with `-Status` stays in `status` and is never overwritten. `-VerifyNote` refuses a note whose header names a different environment, database **or backend URL**, so preview keys can never be "verified" against production and keys are never sent to any server other than the one they were issued for. If a note was written for the wrong backend, issue a new pinned note with `-Rotate <reviewer_id> -ApiBaseUrl <correct>/api -Verify -NotePath <new file>` instead of editing the note.

Then: open the production app → *Store reviewer access* → sign in once yourself with the customer key from the note to see the gold **STORE-REVIEW ENVIRONMENT** banner; then paste the note's "TEXT FOR THE STORE REVIEW FORMS" plus the Reviewer ID/Access key pairs into App Store Connect (*App Review Information → Sign-in required*) and Play Console (*App content → App access → All or some functionality is restricted*). Give reviewers the **customer** account as the primary login and the **admin** account as the second login; telecaller/billing are optional.

Repeat runs: `-Status` (read-only), `-Seed` (add missing synthetic rows), `-ResetData` (wipe synthetic data, keep accounts), `-Rotate <reviewer_id> -Verify -NotePath <new file>` (new key; old key and sessions stop working immediately), `-Revoke <reviewer_id>`, `-VerifyNote <existing note> -ApiBaseUrl <…/api>` (re-verify stored keys, read-only). `-Provision` on existing accounts issues nothing and writes no note (no stale key can leak); combined with `-Verify` it exits 2 (`verification_incomplete`) because there is nothing new to prove. Console and CLI operate on the same accounts: a key issued in the app can be revoked from the CLI and vice versa.

Equivalent non-Windows commands (from `backend/`, with `MONGO_URL` and `DB_NAME` exported in the shell, not on the command line):
`python tools/provision_review_access.py --expected-db <DB_NAME> --provision --seed --status --environment production --api-base-url https://yash-tryon-test.emergent.host/api --verify --write-note ~/Private/yash-review-production.txt`
`python tools/provision_review_access.py --expected-db <DB_NAME> --verify-note ~/Private/yash-review-production.txt --environment production --api-base-url https://yash-tryon-test.emergent.host/api`

Reviewer keys sign in to the **synthetic review copy only**. They never grant, prove or replace admin status on the production database (that is the owner's same-ID recovery in `PRODUCTION_ADMIN_RECOVERY.md` §3).

## What reviewers can do

- **Customer**: catalogue (12 sample products with generated images), live rates, rate list, enquiries/requests (create + history), rewards (120 sample points), AI assistant (bounded), profile, phone-change and account-deletion flows with **simulated** OTP (the code is never delivered; the flow shows the screens and a wrong code fails as in production).
- **Admin**: staff panel — customers (10 synthetic), enquiries (8), rates/slabs, products/batches, banners/schemes/brands, SMS diagnostics (simulated log), media usage, reviewed PDF import (jobs live in `review__import_jobs` / `review__batches`). The *Store review* owner tab is hidden and its API refuses review sessions.
- **Telecaller**: assigned enquiries, claims, follow-ups on synthetic customers. **Billing executive**: customer search, query history, rates.

## Costs and limits in the review environment

AI: 40 messages/day/reviewer, 600 chars/message, genuine Claude Sonnet 4.5 via the existing `EMERGENT_LLM_KEY` after the reviewer grants AI consent (automated tests mock the provider; live preview iteration 27 used the real provider once). Media: 5 MiB/file, 256 MiB total inside `review__review_blobs` of the same database — no managed object-storage writes. SMS: none (simulated; the one-time code for the sample profile's own deletion/phone-change is shown on screen to that session only). Reset with **RESET SAMPLE DATA** / `-ResetData` at any time.

## Evidence

- Backend (pytest, isolated synthetic databases, SMS/storage/AI transports intercepted): `tests/shared/test_review_access_isolation.py` (9: 503 when disabled, cross-scope reads/writes refused, forged scope claims, review phones invisible to production OTP and website lookup, per-account rate limit, simulated-OTP disclosure only to the owning review session, fresh sample profile after deletion), `test_review_prefixed_storage.py` (2: a real `mongod --auth` user restricted to the main database serves reviewer sign-in from the `review__` collections **without a second database**; the prefixed view resolves only `review__` names and RESET never touches unprefixed data), `test_review_owner_console.py` (4: only the owner in production scope may open the console — reviewer admin `REVIEW_SCOPE_FORBIDDEN`, other admin `OWNER_ADMIN_REQUIRED`; keys need a fresh single-use OTP, are shown once and never rotate implicitly; reset keeps keys and signs reviewers out; console 503 when review access is disabled), `test_ai_consent_and_deletion.py` (3: no text reaches the provider without current consent and withdrawal purges history; an in-flight reply after withdrawal is not stored; account deletion removes analytics/AI history/consent and reports truthfully), `test_review_provisioning_cli.py` (8: real subprocess CLI provisioning/idempotency/status, fail-closed configuration, private note + rotate/revoke/reset, verify-step checks incl. failed logout → FAIL, `--verify-note` pinning of environment/database/backend URL, live-backend exit codes 0/1/2, bounded AI in review scope, background-job scope), `test_placeholder_configuration.py` (2: `SET_IN_PUBLISH_SECRETS` never becomes a staff credential; the CLI refuses placeholders before touching Mongo). Full shared suite: `test_reports/pytest/store_submission_full_2026-09-13.xml`.
- Frontend (Jest, API mocked): `reviewAccessScreen.test.tsx` (reviewer sign-in screen: gating, four role destinations, 503/429/401, masking, back), `reviewKeysAndAiConsent.test.tsx` (owner console: non-owner refusal, fresh OTP + keys shown once + copy, wrong OTP; AI assistant consent gate), `reviewKeysAccessGate.test.tsx` (hydrating → no redirect/no API call; signed-out → `/login` without API call; owner → table + actions; reviewer admin → `REVIEW_SCOPE_FORBIDDEN` card, no redirect; other admin → `OWNER_ADMIN_REQUIRED` card), `authSessionWeb.test.tsx` (web sessions are memory-only: no token → signed out without `/auth/me`; a provider remount re-validates the in-memory token with the server; a rejected token or logout ends in signed-out). `frontend/app/review-access.tsx` and `review-keys.tsx` are tracked in Git.
- Live PREVIEW (automated, `https://trade-app-submit.preview.emergentagent.com`, no real SMS): testing-agent iterations 26/27 (`test_reports/iteration_26.json`, `iteration_27.json`, prod-snapshot JSONs: unprefixed collection counts unchanged while reviewers uploaded, imported a PDF, exported, chatted with the real AI once and deleted the sample profile). 13 Sep follow-up (main agent, browser): signed-out direct URL → `/login`; reviewer admin client-side navigation to `/review-keys` → locked card *Not available in the store-review environment* with the banner still shown, hard reload → `/login`; a disposable non-owner admin (synthetic record, removed afterwards) → *Owner administrator only* card via the panel tab and via client-side navigation, hard reload → `/login`. Preview reviewer accounts are **revoked** again after each run.
- Not yet done (owner, production): provisioning the production accounts, the four production sign-ins, a reviewer sign-in on a physical device, and the owner console positive path with a real OTP.
