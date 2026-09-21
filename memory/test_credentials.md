# Controlled testing only

Follow-up: no real/reusable reviewer credentials created. Second-admin isolation tests use ephemeral fixture9999813335 only; its OTP is freshly generated/intercepted by pytest, never a reusable code. No production account or Play review access. Tests must use isolated_db and intercept transports. Intended owner<production owner number - NEVER used in tests> role/history remains unmodified in genuine data.

Legacy fixed-OTP and seeded logins are disabled. Do not send SMS to any real phone.
No reusable OTPs, credentials, tokens or integration secrets belong in this repository.
Automated tests must use a separate synthetic database and intercept SMS dispatch IN TESTS ONLY.
Authenticated UI test sessions may be provisioned privately outside the repository, then revoked.
Approved testing method: local Playwright routes browser /api requests into the existing isolated
ASGI fixture on the same async test loop. Its dynamic OTPs and sessions remain in memory only;
no loopback server or new production endpoint is necessary. All four synthetic fixture roles may
be used this way. This is test-transport isolation, not reusable Play Console access.
The owner explicitly authorised a scoped same-ID customer-to-admin correction on 12 September 2026.
Read-only production GET confirmed <production owner number - NEVER used in tests> is active/verified/customer, canonical ID
bcdf18c9-dc87-4d46-b580-30cf519103df. The correction has NOT been applied; local users DB is empty.
No real credentials/accounts were created or changed. Recovery tests must use isolated_db only,
starting the synthetic owner as CUSTOMER (existing seeded_users otherwise starts it as admin).
No reusable OTP exists. No website export has been received; full identity merge remains separate.
Play review accounts (state on 13 Sep 2026, build shared-v1-store-submission-2026-09-13): PREVIEW-ONLY reviewer accounts
(store-review-customer/admin/telecaller/billing) exist as bcrypt hashes in the `review__review_accounts` collection of the preview
database `jewellers_app` (REVIEW_ACCESS_ENABLED=true; there is NO separate review database and NO REVIEW_DB_NAME any more).
ALL FOUR ARE REVOKED (health flows.review.accounts_enabled=0); their former keys were only in private /tmp notes of disposable
containers and are gone. To test a reviewer flow, rotate one account from backend/ with MONGO_URL/DB_NAME exported:
`python tools/provision_review_access.py --expected-db jewellers_app --environment preview --rotate <reviewer_id> --write-note /tmp/yash-private/<new-file>.txt`
(the key lands ONLY in that file; never print/log/screenshot it), and revoke it again afterwards:
`python tools/provision_review_access.py --expected-db jewellers_app --revoke <reviewer_id>`.
These are not the store-submission credentials; production accounts are provisioned by the owner from the production app
(Panel > Store review, fresh owner OTP) or the CLI (STORE_REVIEW_ACCESS.md). Sign-in path in the app (since 14 Sep 2026): login screen -> "Help" link (/help, no session needed) -> "App review access" ->
"Open reviewer sign-in" (/review-access) -> Reviewer ID + Access key -> SIGN IN AS REVIEWER; the gold STORE-REVIEW ENVIRONMENT banner
confirms the isolated session. Endpoint: POST /api/auth/review/login {reviewer_id, access_key}.
Owner console (/review-keys, GET/POST /api/admin/review/*): owner administrator only; every write action sends a REAL OTP to
<production owner number - NEVER used in tests> -> automated tests must never trigger provision/rotate/revoke/reset there (read-only GET /status is safe).
Disposable production-scope fixtures (non-owner admin / customer) used for E2E on 13 Sep were synthetic records with minted
sessions in the preview DB and have been DELETED; recreate them ad hoc if needed (never dial their 91000099xx numbers).
Real users: normal MSG91 OTP only. No fixed OTP exists in code (DEMO_PHONES is empty).
Default owner administrator (12 Sep 2026): backend/.env OWNER_ADMIN_PHONE=<production owner number - NEVER used in tests> -> the record with that phone is admin in every environment (preview record bcdf18c9-dc87-4d46-b580-30cf519103df promoted customer->admin by the startup bootstrap; no fixed OTP, no password; real MSG91 OTP only - DO NOT send OTPs to this real number in automated tests). Tests use isolated synthetic databases with OWNER_ADMIN_PHONE set via monkeypatch and intercepted SMS.
14 Sep 2026: store-review-customer was rotated for testing-agent iterations 28/29 and REVOKED again afterwards; the private note was shredded. All four reviewer accounts are REVOKED (accounts_enabled=0). Reviewer sign-in path is Login -> Help -> App review access -> Open reviewer sign-in.
15 Sep 2026 (fork): store-review-admin and store-review-customer were rotated for testing-agent iteration 30 and REVOKED again; notes shredded. A disposable production-scope synthetic admin (e2e-admin-fixture-2026-09-15, phone 9100009911) with a minted session was used for read-only ledger checks and DELETED afterwards (0 users with registration_source=e2e_fixture remain). All four reviewer accounts REVOKED (accounts_enabled=0).
15 Sep 2026 (media budget fix, iteration 33): store-review-admin and store-review-customer were rotated for the run and REVOKED again (accounts_enabled=0); notes shredded. Review-scope test batches/imports/products created that day were removed. All four reviewer accounts REVOKED.

20 Sep 2026 (independent-review closeout fork) — PRODUCTION ACCOUNT PROTECTION RULE (owner instruction):
- The production owner administrator's phone number MUST NOT appear in testing instructions, test fixtures or this file. Nobody logs into it,
  requests its OTP or modifies it. pytest fixtures use the SYNTHETIC owner 9000000000 (conftest SYNTHETIC_OWNER_PHONE, OWNER_ADMIN_PHONE set by
  monkeypatch in isolated_db); the former second-admin fixture number is now 9000000010. tools/reconcile_identities.py reads OWNER_ADMIN_PHONE from the
  environment (no literal).
- Isolated E2E environment = the store-review scope (review__* collections). Reviewer accounts are now SIX: store-review-customer, store-review-admin,
  store-review-telecaller, store-review-telecaller-2 (second telecaller, user review-telecaller-0002), store-review-billing, store-review-upload
  (Upload Executive, user review-upload-0001). Sign-in: Login -> Help -> App review access -> Open reviewer sign-in, or POST /api/auth/review/login.
- For the 20 Sep E2E run all six were provisioned/rotated on the preview backend; keys are ONLY in /tmp/yash-private/e2e-review-keys.json
  ({reviewer_id: access_key}) of this container (never print/log/screenshot). They are REVOKED after the run (health flows.review.accounts_enabled=0).
- Synthetic review-scope fixture request review-request-stale-0001 (yesterday's claim by telecaller-1) exists for the 03:00 release check.
- Never: send real SMS (send-otp / delete-account / phone-change with a production-scope session), broadcast notifications with a production-scope
  session, delete real users, reset production queues, or touch the owner console write actions.
