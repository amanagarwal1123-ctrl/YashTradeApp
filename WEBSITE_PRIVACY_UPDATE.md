# WEBSITE_PRIVACY_UPDATE — exact replacement wording for the Yash Ornaments privacy policy (14 September 2026)

For the website team. Apply to the privacy policy page that the app opens (`EXPO_PUBLIC_PRIVACY_URL`, today
`https://yash-register.emergent.host/privacy`; canonical domain `register.yashsilver.com`). Every block below is **replacement text**:
delete the old paragraph on the same subject and paste the new one verbatim. Bracketed `[OWNER: …]` items must be filled by the
owner before publishing; do not publish a placeholder. Nothing here requires a new website API, a new database or a website
reviewer-login feature (see §6).

Why this update is needed (all confirmed against the app source on 14 Sep 2026):
* The old text promised that names or phone numbers are *never* sent to the AI provider. Untrue as written — users can type them into a message, and what they type is transferred as written. Profile fields are not attached automatically; that is the correct claim.
* The old text said account deletion is "completed within 30 days" while the app reported deletions as "pending provider erasure" indefinitely. The app has been corrected (only the website's acknowledgement is awaited; SMS/AI-provider copies are disclosed as *not erased*), and the policy must say the same.
* Staff uploads (photos, PDF catalogues) and their storage provider were not mentioned.
* Store-review accounts were not described.

---

## 1. Replace the "Automated assistant" / "AI" paragraph with:

> **AI business assistant (optional).** The app contains an optional AI assistant for trade questions (selling tips, silver care,
> stock suggestions). It is switched off until you tap **Allow and continue** on the consent card shown inside the assistant.
> When you use it, the following is transferred to **Anthropic PBC** (Claude model, United States) through the **Emergent LLM gateway**
> (integrations.emergentagent.com), which relays the request to Anthropic on our behalf:
>
> * the exact text of each message you type or quick prompt you tap — **including any name, phone number, address or other detail
>   you choose to write in it**;
> * the earlier messages and replies of the same conversation (up to the last ten stored), so the assistant has context;
> * our fixed instruction describing the assistant's role and your chosen reply language (English, Hindi or Punjabi);
> * our gateway credential, which identifies Yash Ornaments as the sender — not you.
>
> Your profile fields (name, phone number, shop name, city), your account ID, enquiries, orders, cart, wishlist and reward balance
> are **not attached automatically** to these requests, and no photo or file is ever sent — the assistant is text only. Only what
> you write yourself is transferred, so please do not type personal details into the assistant that you do not want the provider to receive.
>
> **Purpose and legal basis:** generating the assistant's reply, on the basis of your explicit consent (consent version shown on the card;
> if the disclosure changes you are asked again before anything further is sent).
>
> **Retention:** we keep the conversation in the app until you withdraw consent or delete your account; then our copy is deleted.
> The gateway and Anthropic process the request under their own terms. We have no per-user deletion request that we can send to
> them, so we do not claim that their copies are erased and we do not state a retention period for them.

## 2. Replace the "Withdrawing consent" paragraph with:

> **Withdrawing AI consent and deleting your AI chat history.** Open **Profile → AI Data Sharing** in the app and tap
> **Withdraw and delete AI chat history**. From that moment no further text is sent to the AI provider, and every AI message,
> reply and content report stored for your account is deleted immediately from our systems — including a reply that was still being
> generated at the time of withdrawal, which is discarded rather than saved. Every other part of the app keeps working. You can allow
> the assistant again at any time. Withdrawal does **not** erase copies already processed by the gateway or the AI provider (see §1).

## 3. Add a new section "Photos and documents uploaded by staff":

> **Photos and documents uploaded by staff.** Customers cannot upload photos or files in the app. Authorised Yash Ornaments staff
> (administrators, billing executives) upload product photographs, promotional banners and PDF catalogues from their device to build
> the catalogue you see. These files are business content and are stored with our storage service provider, **Emergent Managed Object
> Storage**, and served to signed-in users through our servers. The provider does not offer a per-file deletion function: when a file is
> withdrawn from the catalogue we revoke access to it and mark it deleted in our records, but we cannot guarantee that the stored bytes
> are erased until the files are migrated to a storage service that supports deletion. If a catalogue document ever contains personal
> data about you, contact us and we will revoke access to it.

## 4. Replace the whole "Account deletion" / "Retention" section with:

> **Deleting your account.** In the app: **Profile → Delete My Account**, confirmed with a one-time code sent to your registered
> number. On this website: the *Delete account* page, confirmed the same way. Store-review sample accounts follow the same steps with a
> simulated code.
>
> **What happens immediately.** All your sessions are signed out and your login stops working. We delete your name, phone number, shop
> name and location, your cart and wishlist, reward points and reward history, telecaller notes about you, your AI chat history and AI
> consent record, content reports, any usage records, and the one-time-code and SMS-delivery records for your number. Your enquiries are
> anonymised: the type, status, dates and assigned staff member remain as anonymous business statistics, but your name, phone number,
> shop, notes and item details are blanked. You receive a deletion reference (`DEL-…`).
>
> **What we keep, and why.** (1) A keyed hash of your phone number with the deletion time, so that a retried enrolment or a stale
> sign-in cannot silently recreate your account; (2) the deletion reference and its timestamps as proof that your request was honoured;
> (3) the anonymised enquiry statistics described above. None of these contain your name or phone number in readable form.
>
> **This website.** The app sends this website an erasure event for your account. We remove the enrolment record, drafts, cached
> profile data and sessions held here and acknowledge the event **within 30 days of your request**; the deletion is then recorded as
> complete. The 30-day period applies to our own systems only.
>
> **Service providers — not erased by your request.** Our SMS provider (**MSG91**) keeps its own delivery records of the one-time codes
> sent to your number, and, if you used the AI assistant, the AI provider and its gateway (§1) keep whatever they retain under their own
> terms. We have no per-user deletion request that we can send to these providers and therefore do not claim that their copies are
> erased or state a retention period for them. Operational server logs contain only the last four digits of a phone number and are kept
> for **[OWNER: confirm the log-retention period of the hosting platform]**; database backups age out after
> **[OWNER: confirm the backup-retention period of the hosting platform]** and are not edited individually.
>
> **Retention while your account is active.** Profile, enquiries, cart, wishlist, rewards and AI history: for as long as your account
> exists (AI history: until you withdraw consent). One-time codes and sign-in grants: 10 minutes. SMS-delivery diagnostics for your
> number: 90 days. Rate-limiting counters: 10 minutes, keyed hash only.

Remove wherever it still appears: *"Deletion is completed within 30 days"* as a global statement, and any sentence saying that
provider copies are deleted, that data is "erased from all systems", or that names/phone numbers are "never sent" to the AI provider.

## 5. Add to the "Staff" or "Who uses this app" section:

> **Staff accounts.** Yash Ornaments staff (administrators, telecallers, billing executives) sign in with their phone number and a
> one-time code. Their name, phone number and the actions they take in the app (assignments, notes, uploads) are kept as the business's
> staff record and are not covered by the customer self-service deletion above; a staff account is deactivated by the owner and its
> record removed on written request to Yash Ornaments.

## 6. Add a short "Store review accounts" paragraph (informational; no website work is required):

> **Store review accounts.** App-store review teams may sign in to the app with a Reviewer ID and access key issued privately by
> Yash Ornaments (app: Login → Help → App review access). These accounts see only clearly labelled sample data; SMS and calls are
> simulated. Their records are kept in separate `review__`-prefixed collections inside the app's main database, isolated by the server
> from live customer data. No separate review database exists and this website neither stores nor authenticates reviewer accounts.

**Website team note (not for the policy page):** reviewer storage moved from a separate review database to `review__*` prefixed
collections in the same MongoDB database (`DB_NAME`), application-enforced by the signature-verified session scope. Consequences for you:
nothing. There is **no** `REVIEW_DB_NAME` setting to add, no reviewer-login endpoint to proxy, and no reviewer-auth API to build. Your
existing obligations are unchanged: enrolment (`POST /api/integrations/enrollments`), deletion by grant, and consuming the deletion outbox
(`GET /api/integrations/deletions` → `POST …/{event_id}/ack`). One contract detail changed on 14 Sep: `required_acknowledgements` on
`account_erased` events is now `["website"]` only — your acknowledgement completes the deletion (`all_acknowledged: true`).

## 7. Service-provider list (append or reconcile with your existing list)

| Provider | Data | Purpose | Location |
|---|---|---|---|
| MSG91 | phone number, one-time code, template ID | SMS one-time codes | India |
| Emergent LLM gateway → Anthropic PBC | AI-assistant message text, conversation context, fixed instruction, our credential | AI assistant replies (consent-based) | United States |
| Emergent Managed Object Storage | staff-uploaded photos, banners, PDF catalogues and derived images | Catalogue storage | [OWNER: region as stated by Emergent] |
| Emergent (hosting) | all server-side data, operational logs, database backups | Hosting of the app backend and this website | [OWNER: region as stated by Emergent] |

No data is sold. No advertising, analytics or crash-reporting SDK is embedded in the app.
