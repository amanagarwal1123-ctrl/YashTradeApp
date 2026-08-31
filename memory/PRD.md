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

### Real SMS OTP via MSG91 (June 2026 — replaced Twilio per user request)
- OTP send/verify via **MSG91 OTP API v5** (`control.msg91.com/api/v5/otp` + `/otp/verify`), authkey in backend/.env, 4-digit codes, account default OTP template (MSG91_TEMPLATE_ID env optional)
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
- SMS OTP: MSG91 OTP API
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
