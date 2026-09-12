# Store-review access — isolated reviewer accounts (owner-run)

App Store and Play reviewers sign in with a **Reviewer ID + reusable access key** on the hidden *Store reviewer access* screen (login screen → small link under the footer → `/review-access`). Sessions are bound server-side to a **separate review database** (`REVIEW_DB_NAME`): synthetic customers, products, rates, enquiries and rewards; SMS/calls are simulated and logged; media uploads are stored inside the review database (5 MiB/file, 256 MiB total); the AI assistant is genuine but limited to 600 characters per message and 40 messages per reviewer per UTC day. Real users keep the normal MSG91 OTP flow; nothing about it changed.

## Isolation guarantees (all covered by tests)

| Guarantee | Enforced by |
|---|---|
| Missing `REVIEW_DB_NAME` → `POST /api/auth/review/login` answers **503 `REVIEW_UNAVAILABLE`**; never falls back to production | `shared/review.py`, `core.active_db()`; `test_review_login_is_denied_when_no_review_database_is_configured` |
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
4. **verifies each new key against the deployed backend**: `POST /auth/review/login` → `GET /auth/me` (role and `review_environment=true`) → `POST /auth/logout`; results appear as `verification` / `verified_all` in the JSON output, without secrets;
5. writes the keys, sign-in steps, store-form text and rotate/revoke commands **only** to the note file (owner-only permissions where the file system supports it). Nothing secret is printed.

Then: open the production app → *Store reviewer access* → sign in once yourself with the customer key from the note to see the gold **STORE-REVIEW ENVIRONMENT** banner; then paste the note's "TEXT FOR THE STORE REVIEW FORMS" plus the Reviewer ID/Access key pairs into App Store Connect (*App Review Information → Sign-in required*) and Play Console (*App content → App access → All or some functionality is restricted*). Give reviewers the **customer** account as the primary login and the **admin** account as the second login; telecaller/billing are optional.

Repeat runs: `-Status` (read-only), `-Seed` (add missing synthetic rows), `-ResetData` (wipe synthetic data, keep accounts), `-Rotate <reviewer_id> -Verify -NotePath <new file>` (new key; old key and sessions stop working immediately), `-Revoke <reviewer_id>`. `-Provision` on existing accounts issues nothing and writes no note (no stale key can leak).

Equivalent non-Windows command (from `backend/`, with `MONGO_URL`, `DB_NAME`, `REVIEW_DB_NAME` exported in the shell, not on the command line):
`python tools/provision_review_access.py --expected-review-db <REVIEW_DB_NAME> --provision --seed --status --environment production --api-base-url https://yash-tryon-test.emergent.host/api --verify --write-note ~/Private/yash-review-production.txt`

## What reviewers can do

- **Customer**: catalogue (12 sample products with generated images), live rates, rate list, enquiries/requests (create + history), rewards (120 sample points), AI assistant (bounded), profile, phone-change and account-deletion flows with **simulated** OTP (the code is never delivered; the flow shows the screens and a wrong code fails as in production).
- **Admin**: staff panel — customers (10 synthetic), enquiries (8), rates/slabs, products/batches, banners/schemes/brands, SMS diagnostics (simulated log), media usage, reviewed PDF import (jobs live in the review DB).
- **Telecaller**: assigned enquiries, claims, follow-ups on synthetic customers. **Billing executive**: customer search, query history, rates.

## Costs and limits in the review environment

AI: 40 messages/day/reviewer, 600 chars/message, genuine Claude Sonnet 4.5 via the existing `EMERGENT_LLM_KEY` (automated tests mock the provider). Media: 5 MiB/file, 256 MiB total inside the review database — no managed object-storage writes. SMS: none (simulated). Reset with `-ResetData` at any time.

## Evidence

- Backend: `backend/tests/shared/test_review_access_isolation.py` (8 tests) and `backend/tests/shared/test_review_provisioning_cli.py` (6 tests: real subprocess CLI provisioning/idempotency/status, fail-closed configuration, private note + rotate/revoke/reset, verify step, bounded AI in review scope, background-job scope) — all pass with the full shared suite (`test_reports/pytest/review_fonts_2026-09-12.xml`).
- Preview end-to-end: `test_reports/review_provisioning_preview_2026-09-12.json` (no secrets).
- Not yet done: production provisioning and a reviewer sign-in on a physical device against production (owner actions above).
