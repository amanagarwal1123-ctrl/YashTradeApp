# Yash Trade App - Product Requirements Document

## Original Problem Statement
Private mobile app for Yash Trade jewelry business, serving ~40,000 wholesale and retail jewelers. The app functions as a daily-use business utility combining:
- Endless jewelry media viewer (10,000+ images)
- Daily gold/silver rate updates (6-point system)
- Customer engagement tools (requests, rewards, AI assistant)
- Operational management (admin panel, executive dashboard)

## Tech Stack
- **Backend:** FastAPI (Python) + MongoDB (via Motor async)
- **Frontend:** Expo (React Native) with Expo Router, running as web app
- **Storage:** Emergent Object Storage for production image uploads
- **AI:** Claude Sonnet 4.5 via Emergent LLM Key
- **Auth:** JWT with mocked phone OTP (mock code: 1234)

## User Roles
1. **Admin** (phone: 9999999999) - Full control
2. **Executive** (phone: 7777777777) - Request management
3. **Customer** (phone: 8888888888) - Browse, request, rewards

## Core Architecture
```
/app/backend/server.py  - Monolithic FastAPI (all routes + models + storage)
/app/frontend/app/      - Expo Router file-based routing
  ├── (tabs)/            - Main tabs (Home, Feed, Calculator, Profile)
  ├── admin.tsx          - Admin panel with tabs
  ├── admin-batches.tsx  - Batch management + file upload
  ├── admin-batch-detail.tsx - Batch image grid + management
  ├── image-viewer.tsx   - Full-screen image viewer
  └── ...
/app/frontend/src/api.ts - API layer with file upload support
```

## What's Been Implemented

### Phase 0 (Previous Sessions)
- [x] JWT Auth with 3 roles (admin/executive/customer)
- [x] 6-point rate system (Dollar/MCX/Physical for Gold & Silver)
- [x] Endless feed with pagination
- [x] URL-based bulk upload
- [x] Silver calculator
- [x] AI assistant (Claude Sonnet 4.5)
- [x] Multi-language (English/Hindi/Punjabi)
- [x] Executive dashboard
- [x] Stories/highlights
- [x] Rewards system (basic)
- [x] Request system (call/video call/ask price)
- [x] Knowledge articles

### Phase 1 (2026-03-07) - Production Media Upload + Batch Management
- [x] **Emergent Object Storage Integration** - init, put_object, get_object
- [x] **Image Processing** - Pillow-based compression + thumbnail generation
  - Thumbnails: 400px max, 60% JPEG quality (for feed)
  - Originals: 1600px max, 85% JPEG quality (for viewer)
- [x] **Real File Upload** - Admin can upload actual image files from device
  - Multi-file selection
  - Chunked upload (3 files per batch request)
  - Upload progress tracking
  - File size validation (max 20MB per file)
- [x] **Batch/Folder Management (CRUD)**
  - Create batch with name, metal type, category
  - List/search batches
  - Edit batch metadata (name, metal, category)
  - Delete batch (soft-delete/archive)
  - Toggle visibility (hide/show from customer feed)
  - Batch reassigns metal/category to all child products
- [x] **Batch Image Management**
  - Upload images to specific batches
  - View all images in a batch (paginated grid)
  - Multi-select images
  - Bulk delete selected images
  - Image count tracking per batch
- [x] **File Serving** - Backend serves images from storage with 24hr cache
- [x] **Products Visibility Filtering** - Hidden/deleted products excluded from public feed
- [x] **Enhanced Request Management** - Notes history, customer info retrieval

### Phase 2 (2026-03-07) - Feed Viewer Experience
- [x] **Full-Screen Image Viewer** - Opens on tap from feed
  - Navigation arrows (prev/next)
  - Image counter (1/N)
  - Close button
  - Ask Price + Video Call action buttons
  - Smooth transitions
- [x] **Feed Improvements**
  - Uses getImageUrl() utility for both URL and storage-backed images
  - Increased page size (20 items)
  - FlatList performance optimizations (windowSize, removeClippedSubviews)
  - Latest uploads first (sorted by created_at DESC)
- [x] **Home Screen** - Updated to use getImageUrl for product cards
- [x] **Product Detail** - Updated to use storage images when available

## Key API Endpoints

### Auth
- POST /api/auth/send-otp
- POST /api/auth/verify-otp
- GET /api/auth/me

### Products
- GET /api/products (pagination, filters, excludes hidden/deleted)
- POST /api/products (admin)
- POST /api/products/bulk (admin - URL-based)

### Batches (NEW)
- POST /api/batches (admin - create)
- GET /api/batches (admin - list)
- GET /api/batches/{id} (admin - detail)
- PUT /api/batches/{id} (admin - update)
- DELETE /api/batches/{id} (admin - archive)
- PATCH /api/batches/{id}/visibility (admin - toggle)
- POST /api/batches/{id}/upload (admin - file upload)
- GET /api/batches/{id}/images (admin - paginated images)
- POST /api/batches/{id}/images/delete (admin - delete selected)

### Files
- GET /api/files/{path} (serves images from storage, cached 24hr)

### Rates
- GET /api/rates/latest
- POST /api/rates (admin)
- GET /api/rates/history

### Requests
- POST /api/requests (user)
- GET /api/requests (exec/admin, with filters)
- PATCH /api/requests/{id} (exec/admin, notes history)
- GET /api/requests/{id}/history (customer detail + past requests)

## DB Collections
- **users** - phone, name, city, role, reward_points
- **products** - title, images[], storage_path, thumbnail_path, batch_id, visibility, is_deleted
- **batches** - name, metal_type, category, status, image_count, upload_type
- **rates** - 6 rate values, movement, physical mode/premium
- **requests** - request_type, status, notes_history[]
- **reward_transactions** - points, type, reason
- **knowledge** - articles/tips
- **stories** - highlights

### Bug Fixes (2026-03-07)
- [x] Fix 1: Prevent points exploit — POST /api/rewards/redeem rejects points <= 0
- [x] Fix 2: Seed endpoints protected with admin auth
- [x] Fix 3: Product detail gallery — thumbnail selection changes main image correctly
- [x] Fix 4: Image viewer index — productId match prioritized over startIndex fallback
- [x] Fix 5: verify-otp returns fresh user state after welcome-bonus credit
- [x] Fix 6: Wired dead CTAs — Home Ask Price/Wishlist, Profile My Requests/Wishlist, Product wishlist
- [x] Fix 7: Unified request statuses (pending/in_progress/contacted/resolved/no_response), `done`→`resolved` and `assigned`→`in_progress` aliased
- [x] Fix 8: Admin rates tab hydrates movement + market summary on load
- [x] Fix 9: Frontend .env.example + missing-env console warning
- [x] Fix 10: Executive user seeded at startup (no manual seed/expand needed)
- [x] Fix 11: i18n strings verified as proper UTF-8 Hindi/Punjabi
- [x] Fix 12: PATCH /api/requests/{id} returns 404 for non-existent requests

## Prioritized Backlog

### P1 - Upcoming
- [ ] Executive Panel upgrade (WhatsApp/Call buttons, advanced filters, customer detail modal)
- [ ] Rate History charts (mini charts, intraday history, previous update comparison)
- [ ] Push notification architecture
- [ ] Rewards/Loyalty system enhancement (catalog, redemption flow, campaigns)

### P2 - Next
- [ ] Silver Knowledge section build-out (admin + display)
- [ ] Calculator improvements (multi-item, copy/share, save history)
- [ ] Language improvements (full localization of all sections)
- [ ] Analytics improvements (views, engagement, scroll depth)
- [ ] Stories/Highlights admin management

### P3 - Future
- [ ] Real OTP integration (Twilio/SMS)
- [ ] Parcel/Order status tracking
- [ ] Personalized AI feed recommendations
- [ ] City-wise notification campaigns
- [ ] Backend modularization (APIRouter)
