# Yash shared API contract — v1

Build label: `shared-v1-2026-09-11`. Implementation is in this workspace, not a claim of production rollout.
Production last inspected: `https://yash-tryon-test.emergent.host/api/health`, build `2026.09.09-integration-v7`.
All paths below include `/api`; HTTPS only outside local tests. Generated OpenAPI: `contracts/openapi.shared-v1.json` and running `/openapi.json`.

## Authority, mappings and errors

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

Admin directory: `GET /customers?page=1&limit=20&search=&account_status=&login_state=&onboarding_status=&assigned_to=`. Limits1–100. Response `{customers,total,page,limit,pages}`; each row has `number`. `login_state=logged_in|never`; onboarding independent. `GET /customers/{id}` adds latest100 queries/activity (explicit `detail_limit:100`; request queue pagination is the full history access). `PATCH /customers/{id}` permits profile, active/inactive account status and active telecaller assignment only. Staff editing uses staff APIs.

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

`GET /requests/metrics/summary?start=YYYY-MM-DD&end=YYYY-MM-DD&search=&request_type=`. Admin team; telecaller own rows plus explicit team denominator. Defaulttoday, max366 calendar days, Asia/Kolkata boundaries converted to UTC half-open interval.

Received cohort counts queries created in interval; current open/resolved/cancelled partition that cohort. Period throughput counts distinct requests having resolution events in interval, including old receipts. Repeated resolutions deduplicated; last qualifying event actor receives interval credit, even if later reopened. No legacy timestamp/credit invention.
Each row: resolved/team_resolved; resolved_from_assigned/assigned_workload (created-in-range cohort currently assigned to that person); open_workload from same assigned cohort; distinct ledger-work IST active_days/calendar_days, daily work_events/resolved, top_performer. Team resolutions include authorized admin resolutions. Highest **nonzero** telecaller count highlights all ties with text indicator. Zero is never a winner. Status chips affect table only; summaries use full matching search/type dataset, not current page. Dates are reporting calendar dates, not attendance.

## Rates and product media

`GET /rates/latest` preserves silver/gold legacy fields and adds version, units, actor/effective time. Physical/MCX are INR/g; dollar references USD/troy_oz. Ambiguous USD→physical calculations are rejected: automatic physical base must use MCX with same INR/g unit. `POST /rates` admin/billing only, requires `version`, updates only supplied fields, atomically increments version and embeds actor history. Stale409, omitted version428. Per-metal purity validated when supplied; no reset of other metal. `GET /rates/audit?page=&limit=` authorized actor history.
`GET /rate-list?metal_type=` existing slab envelope. POST rate-list / PUT rate-list/{id} / DELETE rate-list/{id}?version=N permit admin/billing. Updates/deletes require version, record actor history; deletion soft-hides list entry. Slab item_name/metal_type/purity/wastage/labour_kg (INR/kg), optional category/subcategory/order.

`POST /products/upload-image` admin multipart `file`: validated actual JPG/PNG/WEBP/GIF, ≤8MB, ≤40MP. Re-encoded metadata-free JPEG (GIF first frame); permanent managed storage, no banner expiry. `{url,storage_path,content_type,permanent:true}`. New URLs root-relative `/api/files/...`.
`PUT /products/{id}` requires `version`; supports existing product fields plus optional case-sensitive globally unique product_code (legacy products can omit it), base_metal and stone_weight_ct. images[] changes only additional photos; original/canonical scan path is server-owned. New image references must be uploaded managed media, not arbitrary URLs. Stale edits409; duplicate SKU409. Gallery combines original_source_storage_path, storage_path and every images[] URL without repeating the scan for every selection.
`GET /files/{path}` public only when referenced by a visible live product or active banner; otherwise canonical admin auth. Traversal rejected. Import sources/chunks/private previews never inherit public access. Existing hidden-product thumbnail clients must provide authorized retrieval; no public source-document endpoint is introduced.

## PDF template and import — one service for both clients

`GET /pdf-template/capabilities` (admin) -> `{template,limits,sample_url,authoring_url,default_mode}`. `GET /pdf-template/sample.pdf` admin attachment `Yash-Catalog-Template-v1.pdf`, `application/pdf`; `GET /pdf-template/authoring.json` editable companion. Generator and schema: `backend/tools/generate_catalog.py`, `backend/shared/pdf_schema.py`; fixtures/manifest in `backend/fixtures/catalog-v1/`. Website must reuse these, not another parser.

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
| PATCH `/pdf-upload/{id}/rows/{rowId}` | `{version,fields?,excluded?,duplicate_policy:"skip"|"update"?,expected_product_version?,crop_points?:[x0,y0,x1,y1]}` -> saved/row_id/version |
| POST `/pdf-upload/{id}/commit` | `{version,confirm:true,allow_partial:false,publish:false}` -> `{created,updated,skipped,failed,rows:[{row_id,status,reason?,product_id?}]}` |

No analysis-time product creation. Commit hidden by default; publication explicit. Update Existing requires displayed product version; skip default. Unique global code and stable row/source fingerprint prevent silent duplicate inserts; recovered partial rows report original outcome. Partial valid-only commit needs explicit allow_partial. Failed rows remain reviewable; result is never labeled total success. Repeated completed commit returns stored result. Per-code and per-import renewable locks + product version predicates guard concurrent edits; real multi-worker outage chaos remains to validate.

Configured limits:64MiB file,200 pages,1MiB chunks; environment-adjustable byte/page caps, returned to both clients. SHA-256 whole-file and chunks; bounded one-chunk client reads; native SDK54 DocumentPicker/FileHandle, no web-only chooser. Web base64 disabled. Local native resume state in SecureStore; web minimal file identity in AsyncStorage (reselect file after reload). Wrong file resume rejected. Bounded retries for network/5xx. Pausing is not cancelling; background return refreshes status.

Mongo job phases/checkpoints plus lease worker survive backend restart; in-process task is only a polling runner, not the source of job state. Chunks/previews durable managed storage; per-page child process512MiB address-space budget, CPU22s, timeout25s. Local abandoned temporary data expires after7 days. **Managed-object deletion/purge integration remains operationally unverified**; do not claim remote source retention cleanup complete. No PDF scripts/actions/URLs are executed/fetched.

Measured evidence: exact sample~3.9MiB;32-page/60-product generated catalog4,127,720 bytes,39.321s parser path,447,312KB peak RSS. This is not a64MiB/200-page or native-device performance guarantee. See `PDF_VALIDATION_EVIDENCE.md` for remaining acceptance cases.

## Secrets, origins, rollout and known limits

Non-secret env names: `MONGO_URL`, `DB_NAME`, `JWT_SECRET`, `MSG91_AUTHKEY`, `MSG91_TEMPLATE_ID`, `MSG91_SENDER_ID`, `MSG91_OTP_VAR`, `MSG91_BASE_URL`, `MSG91_VALIDATE_URL`, `ENROLLMENT_INTEGRATION_KEY`, `STAFF_SERVICE_KEY`, `CORS_ORIGINS`, `BUILD_COMMIT`, `PDF_MAX_BYTES`, `PDF_MAX_PAGES`, `PDF_WORK_DIR`, `EXPO_PUBLIC_BACKEND_URL`, `EXPO_PUBLIC_REGISTRATION_URL`, plus existing storage/AI variables. Never bundle secrets. JWT and integration keys require strong values. No fallback integration/JWT secret; no fixed OTP activation by old demo environment flags. MSG91 config must be supplied; template IDs no longer silently substitute missing config.

`CORS_ORIGINS` is explicit comma-separated origins, no wildcard. Native clients have no browser CORS dependency. Website browser should call its same-origin BFF; canonical server-to-server calls do not require CORS. If direct noncredentialed preview calls are needed allow the actual current preview origin, not old fork hostnames. Production website origins: `https://register.yashsilver.com`, `https://yash-register.emergent.host`; app backend `https://yash-tryon-test.emergent.host`. Do not edit protected Expo proxy/hostname values.

**Release gates still open:** real website BFF/UI cutover, private export/backup/owner-approved reconciliation, exposed-key rotation, `STAFF_SERVICE_KEY` provisioning, real provider delivery test to an owner-controlled number, isolated Play-review access provisioning outside Git, physical Android/iOS/release-build native tests, complete provider deletion/retention and privacy/Data Safety audit, large-file/multi-worker/storage-outage chaos and remaining negative parser fixtures. Legacy demo records are not silently deleted; startup no longer creates/promotes seeds. Genuine admin continuity must be established through approved migration before legacy records are retired.

Automated evidence:27 isolated backend tests pass together;4 authenticated routed-browser tests pass. Corrected admin PDF test waits for complete upload before invoking the worker; the earlier409 was test-induced premature phase mutation, not proof of a production uploader race. External SMS/storage are test-only stubs. Native physical-device and cross-deployment end-to-end behavior are not proven by those tests.

Final combined verification: **31 tests passed in one run**, recorded in `test_reports/pytest/shared_final.xml`. This is controlled synthetic-environment coverage, not completion of all original release acceptance cases.