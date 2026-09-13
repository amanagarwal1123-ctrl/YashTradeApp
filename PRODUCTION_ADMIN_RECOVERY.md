# Production owner recovery and configuration — owner-operated runbook

## Status (12 September 2026)

- App production `https://yash-tryon-test.emergent.host/api` was last observed running `shared-v1-followup-2026-09-11`. An authenticated **GET only** (existing private enrollment credential) confirmed exactly one customer for **9999813334**: canonical ID **`bcdf18c9-dc87-4d46-b580-30cf519103df`**, role **customer**, account active, phone verified. No profile fields are reproduced here.
- Production reports `STAFF_SERVICE_KEY=false`. Both website domains report missing `CANONICAL_API_BASE_URL`, `ENROLLMENT_INTEGRATION_KEY`, `STAFF_SERVICE_KEY`. The website staff-login screenshot is that configuration failure; it happens before phone/OTP/role checks, so promoting the account alone cannot fix it.
- **Operator = the owner.** Emergent support confirmed: production settings are edited in **Manage Publishes → Secrets** (a new setting name must first exist in the preview `backend/.env`, with a non-working placeholder; preview edits never overwrite production values); changes take effect after **Redeploy** (never *Replace with a fresh database*); production database access is **Manage Publishes → Database**; support does not run our scripts. This runbook is therefore written for the owner's Windows PC. Nobody else needs to be nominated.
- **Nothing in production has been changed by this workspace**: no role, setting, SMS, session, account or identity merge. The preview database holds an older preview copy of the owner record (role customer); it is not production.
- Workspace build: `shared-v1-review-fonts-2026-09-12` (this code). Production keeps the old build until the owner redeploys after *Save to GitHub*.
- **PREVIEW SMS TEST — 12 September 2026, 14:17 UTC (owner-authorised, one SMS).** From the configured **preview** backend (`https://owner-setup-1.preview.emergentagent.com/api`), the normal `POST /auth/send-otp {phone:"9999813334", purpose:"login", channel:"mobile"}` was called once — no identity change, no validation bypass, no demo OTP. Reported **separately**: (1) **Dispatch**: HTTP 200, MSG91 accepted the message (`sms_log` id `91fda9b6-b641-4501-9455-2ceb1e69f4cd`, provider request id recorded, status `accepted`); (2) **Receipt**: MSG91's delivery report returned `Delivered` at 19:47:25 IST 6 s after sending — this is the provider's report, not a confirmation from the handset; (3) **OTP verification**: **NOT performed by the agent** (the code is never visible to it; the owner may enter it in the preview app within the 10-minute validity, at most one resend); (4) **Role routing**: **NOT verified** — the preview record for 9999813334 is `customer`, so a successful preview sign-in would route to the customer experience, not admin. **Preview success is not production verification**: production dispatch, receipt, verification and admin routing remain the owner's steps in §5 after §1 and §3.
- **Readiness is not login.** `flows.mobile.ready=true` (or any `configuration.*=true`) confirms configuration checks only — never SMS delivery, OTP verification or correct role routing; `sms_delivery_verified` and `account_role_verified` are always `false` in `/api/health`. A website value reported `false` means that setting is missing/invalid on the website, not that the canonical backend is unreachable. Actual login stays **unverified** until the §5 test is performed and recorded.

## Boundary

**Decision of 12 September 2026 (owner): 9999813334 is the DEFAULT ADMINISTRATOR on the app and the website.** The backend applies it itself at every start (`OWNER_ADMIN_PHONE=9999813334` in `backend/.env`, `backend/shared/owner_admin.py`): the single existing record for that phone is promoted to admin **on the same canonical record** (ID `bcdf18c9-dc87-4d46-b580-30cf519103df` in production, phone, verification, customer code, requests, rewards and history untouched; one audit event; open sessions revoked once), or — where no record exists — an active admin record is created so the first genuine OTP login already carries the role. Sign-in stays the normal MSG91 OTP flow (no fixed/universal OTP, no password); the website's staff exchange reads the same record, so one bootstrap serves both surfaces. The bootstrap never touches any other account, never merges identities (two records for the phone → reported, nothing changed), never reactivates an inactive or deleted identity, and the owner record cannot be demoted, disabled or deleted through the staff API (`409 OWNER_ADMIN_PROTECTED`). The manual operator repair of §3 therefore becomes an **alternative**, not a prerequisite. The website identity export is a separate, later task.

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

**Sequence (support-confirmed):** (a) the agent declares every needed name in the real preview `backend/.env` / `frontend/.env` (done — see table; secrets carry the non-working placeholder `SET_IN_PUBLISH_SECRETS`); (b) **first republish** registers the new names in *Manage Publishes → Secrets*; (c) the owner edits the values there using the existing-key editor (never create keys by hand, never paste values into chat); (d) **second republish** activates them. Keys that already exist in production keep the value stored in Secrets — a preview `.env` edit never updates them, so update existing production values in the editor too. In executable code a placeholder value is treated as **absent**: `REVIEW_DB_NAME=SET_IN_PUBLISH_SECRETS` never becomes a database (review flow `ready=false`, reviewer login 503, no such database is created — `backend/tests/shared/test_placeholder_configuration.py`), a placeholder `STAFF_SERVICE_KEY` is not a credential (503 `CONFIGURATION_REQUIRED`), and a placeholder `BUILD_COMMIT` is reported as `commit:"unrecorded"`, never as a verified deployment commit.

| Setting | Required | Production action |
|---|---|---|
| `MONGO_URL`, `DB_NAME` | yes | Platform-managed. Do not change. Note `DB_NAME`. |
| `JWT_SECRET` (≥ 32 chars) | yes | Keep the existing value. |
| `MSG91_AUTHKEY`, `MSG91_TEMPLATE_ID` | yes (OTP) | Keep existing. `MSG91_BASE_URL` optional. |
| `ENROLLMENT_INTEGRATION_KEY` (≥ 32) | yes (website enrollment/deletion) | Keep existing; the website's `ENROLLMENT_INTEGRATION_KEY` must hold the same value. |
| **`STAFF_SERVICE_KEY`** (≥ 32, **different** from the enrollment key) | yes for website staff login | **Declared** in preview `backend/.env` as `SET_IN_PUBLISH_SECRETS` (too short on purpose → staff flow fails closed). After the first republish, set ONE generated value in the app Secrets **and** the website's `STAFF_SERVICE_KEY`. Generate on your PC: `.\backend\.operator-venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(48))"` |
| **`REVIEW_DB_NAME`** | yes for store-review accounts | **Declared** in preview `backend/.env` as the placeholder `SET_IN_PUBLISH_SECRETS` (since the 12 Sep hotfix — the earlier preview value `jewellers_app_review` was inherited by the first production deployment, whose MongoDB user has no rights on that database, and crashed the backend at startup). Production: set a **different** name such as `<DB_NAME>_review` **and make sure the deployment's database user may readWrite it**. Must differ from `DB_NAME`; when absent or a placeholder, reviewer login answers 503 and never touches production data. When the name is set but not authorised/reachable, the app now **still starts**: `/api/health` shows `flows.review.ready=false`, `issues=["REVIEW_DB_UNAUTHORIZED"]` (or `REVIEW_DB_UNAVAILABLE`), `configuration.REVIEW_DB_USABLE=false`; reviewer sign-in answers 503; production flows are unaffected. |
| **`OWNER_ADMIN_PHONE`** | yes (default administrator) | **Declared** in preview `backend/.env` as `9999813334` (a real value, not a placeholder — the same number is the default admin in every environment). Carried into production by the republish; keep it. At each start the backend makes the single record with this phone admin (see *Boundary*); `/api/health` reports the result in `flows.owner_admin` (`state`: `created` / `promoted` / `already_admin`; `issues`: `OWNER_ADMIN_IDENTITY_CONFLICT` = two records carry the phone, `OWNER_ADMIN_ACCOUNT_INACTIVE` = the record is inactive/deleted, `OWNER_ADMIN_DELETED_IDENTITY` = tombstoned identity, `OWNER_ADMIN_PHONE` = missing/invalid, `OWNER_ADMIN_NOT_APPLIED` = database/configuration error) and `configuration.OWNER_ADMIN_PHONE`. |
| `CORS_ORIGINS` | yes | Keep existing (production host + both website origins). |
| `EMERGENT_LLM_KEY` | yes (AI assistant, managed object storage) | Keep existing. `INTEGRATION_PROXY_URL` is platform-managed. |
| **`BUILD_COMMIT`** | recommended | **Declared** as `SET_IN_PUBLISH_SECRETS` (reported as `unrecorded`). After *Save to GitHub*, set it to the final source commit SHA so `/api/health` reports it. |
| `MEDIA_WRITE_BUDGET_BYTES`, `MEDIA_WRITE_OBJECT_LIMIT`, `PDF_MAX_BYTES`, `PDF_MAX_PAGES`, `PDF_WORK_DIR` | optional | Defaults 2 000 000 000 / 10 000 / 64 MiB / 200 / system temp. |
| `OTP_DEMO_PHONES` | inert | Not read by this build (`DEMO_PHONES` is empty in code). Remove if present. |
| **Frontend `EXPO_PUBLIC_BACKEND_URL`** | yes (app release) | Deployment value must be `https://yash-tryon-test.emergent.host`. `frontend/app.config.js` additionally guarantees that a **release build** (`NODE_ENV=production`: Publish web export and iOS/Android store builds) never ships a `*.preview.emergentagent.com` origin — it resolves to `EXPO_PUBLIC_PRODUCTION_BACKEND_URL` (declared in `frontend/.env` = `https://yash-tryon-test.emergent.host`). Verified: `NODE_ENV=production expo config` → `extra.backendUrl=https://yash-tryon-test.emergent.host`; the Metro preview keeps the preview origin (`frontend/src/__tests__/appConfig.test.ts`). |

After Redeploy, from any browser: `GET https://yash-tryon-test.emergent.host/api/health/live` → 200; `GET .../api/health` → `build` = `shared-v1-review-fonts-2026-09-12`, `commit` = the SHA you set, `configuration.STAFF_SERVICE_KEY=true`, `configuration.OWNER_ADMIN_PHONE=true`, `configuration.REVIEW_DB_NAME=true`, `configuration.REVIEW_DB_USABLE=true`, `flows.mobile/staff/enrollment/deletion/owner_admin/review.ready=true` (`owner_admin.state` should read `promoted` on the first start after this build reaches production — the existing customer record became admin — and `already_admin` afterwards; `review.ready` is true only when the review database is both named **and** usable by the deployment's database user; `issues=["REVIEW_DB_UNAUTHORIZED"]` means grant rights on that database and redeploy — the app serves customers meanwhile). **These booleans prove configuration and the database role only** — not SMS delivery, OTP verification or website reachability; login is verified only by §5. The website needs `CANONICAL_API_BASE_URL=https://yash-tryon-test.emergent.host/api`, `ENROLLMENT_INTEGRATION_KEY` (same as app), `STAFF_SERVICE_KEY` (same as app, ≠ enrollment), and both public origins in `BFF_ALLOWED_ORIGINS`, declared by the website's agent in the website's own backend `.env` first and then valued in that project's Secrets — see `WEBSITE_AUTH_FIX_PROMPT.md`.

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

## 3. Owner role repair — now automatic; manual path kept as an alternative

**Automatic (default since 12 September 2026):** the first start of this build in production promotes the existing customer record of 9999813334 to admin on the same ID (see *Boundary*). No command, backup approval or dry-run is required for it; check `GET /api/health` → `flows.owner_admin.state=promoted` (then `already_admin`). If it reports `OWNER_ADMIN_IDENTITY_CONFLICT`, two production records carry the phone — nothing was changed; resolve the duplicate (Manage Publishes → Database) and redeploy. A backup before the redeploy (§2) is still good practice.

**Manual alternatives** (unchanged, for a database where the automatic step is refused or when you prefer an explicit audited operation): another genuine canonical admin signs in with real OTP and calls `POST /api/integrations/staff/9999813334/convert` with `{"role":"admin","confirm_user_id":"bcdf18c9-dc87-4d46-b580-30cf519103df","reason":"..."}`, or run the **operator-only** command from your PC (never an HTTP route, never at login). The wrapper fixes the target to phone `9999813334` / ID `bcdf18c9-dc87-4d46-b580-30cf519103df`, so no other account can be selected. Do this while nobody else is changing staff/identity data.

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

Follow `STORE_REVIEW_ACCESS.md` (`Provision-ReviewAccess.ps1`). Requires `REVIEW_DB_NAME` set in production Secrets (a database the deployment's user may readWrite) and redeployed first; production reviewer keys are written only to a private file on your PC and verified against the deployed backend by the script itself. Exit code **0** = every key proved; **1** = blocked before any change and before any request (including `-VerifyNote` against a backend other than the one pinned in the note); **2** = keys issued/kept but verification failed or incomplete → fix the cause and re-run the same `-VerifyNote <note> -ApiBaseUrl <pinned backend>` command (read-only, no connection string). Reviewer keys open the **synthetic review copy only** — they never grant, prove or replace admin status on the production database.

## 5. Real OTP test — authorised for 9999813334 only

**Keys do not grant admin status.** Neither `STAFF_SERVICE_KEY` nor the reviewer keys change any role: the admin role of 9999813334 (`bcdf18c9-dc87-4d46-b580-30cf519103df`, history preserved) comes from the automatic bootstrap of §3 (or its manual alternative). "Admin login restored" may be claimed only after an authenticated **app** session and an authenticated **website** session both return `/auth/me` with that ID and `role=admin`.

Run only after section 1 is complete (production redeployed on this build, `flows.owner_admin.ready=true`). One initial SMS per test, at most one resend after the normal 60-second cooldown, stop on any unexpected failure, no other recipients. (The single **preview** SMS on 12 September — see *Status* — was a transport test of the preview backend only and counts for nothing here.)

1. **App**: install the production build, open it, enter `9999813334`, tap Send OTP (one SMS). Enter the received code. Expected: sign-in succeeds and the app routes to the **admin** experience (staff panel available). Record: SMS received (time), verification success, `Profile → role = Admin`.
2. **Website** (`https://register.yashsilver.com` and `https://yash-register.emergent.host`): staff login with the same number (one more SMS each). Expected: `/auth/me` shows the SAME canonical ID with `role=admin`; the customer area is not offered.
3. Dispatch evidence without exposing the code: after signing in as admin, `GET https://yash-tryon-test.emergent.host/api/admin/sms/diagnostics` (bearer) and the panel **SMS** tab show the `sms_log` entry for `…3334` with provider status. Report dispatch, receipt, verification and routing **separately**; a delivered SMS does not prove the role, and the role check does not prove delivery.
4. If Send OTP returns 503 `CONFIGURATION_REQUIRED` → a setting in section 1 is missing; 404 `USER_NOT_FOUND` → wrong database/name; 429 → wait for the cooldown, one resend only.

## 6. No-SMS verification contract (available once the new build is live)

| Check | Expected result |
|---|---|
| `GET /api/health/live` | 200 if process alive; NOT auth readiness |
| `GET /api/health` or `/api/health/ready` | 200 only if all auth flows configured, the default owner administrator applied (`flows.owner_admin`) and DB reachable; otherwise 503 with `flows.*.issues` and boolean configuration names (`review` flow is optional and never blocks readiness) |
| `GET /api/integrations/staff/readiness` + server-only `X-Staff-Service-Key` | 200 and `credential_verified=true` for ready staff flow; missing/weak/shared server key 503, wrong supplied key 401 |
| `GET /api/integrations/enrollment/readiness` + server-only `X-Integration-Key` | 200 and `credential_verified=true` for ready enrollment flow; wrong supplied key 401 |
| `GET /api/fonts/ionicons.ttf` | 200, `content-type: font/ttf`, 389 724 bytes, `x-font-sha256` equal to `frontend/src/fonts/ionicons.manifest.json` |
| `POST /api/auth/review/login` with an unknown reviewer | 401 `REVIEW_CREDENTIALS_INVALID` when `REVIEW_DB_NAME` is set and usable; 503 `REVIEW_UNAVAILABLE` when it is not set, not authorised for the deployment's database user or unreachable |

All checks are `no-store`; no phone is submitted, no SMS sent, no account created. Liveness monitors should use `/health/live`.

## Safeguards preserved

Default owner administrator: one configured phone, same canonical record, idempotent, audit event, version-scoped session invalidation, refusal on duplicate/inactive/deleted identities, no other account touched, no fixed OTP, no password, protected from demotion/disabling/deletion (`OWNER_ADMIN_PROTECTED`). Manual repair (alternative): verified production target (database name must match), unique active identity, restorable backup reference, dry-run by default, reviewed report hash, controlled apply with maintenance confirmation, intent record before the single atomic update, audit receipt, idempotent replay. No second owner record, no identity merge.

## Verification state

Local: testing-agent iteration 21 passed 19/19 focused recovery/readiness tests and 29/29 shared regressions; this build adds review-access provisioning, font-fallback, D2/D3/D4, the review-storage hotfix and the default-owner-administrator suites (`backend/tests/shared/test_owner_admin_bootstrap.py`: creation, same-ID promotion with revoked old sessions, idempotent restarts, refusals, protection, admin sign-in on the mobile and portal channels — see `RELEASE_READINESS.md`). Both operator commands were exercised from a fresh minimal virtual environment built from `requirements-operator.txt`; the recovery dry-run against the preview database returned a complete report without writing. SMS/storage transports are intercepted in tests only, except the single owner-authorised **preview** SMS recorded under *Status* (dispatch + provider delivery report only). **Production promotion happens automatically on the first start of this build; production settings, the production OTP test and the admin-role confirmation on app and website remain owner actions and are not yet done; production login is unverified.**