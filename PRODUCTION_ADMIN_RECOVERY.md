# Production owner recovery and configuration — owner-operated runbook

## Status (12 September 2026)

- App production `https://yash-tryon-test.emergent.host/api` was last observed running `shared-v1-followup-2026-09-11`. An authenticated **GET only** (existing private enrollment credential) confirmed exactly one customer for **9999813334**: canonical ID **`bcdf18c9-dc87-4d46-b580-30cf519103df`**, role **customer**, account active, phone verified. No profile fields are reproduced here.
- Production reports `STAFF_SERVICE_KEY=false`. Both website domains report missing `CANONICAL_API_BASE_URL`, `ENROLLMENT_INTEGRATION_KEY`, `STAFF_SERVICE_KEY`. The website staff-login screenshot is that configuration failure; it happens before phone/OTP/role checks, so promoting the account alone cannot fix it.
- **Operator = the owner.** Emergent support confirmed: production settings are edited in **Manage Publishes → Secrets** (a new setting name must first exist in the preview `backend/.env`, with a non-working placeholder; preview edits never overwrite production values); changes take effect after **Redeploy** (never *Replace with a fresh database*); production database access is **Manage Publishes → Database**; support does not run our scripts. This runbook is therefore written for the owner's Windows PC. Nobody else needs to be nominated.
- **Nothing in production has been changed by this workspace**: no role, setting, SMS, session, account or identity merge. The preview database holds an older preview copy of the owner record (role customer); it is not production.
- Workspace build: `shared-v1-review-fonts-2026-09-12` (this code). Production keeps the old build until the owner redeploys after *Save to GitHub*.

## Boundary

The owner authorises making **existing account 9999813334 admin**, keeping its canonical ID, phone, verification, customer code, requests, rewards and history. No replacement account, no startup admin seed, no fixed/universal OTP, no bulk identity merge. The website identity export is a separate, later task and does **not** block this repair.

## 0. One-time setup on the owner's Windows PC

1. Install **Python 3.11 or newer** from python.org (tick *Add python.exe to PATH*).
2. Get the repository at the implementation commit: after *Save to GitHub*, download the ZIP (or `git clone`) and unzip it, e.g. `C:\Yash\app`.
3. Open **PowerShell** in that folder and run:
   ```powershell
   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
   .\backend\tools\windows\Setup-Operator.ps1
   ```
   This creates `backend\.operator-venv` with the pinned minimal packages from `backend/tools/requirements-operator.txt` (motor, pymongo, bcrypt, PyJWT, python-dotenv, pillow, httpx, fastapi/pydantic). Nothing starts the API server. Re-running is safe.
4. Have ready, but **never type on a command line**: the production MongoDB connection string (**Manage Publishes → Database**). Every script below asks for it with a hidden prompt, hands it to Python as a process-only environment variable and removes it afterwards, so it stays out of PowerShell history, logs and files. Do not paste it into `.env`, notes or chat.
5. Note the exact production `DB_NAME` value from **Manage Publishes → Secrets**. Scripts refuse to run when the database name you pass does not match the one they connect to.
6. If the Database page shows an IP allowlist, add your PC's current public IP for the session and remove it afterwards.

## 1. Production settings — exact names used by this code

Edit values in **Manage Publishes → Secrets**, then **Redeploy**. Preview placeholders for the two NEW names already exist in `backend/.env` so the names appear in the Secrets screen.

| Setting | Required | Production action |
|---|---|---|
| `MONGO_URL`, `DB_NAME` | yes | Platform-managed. Do not change. Note `DB_NAME`. |
| `JWT_SECRET` (≥ 32 chars) | yes | Keep the existing value. |
| `MSG91_AUTHKEY`, `MSG91_TEMPLATE_ID` | yes (OTP) | Keep existing. `MSG91_BASE_URL` optional. |
| `ENROLLMENT_INTEGRATION_KEY` (≥ 32) | yes (website enrollment/deletion) | Keep existing; the website's `ENROLLMENT_INTEGRATION_KEY` must hold the same value. |
| **`STAFF_SERVICE_KEY`** (≥ 32, **different** from the enrollment key) | yes for website staff login | **NEW name.** Preview `.env` holds `SET_IN_PUBLISH_SECRETS` (too short on purpose → staff flow fails closed). Generate ONE value and set it in the app Secrets **and** the website's `STAFF_SERVICE_KEY`. Generate on your PC: `.\backend\.operator-venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(48))"` |
| **`REVIEW_DB_NAME`** | yes for store-review accounts | **NEW name.** Preview `.env` uses `jewellers_app_review` (preview database). Production: choose a distinct name such as `<DB_NAME>_review`. Must differ from `DB_NAME`; when absent, reviewer login answers 503 and never touches production data. |
| `CORS_ORIGINS` | yes | Keep existing (production host + both website origins). |
| `EMERGENT_LLM_KEY` | yes (AI assistant, managed object storage) | Keep existing. `INTEGRATION_PROXY_URL` is platform-managed. |
| `BUILD_COMMIT` | recommended | Set to the deployed commit SHA so `/api/health` reports it. |
| `MEDIA_WRITE_BUDGET_BYTES`, `MEDIA_WRITE_OBJECT_LIMIT`, `PDF_MAX_BYTES`, `PDF_MAX_PAGES`, `PDF_WORK_DIR` | optional | Defaults 2 000 000 000 / 10 000 / 64 MiB / 200 / system temp. |
| `OTP_DEMO_PHONES` | inert | Not read by this build (`DEMO_PHONES` is empty in code). Remove if present. |

After Redeploy, from any browser: `GET https://yash-tryon-test.emergent.host/api/health/live` → 200; `GET .../api/health` → `build` = `shared-v1-review-fonts-2026-09-12`, `configuration.STAFF_SERVICE_KEY=true`, `configuration.REVIEW_DB_NAME=true`, `flows.mobile/staff/enrollment/deletion/review.ready=true`. The website needs `CANONICAL_API_BASE_URL=https://yash-tryon-test.emergent.host/api`, `ENROLLMENT_INTEGRATION_KEY` (same as app), `STAFF_SERVICE_KEY` (same as app, ≠ enrollment), and both public origins in `BFF_ALLOWED_ORIGINS` — see `WEBSITE_AUTH_FIX_PROMPT.md`.

## 2. Restorable backup (before any write)

1. **Manage Publishes → Database**: if the page offers a backup/snapshot/export, create one now and record its name/time — that is your `-BackupRef`.
2. If it does not, take one from your PC with MongoDB Database Tools (`mongodump`/`mongorestore`, free download from mongodb.com). To keep the connection string out of history, write it into a private config file and delete the file afterwards:
   ```powershell
   New-Item -ItemType Directory -Force "$env:USERPROFILE\Private" | Out-Null
   notepad "$env:USERPROFILE\Private\mongodump.yaml"     # single line:   uri: <paste connection string>
   mongodump --config "$env:USERPROFILE\Private\mongodump.yaml" --db <DB_NAME> --out "$env:USERPROFILE\Private\yash-backup-<date>"
   mongorestore --config "$env:USERPROFILE\Private\mongodump.yaml" --nsInclude "<DB_NAME>.*" --dir "$env:USERPROFILE\Private\yash-backup-<date>" --dryRun
   Remove-Item "$env:USERPROFILE\Private\mongodump.yaml"
   ```
   The dry-run restore proves the archive is readable; `yash-backup-<date>` is your `-BackupRef`. Keep it private.

## 3. Owner role repair — dry-run, apply, confirm

Preferred when another genuine canonical admin exists: that admin signs in with real OTP and calls `POST /api/integrations/staff/9999813334/convert` with `{"role":"admin","confirm_user_id":"bcdf18c9-dc87-4d46-b580-30cf519103df","reason":"..."}`.

Otherwise run the **operator-only** command from your PC (it is never an HTTP route and never runs at startup or login). The wrapper fixes the target to phone `9999813334` / ID `bcdf18c9-dc87-4d46-b580-30cf519103df`, so no other account can be selected. Do this while nobody else is changing staff/identity data.

```powershell
cd C:\Yash\app
# 1) DRY RUN — no writes. Paste the connection string at the hidden prompt.
.\backend\tools\windows\Recover-OwnerAdmin.ps1 -DbName <DB_NAME> -OperationId owner-admin-recovery-20260912 -Operator "<your name>"
```
Read the JSON: `dry_run=true`, `changed=false`, `database=<DB_NAME>`, `user_id=bcdf18c9-…`, `phone_suffix=3334`, `from_role=customer`, `to_role=admin`, `account_status=active`, and copy `report_sha256`. An empty database, duplicate phone, mismatched ID, inactive or deleted account **blocks** with a code instead of creating or activating anyone.

```powershell
# 2) APPLY — identical operation ID + the reviewed hash + your backup reference.
.\backend\tools\windows\Recover-OwnerAdmin.ps1 -DbName <DB_NAME> -OperationId owner-admin-recovery-20260912 -Operator "<your name>" `
    -Apply -ApprovedReportSha256 <report_sha256 from step 1> -BackupRef "yash-backup-<date>" -MaintenanceConfirmed
```
The command records intent in `admin_recovery_operations` **before** one atomic update of that single user document: `role=admin`, `session_version+1`, timestamp, one audit event. ID, phone, verification, profile, customer code, requests, rewards and history are untouched. Old access **and** refresh tokens fail immediately; only session families from the pre-repair version are revoked, so a fresh login is unaffected. If the run is interrupted after the update, rerun the identical command to finish bookkeeping; a completed replay changes nothing. Changing any parameter invalidates the approval; a later demotion is never re-promoted by replay.

```powershell
# 3) CONFIRM — dry run again; expect already_admin=true for the same ID.
.\backend\tools\windows\Recover-OwnerAdmin.ps1 -DbName <DB_NAME> -OperationId owner-admin-recovery-20260912 -Operator "<your name>"
```
Keep the two JSON outputs privately as the audit receipt. Fresh genuine OTP login is still required (section 5).

## 4. Store-review accounts

Follow `STORE_REVIEW_ACCESS.md` (`Provision-ReviewAccess.ps1`). Requires `REVIEW_DB_NAME` set in production Secrets and redeployed first; production reviewer keys are written only to a private file on your PC and verified against the deployed backend by the script itself.

## 5. Real OTP test — authorised for 9999813334 only

Run only after sections 1 and 3 are complete (production redeployed, role repaired). One initial SMS per test, at most one resend after the normal 60-second cooldown, stop on any unexpected failure, no other recipients.

1. **App**: install the production build, open it, enter `9999813334`, tap Send OTP (one SMS). Enter the received code. Expected: sign-in succeeds and the app routes to the **admin** experience (staff panel available). Record: SMS received (time), verification success, `Profile → role = Admin`.
2. **Website** (`https://register.yashsilver.com` and `https://yash-register.emergent.host`): staff login with the same number (one more SMS each). Expected: `/auth/me` shows the SAME canonical ID with `role=admin`; the customer area is not offered.
3. Dispatch evidence without exposing the code: after signing in as admin, `GET https://yash-tryon-test.emergent.host/api/admin/sms/diagnostics` (bearer) and the panel **SMS** tab show the `sms_log` entry for `…3334` with provider status. Report dispatch, receipt, verification and routing **separately**; a delivered SMS does not prove the role, and the role check does not prove delivery.
4. If Send OTP returns 503 `CONFIGURATION_REQUIRED` → a setting in section 1 is missing; 404 `USER_NOT_FOUND` → wrong database/name; 429 → wait for the cooldown, one resend only.

## 6. No-SMS verification contract (available once the new build is live)

| Check | Expected result |
|---|---|
| `GET /api/health/live` | 200 if process alive; NOT auth readiness |
| `GET /api/health` or `/api/health/ready` | 200 only if all auth flows configured and DB reachable; otherwise 503 with `flows.*.issues` and boolean configuration names (`review` flow is optional and never blocks readiness) |
| `GET /api/integrations/staff/readiness` + server-only `X-Staff-Service-Key` | 200 and `credential_verified=true` for ready staff flow; missing/weak/shared server key 503, wrong supplied key 401 |
| `GET /api/integrations/enrollment/readiness` + server-only `X-Integration-Key` | 200 and `credential_verified=true` for ready enrollment flow; wrong supplied key 401 |
| `GET /api/fonts/ionicons.ttf` | 200, `content-type: font/ttf`, 389 724 bytes, `x-font-sha256` equal to `frontend/src/fonts/ionicons.manifest.json` |
| `POST /api/auth/review/login` with an unknown reviewer | 401 `REVIEW_CREDENTIALS_INVALID` when `REVIEW_DB_NAME` is set; 503 `REVIEW_UNAVAILABLE` when it is not |

All checks are `no-store`; no phone is submitted, no SMS sent, no account created. Liveness monitors should use `/health/live`.

## Safeguards preserved

Verified production target (database name must match), unique active identity, restorable backup reference, dry-run by default, reviewed report hash, controlled apply with maintenance confirmation, intent record before the single atomic update, version-scoped session invalidation, audit receipt, idempotent replay. No fixed OTP, no seeded admin, no second owner record, no identity merge.

## Verification state

Local: testing-agent iteration 21 passed 19/19 focused recovery/readiness tests and 29/29 shared regressions; this build adds review-access provisioning, font-fallback and D2/D3/D4 suites (see `RELEASE_READINESS.md`). Both operator commands were exercised from a fresh minimal virtual environment built from `requirements-operator.txt`; the recovery dry-run against the preview database returned a complete report without writing. SMS/storage transports are intercepted in tests only. **Production role promotion, production settings and the real OTP test remain owner actions and are not yet done.**