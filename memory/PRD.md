# Yash Trade - Jewellery Business App

## Original Problem Statement
Build a production-grade, private mobile app for "Yash Trade" / "Yash Ornaments" - a wholesale jewellery business serving ~40,000 wholesale/retail jewelers.

## Architecture
- **Customer App**: Expo (React Native) mobile app
- **Admin Panel**: React web panel at `/panel` route
- **Backend**: FastAPI + MongoDB
- **Storage**: Emergent Object Storage
- **AI**: Claude Sonnet 4.5 via Emergent LLM Key

## User Roles & Access Links

| Role | URL | Phone | OTP |
|------|-----|-------|-----|
| **Customer** | `{PREVIEW_URL}/` | `8888888888` | `1234` |
| **Admin** | `{PREVIEW_URL}/panel` | `9999999999` | `1234` |
| **Executive** | `{PREVIEW_URL}/panel` | `7777777777` | `1234` |
| **Billing Executive** | `{PREVIEW_URL}/panel` | `6666666666` | `1234` |

> **IMPORTANT FOR ALL AGENTS:** Always include these access links and credentials in every handoff summary and finish summary.

## Implemented Features

### Core Features
- JWT auth with OTP store (expiry, retry limits, rate limiting). OTP_DEMO_MODE=true for dev
- Product catalog with feed, search, filters
- Cart, Requests, Rewards, AI assistant, Silver Calculator, Stories, Knowledge base

### Unified Login, Website Parity & Telecaller CRM (June 2026)
- **Registered numbers only**: send-otp no longer auto-creates users; unknown numbers → 404 + "Registration Required" UI with enroll button (EXPO_PUBLIC_ENROLLMENT_URL, placeholder https://enroll.yashornaments.com); inactive accounts blocked at send/verify/get_current_user (403)
- **Unified role-based login**: one phone+OTP screen for all; after verify the backend role routes: customer→tabs, executive→/telecaller, admin/billing_executive→/panel; guards in (tabs)/_layout, telecaller.tsx, panel (auto-login from app session via AuthContext, customers redirected out); session restore lands directly in the right flow; panel logout = app logout → /login
- **Website-parity user schema**: shop_name, location, phone_verified, onboarding_status, has_logged_in, account_status (mirrored with legacy status), registration_source, registered_at, first_login_at, last_login_at; one-time backfill migration in seed; /auth/me returns all; profile card shows Name/Phone/Shop/Location
- **Profile editing**: /edit-profile screen (name, shop_name, location→city synced) via PUT /auth/profile (whitelisted); protected phone-change flow: POST /auth/phone-change/request (duplicate check 409, OTP to NEW number) + /verify (OTP recheck, dup recheck) with in-memory pending store
- **Login tracking**: has_logged_in/first_login_at/last_login_at set only on successful verify; panel customers tab shows ACTIVE/INACTIVE + NEVER LOGGED IN/LAST LOGIN badges, registration_source, telecaller assignment
- **Telecaller CRM**: mobile dashboard /telecaller — summary cards (assigned/follow-ups due/actions today/status counts), search+status filters, customer cards with Call/WhatsApp (auto-logged), detail modal (status grid: new/contacted/interested/follow_up_required/converted/not_interested/unable_to_reach, follow-up date+time, notes, activity history). APIs: GET /telecaller/customers (assigned-only for execs; admin sees all), POST /telecaller/customers/{id}/action (records telecaller_id, customer_id, action, notes, prev/new status, timestamp in telecaller_activity), GET .../activity, GET /telecaller/summary. Admin assigns telecallers in panel customers tab (PATCH /customers/{id} assigned_salesperson)
- **Security**: SecureStore token storage on devices (AsyncStorage on web, with migration); demo OTP only for OTP_DEMO_PHONES allowlist; api.ts errors carry HTTP status
- **Demo data (dev)**: website customer 8888800001 (Suresh Verma/Verma Jewellers/Ludhiana), inactive 8888800002; DEMO_LOGIN_CREDENTIALS.txt at /app

### Website ↔ App integration + In-app Account Deletion — build `2026.09.09-integration-v6` (Sept 2026)
- **Why:** website sync used to piggyback on customer OTP login (demo OTP 1234) → impossible once demo mode is off; `shop_name`/`registration_source`/`onboarding_status` were dropped; no in-app deletion (Play policy). Implements the website's `docs/YASH_TRADE_APP_INTEGRATION.md` spec exactly.
- **Server-to-server auth:** header `X-Integration-Key` compared (constant-time) with env `ENROLLMENT_INTEGRATION_KEY` (backend/.env; MUST also be added to deployment secrets, and the same value set on the website as `LIVE_INTEGRATION_KEY`). 401 bad key, 503 if unset. `/api/health.integration` = {enabled, header, enrollments_path, delete_path}; warning when key missing.
- **`POST /api/integrations/enrollments`** body {phone, name, shop_name, location, city, registration_source='website', registered_at, onboarding_status='registered', phone_verified, consent_terms, consent_privacy} → upsert by phone (create full customer record with is_new=True / has_logged_in=False; update never touches login tracking, ignores empty strings, re-activates a previously deleted account); 400 invalid phone; 409 staff phone. Returns {created, customer}. No SMS.
- **`GET /api/integrations/customers/{phone}`** → {customer} (field-by-field verify). **`DELETE /api/integrations/customers/{phone}`** → account deletion from the website's /delete-account page; idempotent ({already_deleted:true}).
- **Account deletion semantics (`_delete_customer_data`, owner decision):** KEEP name, shop_name, location/city, phone (+id, role, customer_code, created_at, registration_source, registered_at, assigned_salesperson) as a business record with account_status/status='deleted', deleted_at, deletion_source; REMOVE cart, wishlists, ai_chat_history (session jeweller-{uid}), reward_transactions, telecaller_activity, reward_points→0, consents/login fields. Enquiries/orders in `requests` are kept as trade history. Audit row in `deletion_requests` {reference DEL-YYYYMMDD-XXXXXX, phone, name, shop_name, source app|website, requested_at, completed_at, status, removed}. Deleted accounts: send-otp/verify-otp → 404 "not registered" (re-enroll on website), tokens → 403, hidden from telecaller lists.
- **In-app deletion:** `POST /api/auth/delete-account/request` (customer token; OTP to own number, purpose account_deletion) → `POST /api/auth/delete-account/confirm {otp}` → {deleted, reference}. Staff → 403. Admin `GET /api/admin/deletion-requests`.
- **Customer app:** Profile → new PRIVACY section: "Privacy Policy" (opens `EXPO_PUBLIC_PRIVACY_URL`, default https://yash-register.emergent.host/privacy) + "Delete My Account" → `/delete-account` screen (removed/kept lists, privacy link, SEND OTP → OTP input → confirm dialog → logout → /login). `EXPO_PUBLIC_ENROLLMENT_URL` now https://yash-register.emergent.host.
- **Admin panel Customers tab:** DELETED badge (date + source, actions hidden) and "ACCOUNT DELETION REQUESTS" list.
- `PUT /api/auth/profile` whitelist now also accepts registration_source, onboarding_status, registered_at (spec's optional fallback).

### Deployment-secrets fix — build `2026.09.04-sms-v5` (Sept 2026)
- **Deployed-server root cause:** Emergent snapshots deployment secrets at the FIRST deploy; `MSG91_TEMPLATE_ID` (added to backend/.env later) never reached the deployed server. Pre-v4 code then silently fell back to demo OTP `1234` for every number → "OTP sent" with no SMS.
- `MSG91_TEMPLATE_ID` now has a built-in default (`MSG91_DEFAULT_TEMPLATE_ID = 61baece18e964726da04e8c5`, not a secret) so Redeploy alone fixes OTPs; `_sms_available()` only needs `MSG91_AUTHKEY`. `JWT_SECRET_FROM_ENV` flag added.
- `GET /api/health` and `GET /api/admin/sms/diagnostics.server_env` now report `env_keys_present` / `env_keys_missing` (names only — MONGO_URL, DB_NAME, JWT_SECRET, MSG91_AUTHKEY, MSG91_TEMPLATE_ID, OTP_DEMO_PHONES, OTP_DEMO_MODE, EMERGENT_LLM_KEY), `template_source` (env | built-in default), `jwt_secret_configured`, `demo_phones_count`, `warnings[]` (e.g. missing template → default used; JWT_SECRET missing → weak default; OTP_DEMO_PHONES missing → demo logins disabled; OTP_DEMO_MODE=true). Startup logs the same.
- Admin panel SMS tab: new "SERVER ENVIRONMENT" card (green/red key chips + warnings) with the Deployments → Secrets → Custom Keys → Redeploy instruction.
- **Deploy checklist:** Deployments → Secrets → Custom Keys must contain `MSG91_AUTHKEY`, `MSG91_TEMPLATE_ID`, `JWT_SECRET`, `OTP_DEMO_PHONES` (if demo staff logins are wanted in prod), `OTP_DEMO_MODE=false`; then Redeploy and check `/api/health` → build `2026.09.04-sms-v5`, `provider_check: ok`, `warnings: []`.

### MSG91 Delivery Hardening — build `2026.09.04-sms-v4` (Sept 2026)
- **Root cause of "OTP not sent":** MSG91 `/flow` returns `{"type":"success"}` + request id even with a wrong authkey/template, then silently drops the SMS. Old code trusted it → false "OTP sent".
- **Pre-flight validation** (`_msg91_preflight`, cached 5 min / 30 s on network error): authkey via `GET control.msg91.com/api/validate.php` (must reply `Valid`) + template via `GET /api/v5/sms/getTemplateVersions` (must return an active version, no reject reason). OTP challenge stored ONLY after pre-flight passes AND MSG91 accepts the send. Failures → HTTP **503** (not 502 — Cloudflare rewrites 502) with explicit text, e.g. `MSG91 rejected the server's SMS configuration (Invalid authkey (MSG91 replied: 201)). OTP was NOT sent.` Missing env → `SMS provider is not configured on the server (...)`. The old silent fallback to demo OTP 1234 when MSG91 env was missing is REMOVED.
- **Delivery confirmation:** every real send → `sms_log` row {id, phone, mobile, purpose(login_otp|phone_change|admin_test), status(accepted|rejected), error, request_id, sent_at/sent_ts, delivery_status(pending|delivered|failed|dropped|n/a), delivery_detail, checks[], msg91_request_date, msg91_status, last_checked_at, delivered_at, build}. Background task checks MSG91 log API `POST /api/v5/report/logs/p/sms` with `{startDate,endDate,requestId}` at +6s/+20s/+60s → Delivered / Failed / Dropped by MSG91 (never appeared in log). MSG91 caches a result-set per distinct filter for minutes, so each attempt rotates `startDate` back one day (3-day window). Log timestamps are IST.
- **APIs:** public `GET /api/health` → {build, provider_check ok|FAILED, provider_message, demo_mode}; admin `GET /api/admin/sms/diagnostics?force=` (provider status, authkey hint, template DLT info, 24h counters accepted/delivered/failed/dropped/pending/rejected, last 30 sends), `POST /api/admin/sms/test {phone}` (real send through production path, returns otp + log; refuses demo phones 400; rate-limited 429), `POST /api/admin/sms/logs/{id}/recheck`.
- **Admin panel → SMS tab** (`src/components/panel/SmsDiagnostics.tsx`, admin only): PROVIDER OK/FAILED card, config grid, template text, 24h stat cards, Send-test form (auto-refreshes at +8/+24/+66 s), recent-messages list with per-row RE-CHECK DELIVERY.
- Verified: real sends to 9711881372 & 9999813334 confirmed **Delivered** by MSG91 within 3 s; fault injection (bad key / bad template / missing config) fails loudly with no OTP challenge stored.

### Real SMS OTP via MSG91 (June 2026 — replaced Twilio per user request)
- OTP delivery via **MSG91 FLOW API** (`POST /api/v5/flow` with template_id + recipients[{mobiles, otp}]). IMPORTANT: template `61baece18e964726da04e8c5` (sender YSILVR) is a FLOW template — the MSG91 OTP API rejects it ("Template ID Missing or Invalid Template"); the enrollment website uses the same Flow route. OTPs are generated server-side (secrets, 4-digit), stored SHA-256 hashed in-memory with 10-min expiry + 5 attempt limit, and verified locally; MSG91 only delivers the SMS. `_sms_available()` requires MSG91_AUTHKEY + MSG91_TEMPLATE_ID. JWT_SECRET now set in backend/.env.
- `/auth/send-otp`: demo-allowlisted phones (`OTP_DEMO_PHONES`) get local OTP 1234; other numbers validated locally (10 digits, starts 6-9) then MSG91 send (mobile format `91XXXXXXXXXX`); errors mapped to friendly messages
- `/auth/verify-otp`: demo phones use in-memory check; others use MSG91 `/otp/verify` (`type: success`); "not match" → Invalid OTP, "not found/expired/already verified" → request new OTP; user record created only after successful OTP dispatch
- MSG91 calls via `requests` (imported as http_requests) in `asyncio.to_thread`; local per-phone rate limiting (5/10min) applies to both paths
- Env vars: MSG91_AUTHKEY, optional MSG91_TEMPLATE_ID/MSG91_BASE_URL, OTP_DEMO_PHONES, OTP_DEMO_MODE=false. Twilio fully removed (code, env vars, pip package)
- Frontend unchanged from Twilio round (no "Demo OTP" hints; "OTP sent via SMS" text)

### Banners + Bhav/Try-On Removal Overhaul (June 2026)
- **Live Bhav removed completely:** `/live-rates` + `/live-rates/config` APIs, Yahoo scraping, background polling task, home rate card, 60s timers, panel Live Rates Config, DB collections `live_rates`/`live_rate_config` dropped. Admin manual Rates tab (`/rates`, `/rates/latest`, `/rates/history`) KEPT — displayed only on customer Rate List page as "Today's Rates" card (no LIVE indicators)
- **AI Try-On removed completely:** `/ai/try-on` endpoint, Pillow compositing fns, `/api/virtual-try-on` static page + `backend/static/`, `/try-on` screen, product-detail buttons
- **Home banner carousel (admin-managed):** `banners` collection; public GET `/api/banners` (active, ordered, date-windowed); admin GET `/api/banners/all`, POST/PUT/DELETE `/api/banners`, POST `/api/banners/upload` (object storage). Frontend `src/components/BannerCarousel.tsx`: auto-rotate 4.5s, manual swipe, dot indicators, loading skeleton, image-error fallback, hidden when empty. Panel → Content → "Home Banners" CRUD with image upload, CTA (none/feed/product/url), order, active, start/end dates
- **Silver/Gold Latest Collection toggle:** Home fetches silver+gold lists separately; segmented toggle (Silver default each launch); instant switch; per-metal empty states; "See All" passes `metal` param to Feed which reads `metal`/`category` route params
- **Product continuity fix:** `/products?ids=a,b,c` returns products in requested order; Feed passes stable ordered ID list to image-viewer; viewer no longer refetches randomized pages; direct productId load fallback
- **Safe-area bottom nav:** tab bar = 56 + `insets.bottom` via useSafeAreaInsets, tabBarHideOnKeyboard, 44px items, WhatsApp FAB at tabBarHeight+16, Android nav bar buttons set light via expo-navigation-bar
- **My Orders screen:** `/my-orders` (from `/cart/orders`), wired from Profile row; multilingual (EN/HI/PA)
- **Error handling:** user-facing alerts/retry states replace silent catch{} for cart, wishlist, product, requests, feed, home, profile, rate-list, orders
- **Keep-awake fix (P1 regression):** `activateKeepAwakeAsync`/`deactivateKeepAwake` during panel uploads, guarded `Platform.OS !== 'web'`
- **Misc:** deduped product tags (unique keys), literal `\u20b9` text fixed, notification bell kept (shows "No new notifications yet")

### Multi-Executive / Telecaller System (March 2026)
- **Admin CRUD:** Create/edit/disable executives with name, phone, code, role (executive or billing_executive)
- **Individual Login:** Each executive logs in with their own phone+OTP, sees their own name in panel header
- **Action Tracking:** Every request status change stores: handled_by_name, handled_by_phone, handled_by_code, last_action_at
- **Notes History:** Each note entry tracks who wrote it (name, phone, code, timestamp)
- **Admin Filtering:** Filter requests by `handled_by` executive ID
- **Performance Stats:** `/api/executives/performance` shows total_handled and resolved per executive
- **Endpoints:** POST/GET/PUT/DELETE /api/executives, GET /api/executives/performance

### Security Hardening (March 2026)
- **Auth:** OTP store with 5-min expiry, 5 retry limit, 5/10min rate limit per phone. No otp_hint leak. JWT_SECRET validation at startup
- **Product privacy:** include_hidden requires admin auth. Hidden/deleted products return 404 to public
- **Cart validation:** quantity must be >0 (Pydantic Field(gt=0)). Rejects non-existent/hidden products
- **Rewards validation:** credit/deduct reject points <=0 (schema + endpoint checks)
- **Request status integrity:** whitelist check after alias mapping. Returns 422 for invalid statuses
- **CORS:** env-based CORS_ORIGINS allowlist (falls back to * for dev)
- **Auth guard:** Tab layout redirects unauthenticated users to /login
- **Try-on guard:** Disabled when product has no image. Shows "unavailable" message
- **TypeScript:** 0 errors on tsc --noEmit. Fixed panel.tsx, about.tsx, index.tsx
- **Cart cleanup:** Startup migration removes rows with quantity<=0

### 9 Major Content Sections
About, Endless Feed, Rate List, Schemes, Brands, Showroom Photos, Exhibition, Home Banners, Language Support (EN/HI/PA)

### PDF Catalogue Import — Production-Grade Chunked Upload (1GB)
- **Max: 1000MB** — 25MB chunks with resume capabilities
- Endpoints: POST /api/pdf-upload/init, /chunk, /complete, GET /status

### Virtual Try-On (Removed June 2026)
- Feature fully removed (backend endpoint, compositing, static page, mobile screen)

### Zoomable Product Images
- Product detail page: ScrollView with maximumZoomScale=4

## Tech Stack
- Frontend: Expo, React Native, TypeScript
- Backend: FastAPI, Motor (async MongoDB), Pydantic
- Storage: Emergent Object Storage
- AI: emergentintegrations (Claude Sonnet 4.5)
- SMS OTP: MSG91 Flow API + pre-flight validation + delivery confirmation via MSG91 log API (build 2026.09.04-sms-v4)
- PDF: PyMuPDF (fitz)

### Scroll Performance & Category Feed Fix (March 2026)
- **Home page:** Replaced ScrollView with virtualized FlatList for product feed. Reduced initial load from 100K to 200 products, renders 20 at a time with progressive loading
- **Category separation:** Metal type filters (ALL/SILVER/GOLD/DIAMOND) properly filter feed — no cross-mixing. API `metal_type` parameter enforced server-side
- **Layout stability:** Fixed image dimensions (260px height) prevent reflow. `removeClippedSubviews`, `windowSize=5`, `initialNumToRender=8` for memory efficiency

## Backlog / Future Tasks
- P1: Improve feed image quality (HD thumbnails)
- P1: Global success toasts after actions
- P1: Fix back-navigation in customer app
- P2: Rate history with mini-charts
- P2: Push notifications
- P2: Analytics dashboard
- P3: Gold calculator

## Areas Needing Refactoring
- `backend/server.py` (~2500+ lines) — Break into modular routers
- `frontend/app/panel.tsx` (~1450 lines) — Split into components
