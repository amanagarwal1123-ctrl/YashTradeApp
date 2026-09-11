# Yash shared API contract — v1

Build label: `shared-v1-followup-2026-09-11`. Follow-up implementation is in this workspace, not a production rollout. Public main was rechecked before editing: baseline `30796997d3484594c6c5f53965e1c71dd5ed1c86` is verified in GitHub. It is NOT this follow-up's implementation commit. Follow-up remote sync requires the user-controlled Save to GitHub workflow; this workspace has no configured Git remote. See RELEASE_READINESS.md for provenance.
Production last inspected: `https://yash-tryon-test.emergent.host/api/health`, build `2026.09.09-integration-v7`.
All paths below include `/api`; HTTPS only outside local tests. Generated OpenAPI: `contracts/openapi.shared-v1.json` and ingress-accessible `/api/openapi.json` (default internal FastAPI `/openapi.json` is not an ingress routing guarantee).

## Authority, mappings and errors

Follow-up compatibility changes needing coordinated clients: products limit>100 now422; page1 is stable rather than random (explicit discovery available); new manual product creation requires product_code/type/category/title; imported/private media paths cannot use public /files; no-store replaces the old public300second image policy. Existing product PUT version and slab version requirements remain. Legacy field adapters preserve records; no production bulk migration. Capability flags add legacy_units/catalog_pagination/pdf_authoring/pdf_source_preview/media_accounting=1, managed_delete=0. Auth's pre-v1 token/grant breaking cutover remains separately gated.

App backend owns identity, permission, account state, products, rates and the request ledger. Website retains drafts, backend sessions, an outbox and cache only. No browser database or integration-key access.

- Canonical roles: `customer`, `admin`, `telecaller`, `billing_executive`. Legacy `executive` maps to `telecaller`. Unknown roles return `403 UNKNOWN_ROLE`, never customer fallback.
- Indian phone storage: 10 national digits, first digit 6–9. Boundaries accept `+91`/12-digit `91` formats and common separators; **enrollment requires exactly 10 digits**. Stable `id` survives phone change. Duplicate legacy identities return `409 IDENTITY_CONFLICT` pending approved reconciliation.
- Account state is separate from query/lead/onboarding. `disabled`/`inactive`/`blocked` account flags deny access; conflicting blocked flags win. `deleted` cannot be reactivated by enrollment.
- Error envelope: `{code: string, detail: string, fields?: string[]}`. Common codes: `USER_NOT_FOUND`, `AUTH_REQUIRED`, `SESSION_REVOKED`, `ACCOUNT_INACTIVE`, `PERMISSION_DENIED`, `VERSION_CONFLICT`, `CONFIGURATION_REQUIRED`, `VERIFICATION_REQUIRED`. Do not match English strings. Unsupported legacy direct PDF import returns `410 REVIEWED_IMPORT_REQUIRED`.
- Health includes build, non-secret `commit` (from `BUILD_COMMIT`, otherwise `unrecorded`), capabilities and presence booleans only. It does not prove SMS delivery, secret rotation, data reconciliation or review-account isolation.

## Authentication

### `POST /api/auth/send-otp`

Body `{phone, purpose?: "login"|"enrollment"|"deletion", channel?: "mobile"|"portal"}`.
Login requires an existing active identity. Enrollment permits new numbers but does not create a completed profile. `purpose=enrollment|deletion` requires server-only `X-Integration-Key`. Portal login requires `X-Staff-Service-Key`; enrollment credentials cannot obtain staff portal sessions.

Returns `{message, challenge_id, otp_length:4, expires_in:600, resend_after:60}` only after existing MSG91 **Flow** transport accepts dispatch. Delivery acceptance is not confirmed handset receipt. Required provider config is not replaced by fixed codes.

OTP security: four server-generated digits; purpose/subject-bound HMAC digest; persistent Mongo challenge; atomic single use; five challenge attempts; 60-second resend; phone send limit five/10 minutes; IP send30/10 minutes; phone verification20/10 minutes and IP verification100/10 minutes. Trust ingress configuration, not arbitrary client `X-Forwarded-For`. A website BFF should enforce additional per-browser/IP abuse controls so its shared server IP is not treated as every browser's identity.

### `POST /api/auth/verify-otp`

Same purpose/channel/phone plus `{otp, challenge_id}`. Always reuse canonical challenge: website must not send or verify a second SMS independently.

- Login -> `{token, expires_at, refresh_token, user}`. Access JWT15 minutes, signed issuer `yash-canonical`, audience `yash-clients`, subject stable ID, `sv` session version, `sid` family. Every protected request rechecks live user and family state. Old pre-v1 JWTs are rejected; reauthentication is required at cutover.
- Enrollment/deletion -> `{verification_grant, expires_in:300}`. Opaque single-use grant; no mobile login timestamps; not a staff token.
- Portal customer -> `403 STAFF_ONLY`; route to enrollment/download instructions, never staff portal.

`POST /auth/refresh` with `{refresh_token}` rotates once; reuse revokes the family. Families expire after30 days; refresh is bounded by family expiry. Refresh does **not** change login/activity timestamps.
`POST /auth/logout` revokes the current family. `GET /auth/me` returns current canonical user; load it before role routing. Mobile tokens use SecureStore. The app's browser preview stores auth in memory, not localStorage.

Website BFF must store canonical token/refresh/ID server-side with a random HttpOnly+Secure+SameSite cookie, session rotation, CSRF token/origin checks for mutations, and `/auth/me` revalidation/401 handling. Cookie/BFF implementation belongs to the website project and is **not implemented here**.

### User response fields

`id, phone, name, shop_name, location, city, role, code, customer_code, account_status, status, phone_verified, verified_at, onboarding_status, step1_complete, registration_source, registered_at, created_at, updated_at, profile_version, first_mobile_login_at, last_mobile_login_at, last_portal_login_at, last_login, has_logged_in`, plus applicable existing reward/lead fields. No OTP/session secrets in user JSON.
`has_logged_in` is derived from an actual recorded `first_mobile_login_at`, not enrollment verification or legacy generic `last_login`. Unknown legacy timestamps remain null; they are not fabricated. `city` preserves existing city; `location` is preferred place display, falling back to city. New profile city defaults to location only if no separate existing city exists.

## Enrollment, profiles and deletion

`POST /integrations/enrollments` with `X-Integration-Key`:
`{name,phone,shop_name,location,city?,verification_grant,idempotency_key,consent_version,consent_terms:true,consent_privacy:true}` -> `{created,customer,replayed?}`. Required strings cannot be blank. Public `verified:true`, role/status/timestamp fields are rejected. Retry identical consumed grant payload is replayable while retained; different payload fails. Same phone remains the same identity. Existing staff is never downgraded; it returns `409 STAFF_IDENTITY`.

`GET /integrations/customers/{phone}` -> `{customer}` (customer-only; scoped server key).
`PUT /auth/profile` -> canonical user; exactly name/shop/location and optional city. Reject role/status/phone/consent/timestamp ownership edits.
`POST /auth/phone-change/request` `{new_phone}` -> challenge; `POST /auth/phone-change/verify` `{new_phone,otp,challenge_id}` -> `{id,phone,reauthentication_required:true}`. Requires existing authenticated subject, uniqueness check and atomic existing-ID update; revokes all old sessions. No re-enrollment of a new identity.

Admin directory: `GET /customers?page=1&limit=20&search=&account_status=&login_state=&onboarding_status=&assigned_to=`. Limits1–100. Response `{customers,total,page,limit,pages}`; each row has `number`. `login_state=logged_in|never`; onboarding independent. `assigned_to=unassigned` matches missing/empty assignment. Added `registered_from,registered_to,login_from,login_to`: inclusive IST YYYY-MM-DD ranges (maximum366 days), filtering registered_at and last_mobile_login_at respectively. Unknown dates are not fabricated. The app now has date, named-assignee, account, login and onboarding controls. `GET /customers/{id}` adds latest100 queries/activity (explicit `detail_limit:100`; request queue pagination is the full history access). `PATCH /customers/{id}` permits profile, active/inactive account status and active telecaller assignment only. Staff editing uses staff APIs.

**Phone-change scope:** `/auth/phone-change/*` changes the authenticated subject only. There is NO admin-targeted customer phone-change endpoint. Customer PATCH rejects phone. Do not impersonate, exchange another user's token or re-enroll to work around this.

Deletion: authenticated customer `POST /auth/delete-account/request` then `/confirm` `{otp,challenge_id}`. Website uses deletion-purpose OTP then `DELETE /integrations/customers/{phone}` with **both** `X-Integration-Key` and `X-Verification-Grant`. Enrollment key alone cannot delete any phone.
Returns `{deleted:true,reference,status:"external_erasure_pending",detail}` meaning local revocation/anonymization, **not complete provider/website deletion**. Tombstones stop enrollment retry resurrection. Personal profile/cart/wishlist/local chat/reward/lead/customer notes are erased/anonymized; anonymous query operational events and restricted deletion references remain. Free-text request snapshots are cleared.
`GET /integrations/deletions` -> `{events:[{id,type,user_id,status,required_acknowledgements,...}]}` (max100 unacknowledged events). `POST /integrations/deletions/{event_id}/ack` acknowledges website cleanup. Website must remove cache/outbox retries/drafts/session data by canonical ID before acknowledgement. Provider erasure and historical unowned chat/cache auditing still require operational confirmation. Current provider acknowledgement workflow is not a completed privacy audit.

## Staff integration

All directory/mutation operations require canonical **admin bearer authentication**, not merely a service/enrollment key:

| Route | Body/result |
|---|---|
| `GET /integrations/staff?role=&status=` | `{users:[...]}`; complete staff directory |
| `POST /integrations/staff` | `{phone,name,role,code?,status?}` -> `{created,user}`; normalized-phone idempotency |
| `PATCH /integrations/staff/{id_or_phone}` | name/role/code/status only -> `{user}`; revokes sessions |
| `DELETE /integrations/staff/{id_or_phone}` | soft inactive -> `{user}`; history retained, sessions revoked |
| `POST /integrations/staff/{id_or_phone}/convert` | `{role,reason,confirm_user_id}` explicit existing customer conversion |
| `POST /integrations/staff/{id_or_phone}/token` | same-subject canonical staff bearer **plus** separate `X-Staff-Service-Key`; no SMS; `{token,expires_at,refresh_token,user}` |

Last usable admin cannot be disabled/demoted. Implicit customer promotion ->409 `EXPLICIT_CONVERSION_REQUIRED`. `issued_via` conveys no permission. Another-subject exchange ->403, expired/revoked sessions ->401. Separate service key never replaces admin authorization for privilege changes.
Staff user contains id/phone/name/role/code/status/last_login/created_at/updated_at and channel login fields. Legacy `/executives` adapters use same authority and canonical returned role.

## Unified requests and ledger

`GET /requests/catalog` -> types/statuses/aliases/open/terminal sets. Types: `video_call`, `ask_price`, `callback`, `similar_products`, `hold_item`, `quick_reorder`, `cart_selection`. Accepted input aliases: `price_enquiry|price_inquiry`→ask_price, `call`→callback, hold→hold_item, reorder→quick_reorder.

Statuses: `pending,in_progress,contacted,no_response,resolved,cancelled`. `completed|done`→resolved; `assigned`→in_progress. Open backlog=first four; terminal=resolved/cancelled. Lead `follow_up`→`follow_up_required` is separate.

`POST /requests` (customer) `{request_type,category?,preferred_time?,notes?,product_id?,product_ids?}`. Optional `Idempotency-Key` header ties payload to authenticated subject. Actor/customer identity is server-owned. Linked products must exist and be available. Existing cart submission appends the same creation ledger event.

`GET /requests/my?page=&limit=` own customer-safe envelope. `GET /requests` staff envelope **preserves existing `{requests,...}` shape** and adds total/page/limit/pages/open_counts_by_type/server_time. It is not an array response change. Limits1–100; no silent200 truncation. Billing defaults to open backlog, `sort=oldest`; all staff see unassigned and non-lead-assigned requests.

Filters: `search` (name/phone/shop/place), `request_type`, `status=all|open|canonical|legacy`, `view=all|mine|unassigned`, `assignee`, `resolver`, `created_from,created_to,resolved_from,resolved_to` (inclusive IST calendar dates YYYY-MM-DD), `min_age_minutes,max_age_minutes`, `sort=oldest|newest|longest_wait`. Stable tie-break=id. Legacy aliases assigned_to/handled_by/city remain accepted.
Period drilldown: `period_resolver,period_start,period_end` uses the same last qualifying resolution attribution as metrics, including requests subsequently reopened. Billing cannot read team metrics; telecaller only own period drilldown.

Request fields: id/customer_id/user_id/customer_name/customer_phone/customer_shop_name/customer_location, legacy user_name/user_phone/user_city, request_type, linked_products/product_ids, permitted notes, status, assignee_id/name, created_at, first_response_at, pending_since, pending_seconds, age_seconds, resolved_at/resolver_id/name, handling_seconds, updated_at, version, legacy_timing_unknown. Customer response excludes internal notes, actor IDs, assignment/resolver metadata and mutation keys.

`POST /requests/{id}/claim`; `PATCH /requests/{id}` `{version?,action:"update"|"claim"|"assign"|"reopen"|"response",status?,notes?,assigned_to?,idempotency_key?}`.
- Telecaller claims open/unassigned, then processes own assignment; no takeover/reassignment. Admin may assign/reassign/process. Billing mutations403.
- Terminal state changes require explicit `action=reopen,status=pending`; reopening resets pending-cycle time, not original created time.
- Atomic document version predicate; exactly one concurrent claim/update wins. Embedded event ledger appended **in the same atomic request write**; no note needed for transitions. Repeated no-op resolve does not add credit.
- Creation/claim/assignment/status/note/response/resolution/reopening event: `{id,type,request_id,actor_id,actor_role,actor_name,old,new,notes,status,timestamp}`. Actor server-derived. Last editor separate from resolver; admin note never changes completion attribution.
- `GET /requests/{id}/history` -> `{request,history:[...]}`; legacy notes adapted with provenance and no fabricated resolution credit.

### Metrics

`GET /requests/staff-options` (any canonical staff) returns `{users:[{id,name,role}],limit:500}`; no phone/contact fields. Includes historical inactive staff for attribution. Named assignee/resolver selectors now use this route. Assignment choices use the active admin staff directory. Each daily performance row has an explicit date+actor drilldown button; range controls remain available. `GET /analytics/dashboard` is the existing canonical admin-only count endpoint, returning total_customers, total_products, total_batches, total_requests, pending_requests, total_executives, recent_customers, recent_requests. It is not a website-local dashboard authority; filtered query metrics use the routes below.

`GET /requests/metrics/summary?start=YYYY-MM-DD&end=YYYY-MM-DD&search=&request_type=`. Admin team; telecaller own rows plus explicit team denominator. Defaulttoday, max366 calendar days, Asia/Kolkata boundaries converted to UTC half-open interval.

Received cohort counts queries created in interval; current open/resolved/cancelled partition that cohort. Period throughput counts distinct requests having resolution events in interval, including old receipts. Repeated resolutions deduplicated; last qualifying event actor receives interval credit, even if later reopened. No legacy timestamp/credit invention.
Each row: resolved/team_resolved; resolved_from_assigned/assigned_workload (created-in-range cohort currently assigned to that person); open_workload from same assigned cohort; distinct ledger-work IST active_days/calendar_days, daily work_events/resolved, top_performer. Team resolutions include authorized admin resolutions. Highest **nonzero** telecaller count highlights all ties with text indicator. Zero is never a winner. Status chips affect table only; summaries use full matching search/type dataset, not current page. Dates are reporting calendar dates, not attendance.

## Rates and product media

`GET /rates/latest` preserves silver/gold legacy fields and adds version, units, actor/effective time. Physical/MCX are INR/g; dollar references USD/troy_oz. Ambiguous USD→physical calculations are rejected: automatic physical base must use MCX with same INR/g unit. `POST /rates` admin/billing only, requires `version`, updates only supplied fields, atomically increments version and embeds actor history. Stale409, omitted version428. Per-metal purity validated when supplied; no reset of other metal. `GET /rates/audit?page=&limit=` authorized actor history.
`GET /rate-list?metal_type=` returns `{slabs:[...]}` (at most1000, order then ID; deleted excluded). POST rate-list / PUT rate-list/{id} / DELETE rate-list/{id}?version=N permit admin/billing. Updates/deletes require version, record actor history; deletion soft-hides list entry. Legacy documents without a version read as0. Required creation fields: item_name, metal_type. Optional purity/wastage/category/subcategory/order.

**Labour compatibility:** preferred `labour:{currency:"INR",amount:"850",basis:"kg"}`; basis is kg/10g/piece. Legacy `labour_kg` accepts `INR 850/kg`, `₹850/kg`, `INR 50/10g`, `INR 20/piece`; bare historical numbers mean INR/kg ONLY because this is the legacy per-kg field. Labelled units always win. No scaling or conversion of amounts. Responses add `labour`, `labour_display`, `unit_review_required`; ambiguous historical values stay stored and display with review=true. Unchanged optional historical fields do not block unrelated updates/soft deletion; changing ambiguous labour returns422 AMBIGUOUS_LABOUR_UNIT. If both representations are supplied they must agree (LABOUR_UNIT_CONFLICT). Updated old panel rate-list entry opens the canonical billing/admin editor, with versions; customer display no longer appends an incorrect /kg label.

### Bounded catalog and shared product validation

`GET /products?page=1&limit=50&metal_type=&category=&post_type=&batch_id=&search=&product_code=&include_hidden=false&mode=catalog` -> `{products,total,page,limit,pages,mode,sort}`. Limit1–100 (larger422, not silently clamped). `include_hidden=true` requires admin bearer. Default order is `created_at DESC,id ASC`, including page1. `search` uses Mongo indexed text words on title/tags/code/category (OR token matching, not substring/exact SKU). `product_code` is indexed exact case-sensitive SKU. Filters intersect. `ids` accepts at most100 comma-separated IDs and preserves requested order among visible matches. `mode=discovery` is explicitly a single random sample; page>1 or ids returns422 DISCOVERY_NOT_PAGINATED. Never concatenate discovery and sorted pages. Offset pagination is stable on an unchanged catalog, not a snapshot guarantee during concurrent insert/delete; refresh resets page state.

Indexes: created_at+id; metal_type+category+created_at+id; catalog_search_v1 text; existing unique nonempty product_code; individual media path/images indexes. Admin `/product-catalog` uses FlatList,40 records per page,6 initial cards, bounded batches/window, thumbnail-first images, debounced search and previous/next. The old100000 product download is removed. Customer feed no longer randomizes page1 and deduplicates by ID; selected viewer ID windows are capped100.

`POST /products` admin creates one hidden-by-default product; requires product_code,title,metal_type,category. Allowed shared fields are the PDF fields below plus images[] (max20). Upload photographs first. A legacy existing product may still have no code. Creation, explicit edits and import all use the same validate_product/units adapters. `45-55 grams` -> `45-55 g`; `25-35 grams per pair` -> `25-35 g per pair`; gm/gms/gram synonyms and per-piece basis accepted. Positive ascending values only. No kg/unknown-quantity guessing. Unchanged historical optional fields remain untouched on image/title-only edits, including ambiguous old representations. Explicitly changed ambiguous fields require correction. Changing metal/base-metal revalidates dependent purity. No bulk normalization migration was run; any later rewrite requires inventory, dry-run report and approval.

`POST /products/upload-image` admin multipart `file`: validated actual JPG/PNG/WEBP/GIF, ≤8MiB, ≤40MP. Re-encoded metadata-free JPEG (GIF first frame), as in baseline; now adds a max320px JPEG thumbnail. Returns `{url,storage_path,thumbnail_path,content_type,permanent:true}`. New URLs root-relative `/api/files/...`. Corrupt PIL SyntaxError is422 INVALID_IMAGE, not500. No originals already in storage were replaced. New manual products use the first added photograph's thumbnail; imported original scan remains the primary reference.
`PUT /products/{id}` requires `version`; supports existing product fields plus optional case-sensitive globally unique product_code (legacy products can omit it), base_metal and stone_weight_ct. images[] changes only additional photos; original/canonical scan path is server-owned. New image references must be uploaded managed media, not arbitrary URLs. Stale edits409; duplicate SKU409. Gallery combines original_source_storage_path, storage_path and every images[] URL without repeating the scan for every selection.
`GET /files/{path}` public only when referenced by a visible live product or active banner; otherwise canonical admin auth. Traversal rejected. Import sources/chunks/private previews never inherit public access. Existing hidden-product thumbnail clients must provide authorized retrieval; no public source-document endpoint is introduced.

Media responses use **private,no-store** even for public variants: no shared CDN/public-cache promise. Each request rechecks indexed current references/authorization BEFORE the byte cache. Published bytes <=2MiB may use a process LRU (16MiB total,60seconds); hidden bytes bypass it. Shared asset remains public if any live published reference remains. Unpublish blocks subsequent non-admin fetches even with a warm process cache; already downloaded copies cannot be recalled. BFF must not override no-store. Never place tokens/service keys in URLs. Product variants keep their existing image/png or image/jpeg content type/path; source PDFs and previews have no public route. Web private images use header-authenticated Blob fetch, with object-URL cleanup; native Image uses authorization headers.

Legacy external HTTPS image references remain renderable without copying them into a new library. They receive NO authorization header; only exact canonical API-origin/prefix images use bearer-authenticated retrieval. New uploaded references remain restricted to the managed store. No credential-bearing URL or plaintext HTTP image fallback is introduced.

### Media accounting and lifecycle

New manual master/thumbnail, PDF chunks/previews/masters/thumbs, legacy batch image uploads and banner writes create a media_assets intent BEFORE PUT, recording purpose/owner/job/bytes/SHA-256/content type; success sets stored, uncertain failure sets unknown. Provider402 is propagated as402; other write failures503. No publication on unconfirmed write. Application safeguards (not entitlements): MEDIA_WRITE_BUDGET_BYTES default2,000,000,000; MEDIA_WRITE_OBJECT_LIMIT default10000; tracked writes serialized during reservation/PUT. Unknown-size legacy objects mean accounting is explicitly incomplete. Budget rejects413 MEDIA_WRITE_BUDGET,80% triggers usage alert; batch route max10 files/request.

Admin `GET /admin/media/usage` returns tracked bytes/objects, purpose groups/unknown-size counts, application budgets, high_watermark, blocked_deletions, inventory_complete:false, provider_delete_supported:false. `POST /admin/media/lifecycle-audit` audits up to500 old candidates and returns `{audited:true,remote_deletions:0,status:"blocked_provider_unsupported"}`. App `/media-usage` displays these warnings and action.

Seven-day temporary policy preserves referenced hidden/deleted products, shared/reused assets, old scans, active reviews and chunks needed by imported products. It queues/audits cancelled/expired/unreferenced/superseded objects and records retained_reference or blocked_provider_unsupported, always remote_deleted:false. **Current managed provider exposes no supported DELETE API; remote deletion is NOT implemented or verified.** There is no invented delete endpoint and no assertion that DB/local expiry erases storage. Intent records make unknown/orphan writes discoverable; actual deletion retries/completion verification remain a provider-capability gate. See STORAGE_CAPACITY.md for costs/measurement limitations.

## PDF template and import — one service for both clients

`GET /pdf-template/capabilities` (admin) -> `{template,limits,sample_url,authoring_url,default_mode}`. `GET /pdf-template/sample.pdf` admin attachment `Yash-Catalog-Template-v1.pdf`, `application/pdf`; `GET /pdf-template/authoring.json` editable companion. Generator and schema: `backend/tools/generate_catalog.py`, `backend/shared/pdf_schema.py`; fixtures/manifest in `backend/fixtures/catalog-v1/`. Website must reuse these, not another parser.

**Form authoring:** `/catalog-author` accepts labelled fields, product/category/stock selectors, grams/carats/purity controls and a selected photograph. Save one hidden product, or collect1–20 entries and export. `POST /pdf-template/export` admin body `{products:[{...product_fields,photo_path:"yash-trade/products/manual/..."}]}` uses only confirmed uploads owned by that admin, rejects duplicate codes/unknown fields, and runs the SAME generate_catalog.py/schema. Returns private application/pdf attachment Yash-Catalog-v1.pdf. Max20 entries,32MiB input photo bytes, output <= configured importer limit; concurrent exports guarded by one shared lock. Long text returns AUTHORING_TEXT_OVERFLOW. No product creation/publication on export. Form entries are session-local, not durable background drafts; leave-screen warning is explicit. Advanced authoring.json/CLI remains available but is not the normal UI.

Exact v1: A4 210×297mm; points=mm×72/25.4. Header `YASH_CATALOG_TEMPLATE_VERSION: 1`, one `YASH_PAGE_ROLE: GUIDE|PRODUCTS`. GUIDE ignored entirely. Two max blocks (10,22,200,151), (10,157,200,286)mm. BEGIN and END markers at x12mm, blockTop+6/+127mm; codes match Product Code. Photo region x16..96mm, yTop+20..100mm (80mm square); labels/frame stroke outside. Text x102..196mm, yTop+12..123mm. Markers on different pages/overlapping/missing/mismatched rejected. 90/180/270 rotation normalized; altered crop boxes rejected with full-A4 instructions.

Required product_code/title/metal_type/category/photo; each product explicit gold/silver/diamond. No batch-metal override. Optional fields map directly to product schema: description/subcategory/approx_weight/purity/selling_touch/selling_label/stock_status/tags/video_url/visibility/is_new_arrival/is_trending/is_pinned; base_metal and stone_weight_ct separate diamond setting/stone metadata. Metal weight positive ascending number/range with `g`; carats separate positive number. Silver fineness925/92.5%, gold22K; no invented price column. Defaults in capability: stock in_stock, visibility hidden, new arrival true, trending/pinned false, tags[]. Blank optional values remain optional. Invalid values create row errors, not guesses. Additional photos use manual upload, no arbitrary private/internal URLs.

PyMuPDF geometric region rendering produces1024² PNG master and320² thumbnail, not whole-page crop in template mode. Low embedded resolution warns; no detail restoration claim. Source upload/page/block/crop/version/fingerprint retained. Explicit `legacy_pages` contains full nonblank page in square padding and requires manual field review; no silent fallback/OCR. Template guide/logos never auto-products. Sample has guide + two products + one diamond product + field-reference guide; parser returns exactly3 products.

### Upload/job routes (canonical admin + owning administrator only)

| Route | Request / response |
|---|---|
| POST `/pdf-upload/init` | `{batch_id,filename,file_size,sha256,total_chunks,mode:"template_v1"|"legacy_pages"}` -> `{upload_id,chunk_size,phase,sha256}` |
| POST `/pdf-upload/{id}/chunk?chunk_index=N` | multipart file + `X-Chunk-Sha256` -> `{received,sha256}` or `{received,duplicate:true}` |
| GET `/pdf-upload/{id}/status` | upload_id/phase/upload_status/sha256/file_size/filename/bytes_received/received_chunk_indices/total_chunks/total_pages/pages_processed/product_count/error/result/version/updated_at/limits |
| POST `/pdf-upload/{id}/complete` | verifies acknowledged manifest, queues analysis; idempotent status response |
| POST `/pdf-upload/{id}/pause` | pause upload or checkpoint analysis; acknowledged data remains |
| POST `/pdf-upload/{id}/resume` | resume paused upload or queue checkpointed/failed analysis; clear prior transient error |
| POST `/pdf-upload/{id}/cancel` | terminal cancelled state; later commit forbidden; already committed409 |
| GET `/pdf-upload/{id}/preview?page=&limit=` | `{rows,page,limit,total}`; rows include fields/errors/warnings/source page+block/crop/template/version/excluded/duplicate_policy/existing_product/preview_url/commit_result |
| GET `/pdf-upload/{id}/rows/{rowId}/image` | authorized private PNG, no-store |
| GET `/pdf-upload/{id}/pages/{page}/image` | owning admin, phase review/committed, 1-based page; upright900px-wide private PNG. `?metadata=true` -> width_points,height_points,rotation:0,coordinate_space:unrotated_pdf_points. Never source PDF bytes. |
| PATCH `/pdf-upload/{id}/rows/{rowId}` | `{version,fields?,excluded?,duplicate_policy:"skip"|"update"?,expected_product_version?,crop_points?:[x0,y0,x1,y1]}` -> saved/row_id/version |
| POST `/pdf-upload/{id}/commit` | `{version,confirm:true,allow_partial:false,publish:false}` -> `{created,updated,skipped,failed,rows:[{row_id,status,reason?,product_id?}]}` |

No analysis-time product creation. Commit hidden by default; publication explicit. Update Existing requires displayed product version; skip default. Unique global code and stable row/source fingerprint prevent silent duplicate inserts; recovered partial rows report original outcome. Partial valid-only commit needs explicit allow_partial. Failed rows remain reviewable; result is never labeled total success. Repeated completed commit returns stored result. Per-code and per-import renewable locks + product version predicates guard concurrent edits; real multi-worker outage chaos remains to validate.

Staff review uses labelled ProductFields and a draggable/resizable square over the private upright source page. Mapping: screen pixels / displayedWidth * width_points, both axes; backend/source preview/parser normalize page rotation to0. The saved rectangle is x0,y0,x1,y1 in unrotated PDF points; square/outside/text-overlap checks remain server-side. JSON/coordinate typing removed from normal workflow. Preview GET has its own read lock and bounded10second contention wait, separate from versioned mutations; source reconstruction is independently locked. Native gesture/file-provider acceptance remains pending despite passing routed-browser move/resize tests. At most4 active imports per admin; default64MiB PDF,1MiB chunks,200pages remain CONFIGURED limits, not production-proven capacity.

Configured limits:64MiB file,200 pages,1MiB chunks; environment-adjustable byte/page caps, returned to both clients. SHA-256 whole-file and chunks; bounded one-chunk client reads; native SDK54 DocumentPicker/FileHandle, no web-only chooser. Web base64 disabled. Local native resume state in SecureStore; web minimal file identity in AsyncStorage (reselect file after reload). Wrong file resume rejected. Bounded retries for network/5xx. Pausing is not cancelling; background return refreshes status.

Mongo job phases/checkpoints and leases enable reconstruction; in-process task is only a polling runner. Source-cache loss/reconstruction and transport-failure retries were simulated and tested, not a real production kill/restart/network partition. Chunks/previews durable managed storage; per-page child process512MiB address-space budget, CPU22s, timeout25s. Local abandoned temporary data expires after7 days. **Remote DELETE is unsupported by the available managed adapter and therefore blocked**, not merely an untested successful operation. No PDF scripts/actions/URLs are executed/fetched.

Current measurement:32-page/60-product generated catalog4,128,423 bytes,54.641s via current per-page subprocess path,235,646,976bytes combined imported-backend-parent + child peak RSS sampled50ms. Excludes full concurrent HTTP/authoring/Mongo service load; not a production capacity guarantee. Historical447,312KB measurement used a different in-process harness and is not the release sizing basis. See PDF_VALIDATION_EVIDENCE.md and STORAGE_CAPACITY.md.

## Secrets, origins, rollout and known limits

Non-secret env names: `MONGO_URL`, `DB_NAME`, `JWT_SECRET`, `MSG91_AUTHKEY`, `MSG91_TEMPLATE_ID`, `MSG91_SENDER_ID`, `MSG91_OTP_VAR`, `MSG91_BASE_URL`, `MSG91_VALIDATE_URL`, `ENROLLMENT_INTEGRATION_KEY`, `STAFF_SERVICE_KEY`, `CORS_ORIGINS`, `BUILD_COMMIT`, `PDF_MAX_BYTES`, `PDF_MAX_PAGES`, `PDF_WORK_DIR`, `EXPO_PUBLIC_BACKEND_URL`, `EXPO_PUBLIC_REGISTRATION_URL`, plus existing storage/AI variables. Never bundle secrets. JWT and integration keys require strong values. No fallback integration/JWT secret; no fixed OTP activation by old demo environment flags. MSG91 config must be supplied; template IDs no longer silently substitute missing config.

`CORS_ORIGINS` is explicit comma-separated origins, no wildcard. Native clients have no browser CORS dependency. Website browser should call its same-origin BFF; canonical server-to-server calls do not require CORS. If direct noncredentialed preview calls are needed allow the actual current preview origin, not old fork hostnames. Production website origins: `https://register.yashsilver.com`, `https://yash-register.emergent.host`; app backend `https://yash-tryon-test.emergent.host`. Do not edit protected Expo proxy/hostname values.

**Release gates still open:** real website BFF/UI cutover, private export/backup/owner-approved reconciliation, exposed-key rotation, `STAFF_SERVICE_KEY` provisioning, real provider delivery test to an owner-controlled number, isolated Play-review access provisioning outside Git, physical Android/iOS/release-build native tests, complete provider deletion/retention and privacy/Data Safety audit, large-file/multi-worker/storage-outage chaos and remaining negative parser fixtures. Legacy demo records are not silently deleted; startup no longer creates/promotes seeds. Genuine admin continuity must be established through approved migration before legacy records are retired.

Automated evidence:27 isolated backend tests pass together;4 authenticated routed-browser tests pass. Corrected admin PDF test waits for complete upload before invoking the worker; the earlier409 was test-induced premature phase mutation, not proof of a production uploader race. External SMS/storage are test-only stubs. Native physical-device and cross-deployment end-to-end behavior are not proven by those tests.

Follow-up combined verification: **54 passed,0 failed,0 skipped**, `test_reports/pytest/followup_combined_after_races.xml`. Includes5 authenticated routed mobile-web journeys and isolated backend cases, simultaneous chunk/commit/cancel tests, partial-variant write recovery and simulated expired-lease checkpoint resume. SMS/storage transports in these tests are test doubles;6 genuine read-only storage reads are separate evidence. No live SMS, storage-write/rotation/deletion or physical-device proof. Baseline31-test report remains historical.