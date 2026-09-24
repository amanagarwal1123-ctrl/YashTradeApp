# App Store submission — Yash Trade / Yash Silver (iOS) — working document

Created 20 September 2026 during the R00–R17 run (brief `memory/briefs/YASH_TRADE_COMPLETE_IMPLEMENTATION_BRIEF_2026-09-20.md`, R17).
Status legend used below: **VERIFIED** (read from the source tree / generated native project in this workspace) ·
**OWNER TO CONFIRM** (value exists but only the owner can confirm it is the intended public value) · **BLOCKED** (needs an
account, device, credential or tool this container does not have) · **NOT DONE**.

This file is the iOS counterpart of `GOOGLE_PLAY_DATA_SAFETY.md` (Play) and reuses the Play listing assets in
`store_assets/` as the copy baseline. Nothing here is a claim that the app is submitted, approved or live.

## 0. Release states (kept separate — never merged)

| State | Value (21 Sep 2026, closeout) |
| --- | --- |
| Code Complete (app + backend, R00–R17) | **COMPLETE in the working tree** for R00–R17 and the review findings F01–F09 / G01–G04 (incl. G01c, G04b) — per-surface states in `IMPLEMENTATION_ACCEPTANCE_MATRIX.md`. Website (R16-A) BLOCKED (no repository access). `frontend/yarn.lock` (four native dependencies, L01) and `frontend/.env.example` are modified but not yet in any commit — the owner's Save to GitHub must include them (verify on GitHub) |
| Tests Passed | **21 Sep 2026**: backend pytest `tests/shared` **194 passed / 5 skipped / 0 failed** (`test_reports/pytest/recheck_c3da84e_2026-09-21.xml`; skips = Playwright-based UI cases, Playwright not importable in this Python env); Jest **24 suites / 147 tests / 0 failed** (`test_reports/jest_recheck_c3da84e_2026-09-21.txt`); `yarn install --frozen-lockfile` exit 0; browser journeys on the isolated review scope 8/8 after iteration 39-B; live-API E2E C1–C8 6/6 (iteration 38). Codex independent verification of the last fixes: 10/10 focused checks (owner-reported) |
| Native Verified | **NOT VERIFIED** — no iOS simulator/device, no Android emulator/device, no signing credentials in this container. All browser evidence is Expo-web evidence; R02 zoom, R06 keyboard, R07 OTP autofill, R09 push (text + image) need a store build on a device |
| Website Deployed | **BLOCKED** — no website repository/project access in this environment (`git remote -v` empty; no website env names present) |
| Build Uploaded | NOT DONE — owner: Save to GitHub → confirm the lockfile is in the commit → Emergent **Publish** → store builds |
| Submitted for Review | NOT DONE |
| Store Live | NOT DONE |

## 1. App record identity (VERIFIED from `frontend/app.json` and the generated iOS project)

| Field | Value | Source |
| --- | --- | --- |
| Display name (`CFBundleDisplayName`) | `Yash Trade App` | `app.json` `expo.name` |
| Bundle identifier | `com.emergent.yashtryontest.lt5e6b` | `app.json` `ios.bundleIdentifier`; generated `project.pbxproj` `PRODUCT_BUNDLE_IDENTIFIER` |
| Marketing version (`CFBundleShortVersionString`) | `1.0.0` | `app.json` `expo.version`; generated `Info.plist` |
| Build number (`CFBundleVersion`) | `1` (Expo default — `ios.buildNumber` is not declared; Emergent Publish/EAS assigns the uploaded build number) | generated `Info.plist` |
| Android package / versionCode / versionName (same record family) | `com.emergent.yashtryontest.lt5e6b` / `1` / `1.0.0` | generated `android/app/build.gradle` |
| Expo SDK / React Native | 54.0.37 / 0.81.5 (owner decision 15 Sep: stay on SDK 54) | `node_modules/expo/package.json`, `package.json` |
| Deep-link scheme | `yash-trade` | `app.json` `expo.scheme` |
| Orientation / tablets | portrait; `supportsTablet: true` | `app.json` |
| Icon | `assets/images/icon.png` 1024², Yash gold "Y" + diamond on green `#013625` (owner artifact, 14 Sep) | `app.json` |
| Minimum iOS | 15.1 (`IPHONEOS_DEPLOYMENT_TARGET`, Expo SDK 54 default) | generated `project.pbxproj` |
| Export compliance | App uses only HTTPS/TLS (exempt encryption). `ITSAppUsesNonExemptEncryption=false` declared in `app.json` `ios.infoPlist` (20 Sep) so App Store Connect does not ask on every upload | `app.json` |

**Do not change** the bundle identifier, package name, scheme or icon in the listing work; the existing record is kept (brief §3).

## 2. Listing copy (iOS field limits applied) — baseline = the Play listing assets in `store_assets/`

The Play Console listing TEXT (title / short / full description) is not stored in this repository — only the Play graphic
assets and their `README.txt` are. The copy below is derived from the ACTUAL shipped functionality (screens in
`frontend/app/`) and from the Play asset descriptions; **OWNER TO CONFIRM** that it matches the wording already live on
Google Play (paste the Play text here if it differs, keeping the limits).

| App Store Connect field | Limit | Proposed value | Status |
| --- | --- | --- | --- |
| Name | 30 | `Yash Silver` (the Play listing/asset name) — alternative `Yash Trade App` (bundle display name) | OWNER TO CONFIRM which brand name is on the Play listing |
| Subtitle | 30 | `Silver & gold trade catalogue` (29) | proposed |
| Promotional text | 170 | `Browse the latest silver and gold designs from Yash, save favourites, and send price, call-back or video-call enquiries to the team in one tap.` (150) | proposed |
| Keywords | 100 | `silver,gold,jewellery,jeweller,wholesale,catalogue,MCX,rate,enquiry,Yash` (75) | proposed |
| Description | 4000 | see §2.1 | proposed — every sentence maps to a shipped screen |
| Primary category | — | **Business** (private B2B catalogue and enquiry tool for verified jewellers) | proposed; alternative Shopping is NOT accurate (no purchases in the app) |
| Secondary category | — | none | — |
| Copyright | — | `© 2026 Yash Ornaments` | OWNER TO CONFIRM legal entity name |
| Support URL | — | **OWNER TO PROVIDE** (no support URL exists in the app config; Help screen has no URL) | BLOCKED (missing input) |
| Marketing URL | — | optional; `https://register.yashsilver.com` (enrolment site) if desired | OWNER TO CONFIRM |
| Privacy Policy URL | — | `EXPO_PUBLIC_PRIVACY_URL` = `https://yash-register.emergent.host/privacy` (the URL the app opens). Must carry the text of `WEBSITE_PRIVACY_UPDATE.md` **before** submission | OWNER TO CONFIRM (canonical `https://register.yashsilver.com/privacy` preferred) |
| Terms of use (EULA) | — | Apple standard EULA unless `EXPO_PUBLIC_TERMS_URL` is set (currently empty → the app's Terms link opens the Privacy Policy) | OWNER TO PROVIDE |
| Account-deletion URL (App Store Connect → App Privacy → "Account deletion") | — | In-app: Profile → *Delete My Account* (OTP-confirmed). Web: enrolment site `/delete-account` page — **OWNER TO CONFIRM public URL** (expected `https://register.yashsilver.com/delete-account`) | OWNER TO CONFIRM |
| Age rating | — | **4+ expected**: no user-generated public content, no violence, no gambling, no unrestricted web access (the WebView opens only the privacy/terms/enrolment URLs set by the app), no medical/drug content. Re-answer the questionnaire from these facts; the Business category + "unrestricted web access = No" must be answered explicitly | to be answered by the owner in App Store Connect |
| Made for Kids | No | private B2B app | VERIFIED (`login.tsx` footer) |

### 2.1 Description (proposed, 4000-char limit; ~1,650 chars)

```
Yash Silver is the private catalogue and enquiry app of Yash Ornaments for verified jewellers.

BROWSE THE COLLECTION
• Latest silver and gold designs with real product photographs, filtered by metal and category
• Pull to refresh to see designs you have not viewed yet first
• Pinch, pan and double-tap to zoom into every photograph

SAVE AND ENQUIRE
• Wishlist your favourite designs and build a selection cart
• Send an Ask-Price, Call-back or Video-call enquiry on any design — the team calls you back or opens WhatsApp
• Track your enquiries under My Requests (Pending, In Progress, Resolved)

RATES AND TOOLS
• Live silver and gold reference rates (silver per kg, gold per 10 g) and the item-wise rate list
• Jewellery calculator for weight, rate, making charges, discount and GST
• Reward points on your account

ACCOUNT
• Sign in with your mobile number and a one-time code (no password)
• Notifications for offers can be switched off any time; account deletion is available in Profile

Yash Silver is for the jewellery trade. New customers register with their mobile number in the app or on the Yash registration website.
```

Not in the description (deliberately): staff/admin features (Panel, Contents/PDF import, telecaller workspace,
notification composer), store-reviewer sign-in, AI assistant beyond what ships (the assistant exists behind an explicit
consent screen; add one line only if the owner wants it advertised), any "buy"/payment wording (no payments exist).

## 3. Reviewer access (App Review Information → Sign-in required)

### 3.0 App Review rejection of iOS 1.0.2 (107) — 24 September 2026 — and the fixes in this source tree

| Guideline | Apple's finding | Fix (code, this tree) | Owner action in App Store Connect |
|---|---|---|---|
| **5.1.1(v) Data Collection and Storage** | "The app requires users to register before browsing products. Registration can only be required for account-based features like adding to cart or checking out." | **iOS-only guest catalogue preview** (owner decision: Android keeps login-first, preview capped at **100** products, only the catalogue is public). `src/navigation.ts` `guestHomeRoute()` → `/guest-preview` on iOS, `/login` elsewhere; new `app/guest-preview.tsx` (public `GET /api/products`, pages of 20, stops at 100, then an *End of preview* card with the catalogue total and a Sign in button; header Sign in; Help link). Product detail and the photo viewer open read-only; **Add to Cart, wishlist, Ask Price, Video Call, Hold, Reorder** show *Sign in to continue* (`src/hooks/useRequireSignIn.ts`) and lead to `/login`. The login screen gets an iOS-only *Browse the collection* back control; logout / account deletion return to the preview on iOS. No prices exist anywhere in the app, so the preview reveals nothing commercial. Android/web: `/` still lands on `/login`, no exit control on login, nothing else changed | Reply to the rejection (draft below); resubmit the new build |
| **2.3.10 Accurate Metadata** | "Revise the app's binary to remove Google Play references." | All in-app strings reworded: Help card (EN/HI/PA) "For app store review teams only…", reviewer sign-in subtitle "For app store review teams", owner Review-Keys console label "OTHER STORE CONSOLES (APP ACCESS FORM)". `grep -ri "google play" frontend/app frontend/src` → 0 hits (tests excluded) | **Check the listing yourself**: description, keywords, promotional text, What's New, review notes and screenshots must not mention Google Play / Android / Play Store — the agent cannot see or edit App Store Connect |
| Login footer | (not cited; contradicted public browsing) | "Private app for verified jewellers only" → **"Yash Trade App - Wholesale silver & gold jewellery"** (EN/HI/PA) | — |

Evidence: Jest 29 suites / **170 passed** (new `guestPreview.test.tsx` 4, `guestGate.test.tsx` 4; `navigationSession.test.tsx` updated for the platform split), `tsc --noEmit` clean, eslint 0 errors; browser iteration 40 (web, `test_reports/iteration_40.json`, 24 Sep 2026): `/guest-preview` loads without Authorization, pages 2–5 only (page 6 never requested), 100-item cap, end card "browse all 345 products", every gated button → *Sign in to continue* → `/login`, `/` on web still → `/login`, no "Google Play" on `/help` or `/review-access`. The iOS routing itself (`Platform.OS === 'ios'`) is covered by Jest only — the web preview cannot run as iOS; verify once on the TestFlight build: cold start → preview, Sign in → OTP → customer Home, logout → preview.

**Draft reply to App Review (Resolution Center)** — "Thank you for the review. 5.1.1(v): the app now opens directly on a read-only preview of our jewellery catalogue (up to 100 products, product details and photographs) without any registration. Registration (mobile-number OTP) is requested only for account-based features: saving items to the cart or wishlist, submitting price / video-call / hold / reorder enquiries, reward points, notifications and the profile. There are no prices or purchases in the app; enquiries are handled by our sales team by phone. 2.3.10: all references to other platforms have been removed from the binary and we have checked the listing metadata. Reviewer accounts remain available as described in the review notes."

- **Mechanism (VERIFIED in code, `shared/review.py`, `frontend/app/review-access.tsx`, `help.tsx`)**: isolated reviewer
  accounts (Reviewer ID + access key) on the `review__*` collections; path in the app: **Login → Help → App review access →
  Open reviewer sign-in → Reviewer ID + Access key → SIGN IN AS REVIEWER** (gold STORE-REVIEW ENVIRONMENT banner). No OTP,
  no owner phone, no production bypass. Roles: `store-review-customer`, `store-review-admin`, `store-review-telecaller`,
  `store-review-billing`.
- **Production credentials: NOT PROVISIONED** (`STORE_REVIEW_ACCESS.md` "Preview vs production"). Owner provisions them in
  the production app (Panel → Store review → PROVISION, one real owner OTP) after the new build is deployed, then pastes
  the generated "TEXT FOR THE STORE REVIEW FORMS" + the customer (and, if desired, admin) Reviewer ID / key into App
  Store Connect. **Keys never go into this repository or any public document.**
- Preview reviewer accounts in this workspace: all four REVOKED (`/api/health` `flows.review.accounts_enabled=0`).
- Notes for the reviewer (draft, ≤4000 chars): "Sign in with the Reviewer ID and access key above via Login → Help → App
  review access → Open reviewer sign-in. The reviewer environment holds synthetic customers, products, rates and
  enquiries; SMS one-time codes are simulated and shown on screen for the reviewer account only. Real customers sign in
  with an SMS code sent to their registered Indian/international mobile number."

## 4. Permissions and purposes (VERIFIED from the generated native projects, 20 Sep 2026)

iOS (`Info.plist` of the prebuilt project): **no** `NSCameraUsageDescription`, `NSPhotoLibraryUsageDescription`,
`NSLocationWhenInUseUsageDescription`, `NSContactsUsageDescription`, `NSUserTrackingUsageDescription` or
`UIBackgroundModes` — the app requests none of those capabilities. Entitlement `aps-environment` present
(push; value `development` in prebuild, switched to `production` by the distribution signing step).

| Capability | Trigger in the app | Purpose shown to the user | Code |
| --- | --- | --- | --- |
| User notifications (OS prompt) | **First open of the app (Android + iOS, owner decision 21 Sep 2026): a branded explanation card ("Stay updated — Allow notifications to get enquiry updates and offers", Continue / Not now) is shown once per install before sign-in, then the OS dialog.** A denial or "Not now" is never re-asked at launch; afterwards only the bell → Notifications screen offers *Turn on notifications* (tap → OS dialog while the OS still asks, → app Settings once it refuses). No prompt on web/simulators or when the OS already decided | operational enquiry updates for staff; offers for customers who keep *Offers & new collections* on (separate marketing preference, default on, opt-out in-app) | `src/components/FirstOpenNotificationPrompt.tsx`, `src/push.ts` (`firstOpenPromptDue`, `requestPermission`), `app/notifications.tsx`, `src/components/NotificationBell.tsx`, `shared/notifications.py` preferences |
| Files (document picker, no permission) | staff PDF/photo upload only | catalogue content management | `pdf-import.tsx`, `catalog-author.tsx`, `product-photos.tsx` |
| Network | always | HTTPS to the Yash backend only | `src/api.ts` |

Android (`AndroidManifest.xml` after merge): `INTERNET`, `VIBRATE`, `POST_NOTIFICATIONS` + `RECEIVE_BOOT_COMPLETED`
(expo-notifications library manifest), `READ_EXTERNAL_STORAGE`/`WRITE_EXTERNAL_STORAGE` (legacy, maxSdk-limited by
Expo; no runtime storage permission is requested), `SYSTEM_ALERT_WINDOW` (Expo dev-client/template default —
**recommend blocking via `android.blockedPermissions` before the store build**; not user-facing). **No** `READ_SMS` /
`RECEIVE_SMS` (OTP autofill uses `autoComplete="one-time-code"`/`textContentType` only, R07).

## 5. App Privacy (Apple nutrition labels) — derived from the shipped backend, not copied

Same evidence base as `GOOGLE_PLAY_DATA_SAFETY.md` §1–§3, re-classified into Apple's types. "Linked" = tied to the
account (all account data is keyed by the canonical user id). "Tracking" per Apple's definition (cross-company
advertising/data-broker linkage) = **No** for every type: no ad SDK, no IDFA, no third-party analytics.

| Apple data type | Collected | Linked to user | Tracking | Purposes | What / where |
| --- | --- | --- | --- | --- | --- |
| Contact Info → Name | Yes | Yes | No | App Functionality | `users.name`; enquiry snapshots |
| Contact Info → Phone Number | Yes | Yes | No | App Functionality | login identifier; sent to MSG91 for the OTP; `sms_log` 90-day TTL |
| Contact Info → Physical Address | Yes (shop location/city as typed) | Yes | No | App Functionality | `users.location/city` |
| Contact Info → Email | No | — | — | — | no field |
| Identifiers → User ID | Yes | Yes | No | App Functionality | server UUID / `customer_code` in JWT claims and records |
| Identifiers → Device ID | **Yes — push token only** | Yes | No | App Functionality | `push_devices.token` (Expo push token, per account+device; unlinked on logout/deletion, disabled on provider `DeviceNotRegistered`) — new since R09; **not** IDFA/IDFV |
| User Content → Photos or Videos | Yes (staff roles only) | Yes | No | App Functionality | product photos/PDF pages uploaded by staff |
| User Content → Other User Content | Yes | Yes | No | App Functionality | enquiry notes, telecaller notes, AI-assistant messages (after explicit consent; deleted on withdrawal) |
| Usage Data → Product Interaction | Yes | Yes | No | App Functionality, **Personalization** | cart, wishlist, enquiries, reward transactions; **product viewing impressions** (`product_impressions`: which catalogue items were actually on screen, per account — new in R03, used only to order the Home feed unseen-first; deleted with the account) |
| Usage Data → Advertising Data / Other Usage | No | — | — | — | no analytics SDK |
| Diagnostics (crash/performance) | No | — | — | — | no crash SDK; server request logs carry masked phone suffixes only |
| Financial Info, Health, Location (device), Contacts, Browsing/Search history, Sensitive Info | No | — | — | — | no purchases, no device location, no contacts access, searches are not stored |

Third parties that receive data (all as service providers, none for tracking): MSG91 (OTP SMS), Expo Push Service
(push token + notification title/body/image URL; **no customer personal data in payloads** — `data` carries only
destination/campaign/request ids), Emergent LLM gateway → Anthropic (AI messages after consent), Emergent object
storage (staff media). Update the published Privacy Policy with the two NEW items before submission: **push tokens**
and **product viewing history used for feed ordering** (`WEBSITE_PRIVACY_UPDATE.md` needs a matching block — OWNER/website).

## 6. Screenshots and previews

| Item | Requirement | Status |
| --- | --- | --- |
| iPhone 6.9" (1320×2868) and 6.5"/6.7" screenshots, 3–10 each | **Captured from a native iOS build / Xcode simulator** | **BLOCKED — no macOS/Xcode/simulator in this container. The PNGs in `store_assets/screenshots/` are Expo-WEB captures framed at 1080×1920 (disclosed in their README) and are NOT acceptable as iOS screenshots.** |
| iPad 13" (2064×2752) screenshots (required because `supportsTablet: true`) | native iPad simulator | BLOCKED (same reason) — alternatively set `supportsTablet: false` before the build if the owner does not want iPad distribution (owner decision) |
| App preview video | optional | not planned |
| Suggested screens to capture natively (same order as the Play set): Home (silver collection), Feed gold filter, Product detail + zoom, Wishlist, Enquiry form, My Requests | reuse the synthetic "Sample Customer" preparation script method described in `memory/PRD.md` (15 Sep) on the reviewer environment | plan only |

How the owner can get native screenshots: build with Emergent **Publish** (iOS), install the TestFlight/simulator build,
sign in as `store-review-customer`, capture on iPhone 15 Pro Max/16 Pro Max and iPad Pro 13" simulators. No screenshot
may show real customer names/phones.

## 7. Build and upload

| Step | Owner / tool | Status |
| --- | --- | --- |
| Save to GitHub (creates the source commit of this work) | owner (Emergent UI) | HEAD `1f7413d` (22 Sep 2026) contains the corrected `frontend/yarn.lock` (committed by the build support in `c59cf80`/`1f7413d`); the 21 Sep concern about snapshot commits omitting the lockfile is closed. The agent still makes no Git commits (owner rule) |
| Republish backend (`shared-v2-operations-2026-09-20` must appear in `/api/health` `build`) | owner (Publish) | NOT DONE |
| Deployment Secrets: `EXPO_PUSH_ACCESS_TOKEN` (Expo access token for the push API; without it `/api/health` `flows.push_notifications` reports the provider as unauthenticated-mode), `STAFF_SERVICE_KEY`, `BUILD_COMMIT`, frontend `EXPO_PUBLIC_BACKEND_URL` | owner | NOT DONE / unknown |
| iOS push credentials (APNs key uploaded to the Expo project used by Publish) | owner | BLOCKED (credential) — required for ANY remote push on iOS, image or not |
| Android push credentials (FCM v1 service account in the Expo project) | owner | BLOCKED (credential) |
| Native binaries (iOS .ipa / Android .aab) | owner: Emergent Publish → store builds; the R02 (gesture zoom), R06 (keyboard controller), R09 (expo-notifications) changes are **native** — installed binaries do not pick them up from a web publish | **iOS build `3dd71227` (22 Sep 08:07 UTC) FAILED** at archive — "No profiles for `…NotificationServiceExtension` were found": the service-extension target added by `expo-rich-notifications` needs its own provisioning profile and the pipeline signs the main app only. **Fixed in source 22 Sep 08:23–08:27 (`828c63d`, `1f7413d`: plugin + dependency + `plugins/withNSEDevelopmentTeam.js` removed); scratch prebuild 12:58 UTC shows a single target.** Next iOS build must be started from this source; no rebuild recorded yet |
| Notification Service Extension in the iOS build | previously generated by `expo-rich-notifications` during prebuild (scratch prebuild 20 Sep) | **REMOVED 22 Sep 2026** to unblock the iOS build. Consequence: iOS notifications show title/body only (no image attachment); Android keeps images via `richContent`. Re-adding needs the iOS pipeline to provision the extension target (App ID `com.emergent.yashtryontest.lt5e6b.NotificationServiceExtension` + profile) — an Emergent support/engineering task, not a code change |
| **Push transport vs. the Emergent build flow (decision needed)** | owner + agent | The backend currently sends through the **Expo Push Service** (`exp.host/--/api/v2/push/send`, Expo push tokens from `getExpoPushTokenAsync`, `EXPO_PUSH_ACCESS_TOKEN`). The Emergent build flow instead routes the `.p8` APNs key / Firebase service account into **Emergent's managed push relay** (`integrations.emergentagent.com`, `EMERGENT_PUSH_KEY` injected at deploy; native device tokens via `getDevicePushTokenAsync`; `POST /api/v1/push/users/register`, `POST /api/v1/push/trigger`, ≤ 100 recipients per call, `image_url`/`action_url`, `$idempotency_key`). With the Emergent-built binaries the Expo route has no credentials, so **pushes would not arrive**. Recommended: switch the transport layer of `shared/notifications.py` + `src/push.ts` to the managed relay while keeping the durable outbox (frozen audience, pre-send re-validation, inbox rows, idempotent batches). Known relay limits to accept: no receipt/ticket API (invalid-token cleanup becomes relay-side), no documented device-unlink call (logout stops alerts through our pre-send re-validation, not by unregistering the token) |
| TestFlight internal test on a real iPhone: sign-in, OTP autofill, keyboard avoidance, pinch zoom, push (text + image), back navigation | owner + one approved test recipient | BLOCKED (device) |

## 8. Genuine missing submission items (consolidated)

0. **24 Sep 2026 rejection (§3.0)**: build a new iOS binary from this source (guest preview + wording fixes), scrub Google Play / Android mentions from the App Store Connect listing text and screenshots, resubmit with the reply drafted in §3.0.
1. Support URL (no value exists anywhere) — **OWNER TO PROVIDE**.
2. Confirm brand name on the listing (`Yash Silver` vs `Yash Trade App`) and the legal copyright holder.
3. Publish the updated Privacy Policy (incl. push tokens + viewing history) at the URL configured in `EXPO_PUBLIC_PRIVACY_URL`; optionally set `EXPO_PUBLIC_TERMS_URL`.
4. Confirm the public account-deletion web URL.
5. Provision production reviewer accounts (Panel → Store review) AFTER the new build is deployed; paste credentials into App Store Connect only.
6. Native iOS/iPad screenshots from a simulator/device (blocked here).
7. Push credentials in the **Emergent build flows** (not in an Expo project): iOS — App Capabilities step with the `.p8` APNs key + Key ID + Team ID (do not Skip: it also enables the push capability the `aps-environment` entitlement needs); Android — `service-account.json` in the build flow **and** `google-services.json` in the source (`android.googleServicesFile`, Firebase Android app with package `com.emergent.yashtryontest.lt5e6b`) — the latter is still missing. `EXPO_PUSH_ACCESS_TOKEN` is only relevant if the Expo route is kept (see §7 decision).
8. Decide `supportsTablet` (keep → iPad screenshots mandatory).
9. Age-rating questionnaire answered from §2 facts; App Privacy labels entered from §5.
10. Optional hardening before the store build: `android.blockedPermissions: ["android.permission.SYSTEM_ALERT_WINDOW"]`.

Everything above that is marked OWNER/BLOCKED needs an external account, credential, device or decision; it is not a
code gap. Final test counts are in §0 (21 Sep 2026). Commit hashes are not recorded by the agent: the source commit is
created by the owner's Save to GitHub and must be pinned by the owner (`BUILD_COMMIT` Secret) after that step.
