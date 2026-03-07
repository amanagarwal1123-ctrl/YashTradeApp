# Aman Agarwal Jewellers - Private Business App PRD

## Product Overview
A production-grade private mobile app for Aman Agarwal's jewellery business, serving 40,000+ verified jeweller customers. The app combines daily utility (rates, calculator), engagement (endless feed, AI assistant), and business tools (rewards, request management) in a premium dark-themed experience.

## Tech Stack
- **Frontend**: React Native (Expo SDK 54) with Expo Router
- **Backend**: FastAPI (Python) with Motor (async MongoDB driver)
- **Database**: MongoDB
- **AI**: Claude Sonnet 4.5 via emergentintegrations (Emergent LLM Key)
- **Auth**: JWT-based with phone OTP (mock for MVP)

## MVP Features Built

### 1. Authentication
- Phone + OTP login flow (mock OTP: 1234)
- JWT token-based auth with 30-day expiry
- Auto-redirect based on auth state
- Admin role: 9999999999 | Demo customer: 8888888888

### 2. Home Screen
- Daily silver & gold rate ticker with movement indicators
- Market summary text
- 6 quick action buttons (Calculator, Call, Video Call, Rewards, AI, Knowledge)
- Stories/Highlights horizontal scroll
- Product feed preview with "See All"
- Pull-to-refresh

### 3. Endless Product Feed
- Infinite scroll product grid (2-column)
- Metal type filter (All, Silver, Gold, Diamond)
- Category filter chips (15 categories)
- Search functionality
- Product cards with metal badges, NEW/TRENDING labels
- Pagination (20 per page)

### 4. Silver Jewellery Calculator
- Single item mode: Weight × Rate + Making - Discount + GST
- Multi-item bill mode: Add/remove rows, per-item totals
- Configurable GST% (default 3%)
- Real-time calculation
- Clear all function

### 5. Request Call / Video Call
- 6 request types: Call, Video Call, Ask Price, Ask Similar, Hold Item, Quick Reorder
- Category of interest selection (9 options)
- Preferred time slot
- Notes field
- Admin queue with status management

### 6. Reward Points System
- Welcome bonus (100 pts on first login)
- Wallet view with earned/redeemed summary
- Points value in INR (1 pt = ₹1)
- Transaction history
- Admin-configurable rules (per-1000, welcome, video bonus)

### 7. AI Business Assistant
- Claude Sonnet 4.5 integration
- 6 quick prompt suggestions for jewellers
- Chat interface with message history
- Selling tips, silver knowledge, trend suggestions, content generation
- Session-based conversations

### 8. Silver Knowledge / Education
- 5 seeded articles (silver care, cleaning, benefits, storage, gifting)
- Category filters (All, Silver Care, Benefits, Gifting)
- Expandable article cards
- Designed for retailers to show their own customers

### 9. Customer Profile
- User info display (name, phone, code, type)
- Reward wallet snapshot
- Menu navigation to all tools
- Recent request history with status
- Logout

### 10. Admin Dashboard
- **Dashboard**: Total customers, products, requests, pending count, reward points
- **Products**: Add new products (title, description, metal, category, weight, image URL), list, delete
- **Rates**: Update silver/gold rates, movement indicators, market summary
- **Requests**: View all requests, assign, mark done, no-response
- **Customers**: List all customers with type, city, code, points

## Product Detail Screen
- Full-size product images
- Metal type, category, stock status badges
- Description and weight details
- Tags display
- CTAs: Ask Price, Video Call, Ask Similar, Hold Item, Reorder

## Database Collections
- `users` - Customers and admins
- `products` - Product catalog (15 seeded items)
- `rates` - Daily rate entries
- `requests` - Call/video call requests
- `reward_transactions` - Points history
- `reward_config` - Points rules
- `knowledge` - Education articles
- `stories` - Highlights/stories
- `wishlists` - User wishlists
- `analytics` - Event tracking
- `ai_chat_history` - AI conversation history

## Design System
- Theme: Dark Premium (bg: #050505, surface: #121212, card: #1A1A1A)
- Primary: Gold (#D4AF37)
- Secondary: Silver (#E0E0E0)
- Text: White (#FFFFFF) with secondary (#A1A1AA) and muted (#52525B)
- Functional: Success (#10B981), Error (#EF4444), Warning (#F59E0B), Info (#3B82F6)
- 8pt spacing grid, 44px minimum touch targets

## API Endpoints (30+ endpoints)
- Auth: send-otp, verify-otp, me, profile update
- Products: list, get, create, update, delete, categories
- Rates: latest, update, history
- Requests: create, my-requests, list (admin), update (admin)
- Rewards: wallet, history, redeem, credit (admin), config (admin)
- AI: chat, suggestions
- Knowledge: list, get, create
- Stories: list, create
- Wishlist: toggle, list
- Analytics: track event, dashboard (admin)
- Customers: list, get, update (admin)

## Phase 2 Features (Roadmap)
- Real SMS OTP integration (Twilio)
- Push notifications
- Parcel/order tracking
- Advanced reward campaigns
- Personalized feed recommendations
- City-wise analytics
- Retailer education videos
- App install campaign tracking
- Customer segmentation campaigns
- Multi-image upload from device
- Video content support

## Business Enhancement Suggestion
**Referral Program**: Implement a "Refer a Jeweller" feature where existing customers earn bonus points (e.g., 500 pts) for each verified jeweller they invite. This leverages the existing 40,000-customer network for organic growth while the reward system incentivizes participation. Track referral chains for attribution analytics.
