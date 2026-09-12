# Production owner recovery — scoped repair, not an identity merge

## Confirmed 12 September 2026 (read-only)

- App production: `https://yash-tryon-test.emergent.host/api` runs `shared-v1-followup-2026-09-11`.
- An authenticated **GET only**, using the existing private enrollment credential, confirmed exactly one customer returned for **9999813334**: canonical ID **`bcdf18c9-dc87-4d46-b580-30cf519103df`**, role **customer**, account active, phone verified. No profile fields are included in this report.
- Production app reports `STAFF_SERVICE_KEY=false`. Both website domains report missing `CANONICAL_API_BASE_URL`, `ENROLLMENT_INTEGRATION_KEY`, `STAFF_SERVICE_KEY`.
- The screenshot is the WEBSITE staff-login configuration failure. It occurs before phone/OTP/role checks. Promoting the user alone cannot resolve it.
- This workspace has an empty LOCAL application database. **Production role/settings have NOT been changed.** No production SMS, session issuance, account creation or identity merge occurred.
- Cached web crawls returned an older v7 health result; the facts above use fresh direct HTTPS responses instead.

## Authorization and boundary

The owner explicitly requests making **existing account 9999813334 admin**. This narrowly scoped, same-ID role correction does **not** need the unrelated full website identity export. It still requires an authorised operator with live database/settings access, verification of the exact target below and a restorable backup. Other users, identity links, customer records, orders, rewards and history must not be merged or rewritten.

No production settings writer or production Mongo connection is available in this chat. An enrollment key may read a customer but cannot change staff roles. Do not reuse that key as staff authority or mint a token with the JWT secret. Do not seed a substitute admin or restore demo OTPs.

## A. Privately configure the existing services

An operator with access to BOTH projects must generate ONE strong random staff credential (at least 32 characters, preferably 48 random bytes encoded), keep it private, and set that same value as server-only `STAFF_SERVICE_KEY` in both app and website. It must differ from `ENROLLMENT_INTEGRATION_KEY`. Never place keys in source code, chat, screenshots, frontend variables or command history.

Website server:
- `CANONICAL_API_BASE_URL=https://yash-tryon-test.emergent.host/api`
- `ENROLLMENT_INTEGRATION_KEY`: privately copy the matching existing app enrollment credential. The website's existing `LIVE_INTEGRATION_KEY` can be migrated ONLY after a private credential-match check. Do not silently introduce an auth fallback.
- `STAFF_SERVICE_KEY`: the separate matching value above.
- `BFF_ALLOWED_ORIGINS`: explicitly include `https://register.yashsilver.com` AND `https://yash-register.emergent.host`, using that website's supported format. Retain only verified ingress aliases; no wildcard, Host reflection or disabling CSRF.

App server retains its real `JWT_SECRET`, `MSG91_AUTHKEY`, `MSG91_TEMPLATE_ID`, `MONGO_URL`, `DB_NAME` and enrollment credential. Do not copy JWT/SMS/database secrets to the website. Restart services after private configuration changes. App-side CORS cannot repair the website's own BFF origin validator.

## B. Apply only the authorised role change

Preferred when another genuine canonical admin is available: real OTP login, then existing admin-authorised `POST /api/integrations/staff/9999813334/convert`:

```json
{"role":"admin","confirm_user_id":"bcdf18c9-dc87-4d46-b580-30cf519103df","reason":"Owner explicitly authorised correction of the existing app customer to admin"}
```

If no usable admin exists, use the new **operator-only command**. It requires normal private database administration access, NOT a public recovery endpoint. It never runs at application startup or login.

1. Make this tested code available in the authorised app maintenance environment. Confirm its `MONGO_URL` points to the LIVE canonical database and verify the actual live `DB_NAME` (do not assume the local database name is production).
2. Pause authentication/identity writes and take/verify a restorable backup. Retain backup receipts privately.
3. From `backend/`, run a **dry-run** with the exact account and a fresh operation ID. Substitute actual operator/database values:

```bash
python tools/recover_owner_admin.py \
  --phone 9999813334 \
  --user-id bcdf18c9-dc87-4d46-b580-30cf519103df \
  --expected-db '<VERIFIED_PRODUCTION_DB_NAME>' \
  --operation-id owner-admin-recovery-20260912 \
  --operator '<AUTHORISED_OPERATOR_ID>' \
  --reason 'Owner authorised same-ID customer-to-admin correction for 9999813334'
```

4. Review returned database, canonical ID, phone suffix, current role/status and `report_sha256`. Dry-run performs **no writes**. An empty local database/duplicate/mismatched/inactive/deleted identity blocks rather than creating or activating anyone.
5. Repeat the **identical command** with these additional flags, using the reviewed hash and private backup receipt identifier:

```bash
  --apply \
  --approved-report-sha256 '<REVIEWED_REPORT_SHA256>' \
  --backup-ref '<VERIFIED_RESTORABLE_BACKUP_REFERENCE>' \
  --maintenance-confirmed
```

The command records intent in `admin_recovery_operations` BEFORE updating. One atomic user-document update sets `role=admin`, increments `session_version`, records a timestamp and appends one audit event. ID, phone, verification, profile, customer code, history, rewards and other records remain untouched. Old access AND refresh tokens immediately fail version checks. Version-scoped session-family revocation and the operation completion receipt follow; even an interrupted operation's replay never touches new-version sessions. Older families without remaining refresh records are still invalidated by the user version check. No transactions/replica-set conversion is required.

If interrupted after the user update, rerun the identical approved operation to finish bookkeeping. A completed replay performs no further changes and will not revoke new sessions. Changed identity snapshot/operation metadata requires review; never change parameters to force a stale approval. A previously applied operation cannot re-promote a later demotion.

6. Repeat dry-run: expect `already_admin=true`, same ID, active account. Record the private completion receipt and resume writes. Fresh genuine OTP login is still mandatory.

## C. No-SMS verification contract added by this fix

These endpoints require the new app build `shared-v1-owner-recovery-2026-09-12`; old production does not have them until the code is activated there.

| Check | Expected result |
|---|---|
| `GET /api/health/live` | 200 if process alive; NOT auth readiness |
| `GET /api/health` or `/api/health/ready` | 200 only if all auth flows configured and DB reachable; otherwise 503 with `flows.*.issues` and boolean configuration names |
| `GET /api/integrations/staff/readiness` + server-only `X-Staff-Service-Key` | 200 and `credential_verified=true` for ready staff flow; missing/weak/shared server key 503, wrong supplied key 401 |
| `GET /api/integrations/enrollment/readiness` + server-only `X-Integration-Key` | 200 and `credential_verified=true` for ready enrollment flow; wrong supplied key 401 |

All checks are `no-store`. No phone is submitted, no SMS sent and no OTP/session/account record is created. Public health does not prove credential matching; protected checks do. None proves delivery or user role. Missing staff settings need not disable the separately healthy mobile flow. Liveness monitors should use `/health/live`, not the stricter `/health` readiness response.

Verify BOTH website domains' origin checks and staff/enrollment/deletion readiness. Only then ask the owner to perform one real OTP login; confirm canonical `/auth/me` returns the SAME ID with `role=admin` in app and BFF. Do not label production restored based only on local tests or boolean key presence.

## Verification state

Testing agent iteration21 passed **19/19 focused recovery/readiness tests** and **29/29 shared regression tests** (the additional 12/12 auth/people run overlaps the latter). Verified customer-to-admin same-ID OTP login, old-session invalidation, interrupted/completed replay safety, negative guards, CLI, readiness/OpenAPI and mobile preview. Embedded development preview origin accepted; unrelated origin rejected; production native-origin configuration untouched. SMS/storage transports were MOCKED only in isolated tests. No live SMS/writes.

The separate production probe still finds `/api/health/live=404` on the older running build: an unresolved production activation gate, not a passing live test. **Production role promotion and private configuration remain unapplied.** See `WEBSITE_AUTH_FIX_PROMPT.md` for the companion website task. Test report: `test_reports/iteration_21.json`.