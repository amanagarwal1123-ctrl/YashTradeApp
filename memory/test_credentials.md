# Test Credentials — Yash Trade

Real SMS OTP is live via **MSG91 OTP API** (4-digit codes, account default OTP template). The phones below are on the
demo allowlist (`OTP_DEMO_PHONES` in backend/.env) and always accept OTP `1234` —
no SMS is sent for them. Any other valid Indian mobile (starts 6-9) receives a real SMS.
`OTP_DEMO_MODE=false` (set to `true` to mock ALL numbers).

| Role | Where to log in | Phone | OTP |
|------|-----------------|-------|-----|
| Customer | App root `/` (mobile app) | 8888888888 | 1234 |
| Customer (website-registered, has shop/location) | `/` | 8888800001 | 1234 |
| Customer (INACTIVE — must be blocked) | `/` | 8888800002 | 1234 |
| Telecaller (role `executive` → /telecaller) | `/` (same login) | 7777777777 | 1234 |
| Admin (→ /panel) | `/` or `/panel` | 9999999999 | 1234 |
| Billing Executive (→ /panel) | `/` or `/panel` | 6666666666 | 1234 |

Unified login: everyone uses the same phone+OTP screen; the backend role decides the flow.
Unknown numbers (e.g. 9876501234) get 404 "Registration required" and NO account is created.

⚠️ Do NOT test login with arbitrary real phone numbers — it sends real paid SMS via MSG91.
Safe negative-test numbers: 1111111111 (fails local validation, no SMS).

Preview URL: https://yash-tryon-test.preview.emergentagent.com
Backend API base: https://yash-tryon-test.preview.emergentagent.com/api
