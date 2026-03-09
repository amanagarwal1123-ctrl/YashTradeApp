# Changelog

## March 9, 2026 - 9 UI/UX Business Changes (Batch 2)

### Point 1: Silver Rate List → Item-wise Structure
- Removed old quantity-slab system (Below 5KG, Above 10KG etc.)
- Each entry now has: Item Name, Category/Subcategory, Purity, Wastage, Labour in KG
- 6 silver items, 3 gold items, 2 diamond items seeded
- Admin can add/edit/delete entries via Panel > Content > Rate List

### Point 2: Office Addresses Fixed
- Head Office = 1159/1114, 2nd-4th Floor, Yash Complex, Kucha Mahajani, Chandni Chowk, Delhi - 110006
- Branch Office = 20/2799, Beadon Pura, Karol Bagh, New Delhi - 110005

### Point 3: Showroom Title → "Showroom Photos"
- Updated label everywhere including About page quick links, home quick actions

### Point 4: Showroom Photos with Floor Product Description
- Each floor shows: photo + floor name + products available text
- Admin manages both photo and description

### Point 5: Brands Section → Poster-style Image Layout
- Full-width poster image cards with "Authorized Dealers" banner
- Admin uploads poster images from Panel > Content > Brands

### Point 6: About Points → Clickable with Detailed Written Matter
- Each "Why Buy" point is now a clickable expandable card
- Tap to expand shows detailed description for each point
- "Tap any point to see details" hint shown

### Point 7: Product View → Swapped Ask Price & Add to Cart
- "Add to Cart" is now the primary (gold) button
- "Ask Price" moved to secondary position
- Alert shows "Product added to the cart" on Add to Cart tap

### Point 8: Cart Submit → Thank You Success Screen
- After Submit Selection, user is navigated to the full-page success/thank-you screen

### Point 9: Feed Cards → Compact Product Metadata
- Product cards in feed and home now show: Purity, Touch, Label as small gold tags
- Weight and category already shown in meta line

### Point 1: About Yash Ornaments (5th Tab)
- Added new `about.tsx` tab with brand presentation
- Includes: Brand intro, Why Buy (9 points), New Shop Benefits (4 points), B2B Benefits (8 points), Locations (Chandni Chowk + Karol Bagh)
- Admin-manageable content via `/api/about` endpoints
- Multi-language support (EN/HI/PA)

### Point 2: Endless Home Feed
- Modified `index.tsx` to cycle products infinitely
- When products end, they restart from beginning
- ScrollView onScroll handler triggers loadMoreProducts
- Always shows loading indicator at bottom

### Point 3: Auto-Fetch Live Rates
- Background task fetches rates every 60 seconds
- Sources: Yahoo Finance (SI=F for silver, GC=F for gold), ExchangeRate API for USD/INR
- Physical Rate = MCX Rate + Admin-set Premium
- Admin configurable via `/api/live-rates/config`
- LIVE indicator shown on home rate card

### Point 4: Rate List Page
- New `rate-list.tsx` screen with Silver/Gold/Diamond tabs
- Quantity-based slabs (e.g., Below 5 KG, 5-10 KG, Above 10 KG)
- 10 seeded slabs across 3 metals
- Admin CRUD via panel Content > Rate List

### Point 5: Schemes Page
- New `schemes.tsx` screen showing poster-based schemes
- Admin uploads poster URL, title, description
- Multi-language title/description support

### Point 6: Brands Section
- New `brands.tsx` screen showing authorized brand logos
- "We are authorized dealers" presentation
- Admin manages brands via panel

### Point 7: Showroom Photos
- New `showroom.tsx` with floor-wise photo gallery
- Each floor: photos + description + products available
- Multi-language support for floor names/descriptions

### Point 8: Upcoming Exhibition
- New `exhibition.tsx` showing upcoming + past exhibitions
- Clear "No Upcoming Exhibition" state when empty
- Poster/photo support, date/location info

### Point 9: Full Language Support
- Language selector added to login page
- All new screens have EN/HI/PA inline translations
- Admin content supports content_en/content_hi/content_pa fields
- Tab labels translated in bottom navigation

### Admin Panel Updates
- New "Content" tab in admin panel
- Sub-sections: About, Rate List, Schemes, Brands, Showroom, Exhibitions, Live Rates Config
- Full CRUD for all new content types

### Backend Changes
- 7 new MongoDB collections: about_content, rate_slabs, schemes, brands, showroom_floors, exhibitions, live_rates/live_rate_config
- Background rate fetching task
- Seed data for about content and rate slabs
- Added beautifulsoup4 and lxml dependencies
