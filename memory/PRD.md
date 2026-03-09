# Yash Trade - Jewellery Business App

## Original Problem Statement
Build a production-grade, private mobile app for "Yash Trade" / "Yash Ornaments" - a wholesale jewellery business serving ~40,000 wholesale/retail jewelers.

## Architecture
- **Customer App**: Expo (React Native) mobile app
- **Admin Panel**: React web panel at `/panel` route
- **Backend**: FastAPI + MongoDB
- **Storage**: Emergent Object Storage
- **AI**: Claude Sonnet 4.5 via Emergent LLM Key

## User Roles
1. **Customer (user)** - Mobile app access
2. **Admin** - Full panel access (Phone: 9999999999)
3. **Executive** - Request management (Phone: 7777777777)
4. **Billing Executive** - Reward points only (Phone: 6666666666)

## Implemented Features (as of March 2026)

### Core Features
- JWT auth with mock OTP
- Product catalog with feed, search, filters
- Cart (selection/shortlist tool for executives)
- Request flow (call, video call, ask price) with multi-product selection
- Rewards/loyalty system with audit trail
- AI assistant (Claude Sonnet 4.5)
- Silver Calculator with searchable dropdown
- Stories/Highlights
- Knowledge base

### March 9, 2026 - 9 Major Features Added
1. **About Yash Ornaments** (5th tab) - Brand presentation, Why Buy, Benefits, B2B points, Locations
2. **Endless Home Feed** - Products cycle infinitely, never stops
3. **Live Rate Auto-Fetch** - Yahoo Finance for dollar rates, auto-calculate MCX via USD/INR conversion, Physical = MCX + Admin Premium
4. **Rate List** - Silver/Gold/Diamond quantity-based slabs, admin-managed
5. **Schemes Page** - Poster-based scheme display, admin-managed
6. **Brands Section** - Brand logos with authorized dealer presentation
7. **Showroom Photos** - Floor-wise photos with product descriptions
8. **Upcoming Exhibition** - Shows upcoming/past exhibitions with posters
9. **Full Language Support** - Hindi/English/Punjabi selector on login, all screens translated

### Admin Panel Content Management
- About content editor (multilingual)
- Rate list slab manager
- Schemes CRUD
- Brands CRUD
- Showroom floors CRUD
- Exhibitions CRUD
- Live rates premium config

## Tech Stack
- Frontend: Expo, React Native, TypeScript
- Backend: FastAPI, Motor (async MongoDB), Pydantic
- Storage: Emergent Object Storage
- AI: emergentintegrations (Claude Sonnet 4.5)
- Live Rates: Yahoo Finance API + ExchangeRate API

## Key API Endpoints
- Auth: /api/auth/send-otp, /api/auth/verify-otp, /api/auth/me
- Products: /api/products, /api/products/{id}
- Rates: /api/rates/latest, /api/live-rates, /api/live-rates/config
- Requests: /api/requests, /api/requests/my
- Cart: /api/cart, /api/cart/add, /api/cart/submit
- Rewards: /api/rewards/wallet, /api/rewards/credit, /api/rewards/deduct
- Content: /api/about, /api/rate-list, /api/schemes, /api/brands, /api/showroom, /api/exhibitions
- Upload: /api/batches, /api/batches/{id}/upload

## Backlog / Future Tasks
- P0: Improve feed image quality (HD thumbnails)
- P1: Global success toasts after actions
- P1: Fix back-navigation in customer app
- P2: Rate history with mini-charts
- P2: Push notifications
- P2: Analytics dashboard
- P3: Real OTP integration (replace mock)
- P3: Gold calculator
