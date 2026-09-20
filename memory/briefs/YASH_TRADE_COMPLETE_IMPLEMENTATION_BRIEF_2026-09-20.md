# Yash Trade App: Complete Implementation and Release Brief

Date: 20 September 2026
Scope: Existing Android app, iOS app, canonical app backend, and corresponding website workflows.
Purpose: One consolidated instruction for the existing implementation chat. This is a specification and verification gate, not a statement that the work is already complete.

## 1. Decisions Already Made

Proceed with implementation, verification, and release preparation in the existing project. Do not stop to repeat the three approval questions from the previous summary.

- Approve the proposed sanity checks, full tests, independent testing-agent pass, store submission document, PRD, and release-readiness work. Implement the new requirements below BEFORE the final full regression pass and store-readiness sign-off.
- Reuse the existing Play listing as the iOS copy baseline, adapting the text to actual released functionality and Apple's current field limits. Do not invent features, credentials, URLs, or screenshots.
- Preserve and finish the earlier staff-phone, international-number, image-loading, caching, thumbnail-backfill, and website-contract work. These new requests extend that work; they do not replace it.
- Make reasonable implementation decisions using the existing architecture. Record material assumptions. Ask only for genuinely missing access, external credentials, approval for a consequential production action, or an ambiguity that cannot be resolved safely.
- Finish all feasible items in this run. A missing external credential must not stop unrelated implementation and tests. Do not quietly downgrade a requirement or label an unverified feature complete.

## 2. Establish the Actual Baseline First

Read repository instructions, the current working tree, package manifests, existing tests, memory/PRD.md, RELEASE_READINESS.md, WEBSITE_HANDOFF.md, YASH_SHARED_API_CONTRACT.md, and the production handoff documents. Preserve uncommitted work and user changes. Do not reset, fork into an unrelated project, or rebuild the app from scratch.

A read-only source inspection on 20 September found app GitHub commit `0530ebd5753eb75c9b3f489aefe60013c368f178`. It includes the earlier performance changes. The statement that nothing has been committed may therefore be outdated; compare this against your actual working tree. Do not overwrite newer work with this snapshot.

Source observations to investigate, not a claim of runtime verification:

- `frontend/app/image-viewer.tsx` uses ScrollView maximumZoomScale/minimumZoomScale/pinchGestureEnabled. React Native documents these zoom settings as iOS-only; this is insufficient for Android pinch zoom.
- `frontend/app/(tabs)/calculator.tsx` declares InputField inside CalculatorScreen. Its component identity changes when the screen rerenders, which can remount the field and lose keyboard focus.
- `frontend/src/context/AuthContext.tsx` removes saved access state on any initial /auth/me failure. A temporary network/server problem must not be treated as a confirmed logout.
- `backend/shared/auth.py` still has a 60-second resend cooldown and 30-day refresh/session expiry behavior. Inspect the complete flow before changing it.
- `backend/shared/commerce.py` declares MCX as INR/g and calculated physical rates currently add MCX and premium directly. Changing MCX labels alone risks incorrect prices.
- `backend/shared/core.py` and frontend login guards enumerate existing roles without Upload Executive. Adding a role to a broad STAFF set may unintentionally grant access through every generic staff endpoint; audit those endpoints individually.
- `backend/shared/queries.py` already has claims, version checks, status/history, and metrics. Extend this implementation instead of creating a parallel request system.
- `frontend/app/telecaller.tsx` also contains customer-lead statuses, notes, follow-up dates/times, and call/WhatsApp activity logging. Preserve useful existing records and report how these features will be presented.
- The staff DELETE route currently delegates to disabling. Do not present this as actual account deletion.

Record the starting app and website commits and the pre-existing modified/new files. Remove a stray root package-lock.json only after verifying it is an accidental artifact and that this project is genuinely Yarn-only; do not remove valid lockfiles belonging to another workspace.

## 3. Architectural and Safety Boundaries

- The app backend remains the single authority for identity, phones, roles, permissions, account status, requests, rates, notifications, and catalog state. The website consumes the same contracts. Do not create independent website identities or role overrides.
- Keep the existing application identifiers, production data, signing configuration, and deployment environments. Do not leak credentials into code, logs, reports, screenshots, or documentation.
- Protect the existing owner account and last usable administrator. Do not test phone changes, deletion, disabling, demotion, SMS, or push against the real owner or real customers.
- Use isolated fixtures/test accounts and provider mocks for automated tests. Never send a bulk campaign as a test. Any real-device notification/SMS test must use an explicitly approved test recipient.
- Do not run destructive production migrations/backfills or publish to real store users as a side effect of testing. Supply dry runs, impact summaries, rollout/rollback instructions, and obtain any required production approval. Do not buy services or incur new build/provider charges without authorization.
- Use established libraries compatible with the project's installed Expo/React Native versions. Avoid an unrelated framework upgrade. Keep API changes backward compatible with already-installed app versions or provide a deliberate compatibility rollout.

## 4. Required Implementation

### R00. Finish the Previous Iteration Without Regressions

Complete and verify admin staff-phone preview/commit, customer-to-staff promotion confirmation, international phone parsing, thumbnail-first expo-image, deduplicated bounded data caching, pull-to-refresh, HTTP cache policies, and the dry-run thumbnail backfill.

- An unused phone can replace a staff login number while retaining the same canonical staff ID/history. A phone belonging to a customer must show the explicit promotion flow for that existing customer, preserving that customer's identity/history. Never silently merge two people or move one person's history to another.
- Clearly state the outcome before confirmation, including what happens to the original staff account. Existing staff-number conflicts and owner protection must have accurate messages. Disabling an account does not automatically free its phone number unless that is an explicit, implemented identity policy.
- Recheck concurrent same-idempotency-key replay, crash/partial-write recovery, old-session revocation, authorization, and stale preview responses. Bind a commit to the number and customer identity actually previewed.
- International entry must accept normal formatting and supported country prefixes without truncating pasted numbers, including Australian national leading-zero input. Call/WhatsApp links must use normalized international numbers, never a hardcoded +91 for every country.
- Public list images load real thumbnails first; detail/zoom loads appropriate high resolution. Scope private media access and disk caching correctly. Revoke access promptly when visibility or permissions change.
- Use long cache lifetimes only for appropriate versioned public assets. Keep user data separated by account, role, and environment. Logout/deletion/role changes must invalidate private caches, including late in-flight responses. Do not serve stale rates, permissions, query ownership, or completion status as authoritative.
- Measure cold/warm image and list performance under a stated device/network profile. A generic placeholder hiding a slow full-size download is not a thumbnail-first implementation.

### R01. Back Navigation and Durable Login

Fix the underlying authenticated navigation and session lifecycle on Android and iOS, with equivalent safe behavior on the website where applicable.

- After login, remove login/OTP screens from authenticated back history. Android system back on a role's root/home screen must stay on that screen, not logout, show login, or exit. On another screen, back returns to the previous authorized screen; a deep link with no history falls back to the role's home.
- Keyboard dismissal and modal dismissal should take precedence when relevant. Do not globally swallow back events on every screen. Remove listeners correctly when screens unmount.
- Persist login across app close/reopen, process death, device restart, ordinary app updates, navigation, and temporary offline/server failures. Implement secure, revocable device sessions and rotation of short-lived access tokens using securely stored refresh credentials. Do not solve this with an immortal access JWT or unencrypted password/token storage.
- Address fixed session-family expiry so normal active use does not unexpectedly logout after 30 days. Document any unavoidable idle/security expiry. Preserve recent-authentication requirements for sensitive admin actions; step-up authentication need not log the whole account out.
- Only explicit logout or a confirmed security/account event should clear the session: for example disabled/deleted account, administrator revocation, invalid refresh credentials, or an intentional security expiry. Network timeouts, 5xx, and ordinary authorization denials are not proof the entire session is invalid.
- Prevent refresh races and accidental token-family revocation from concurrent API calls. Preserve a safe retry/reconnect state when offline; do not grant privileged operations using a cached identity alone.
- Logout must clear credentials, private cached data, and that device's notification association so the next user cannot receive the prior user's alerts.

Verification: repeated hardware/gesture/header back; role-root/deep-link/modal flows; process restart; simulated time beyond access-token expiry and the old 30-day boundary; offline cold start and recovery; server 5xx; concurrent refresh; actual revoked/disabled/deleted session rejection; explicit logout and account switch.

### R02. Real Image Pinch Zoom

- Implement a proven, maintained zoom/pan solution compatible with this Expo version, using the existing gesture stack where suitable. Android must not rely on iOS-only ScrollView zoom props.
- All relevant product-photo entry points must reach the same reliable viewer: Home, Feed, product detail, wishlist/cart, query-item pictures, and applicable catalog/PDF preview photos.
- Support two-finger pinch around the focal point, bounded pan, reset/double-tap zoom where supported, image switching, close/back, orientation and viewport changes. Image switching resets the previous image's transform. Zoom gestures must not accidentally swipe products or trigger navigation.
- Keep a cached thumbnail visible while the high-resolution image loads. Reset the viewer correctly when the selected product or photo changes. Use authorized public product imagery or protected media loading as appropriate; do not expose private source files to customers.
- Equivalent web viewer behavior should work with supported touch/pointer controls without disabling normal browser accessibility zoom.

Verification: real/native Android and iOS pinch and pan, image navigation while zoomed, rotation, slow network, failed-image recovery, and web pointer/touch behavior. A browser screenshot or a test that merely checks for zoom props is not proof of native pinch zoom.

### R03. Refresh Home With Unseen Products First

- Every explicit Home refresh should prioritize existing eligible catalog products that this signed-in user has not seen, with a fresh shuffled order. Do not limit discovery to newly uploaded products or shuffle only the same first page.
- Track actual meaningful visibility, not merely downloaded/prefetched products. Define a reasonable viewability threshold/dwell rule and test it. Keep lightweight per-user discovery state; synchronize across devices when feasible using the canonical backend.
- Preserve metal/category/availability/permission filters. Within one refresh session, pagination must have stable ordering and no duplicate items. Refresh starts a new discovery session; late responses from the old session must not replace it.
- Show unseen products before previously seen products. Once unseen eligible products are exhausted, fill with a shuffled/least-recently-seen fallback; handle small/empty catalogs without infinite loading. New catalog additions must become discoverable.
- Use indexed, bounded queries/cursors or another measured scalable approach. Do not fetch the entire catalog to the phone, grow an unbounded request body of seen IDs, or independently randomize every page.
- Keep refresh responsive and use cached thumbnails. Offline refresh may use cached eligible items but must not claim a successful server refresh. Update privacy/data-safety documentation if viewing history is now collected or used for personalization.

Verification: multiple users with distinct history, actual visibility versus prefetch, repeated refresh until exhaustion, small/empty catalog, multiple pages without duplicates, changing filters, new/deleted products, concurrent refreshes, logout isolation, and a large representative catalog.

### R04. Calculator Keyboard Stays Open

- Fix remounting/focus loss at its cause, including the nested InputField component. Keep component identities and multi-item row keys stable.
- Weight, rate, making, discount, GST, and multi-item numeric fields must accept continuous typing without closing the keyboard on every digit. Preserve cursor position and incomplete decimal input while typing; do not reformat every keystroke.
- Keep the keyboard open until an explicit Done/Enter, field navigation, or deliberate dismissal. Supply an accessible Done action where the native decimal keyboard has no Enter key, particularly on iOS.
- Preserve calculations, input values, editing in the middle of a number, deletion, item addition/removal, and single/multi-item modes.

Verification: type and edit 123.45 without refocusing in every numeric field, including rows after adding/deleting other items; verify focus, keyboard visibility, and the resulting calculations on both native platforms.

### R05. Correct MCX Units and Calculations

- Display and edit silver MCX as INR per kg, and gold MCX as INR per 10 g, consistently in app, website, admin inputs, API documentation, and any shared views.
- Trace actual existing stored values and consumers before changing the contract. Retain a canonical internal basis with explicit conversion, or introduce versioned unit-aware fields. Do not silently reinterpret old INR/g numbers as INR/kg or INR/10g.
- Any calculated physical rate/premium must use matching units. If physical rate remains INR/g, normalize silver MCX by 1000 and gold MCX by 10 before combining with an INR/g premium. Do not change unrelated labour, wastage, purity, dollar/troy-ounce, or calculator-input units accidentally.
- Provide deterministic unit tests with fixture values, not live-market claims: silver MCX 100000 INR/kg is 100 INR/g; gold MCX 75000 INR/10g is 7500 INR/g. Verify round trips, premiums, movement comparisons, and decimal precision.
- If stored historical numbers are ambiguous, produce a dry-run report and explicit resolution requirement instead of guessing. Maintain backward compatibility for older app clients during backend rollout.

Verification: both metals, read/edit/save/reload from both surfaces, physical calculation, existing fixtures/history, and old-client compatibility. A label-only change fails this requirement.

### R06. Keyboard Avoidance Throughout the App

- Inventory all input screens, not just login. Cover signup/profile, OTP, calculator, search, query notes/status/follow-up, staff-phone/admin forms, Contents/PDF edits, rates, notifications, customer management, and modal/bottom-sheet forms.
- Apply a reusable platform-appropriate keyboard-aware layout using the existing UI conventions. Account for safe areas, header/tab height, Android window-resize behavior, scrolling, and iOS keyboard insets without double-applying offsets.
- The focused field, current typed text, relevant label/error, and next/submit action must be visible or readily scrollable above the keyboard. Do not use brittle fixed screen heights or conceal the whole form behind the keyboard.
- Preserve focus and scroll position across validation/rerenders. Support small phones, landscape where allowed, larger text, numeric and multiline keyboards, and mobile-web viewport resizing.

Verification: native screenshots/recordings with the keyboard OPEN for every input-screen family and each critical modal; include the lowest field on a small Android and iPhone viewport. Checking an empty page with keyboard closed is insufficient.

### R07. Four-Digit OTP Autofill and Paste

- Selecting an OS OTP suggestion containing all four digits must populate all four boxes. Support paste into any box, manual entry, replacement, delete/backspace, focus movement, invalid characters, resend, and retry.
- Prefer a single logical OTP input rendered as four boxes, or implement robust full-string distribution without native maxLength=1 truncating autofill before it reaches the handler.
- Use supported iOS one-time-code and Android SMS OTP/autofill metadata for the installed framework version. Follow documented SMS templates/app hash or domain binding only where required by the chosen supported mechanism.
- Do not request broad READ_SMS/RECEIVE_SMS permissions merely for OTP suggestions. Do not log OTPs or weaken server verification. Submit at most once per completed code and prevent duplicate requests from autofill events.
- Explain that the OS/provider controls whether a suggestion is offered; the app must correctly accept it whenever offered and retain manual entry as a reliable fallback.

Verification: native suggestion acceptance with an approved test flow, component tests for a complete four-digit text-change event, paste into every position, backspace, leading zero, incorrect code, expired code, and resend followed by fresh-code entry.

### R08. Fifteen-Second OTP Resend Cooldown

- Change the normal resend cooldown to 15 seconds on the authoritative backend and all app/website OTP flows, including login, signup, number changes, and relevant step-up challenges.
- Return server-derived resend timing and drive the countdown from it. Handle background/resume and clock skew; do not merely change a frontend label while the server still enforces 60 seconds.
- Keep OTP expiry separate from resend cooldown. Preserve attempt limits, per-phone/IP/device abuse protection, provider limits, and throttling. A 15-second cooldown does not authorize unlimited SMS.
- Use atomic issuance/rate-limiting to prevent parallel taps bypassing the cooldown. Respect stricter provider/abuse throttles and display their actual retry timing instead of falsely promising resend availability.

Verification: fake-clock boundary tests just before/at 15 seconds, concurrent resend attempts, all challenge purposes, app resume, website parity, old/new-code validity rules, provider failures, and retained abuse-limit enforcement. No real-customer SMS load tests.

### R09. Dedicated Custom Notifications Page and Real Push

- Add a dedicated admin-only Notifications page in the app and the corresponding website admin area. Include title, body, optional image upload/selection, safe destination/deep link, preview, explicit audience selection, audience count, test-send, draft, send confirmation, and sent/failed history.
- Support all eligible app users, all eligible customers, selected customers, and useful customer filters backed by actual data: for example city/location, customer type, assigned telecaller, or existing lead head. Do not fabricate filter fields. Show AND/OR semantics clearly and let admins inspect the audience before sending.
- Filtering/permissions and the final recipient resolution belong on the server. Snapshot recipients or otherwise prevent a material audience change between confirmation and sending. Exclude disabled/deleted users, invalid tokens, and opted-out marketing recipients. Count users and devices distinctly.
- Prompt for OS notification permission at an appropriate onboarding moment, before attempting delivery; installation alone cannot force a permission dialog. Explain the purpose briefly, handle already granted/denied/restricted states, and provide Settings access without repeatedly nagging. Refusing notifications must not block app use.
- Separate promotional consent/preferences from operational query notifications and from the OS permission. Provide marketing opt-out where applicable; do not use transactional permission as blanket marketing consent.
- Implement authenticated token registration/rotation, device/account association, unlinking on logout and deletion, Android channels, APNs/FCM/Expo credentials, foreground handling, background/terminated notification taps, and role-authorized deep links. Never put provider server secrets in the client.
- Send real remote push, not only an in-app banner, a local notification, a database row, or a mocked provider success. Use an asynchronous reliable job/outbox with bounded batches, idempotency, retries, receipt/error handling, and invalid-token cleanup. Avoid duplicate sends on retry/double tap.
- Include image notifications on Android AND iOS. With Expo Push Service, Android supports richContent.image; iOS also requires a correctly configured native Notification Service Extension and mutable-content handling. Include extension signing/config plugin/build integration, image size/time limits, safe HTTPS media, and a text-only fallback on attachment failure.
- Lock-screen content must avoid unnecessary customer personal data. Do not publicly expose customer documents just to attach a notification image. Display provider acceptance, delivery evidence, and opens honestly; provider acceptance is not proof the user saw a notification.
- Provide an in-app notification history/read state so users can revisit a message when push is delayed/denied. This is a complement to real push, not a substitute.

Verification: admin-only API/UI authorization, filter inclusion/exclusion and counts, draft/preview/send, repeated-send idempotency, invalid token, retry, opt-out, disabled account, logout/account switch, cold-start deep links, and image notifications on approved Android AND iOS test devices in foreground/background/terminated states. Record credential/build/device blockers separately; a web preview cannot verify native remote push.

### R10. Upload Executive Role

- Add the canonical role `upload_executive`, displayed as Upload Executive, to backend validation, account creation/conversion, staff editing, authentication, route guards, role menus, and website integration.
- This role can upload the PDFs containing product photos/weights and perform the complete existing Contents workflow that an admin can perform: inspect the actual Contents page and enumerate every control, endpoint, source/PDF operation, preview, correction, publish/unpublish, reorder, and deletion action that belongs to content management. Implement and test each applicable action rather than giving only upload access.
- Retain validation, progress, retry/failure states, media budgets, audit logs, and confirmation for destructive content actions. Use the existing upload/import pipeline, not a separate catalog.
- Grant necessary source-media access within the content domain, but no general admin privileges. Do not grant user/role management, customer private data, billing/rewards, marketing sends, or query assignment merely because the role is staff. Explicitly audit every generic c.staff/STAFF and frontend staff-only condition for over-broad access.
- Keep admin/telecaller/billing/customer behavior intact. Role changes must refresh/invalidate sessions and cached permissions. A hidden button is not authorization; direct API and deep-link access must be enforced.

Verification: a real isolated Upload Executive can sign in and complete every enumerated Contents/PDF action in app and website. Negative tests must deny unrelated admin/customer-data endpoints. Include disabled Upload Executive and role-change tests.

### R11. One Central Query Workspace and Complete Telecaller Journey

- Make Requests the telecaller's primary work page. One central list contains ALL unfinished customer queries, across request types and creation dates. Consolidate duplicate Requests/Customer Requests screens into this shared source of truth; redirect old routes safely rather than breaking existing links.
- Show customer/shop, request type, useful item preview, current workflow head, current assignee, creation/freshness time, and clear claimed/unclaimed state. Provide All Pending and My Pending filters, search, request-type/head filters, and a separate My Completed view within the same workspace.
- New/fresh queries appear first. Paginate/load more without an implicit last-day/month/year window or a hidden first-100-record cutoff. Search/filter must work against the full authorized history. Do not fetch the whole history at once just to claim it is unlimited.
- Detail shows customer name, shop name, canonical callable/WhatsApp phone, request text/type, all requested item IDs/names/weights and pictures where available, notes/status timeline, and relevant cart/multiple-item information. Preserve historical request references even when a product is later unpublished/deleted; use a safe historical snapshot or an explicit unavailable-image state, not a crash or data leak.
- Preserve the existing named heads where useful: New, Contacted, Interested, Follow-up, Converted, Not Interested, and Unreachable are present in the customer-leads screen. Distinguish CUSTOMER lead state from QUERY lifecycle. Changing a lead head or query disposition must not silently complete every query for that customer.
- A telecaller can claim, record notes/actions, set the appropriate head/follow-up, revisit the request, and explicitly Mark Complete. Pending requests in any non-completed head remain in the central list until completed or an explicit authorized terminal action. Keep follow-up notes/dates through reassignment/reset, with an accurate history.
- Inventory other existing telecaller capabilities, including customer-lead search/status filters, summary counts, call/WhatsApp activity logs, notes, and follow-up scheduling. Keep useful non-duplicate capabilities accessible, for example customer history from request detail or a secondary customer directory. Explain the resulting navigation and any deliberately retired duplicate screen in the final report.

Verification: start as a customer, create each supported request type, observe it as two telecallers, claim, inspect all details, call/chat handoff, change head/add note/follow-up, return later, and complete. Include old requests, multiple requests from one customer, multiple requested items, missing product imagery, deep links, and empty/error/offline states.

### R12. Query Notifications and Atomic First-Claim Locking

- Every successfully created relevant customer query triggers one operational notification event for eligible active telecallers who have allowed notifications. Wire every request creation path, including cart submission and legacy paths; not just one endpoint.
- A notification tap opens the query. Merely receiving or viewing a notification must not steal ownership. The first successful explicit Take Query action claims it; tapping a claim-required work action may present/perform the same atomic claim before opening external call/chat activity.
- Claiming must be atomic in the canonical database, safe across multiple server workers. For simultaneous claims, exactly one succeeds and the other sees the winner/current state. UI-only locking or a process-local mutex is insufficient.
- Only the current claimant may make telecaller work/status/completion mutations. Other telecallers can see who is working on it, but cannot edit, claim over, or use this app's work actions to bypass the assignment. Admin override requires explicit action, reason, and audit. A public phone number cannot be made impossible to dial outside the app; do not claim such a guarantee.
- Publish fresh ownership/status to all clients via an appropriate authorized subscription or efficient polling fallback. Invalidate the affected cache immediately. A delayed push or old screen must revalidate ownership before mutation.
- Recover from failed sends without losing the query. Use durable events/outbox/idempotency rather than relying on a best-effort in-request push call.

Verification: concurrent claims from two telecallers, duplicate taps, retries, multiple backend workers where feasible, disconnected/reconnected clients, stale notifications, unauthorized updates/completion, admin reassignment, push-provider failure, and idempotent query creation without duplicate notifications.

### R13. Completion, Reporting, and Daily 03:00 IST Release

- Mark Complete removes the request from the shared pending list and puts it in that telecaller's completed history. Preserve the completing actor, completed time, request/customer/item context, and audit events. Completion must be atomic and idempotent.
- Admin can inspect each telecaller's completed count and records for a selected day and custom date range. Use Asia/Kolkata calendar boundaries and document inclusivity. Keep completed history accessible without a date-retention cutoff; filters narrow the view, not erase history.
- Keep an immutable completion event history so retries, reassignment, reset, and reopen cannot silently corrupt counts. Count distinct completed requests per completing telecaller in a reporting interval, with explicit reopen/correction semantics and no duplicate count for a retried completion.
- At 03:00 every day in Asia/Kolkata, release ALL still-unfinished requests from any telecaller, reset them to Fresh/New, and move them to the top of the central queue. This includes Contacted, Interested, Follow-up, Unreachable, and any other nonterminal head. No old-request cutoff. No exemption just because the query is currently claimed.
- Preserve original created_at, prior heads, follow-up details, assignees, and notes in history. Set explicit fresh_at/queue_sort_at and reset-cycle metadata; do not falsify the original creation time. Use a deterministic tie-breaker for a reset batch so pagination is stable.
- New queries created after the 03:00 boundary sort ahead normally. Define the boundary using server time, not phone time. Completed records are not reset. Preserve historical truly cancelled terminal records separately; do not count cancellation as completion or silently reopen historical cancelled requests.
- Implement a real deployed server scheduler/worker, not a function that is only tested manually or a timer that depends on a phone being open. Use a durable daily cycle marker/lease, idempotent retry, bounded batches/indexes, observability, and catch-up after downtime.
- Protect races among reset, claim, completion, and admin reassignment using versions/atomic predicates or another proven transactional approach. A stale reset worker must not erase a completion or a post-boundary claim. A query released at 03:00 may be claimed again immediately; an old claimant's stale write must fail.
- Preserve newly created post-boundary requests during catch-up. Test restart midway through a reset and multiple scheduler workers without duplicate history or repeated releases. Supply the real deployment/startup configuration and evidence that the scheduled job is registered/running.

Verification: fake-clock tests at 02:59:59/03:00:00/03:00:01 IST, dates/month/year boundaries, old pending heads, completed/cancelled exclusion, twice-run same cycle, partial-batch crash/restart, multi-worker execution, downtime catch-up, post-boundary claims, and claim/complete/reset races. Verify admin report counts and audit preservation after every scenario.

### R14. Admin and Billing Use the Same Central Requests

- Update admin and billing views to the same canonical central query workspace, filters, full-history pagination, product/customer details, assignment visibility, live freshness, and completed-history model. Do not leave a legacy conflicting request page active.
- Admin can see all queues/completions, filter by telecaller/date/head/type, inspect reports, and explicitly assign/reassign/reopen with appropriate audit and confirmation.
- Billing sees the same accurate central state and the request details needed for billing, plus its existing authorized billing/rates actions. Retain least-privilege defaults: viewing the central queue does not automatically allow billing users to take over telecaller work, alter admin reports, or manage users. Document and test the role-action matrix.
- Customer-facing request status remains consistent without exposing internal staff notes, private reporting, or unnecessary staff personal information.

Verification: same request observed across customer, two telecallers, billing, and admin before claim, during work, after 03:00 reset, and after completion. Compare API/UI counts, filters, permissions, deep links, and stale-cache behavior on both app and website.

### R15. Admin Disable and Delete Users

- Diagnose and fix the full admin UI-to-API flow for applicable customer and staff accounts on app and website. Return actionable errors instead of silent failures. Preserve owner/last-admin safety and handle self-disable/delete safely.
- Disable and delete must be separate, accurately labeled operations. Disabling is reversible and immediately blocks further authentication/privileged access; reenabling is explicit. Delete must use the actual deletion/anonymization workflow and must not be a disguised disable button.
- Require a clear target confirmation and appropriate recent admin authentication/reason for sensitive changes. Enforce server-side permissions, current state/version, protected-account rules, and concurrency safety.
- Immediately revoke sessions/refresh families, detach push tokens, prevent stale privileged caches/API access, and release or explicitly resolve pending request assignments of disabled/deleted staff. Preserve attribution needed for completion reports without leaving unnecessary personal data exposed.
- Extend existing account-erasure/provider-outbox handling rather than bypassing it. Preserve only legitimately required audit/transaction records using the existing retention policy; scrub personal data where required. Do not promise external-provider erasure is complete while acknowledgements are pending.
- Define deleted-phone reuse/re-registration behavior explicitly and retain the existing anti-silent-reenrolment policy unless a deliberate migration is justified. Make retries idempotent and recoverable after partial failures. Do not cascade-delete business requests or orders just to remove a user.

Verification: isolated customer/telecaller/billing/upload accounts, admin exceptions, last-admin concurrency, current and expired tokens, websocket/push access, repeated deletion, provider-erasure pending state, failed partial deletion/retry, assigned queries, history/report integrity, and website/app parity. Never exercise destructive tests on the real owner or customers.

### R16. Website Integration Is Part of Delivery

- If this execution environment has authorized access to the website repository/project, implement and test its corresponding screens and contract consumers during this same run: staff-phone edit/promotion, international phones/call links, session/error behavior, 15-second OTP timing, MCX units, Upload Executive/Contents rights, central queries/claim/complete/reset/reporting, notifications admin page, and user disable/delete.
- Native-specific keyboard/OTP/zoom/push handling belongs in the native apps; implement relevant responsive/browser behavior on the website, without pretending a web deployment updates already-installed native binaries.
- Update shared contracts with fields, units, roles, authorization, pagination/ordering, errors, idempotency, reset semantics, notification preferences, and examples. Keep the BFF thin and do not duplicate business state.
- Check old website consumers and currently released apps before deploying backend changes. Include additive compatibility and deployment order where needed.
- If website project access is unavailable, do all app/backend work and produce WEBSITE_HANDOFF.md with exact required changes, API examples, tests, and an apply-ready patch only if the actual website source is available. Explicitly mark WEBSITE IMPLEMENTATION/DEPLOYMENT BLOCKED. Updating a handoff file alone is not website completion. Do not invent files or claim the website is fixed without changing and testing it.

### R17. Store Preparation and Release Documentation

- Create/update APP_STORE_SUBMISSION.md after implementation settles. Include verified name/subtitle/keywords/description/category/copyright, support/privacy/account-deletion URLs, reviewer access, required permissions and purposes, build identifiers, screenshots, and any genuine missing submission items.
- Start from existing Play wording and adapt to current iOS limits. Preserve the existing app record/bundle/package IDs. Do not put development/test functionality or unimplemented marketing claims into the listing.
- Re-audit App Privacy and Google Data Safety against the actual shipped backend, SDKs, push tokens, device identifiers, impressions/discovery history, uploaded content, analytics, marketing audience filters, retention, and deletion. Determine linked-to-user, purposes, and tracking individually. Do not copy App Functionality/Linked/No Tracking to every field without evidence.
- Verify age-rating answers against actual released content/features. Do not assume the earlier 4+ selection proves the new release is correctly classified, and do not confuse content age rating with marketing consent or account terms.
- Reviewer access must not depend on reaching the owner's phone for a live OTP. Use the existing legitimate isolated review-account mechanism without adding a production authentication bypass. Keep secrets out of public documents.
- Capture required iOS screenshots from a native iOS build/simulator and Android assets from the actual Android experience. Existing Expo-web PNGs are not proof of native appearance or acceptable substitutes for platform-specific screenshots. Do not fabricate device evidence.
- Update memory/PRD.md, RELEASE_READINESS.md, WEBSITE_HANDOFF.md, YASH_SHARED_API_CONTRACT.md, and migration/operations documentation with the actual outcome.
- Prepare the final Android/iOS binaries and website/backend deployment only using authorized accounts, tooling, credentials, and build resources. If unavailable, report exactly what is prepared and blocked. Native library/extension changes require a new compatible binary; a website publish alone cannot deliver them.
- Keep Code Complete, Tests Passed, Native Verified, Website Deployed, Build Uploaded, Submitted for Review, and Store Live as separate states. Do not submit/release production or claim approval without the required authorization and actual platform result.

## 5. Required Execution Order

1. Reconcile actual code/dirty state and create the requirement matrix below before editing. Inspect existing workflows, DB records/schemas without altering production, and dependencies. Record the old telecaller feature inventory and permission matrix.
2. Implement shared identity/session/role/unit/query/notification contracts, backward compatibility, indexes and idempotent migrations. Use isolated fixtures. Address data integrity and concurrency early.
3. Implement app and available website workflows together. Fix navigation, keyboard/autofill/zoom, discovery, content-role access, notifications, query workspace, and account management. Preserve prior performance gains.
4. Run focused tests while building. Then run the complete backend pytest suite, frontend Jest, TypeScript, ESLint, and relevant website suite. Restart services and smoke-test the actual changed preview.
5. Run a separate testing_agent or equivalent independent test pass against the acceptance requirements, not merely your implementation summary. Give it the requirement IDs and the previous/new bug scenarios. Fix findings and rerun affected and shared regressions.
6. Perform native Android/iOS verification for platform-only behaviors and approved real-device push/autofill tests. Browser/Expo Go results cannot be relabeled as native evidence. Where native access is unavailable, finish code and automated tests but leave the native gate unverified.
7. Run the release/security/data-privacy audit, review migrations and deployment order, generate the store/readiness/handoff artifacts, and record the final diff/commits.
8. Save finished changes to the existing connected repositories using the authorized workflow. No force push, unrelated commits, or removal of user work. Report final app/backend and website commit hashes and deployment/build identities. If save/push is unavailable, explicitly list the uncommitted files and export a patch instead of claiming GitHub is current.

## 6. Mandatory Evidence Matrix

Create IMPLEMENTATION_ACCEPTANCE_MATRIX.md and maintain it throughout the work. Each row must link to changed files/commit, test names or commands, evidence, and a precise remaining blocker. Split composite requirements into subrows so one completed subfeature cannot conceal another missing one.

Use only these per-surface states: NOT STARTED, IN PROGRESS, IMPLEMENTED - NOT VERIFIED, VERIFIED, BLOCKED, or NOT APPLICABLE WITH REASON. Never mark VERIFIED from code inspection alone for a runtime requirement. Record app Android, app iOS, backend, and website separately where relevant. A web pass does not imply an Android/iOS pass.

Minimum rows:

| ID | Acceptance evidence required |
| --- | --- |
| R00-A | Staff phone change, customer promotion, permissions, same-key concurrent replay, partial-failure recovery, stale preview protection |
| R00-B | International formatting/paste and call/WhatsApp links; actual provider delivery distinguished from mocks |
| R00-C | Thumbnail-first loading, bounded/private-safe caching, invalidation, dry-run backfill, cold/warm measurements |
| R01-A | Home back stays put; other screens/modal/deep links navigate correctly without returning to login |
| R01-B | Durable session, offline/5xx recovery, refresh races, logout and security revocation |
| R02 | Native Android/iOS pinch/pan/image switching and corresponding web behavior |
| R03 | Unseen-first refresh, real viewability, stable full-catalog pagination, exhaustion and account isolation |
| R04 | Calculator continuous decimal typing and Done behavior without remount/focus loss |
| R05 | Silver INR/kg and gold INR/10g, conversions/premiums, round trips and old-client compatibility |
| R06 | Keyboard-open evidence for every input-screen family and critical modal on both native platforms |
| R07 | Four-box OTP suggestion/paste/manual/backspace and single submission |
| R08 | Server-driven 15-second timing across all purposes and clients, with concurrency/abuse safeguards |
| R09-A | Dedicated notification composer, image, filters, audience count/confirmation, admin permissions |
| R09-B | Permission/preferences, token lifecycle, account isolation, deep links, notification history |
| R09-C | Real Android image push; real iOS image push with service extension; evidence distinguished from mocks |
| R09-D | Durable sending, receipt handling, retry/idempotency, invalid-token cleanup, no unauthorized audience |
| R10-A | Upload Executive sign-in and every existing Contents/PDF capability explicitly inventoried and tested |
| R10-B | Negative authorization across all generic staff routes and unrelated admin/customer-data features |
| R11-A | One central pending workspace, all-time pagination, filters, complete customer/item detail |
| R11-B | Heads/notes/follow-ups preserved, full create-to-complete journey, old feature inventory |
| R12-A | Query notifications wired to every creation path, durable event/retry behavior |
| R12-B | Two simultaneous telecaller claims, one winner, ownership-enforced mutations and live updates |
| R13-A | Completed list, immutable attribution/history, IST daily/custom reporting without retry inflation |
| R13-B | 03:00 IST release/reset/sort with no old-request cutoff and original history retained |
| R13-C | Deployed scheduler, downtime/partial-run recovery, multi-worker idempotency and completion/claim races |
| R14 | Same accurate queue/report/detail state for admin/billing with enforced role permissions |
| R15-A | Actual disable/reenable and distinct actual delete for applicable roles; clear UI errors |
| R15-B | Sessions/tokens/assignments/erasure cleanup, protected owner/last-admin, retry and history integrity |
| R16-A | Actual website code changes and compatibility tests, or explicit unavailable-access blocker |
| R16-B | Shared API contract/handoff, deploy order and actual website deployment status |
| R17-A | Accurate store metadata/privacy/data-safety/reviewer-access documentation |
| R17-B | Authentic native screenshots and verified native build IDs, or explicit native tooling blocker |
| R17-C | All docs, final tests, commits, migrations/rollback and release-state report |

For every test run record command, environment, timestamp, pass/fail/skip counts, and relevant log/artifact path. Do not hide a flaky failure by reporting only its successful rerun: state the first failure, diagnosis, rerun, and residual risk. Do not delete/skip tests, loosen assertions, or turn off lint/type checks solely to obtain a green summary.

Use deterministic fixtures and fake clocks for edge cases. Concurrency/database semantics need the real supported database behavior in an isolated environment, not only mocks that cannot reproduce atomic conflicts. Native keyboard, gesture, OTP, and push claims require native runtime evidence. Automated tests and device recordings serve different purposes; supply both where needed.

## 7. Final Response Required From the Implementing Chat

Return a concise user-facing summary and links to the full artifacts containing:

1. Every requirement ID with its real status, not only the completed highlights. Put blocked/unverified/not-done items first. State whether the app, website, native binaries, and store submission are ready separately.
2. The exact new telecaller journey, final head/lifecycle rules, first-claim behavior, 03:00 IST reset behavior, completed-report semantics, and the list of other pre-existing telecaller features retained or reorganized.
3. Changed files, final app and website commit hashes, migration/index work, actual test counts/results, independent testing findings, native evidence, and performance measurements with methodology.
4. Proof of the deployed reset worker and notification delivery path, or explicit missing infrastructure/credentials/device tests. No silent fallbacks disguised as completion.
5. Website work actually executed versus handoff-only work. List precise deploy/rebuild/store steps still requiring an external account or approval, collected in one final checklist rather than scattered repeated prompts.
6. Platform limitations and justified deviations. In particular, do not describe a WhatsApp chat link as a direct video-call API, a permanently revocable login as impossible-to-revoke, or a push accepted by a provider as certainly delivered to the user.

Do not finish with a generic 'implemented everything, please test' statement while requirements lack evidence. Finish all controllable work; report unavoidable limitations honestly rather than inventing successful results.

## 8. Platform Notes and Official References

These references were checked on 20 September 2026. Recheck SDK compatibility and current official documentation while implementing; do not blindly apply latest-version APIs to Expo SDK 54.

- React Native lists ScrollView zoom-scale and pinch properties as iOS-only. Use a genuine cross-platform gesture solution for Android. Reference: [React Native ScrollView](https://reactnative.dev/docs/scrollview#maximumzoomscale).
- Expo remote notifications need native configuration/build support; Expo Go is not sufficient for Android remote push in SDK 54. Reference: [Expo SDK 54 notifications](https://docs.expo.dev/versions/v54.0.0/sdk/notifications/).
- Expo documents richContent.image for Android/iOS, with an additional Notification Service Extension needed on iOS. Reference: [Expo push message format](https://docs.expo.dev/push-notifications/sending-notifications/).
- WhatsApp officially documents wa.me links for opening a chat using the full international number. This is not a direct video-call command. Reference: [WhatsApp click to chat](https://faq.whatsapp.com/5913398998672934).
- Meta describes its WhatsApp Calling API as voice calling. A direct arbitrary-number video-call API was not verified in this research. Reference: [Meta WhatsApp Calling API](https://developers.meta.com/resources/videos/whatsapp-calling-api/).

For the requested video-call workflow, research supported official capabilities for this account/platform. If direct video initiation is not available, implement a clearly labeled Open WhatsApp action to the right customer chat, where the telecaller can use WhatsApp's video-call control. Preserve the query's Video Call type. Document the limitation and do not fabricate a wa.me video parameter, unsupported URI, successful video-call log, or fake API. Mark direct video initiation as platform-limited, not fully implemented, while completing the usable handoff and all other work.

Remember that OS permission denial, device power restrictions, missing push credentials/signing, unavailable native test hardware, external project access, provider account limitations, and store review are real external constraints. They must be reported precisely; they are not a reason to omit feasible code, tests, or documentation elsewhere.
