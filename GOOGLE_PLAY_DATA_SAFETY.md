# Google Play Data safety — answers derived from the shipped code (14 September 2026)

Source of truth for every answer below: the current source tree (`frontend/` Expo SDK 54 app, `backend/` FastAPI service,
build `shared-v1-store-submission-2026-09-13` + the 14 Sep changes in this document). Nothing here is copied from an earlier
form or from a policy text; each row names the code path it was read from. Where a fact cannot be established from the code
(operator retention of backups/logs, provider-side retention) it is marked **OWNER TO CONFIRM** or **NOT STATED** — it is not guessed.

Google's definitions used throughout:
* **Collected** = user data transmitted off the device to the developer's server (or to a third party). Data that only ever
  stays on the device (language preference in AsyncStorage, the session token in SecureStore) is *not* collected.
* **Shared** = user data transferred to a third party **other than** (a) a *service provider* processing it on the developer's
  behalf under instructions, (b) a transfer required by law, or (c) a user-initiated transfer after a prominent in-app
  disclosure and consent. Transfers to service providers are declared as *collected*, not *shared*.
* **Ephemeral** processing (memory only, for the duration of the request) does not need to be declared.

## 1. Third parties and SDKs that actually receive data

| Recipient | What reaches it | Triggered by | Role under Google's definition | Code |
|---|---|---|---|---|
| **Yash Trade backend** (FastAPI + MongoDB, HTTPS) | Everything listed in §3 | Every API call | Developer (first party) | `backend/server.py`, `backend/shared/*` |
| **MSG91** (SMS OTP provider, India) | Phone number + one-time code + fixed template ID | Sign-in / deletion / phone-change / owner-console OTP | Service provider | `server.py::_dispatch_sms_otp` |
| **Emergent LLM gateway → Anthropic (Claude `claude-sonnet-4-5-20250929`, United States)** | The typed message / quick prompt **as written**, up to the last 10 stored turns of that conversation, a fixed system instruction (assistant role + reply language), the business's gateway credential. **No** phone, name, account ID or session identifier is attached; `LlmChat.session_id` stays local and is never transmitted | Only after the user grants the current AI consent version; every call is gated | Service provider processing on the developer's behalf **and** user-initiated after prominent disclosure + consent (both exemptions apply) → declared as *collected*, not *shared* | `server.py::ai_chat`, `shared/ai_consent.py`, `emergentintegrations.llm.chat.LlmChat._execute_completion` (params: model, messages, api_key, api_base, optional `X-App-ID` header = app server URL when `APP_URL` is set) |
| **Emergent Managed Object Storage** | Staff-uploaded product photos, banners, PDF catalogues and the derived page/crop images | Staff upload screens only | Service provider (storage) | `server.py` `put_object`, `shared/pdf_jobs.py`, `shared/media_lifecycle.py` |
| **Yahoo Finance / exchange-rate API** | Nothing about the user (server-side metal-rate fetch) | Background task | Not user data | `server.py` live-rates task |
| **Enrolment website (register.yashsilver.com)** | Same canonical customer record; receives `account_erased` events | Enrolment on the website; deletion outbox | Same controller (Yash Ornaments) — first party | `shared/auth.py::enroll`, `shared/people.py::deletion_outbox` |

**SDKs in the APK that could collect data by themselves: none.** `frontend/package.json` contains no analytics, advertising,
crash-reporting or attribution SDK (no Firebase, Sentry, Facebook, AdMob, Amplitude, Segment, Branch). `expo-document-picker`
opens the system file picker (no storage permission); there is no camera, location, contacts, microphone or notification
permission in `app.json`; `react-native-webview` is not used to load remote pages. The customer-facing
`POST /api/analytics/event` endpoint exists but **no screen calls it** (grep of `frontend/app`, `frontend/src`): the app
does not emit behavioural analytics events. Admin dashboards aggregate business records (requests/users) instead.

## 2. Overview answers for the Play form

| Question | Answer | Basis |
|---|---|---|
| Does your app collect or share any of the required user data types? | **Yes** | §3 |
| Is all of the user data collected by your app encrypted in transit? | **Yes** | Backend and every provider endpoint are HTTPS only (`EXPO_PUBLIC_BACKEND_URL` / `extra.backendUrl` are `https://`); no cleartext traffic is configured |
| Do you provide a way for users to request that their data is deleted? | **Yes** | In-app: Profile → *Delete My Account* (OTP-confirmed; `POST /api/auth/delete-account/{request,confirm}`). Website: the `/delete-account` page of the enrolment site calls `DELETE /api/integrations/customers/{phone}` after its own OTP. **OWNER TO CONFIRM the public URL** of that page for the "Delete account URL" field (expected `https://register.yashsilver.com/delete-account`) |
| Account creation | **Yes — accounts are created on the enrolment website, then used in the app** (phone + SMS OTP). Store reviewers use the separate Reviewer-ID + Access-key sign-in reachable from Login → Help → App review access | `shared/auth.py`, `shared/review.py`, `frontend/app/help.tsx` |
| Has your app been independently validated against a global security standard (MASA)? | **No** | No such review has been performed — do not tick |
| Is the app designed for children / Families programme? | **No** — private B2B app for verified jewellers | `login.tsx` footer text |
| Privacy policy URL | The URL the app itself opens: `EXPO_PUBLIC_PRIVACY_URL` (`frontend/.env`, currently `https://yash-register.emergent.host/privacy`). **OWNER TO CONFIRM** this is the published canonical policy (or set it to `https://register.yashsilver.com/privacy` in both the app `.env`/Secrets and the form) and that the text has been updated with `WEBSITE_PRIVACY_UPDATE.md` **before** submission | `frontend/app/(tabs)/profile.tsx`, `help.tsx`, `delete-account.tsx` |

## 3. Data types — what to tick

Legend: C = customer flow, S = staff flow (admin / telecaller / billing executive), R = required (user cannot opt out and still use the feature), O = optional.
"Purpose" values are Google's fixed list. **Shared = No** everywhere because the only third parties are service providers (§1).

| Google category → type | Collected? | Shared? | Who | R/O | Purposes | What exactly, where it lives, code |
|---|---|---|---|---|---|---|
| **Personal info → Name** | Yes | No | C, S | R | App functionality, Account management | Customer name from website enrolment and Profile → Edit; staff name entered by the admin. `users.name`; snapshotted on enquiries (`requests.user_name`, `customer_snapshot`) and staff actions (`events[].actor_name`). `shared/auth.py::Profile`, `server.py::update_profile`, `shared/people.py` |
| **Personal info → Address** | Yes | No | C | R | App functionality, Account management | Shop location/city typed at enrolment (`users.location`, `users.city`, `requests.user_city`). Free text, not derived from the device — so it is *Address*, not *Approximate location* |
| **Personal info → Phone number** | Yes | No | C, S | R | App functionality, Account management, Fraud prevention/security | Sole login identifier; sent to MSG91 for the OTP; `users.phone`/`phone_normalized`, `sms_log.phone` (90-day TTL, 14 Sep), `otp_challenges`/`auth_grants` (10-min TTL), enquiry snapshots |
| **Personal info → User IDs** | Yes | No | C, S | R | App functionality, Account management | Server-generated canonical account ID (UUID) and `customer_code`; carried in JWT claims and every personal record. Not a device ID |
| Personal info → Email, Race/ethnicity, Political/religious beliefs, Sexual orientation, Other | **No** | — | — | — | — | No such fields exist in `users` or any request model |
| **Financial info** (payment info, purchase history, credit score, other) | **No** | — | — | — | — | No payments, prices paid or transactions are recorded. Cart submissions become *enquiries* (`requests.request_type = cart_selection`, product titles + quantities + notes) — declared under *App interactions / Other user-generated content* below, not as purchase history |
| **Health and fitness** | No | — | — | — | — | — |
| **Messages → Other in-app messages** | **Yes** | **No** (service-provider transfer + explicit consent, see §1) | C (and any staff who opens the assistant) | O | App functionality | AI-assistant messages and replies (`ai_chat_history`) and AI content reports (`ai_reports`); transferred to Anthropic via the Emergent gateway only after consent (`shared/ai_consent.py`, `server.py::ai_chat`). Deleted on consent withdrawal or account deletion |
| Messages → Emails, SMS or MMS | No | — | — | — | — | The app never reads SMS; the OTP is typed by the user (`autoComplete="one-time-code"` only offers the OS autofill) |
| **Photos and videos → Photos** | **Yes** | No | **S only** | O | App functionality | Product photos and banners picked with `expo-document-picker` and uploaded by staff (`/products/upload-image`, `/banners/upload`, `catalog-author.tsx`, `product-photos.tsx`, `panel.tsx`) → Emergent object storage, metadata in `media_assets`/`products`. Customers have **no** upload feature |
| Photos and videos → Videos | No | — | — | — | — | No video picker or upload |
| **Files and docs** | **Yes** | No | **S only** | O | App functionality | PDF catalogues uploaded in chunks by staff (`pdf-import.tsx`, `src/pdfClient.ts` → `/api/pdf-upload/*`); pages rendered to images and cropped into products; stored in Emergent object storage (`pdf_jobs`, `import_jobs`, `batches`) |
| Audio, Calendar, Contacts | No | — | — | — | — | No permission, no picker |
| **App activity → App interactions** | Yes | No | C, S | R | App functionality, Analytics | Cart (`cart`), wishlist (`wishlists`), enquiries/call-back requests and their status history (`requests`), reward points and transactions (`reward_transactions`), staff assignment/resolution events, telecaller follow-ups (`telecaller_activity`). Aggregated for the admin dashboard (`/analytics/dashboard`) |
| **App activity → Other user-generated content** | Yes | No | C, S | O | App functionality | Free-text enquiry notes and preferred time (`requests.notes`, `preferred_time`, max 3000 chars), telecaller notes about a customer, catalogue titles/descriptions written by staff |
| App activity → In-app search history | No | — | — | — | — | Catalogue and customer searches are query parameters answered from the database and **not stored** (`GET /products?search=`, `GET /customers/search`) |
| App activity → Installed apps, Other actions | No | — | — | — | — | — |
| **Web browsing** | No | — | — | — | — | — |
| **App info and performance → Crash logs / Diagnostics / Other** | **No** | — | — | — | — | No crash or performance SDK. Backend logs record request outcomes with **masked** phone suffixes (`...{phone[-4:]}`) — server-side operational logging, not app-collected diagnostics |
| **Device or other IDs** | **No** | — | — | — | — | No advertising ID, Android ID, IMEI or installation ID is read (`expo-constants` installation ID is not used); nothing is sent in headers except the bearer token |

Not declared (ephemeral / abuse prevention): the caller's IP address is used for OTP and login rate limiting as a **keyed hash**
with a 10-minute TTL (`shared/auth.py`, `otp_limits`); it is never stored in clear in production scope and never linked to the profile.
(In the store-review copy only, `review__review_access_log` records the reviewer's IP for audit — synthetic accounts, no real users.)

## 4. Verification of account deletion and AI-consent withdrawal against §3

Verified by `backend/tests/shared/test_ai_consent_and_deletion.py` (3 tests, run 14 Sep) plus the live checks in
`test_reports/iteration_26.json` / `iteration_27.json`.

### 4.1 Account deletion (`shared/people.py::erase` → `cleanup_deletion`)
| Declared type | What happens on deletion | Result |
|---|---|---|
| Name, Address, Phone, User ID | `users` document **replaced** by a tombstone `{id, phone:"deleted:<id>", name:"Deleted customer", status:deleted, session_version+1}`; `session_version` bump → every bearer token answers `401 SESSION_REVOKED`; `session_families` revoked; `refresh_tokens` deleted; `otp_challenges`, `auth_grants`, `sms_log` rows for the number deleted | Personal identifiers removed |
| Other in-app messages | `ai_chat_history` (by `user_id` and legacy `session_id`), `ai_reports`, the `ai_consent` record and `ai_consent_events` (inside the replaced document) deleted | Removed |
| App interactions | `cart`, `wishlists`, `reward_transactions`, `telecaller_activity`, `analytics_events` (+ legacy `analytics`) deleted; `requests` **anonymized** (name/phone/city/shop/notes/admin notes/notes_history/customer_snapshot/cart_items/preferred_time/category blanked or unset; `events[]` stripped of `notes/old/new/actor_name`) | Removed or anonymized; only type, status, dates, assignee remain |
| Other user-generated content | Enquiry notes blanked (above); telecaller notes deleted | Removed |
| Photos / Files | Customers have none. `media_assets` owned by the account (defensive path) → `owner_id = deleted:<id>`, `access_revoked = true` | n/a for customers |

**Retained after deletion (app side), purpose, retention — all without name or phone in clear:**
| Record | Content | Purpose | Retention |
|---|---|---|---|
| `deleted_identities` | HMAC-keyed hash of the phone, canonical ID, deletion time | Stop a retried website enrolment or OTP request from silently re-creating the identity | Indefinite (it is the deletion record itself) |
| `deletion_requests` | reference `DEL-<id>`, canonical ID, source (app/website), timestamps, status | Proof that the request was honoured; support reference shown to the user | Indefinite (compliance record) |
| `requests` (anonymized) | type, status, dates, assignee, canonical ID, `anonymized:true` | Anonymous operational counts for the business | Indefinite |
| `integration_outbox` `account_erased` | canonical ID, timestamps, `required_acknowledgements:["website"]`, acknowledgement times | Tell the enrolment website to remove its copy | Until acknowledged; the acknowledged record (IDs only) is kept as audit |
| `users` tombstone | canonical ID, `deleted_at`, `session_version` | Reject any surviving token as revoked (401, never "inactive account") | Indefinite |
| `session_families` (revoked) | family ID, canonical ID, `expires_at` (30 days) | Replay detection until natural expiry | No TTL index — rows stay until a later cleanup; contain IDs only (**minor**, listed for completeness) |
| Backend application logs | Masked phone suffixes, event outcomes | Operations | Platform default — **OWNER TO CONFIRM** the Emergent log-retention period |
| Database backups | Whatever the platform snapshots | Disaster recovery | **OWNER TO CONFIRM** with Emergent (Manage Publishes → Database); until confirmed the policy must say backups age out on the provider's schedule rather than a fixed number of days |

**Discrepancies found on 14 Sep and resolved in code:**
1. `integration_outbox.required_acknowledgements` listed `sms_provider` and `ai_provider`, which have no acknowledgement path (the only outbox consumer credential is the website). Every deletion would therefore stay `pending` / `external_erasure_pending` forever — the root of the "completed within 30 days" vs "indefinitely pending" contradiction. Now only `["website"]` is required (`people.REQUIRED_ACKNOWLEDGEMENTS`, written with `$set`); a startup reconciliation (`people.reconcile_outbox_acknowledgements`, every usable scope) converges events written by older builds and completes those the website had already acknowledged; when the website acknowledges, `deletion_requests.status` becomes `completed` with `completed_at`. Provider copies are reported as `erasure: "not_requested"` in the erasure report, i.e. disclosed, not awaited.
2. `sms_log` (phone number + delivery status per OTP) had **no retention bound**. A TTL index on `expires_at` now removes rows after **90 days** (`shared.core.SMS_LOG_RETENTION_DAYS`); existing rows were back-filled from their send timestamp (also in the `review__sms_log` copy). Account deletion still removes the number's rows immediately.
3. The AI disclosure claimed a "pseudonymous session identifier" is sent and that name/phone are "never sent". The identifier is **not** transmitted at all, and typed text **can** contain names/phones. Disclosure, consent version (`2026-09-14`, existing consents are re-asked), erasure report and the delete-account screen were corrected.
4. The delete-account screen listed "SMS-provider and AI-provider erasure acknowledgements (pending until confirmed)" — an acknowledgement that could never arrive. It now states plainly that those copies are **not erased** by the request.

### 4.2 AI-consent withdrawal (`POST /api/ai/consent {granted:false}`)
Epoch is bumped first, then `ai_chat_history` and `ai_reports` for the account are deleted; a reply that was in flight during the
withdrawal is discarded and not stored (`server.py::ai_chat` re-checks the epoch). Further `/api/ai/chat` calls answer
`403 AI_CONSENT_REQUIRED`. The response says explicitly: `provider_copy: "not erased: …"`. **Matches the Play declaration**
(Other in-app messages, optional, deletable) and the consent card.

### 4.3 Staff accounts
Staff (admin/telecaller/billing) cannot self-delete in the app (`c.allow("customer")`); the owner administrator disables them
(`DELETE /api/integrations/staff/{ref}` → `status: inactive`, sessions revoked). Their name/phone remain as the business's
staff record while the account is inactive. **Play form implication:** the deletion mechanism you declare is the customer path;
state in the policy that staff records are removed on written request to the business (see `WEBSITE_PRIVACY_UPDATE.md` §5).

## 5. Provider limitations that still prevent full erasure (must be disclosed, cannot be coded around)

| Provider | Limitation | Consequence for the answers |
|---|---|---|
| Emergent Managed Object Storage | **No DELETE / rename / list API** (confirmed via the integration playbook). Deletion = access revocation + tombstone; bytes remain | Staff-uploaded photos/PDFs (business content, not customer personal data) cannot be byte-erased until the owner migrates to S3/R2/GCS. Do **not** state that uploaded files are deleted; say access is revoked |
| Anthropic via Emergent LLM gateway | No per-user deletion request; retention/training terms of the provider and the gateway are **NOT STATED** by the app and must not be invented | The policy says the copies are processed under the providers' own terms and are not erased by us |
| MSG91 | Delivery logs are the provider's; no per-user deletion request | Same wording as above |
| Platform logs / DB backups (Emergent) | Retention **OWNER TO CONFIRM** | Policy wording avoids a fixed number of days until confirmed |

## 6. Owner checklist before pressing "Submit"
1. Update the website privacy policy with `WEBSITE_PRIVACY_UPDATE.md` and make sure `EXPO_PUBLIC_PRIVACY_URL` (app `.env` + deployment Secret) points at it.
2. Confirm the public "Delete account" URL of the enrolment website for the form.
3. Confirm with Emergent (support) the log and backup retention period, then fill the `[OWNER: …]` placeholders in `WEBSITE_PRIVACY_UPDATE.md`.
4. Decide whether the Emergent/Anthropic terms qualify as *service-provider* processing for your business. If you cannot confirm it, tick **Shared: Yes** for *Messages → Other in-app messages* (purpose: App functionality) — everything else stays *No*.
5. Upload the 512×512 store listing icon (`Yash_App_Icon_Option_1_1024px_under_1MB.png`, the same artwork now used in `frontend/assets/images/icon.png`).
6. Enter the reviewer credentials from the private note (Login → Help → App review access) in *App access*.
