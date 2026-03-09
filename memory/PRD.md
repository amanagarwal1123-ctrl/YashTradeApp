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
- JWT auth with mock OTP
- Product catalog with feed, search, filters
- Cart, Requests, Rewards, AI assistant, Silver Calculator, Stories, Knowledge base

### 9 Major Content Sections
About, Endless Feed, Live Rates, Rate List, Schemes, Brands, Showroom Photos, Exhibition, Language Support (EN/HI/PA)

### PDF Catalogue Import — Production-Grade Chunked Upload (1GB)
- **Max: 1000MB** — 5MB chunks with 5 retries each (exponential backoff up to 15s, 90s per-chunk timeout)
- **Resumable**: Server tracks received_chunk_indices; client skips already-uploaded chunks on retry
- **Background processing**: PDF assembled on server, pages extracted via PyMuPDF in asyncio task
- **Real-time progress**: Upload %, page X/Y processing, imported/failed/skipped counts
- **Cancel/Close button** visible during upload — user can abort anytime
- **Resume button** appears on failure — re-uploads only missing chunks
- **Keep-awake**: expo-keep-awake prevents screen lock during upload on mobile
- **Detailed errors**: file too large, corrupt PDF, network interruption, chunk timeout, page extraction failure
- Endpoints: POST /api/pdf-upload/init, /chunk, /complete, GET /status
- Legacy: POST /api/batches/{id}/import-pdf still works

### Zoomable Product Images
- Product detail page: ScrollView with maximumZoomScale=4, "Pinch to zoom" hint
- Image viewer: ScrollView with maximumZoomScale=5, full-screen zoom support

## Tech Stack
- Frontend: Expo, React Native, TypeScript
- Backend: FastAPI, Motor (async MongoDB), Pydantic
- Storage: Emergent Object Storage
- AI: emergentintegrations (Claude Sonnet 4.5)
- Live Rates: Yahoo Finance + ExchangeRate API
- PDF: PyMuPDF (fitz)

## Backlog / Future Tasks
- P0: Improve feed image quality (HD thumbnails)
- P1: Global success toasts after actions
- P1: Fix back-navigation in customer app
- P2: Rate history with mini-charts
- P2: Push notifications
- P2: Analytics dashboard
- P3: Real OTP integration (replace mock)
- P3: Gold calculator

## Areas Needing Refactoring
- `backend/server.py` (~2200+ lines) — Break into modular routers
- `frontend/app/panel.tsx` (~1430 lines) — Split into components
