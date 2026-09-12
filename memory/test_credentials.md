# Controlled testing only

Follow-up: no real/reusable reviewer credentials created. Second-admin isolation tests use ephemeral fixture9999813335 only; its OTP is freshly generated/intercepted by pytest, never a reusable code. No production account or Play review access. Tests must use isolated_db and intercept transports. Intended owner9999813334 role/history remains unmodified in genuine data.

Legacy fixed-OTP and seeded logins are disabled. Do not send SMS to any real phone.
No reusable OTPs, credentials, tokens or integration secrets belong in this repository.
Automated tests must use a separate synthetic database and intercept SMS dispatch IN TESTS ONLY.
Authenticated UI test sessions may be provisioned privately outside the repository, then revoked.
Approved testing method: local Playwright routes browser /api requests into the existing isolated
ASGI fixture on the same async test loop. Its dynamic OTPs and sessions remain in memory only;
no loopback server or new production endpoint is necessary. All four synthetic fixture roles may
be used this way. This is test-transport isolation, not reusable Play Console access.
The owner explicitly authorised a scoped same-ID customer-to-admin correction on 12 September 2026.
Read-only production GET confirmed 9999813334 is active/verified/customer, canonical ID
bcdf18c9-dc87-4d46-b580-30cf519103df. The correction has NOT been applied; local users DB is empty.
No real credentials/accounts were created or changed. Recovery tests must use isolated_db only,
starting the synthetic owner as CUSTOMER (existing seeded_users otherwise starts it as admin).
No reusable OTP exists. No website export has been received; full identity merge remains separate.
Play review accounts: PREVIEW-ONLY reviewer accounts (store-review-customer/admin/telecaller/billing)
existed in the preview review database `jewellers_app_review` while backend/.env named it; since the 12 Sep hotfix backend/.env carries the placeholder REVIEW_DB_NAME=SET_IN_PUBLISH_SECRETS, so preview reviewer login answers 503 REVIEW_UNAVAILABLE by design (health flows.review.issues=[REVIEW_DB_NAME]).
Their access keys are NOT in this repository or chat; they live only in the disposable preview
container at /tmp/yash-private/preview-<reviewer_id>.txt (one note per account, rotated 12 Sep 2026 release pass; rotate with
`python tools/provision_review_access.py --expected-review-db jewellers_app_review --rotate <id>`).
They are not the store-submission credentials; production accounts are provisioned by the owner
(STORE_REVIEW_ACCESS.md). Sign-in path in the app: login screen -> "Store reviewer access" link
(/review-access) -> Reviewer ID + Access key -> SIGN IN; the gold STORE-REVIEW ENVIRONMENT banner
confirms the isolated session. Endpoint: POST /api/auth/review/login {reviewer_id, access_key}.
Real users: normal MSG91 OTP only. No fixed OTP exists in code (DEMO_PHONES is empty).