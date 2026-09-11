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
The owner's role reconciliation has NOT been applied. No website export has been received.
Play review accounts have NOT been provisioned; an isolated review environment is required.