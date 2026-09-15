YASH SILVER — Google Play TABLET screenshots
============================================

Capture note (please read):
No Android tablet emulator is available in this environment, so these are the ACTUAL current app screens
rendered by the Expo WEB preview (react-native-web) at tablet-sized viewports. They are fresh tablet renders —
NOT stretched, cropped or relabelled phone screenshots. Signed in as a SYNTHETIC test customer
("Sample Customer", New Delhi) against the preview environment; no real customer details, keys, OTPs or
staff records appear. All jewellery photographs are from the authorised catalogue.

Output spec: opaque PNG (RGB), 9:16 portrait, shortest side >= 1080 px, each file < 8 MB.

tablet_7_inch/   viewport 600 x 1067 dp (Android sw600 = 7-inch bucket) at 1.8x  ->  1080 x 1920 px
tablet_10_inch/  viewport 800 x 1423 dp (classic 10-inch portrait width) at 1.8x  ->  1440 x 2560 px
  (An exact 9:16 target needs a fractional dp height, so each raster was 1-2 px taller than the target; the
   surplus bottom rows — uniform tab-bar background — were removed. No UI was cut: the tab bar is fully intact.)

Screens (identical set in both folders, display order):
  01_catalogue.png        Home "Latest Collection" — silver toggle with catalogue cards (Add to Cart / Ask Price / Wishlist).
  02_product_details.png  Product photograph and details with Add to Cart, Ask Price, Video Call, Hold Item, Reorder.
  03_wishlist.png         Saved designs in the customer's Wishlist.
  04_enquiry_status.png   "My Requests" — submitted enquiries with Pending / In Progress / Resolved status.

Checks performed on every file: fully loaded (all images complete, no loading spinners in view), readable text,
no clipped or overlapping controls, no personal information; dimensions/aspect/mode/size verified programmatically.

Observation recorded separately (web preview only, not tested on native Android): on the Feed/"Collection"
screen the horizontal category chip row (All, Bangles, Chains, ...) renders clipped beneath the metal filters.
For that reason the catalogue screenshot uses the Home "Latest Collection" screen; the app code was not changed.
