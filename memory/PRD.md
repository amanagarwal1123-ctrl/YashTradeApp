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
About, Endless Feed, Live Rates, Rate List, Schemes, Brands, Showroom Photos, Exhibition, Language Support (EN/HI/PA)

### PDF Catalogue Import — Production-Grade Chunked Upload (1GB)
- **Max: 1000MB** — 25MB chunks with resume capabilities
- Endpoints: POST /api/pdf-upload/init, /chunk, /complete, GET /status

### Virtual Try-On (Web)
- Standalone web page at `/api/virtual-try-on`
- Backend compositing: Pillow-based background removal + overlay
- Endpoint: POST /api/ai/try-on

### Zoomable Product Images
- Product detail page: ScrollView with maximumZoomScale=4

## Tech Stack
- Frontend: Expo, React Native, TypeScript
- Backend: FastAPI, Motor (async MongoDB), Pydantic
- Storage: Emergent Object Storage
- AI: emergentintegrations (Claude Sonnet 4.5)
- Live Rates: Yahoo Finance + ExchangeRate API
- PDF: PyMuPDF (fitz)

## Backlog / Future Tasks
- P1: Improve feed image quality (HD thumbnails)
- P1: Global success toasts after actions
- P1: Fix back-navigation in customer app
- P1: Re-add expo-keep-awake with platform-specific guard
- P2: Rate history with mini-charts
- P2: Push notifications
- P2: Analytics dashboard
- P3: Real OTP/SMS integration (replace mock)
- P3: Gold calculator

## Areas Needing Refactoring
- `backend/server.py` (~2500+ lines) — Break into modular routers
- `frontend/app/panel.tsx` (~1450 lines) — Split into components
