# Test Credentials — Yash Trade

Real SMS OTP is live via **Twilio Verify** (4-digit codes). The phones below are on the
demo allowlist (`OTP_DEMO_PHONES` in backend/.env) and always accept OTP `1234` —
no SMS is sent for them. Any other number receives a real SMS.
`OTP_DEMO_MODE=false` (set to `true` to mock ALL numbers).

| Role | Where to log in | Phone | OTP |
|------|-----------------|-------|-----|
| Customer | App root `/` (mobile app) | 8888888888 | 1234 |
| Admin | `/panel` (web panel) | 9999999999 | 1234 |
| Executive | `/panel` | 7777777777 | 1234 |
| Billing Executive | `/panel` | 6666666666 | 1234 |

⚠️ Do NOT test login with arbitrary real phone numbers — it sends real paid SMS via Twilio.

Preview URL: https://yash-tryon-test.preview.emergentagent.com
Backend API base: https://yash-tryon-test.preview.emergentagent.com/api
