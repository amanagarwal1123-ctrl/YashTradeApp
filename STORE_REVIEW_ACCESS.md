# Store-review access — isolated reviewer accounts (owner-run)

App Store and Play reviewers sign in with a **Reviewer ID + reusable access key** on the hidden *Store reviewer access* screen (login screen → small link under the footer → `/review-access`). Sessions are bound server-side to a **separate review database** (`REVIEW_DB_NAME`): synthetic customers, products, rates, enquiries and rewards; SMS/calls are simulated and logged; media uploads are stored inside the review database (5 MiB/file, 256 MiB total); the AI assistant is genuine but limited to 600 characters per message and 40 messages per reviewer per UTC day. Real users keep the normal MSG91 OTP flow; nothing about it changed.

## Isolation guarantees (all covered by tests)

| Guarantee | Enforced by |
|---|---|
| Missing **or placeholder** (`SET_IN_PUBLISH_SECRETS`) `REVIEW_DB_NAME` → `POST /api/auth/review/login` answers **503 `REVIEW_UNAVAILABLE`**; never falls back to production; no database of that name is ever created | `shared/review.py`, `core.active_db()`, `core.setting()`; `test_review_login_is_denied_when_no_review_database_is_configured`, `test_placeholder_configuration.py` |
| `REVIEW_DB_NAME == DB_NAME` → server refuses to start; CLI refuses to run | `server.py`, `core.configure()`, `provision_review_access.py` |
| Scope comes only from the signed session (`scope=review`) or a `review.`-prefixed refresh token; a forged/stripped claim or a production identity in review scope is 401 | `core.current_user`; `test_forged_scope_claims_and_review_phones_cannot_cross_environments` |
| Reviewer sessions cannot read/modify production customers, products, requests, media, staff records, import jobs, outbox or SMS provider | scope-aware `db`/`store_object`/`send_sms` gates; `test_review_sessions_cannot_read_or_modify_production_records`, `test_review_actions_persist…`, `test_review_background_jobs_and_workers_stay_in_review_scope`, `test_review_deletion_flow_stays_out_of_the_website_outbox` |
| Review phones are not OTP identities in production (404, no SMS) and are invisible to the website integration lookup | same test file |
| Only bcrypt hashes are stored; unknown IDs cost the same as wrong keys; per-IP and per-account rate limits; audit rows only in the review DB | `shared/review.py`; `test_reviewer_login_rate_limit_is_per_account` |
| Rotation invalidates the old key **and** live sessions; revocation disables the account; `--reset-data` wipes synthetic data but keeps accounts | `review_seed.rotate/revoke/seed_dataset(reset=True)`; CLI suite |
| Background workers (PDF import, deletion retry) iterate production then review **inside separate scopes** | `core.scopes()`; `test_review_background_jobs_and_workers_stay_in_review_scope` |

## Preview accounts vs production accounts

| | Preview (this workspace) | Production (owner-run) |
|---|---|---|
| Backend | `https://yash-trade-backend.preview.emergentagent.com/api` | `https://yash-tryon-test.emergent.host/api` after Redeploy with `REVIEW_DB_NAME` |
| Review database | `jewellers_app_review` (preview Mongo) | your own name, e.g. `<DB_NAME>_review`, set in Manage Publishes → Secrets |
| Who provisioned | agent, for automated testing only | **owner**, on the owner's PC |
| Where the keys are | private `/tmp` file inside the disposable preview container; rotated after testing | private file on the owner's PC (`-NotePath`), then the store review forms |
| Status | provisioned and verified 12 Sep 2026 (all four roles PASS against the deployed preview backend; `test_reports/review_provisioning_preview_2026-09-12.json`) | **not yet provisioned** — needs section "Production procedure" |

Preview keys are **not** the reviewer credentials for store submission. Never reuse them.

## Production procedure (owner's Windows PC)

Prerequisites: `PRODUCTION_ADMIN_RECOVERY.md` section 0 (Python + `Setup-Operator.ps1`), production `REVIEW_DB_NAME` set in **Manage Publishes → Secrets** and the app **redeployed** so `GET /api/health` shows `configuration.REVIEW_DB_NAME=true` and `flows.review.ready=true`.

```powershell
cd C:\Yash\app
.\backend\tools\windows\Provision-ReviewAccess.ps1 -Environment production `
    -DbName <DB_NAME> -ReviewDbName <REVIEW_DB_NAME> `
    -ApiBaseUrl https://yash-tryon-test.emergent.host/api `
    -Provision -Seed -Status -Verify `
    -NotePath "$env:USERPROFILE\Private\yash-review-production.txt"
```
Paste the production MongoDB connection string at the hidden prompt (from Manage Publishes → Database). The script:

1. checks `DB_NAME ≠ REVIEW_DB_NAME` and that the note path is outside the repository and does not exist yet (refused **before** any key is created, so a key can never be lost);
2. creates indexes and the synthetic dataset in the review database only (idempotent; a second run adds nothing);
3. creates the four reviewer accounts (`store-review-customer`, `store-review-admin`, `store-review-telecaller`, `store-review-billing`) and stores only bcrypt hashes;
4. **verifies each new key against the deployed backend**: `POST /auth/review/login` → `GET /auth/me` (role and `review_environment=true`) → `POST /auth/logout` (must answer `logged_out=true`) → a second `GET /auth/me` with the old token must be **401**. A failed logout or a still-usable session is reported as FAIL, never PASS; results appear as `verification` / `verified_all` / `all_four_roles_verified` in the JSON output, without secrets;
5. writes the keys, sign-in steps, store-form text and rotate/revoke commands **only** to the note file (created exclusively with owner-only permissions **before** any key exists, so a refused or unwritable location never loses a key). Nothing secret is printed. Keys are persisted to the note **before** the network verification runs, so a connectivity failure leaves the keys safe and the note marked `NOT COMPLETED`.

**Exit codes (tested, `test_review_provisioning_cli.py::test_cli_verify_against_live_backend_returns_strict_exit_codes`):**

| Code | Meaning | What to do |
|---|---|---|
| **0** | Requested work done; when `-Verify`/`-VerifyNote` was given, **every** key was proved end-to-end | Use the note for the store forms |
| **1** | Blocked **before any change** (placeholder/mismatched database, note inside the repository or already existing, wrong `-Environment` for the note, production issuance without a note) | Fix the argument/setting and re-run; nothing was issued |
| **2** | Keys were issued/kept but verification **FAILED** (a key was rejected, wrong role/scope, logout not honoured, session reusable) or was **INCOMPLETE** (backend unreachable, or `-Verify` with nothing issued) | The note records the outcome. Fix the cause, then re-run **`-VerifyNote <note>`** (read-only: no connection string, no account change; appends a dated `VERIFICATION RE-RUN` block). Never treat exit 2 as success |

The JSON printed on stdout carries the run result in `outcome` (`ok`, `verification_failed`, `verification_incomplete`); the account table requested with `-Status` stays in `status` and is never overwritten. `-VerifyNote` refuses a note whose header names a different environment or review database, so preview keys can never be "verified" against production.

Then: open the production app → *Store reviewer access* → sign in once yourself with the customer key from the note to see the gold **STORE-REVIEW ENVIRONMENT** banner; then paste the note's "TEXT FOR THE STORE REVIEW FORMS" plus the Reviewer ID/Access key pairs into App Store Connect (*App Review Information → Sign-in required*) and Play Console (*App content → App access → All or some functionality is restricted*). Give reviewers the **customer** account as the primary login and the **admin** account as the second login; telecaller/billing are optional.

Repeat runs: `-Status` (read-only), `-Seed` (add missing synthetic rows), `-ResetData` (wipe synthetic data, keep accounts), `-Rotate <reviewer_id> -Verify -NotePath <new file>` (new key; old key and sessions stop working immediately), `-Revoke <reviewer_id>`, `-VerifyNote <existing note> -ApiBaseUrl <…/api>` (re-verify stored keys, read-only). `-Provision` on existing accounts issues nothing and writes no note (no stale key can leak); combined with `-Verify` it exits 2 (`verification_incomplete`) because there is nothing new to prove.

Equivalent non-Windows commands (from `backend/`, with `MONGO_URL`, `DB_NAME`, `REVIEW_DB_NAME` exported in the shell, not on the command line):
`python tools/provision_review_access.py --expected-review-db <REVIEW_DB_NAME> --provision --seed --status --environment production --api-base-url https://yash-tryon-test.emergent.host/api --verify --write-note ~/Private/yash-review-production.txt`
`python tools/provision_review_access.py --expected-review-db <REVIEW_DB_NAME> --verify-note ~/Private/yash-review-production.txt --environment production --api-base-url https://yash-tryon-test.emergent.host/api`

Reviewer keys sign in to the **synthetic review copy only**. They never grant, prove or replace admin status on the production database (that is the owner's same-ID recovery in `PRODUCTION_ADMIN_RECOVERY.md` §3).

## What reviewers can do

- **Customer**: catalogue (12 sample products with generated images), live rates, rate list, enquiries/requests (create + history), rewards (120 sample points), AI assistant (bounded), profile, phone-change and account-deletion flows with **simulated** OTP (the code is never delivered; the flow shows the screens and a wrong code fails as in production).
- **Admin**: staff panel — customers (10 synthetic), enquiries (8), rates/slabs, products/batches, banners/schemes/brands, SMS diagnostics (simulated log), media usage, reviewed PDF import (jobs live in the review DB).
- **Telecaller**: assigned enquiries, claims, follow-ups on synthetic customers. **Billing executive**: customer search, query history, rates.

## Costs and limits in the review environment

AI: 40 messages/day/reviewer, 600 chars/message, genuine Claude Sonnet 4.5 via the existing `EMERGENT_LLM_KEY` (automated tests mock the provider). Media: 5 MiB/file, 256 MiB total inside the review database — no managed object-storage writes. SMS: none (simulated). Reset with `-ResetData` at any time.

## Evidence

- Backend: `backend/tests/shared/test_review_access_isolation.py` (8 tests) and `backend/tests/shared/test_review_provisioning_cli.py` (8 tests: real subprocess CLI provisioning/idempotency/status, fail-closed configuration, private note + rotate/revoke/reset, verify-step unit checks incl. failed logout → FAIL, `--verify-note` recovery with environment/database pinning, **live-backend end-to-end exit codes 0/1/2** against a real HTTP process, bounded AI in review scope, background-job scope); `backend/tests/shared/test_placeholder_configuration.py` (2 tests: `SET_IN_PUBLISH_SECRETS` never becomes a review database or staff credential in the running backend; the CLI refuses it before touching Mongo).
- Frontend: `frontend/src/__tests__/reviewAccessScreen.test.tsx` (8 tests: login-screen link → `/review-access`; SIGN IN gating; all four roles sign in and route to their destination — customer `/(tabs)`, admin and billing `/panel`, telecaller `/telecaller` — with trimmed payload and no role chosen client-side; 503/429/401 messages; key masking; back navigation). `frontend/app/review-access.tsx` is tracked in Git (the former root `.gitignore` rule `review-access*` that hid it is narrowed to `*review-access*.txt|log|bak` private notes).
- Preview end-to-end: `test_reports/review_provisioning_preview_2026-09-12.json` (no secrets).
- Not yet done: production provisioning and a reviewer sign-in on a physical device against production (owner actions above).
