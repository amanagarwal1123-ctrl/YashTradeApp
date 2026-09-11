# Yash website handoff — canonical backend v1

## Delivery status

Workspace build: **`shared-v1-followup-2026-09-11`**, preview `https://pagination-ui-boost.preview.emergentagent.com` (recorded commit: unrecorded). Public main baseline **30796997d3484594c6c5f53965e1c71dd5ed1c86** was verified before editing; prior claims that this baseline sync was unverified are superseded. Follow-up changes require the user-controlled Save to GitHub action; no new implementation commit/remote verification is available in this environment. Do not call the baseline the new implementation commit. No production deployment performed. Last independent production app observation: `https://yash-tryon-test.emergent.host/api/health`, **2026.09.09-integration-v7**, commit unknown; website health observations **2026.09.10-login-v10**, commits unknown. Code sync is not rollout.

The website lives in another chat/repository. **No website code changes or cross-deployment synchronization have been completed here.** Do not use the new contract against production until its capabilities advertise v1.

Read together:
- `YASH_SHARED_API_CONTRACT.md` — authoritative behavior, fields, permissions and metrics.
- `contracts/openapi.shared-v1.json` — regenerated from actual installed routes, including follow-up catalog/authoring/lifecycle routes; consult info.version rather than a stale route count.
- `IDENTITY_EXPORT_CONTRACT.md` — minimum private export and approval gates.
- `PDF_VALIDATION_EVIDENCE.md` and `RELEASE_READINESS.md` — exact coverage and remaining release blockers.

## Website implementation required

### Authentication and enrollment
1. Website BFF proxies canonical `POST /api/auth/send-otp` and `/verify-otp`. **One challenge, one SMS, one verification**, not separate website/app verifications.
2. Public Step 1 collects `name`, exactly ten-digit `phone`, `shop_name`, `location`, and consent. Use `purpose=enrollment` with server-only `X-Integration-Key`. Four-digit OTP UX is supported by the existing MSG91 Flow transport. Missing provider config is a blocker, never a reason for a fixed-code substitute.
3. Verification returns a five-minute opaque `verification_grant`, not a login session. Complete Step 1 only after `/integrations/enrollments` persists required fields using that grant. Do not submit public `verified:true` or send a second OTP for profile upsert.
4. Step 2 confirms enrollment and shows actual Android/iOS download links with icons, explaining login in Yash Trade with the same phone and a **fresh OTP**. No fictional username/password. Customers do not receive an administration portal.
5. Staff login uses `purpose=login, channel=portal` and separate server-only `X-Staff-Service-Key`. Canonical roles are `admin`, `telecaller`, `billing_executive`, `customer`; legacy `executive` is an adapter for telecaller. Always read `/auth/me` before routing; customer access to `/admin` must be denied. Website-local staff records, selectors, stored roles and unverified phone input are not permission authority.
6. BFF stores canonical ID/access/refresh server-side. Browser receives only a random HttpOnly, Secure, SameSite session cookie, with CSRF/origin checks and session fixation protection. Access expires after 15 minutes; refresh rotates once, family expires after 30 days. Serialize refresh per BFF session. Reuse/revocation/inactive state ends the website session; refresh does not mark mobile login.

### Customer and staff data
- Canonical reads own profile/account state. Cache by stable ID and `profile_version`; preserve old city alongside location. Pending outbox writes must not display “synced” until upstream succeeds.
- Phone change uses authenticated `/auth/phone-change/request` and `/verify`, preserving the same ID/history, checking uniqueness and revoking sessions. These are **SELF-SERVICE for the authenticated subject**, NOT admin-targeted customer controls. Customer PATCH does not accept phone; no admin-targeted change was added. **Never enroll a second record, impersonate a customer, or exchange another subject's token.** Reauthenticate after self-service success.
- Admin customer APIs provide paginated search, onboarding/account/login filters, numbered rows and detail. Public profile edits cannot change role/status/timestamps/consent ownership.
- Implement named active telecaller selection from GET /integrations/staff?role=telecaller&status=active and PATCH /customers/{id} `{assigned_salesperson:id|""}`. Directory filters now include assigned_to (special unassigned), registered_from/to and login_from/to (last mobile login), inclusive IST date strings/max366days. Display registered_at, first_mobile_login_at, last_mobile_login_at, last_portal_login_at separately; unknown is unknown.
- Staff directory/create/edit/disable/convert require canonical **admin bearer authorization**. Service credentials do not replace it. Use explicit conversion for an existing customer; implicit promotion returns 409. Last usable admin is protected.
- Optional staff token exchange requires a valid **same-subject staff session plus the separate staff-service key**. Enrollment credentials cannot impersonate any staff member. `issued_via` is not authentication evidence.

### Requests, metrics, rates and media
- Consume `/requests` as `{requests,total,page,limit,pages,open_counts_by_type,server_time}`. No 200-record ceiling. All authorized staff can read unassigned enquiries, regardless of customer lead assignment.
- Telecaller Requests is primary: All/Mine/Unassigned, claim, own-assignment processing, details/history. Keep lead CRM separate. Billing reads all query types/history, default open backlog oldest first; billing cannot claim, add internal notes or change query status.
- Canonical query statuses: pending/in_progress/contacted/no_response/resolved/cancelled. Legacy completed/done map to resolved; assigned maps to in_progress. UI may label resolved **Completed**. Terminal reopening is explicit action=reopen/status=pending. Use version/idempotency on mutations and surface 409 conflicts.
- Read `{request,history:[]}`. Internal notes stay staff-only. Last editor is separate from resolver; admin note edits do not steal completion credit.
- Follow the shared IST metrics definitions exactly: received cohort partition vs period throughput, last qualifying resolution per request in interval, explicit team/assigned denominators, active work dates—not attendance. Highest nonzero ties get green plus text/icon; all-zero rows have no winner. Status chips affect table only. Use `period_resolver,period_start,period_end` drilldown to match event attribution, not current resolver alone.
- Use GET /requests/staff-options for named assignee/resolver filters (id,name,role only; cap500). Daily row click sets period_start=period_end=that IST day and period_resolver=row.id. Range drilldown uses the selected range and same actor; ordinary resolver filter alone is not equivalent. GET /analytics/dashboard is canonical admin aggregate counts; no website-local counts authority.
- Admin and billing may update both metals and slabs with version checks and actor history. Physical/MCX are INR/g; dollar reference is USD/troy_oz and cannot silently become an INR physical base. Preserve the other metal; show purity, unit, effective time and stale failures.
- Additional photos use permanent `POST /products/upload-image`, not banner expiry. PUT product with version and images[]; preserve original scan. Private hidden/import media must be fetched through authorized BFF requests, not public token-bearing URLs.
- Product lists MUST use GET /products with limit<=100 (app40), page and mode=catalog. Stable sort created_at desc/id asc includes page1. Indexed search is Mongo text OR-words, not substring/SKU equality; use product_code for exact case-sensitive SKU and intersect category/metal filters. Response products,total,page,limit,pages,mode,sort. ids capped100. Discovery is separate mode=discovery,page1 only; never append random results to catalog pages. Virtualize and lazy-load thumbnails before masters. New creation POST /products requires unique product_code/title/metal_type/category; default hidden. Existing PUTs require version.
- Preserve legacy units: weight "25-35 grams per pair" normalizes to "25-35 g per pair" on explicit writes; do not resave unchanged historical optional fields unnecessarily. Rate slab GET supplies labour_display and labour:{currency,amount,basis}; kg/10g/piece retain their amount, no conversion. Prefer structured labour on writes; legacy labelled labour_kg also accepted. Show unit_review_required rather than guessing. PUT/DELETE slabs require version (legacy0), deletion is soft. Do not append /kg to all displays.
- Refresh on focus, pull-to-refresh and polling within approximately 15 seconds; show stale/error state rather than premature success.

### Deletion
Public website deletion must obtain a canonical deletion-purpose verification grant. `DELETE /integrations/customers/{phone}` requires **both** enrollment integration credential and `X-Verification-Grant`. Remove website caches/drafts/outbox retries/sessions by canonical ID, then acknowledge the deletion event. Do not resurrect tombstoned users by retrying enrollment.

Local app anonymization is not global provider erasure. Status remains `external_erasure_pending` until external obligations are confirmed. Website/provider retention and legacy unowned data still need a full audit.

## Minimal private identity export

No verified export has been supplied. Export only:
`collection, record_id, canonical_user_id|null, phone, phone_verified|null, verified_at|null, role|null, account_status|null, created_at|null, updated_at|null`.

If status is overloaded, explain whether it means account, lead or onboarding state. Provide a count-only manifest of collections/reference fields containing identity IDs. Names, addresses and shop details are unnecessary for the initial linkage report. A narrowly scoped supplement can be requested only for a named conflict.

**Never export passwords/hashes, OTPs, tokens/cookies, integration/SMS keys, chat/customer notes, financial records or a full dump. Transfer PII privately, never through public GitHub.** Exact schema, synthetic fixture and report command are in `IDENTITY_EXPORT_CONTRACT.md`.

Owner phone **9999813334** targets admin on both surfaces while retaining its existing canonical app ID/history. This is **not applied**. Specific production reconciliation remains dry-run until restorable backup, reviewed conflict report and owner approval of that report hash/mapping exist. Other roles require explicit approved mappings. Do not create a default phone/password admin or independently promote website records.

## Route quick map

All paths below use `/api`. Canonical JSON errors are `{code,detail,fields?}`; match `code`, not English wording.

| Area | Routes |
|---|---|
| Authentication | POST auth/send-otp, auth/verify-otp, auth/refresh, auth/logout; GET auth/me |
| Profile/phone | PUT auth/profile; POST auth/phone-change/request, auth/phone-change/verify |
| Enrollment/sync | POST integrations/enrollments; GET/DELETE integrations/customers/{phone} |
| Customers | GET customers; GET/PATCH customers/{id} |
| Staff | GET/POST integrations/staff; PATCH/DELETE integrations/staff/{id_or_phone}; POST .../convert, .../token |
| Requests | GET requests/catalog, requests/my, requests, requests/{id}/history, requests/metrics/summary; POST requests, requests/{id}/claim; PATCH requests/{id} |
| Rates | GET rates/latest, rates/audit, rate-list; POST rates, rate-list; PUT/DELETE rate-list/{id} |
| Media | POST products/upload-image; PUT products/{id}; GET files/{path} |
| Deletion outbox | GET integrations/deletions; POST integrations/deletions/{event_id}/ack |

Customer/staff/token bodies, user fields, filters, aliases, date rules and pagination defaults are specified in the shared API contract and generated OpenAPI. Customer list and request list retain their existing envelopes with additive metadata.

## PDF importer — reuse this service, not another parser

### Shared sample, authoring and layout

- `GET /api/pdf-template/capabilities` returns `{template,limits,sample_url,authoring_url,default_mode}`.
- `GET /api/pdf-template/sample.pdf` returns the actual regression fixture, admin-authorized attachment **Yash-Catalog-Template-v1.pdf**, content type **application/pdf**.
- `GET /api/pdf-template/authoring.json` returns the editable companion. Generator: `backend/tools/generate_catalog.py`; schema: `backend/shared/pdf_schema.py`; photos/sample/manifest: `backend/fixtures/catalog-v1/`.
- Build an ordinary labelled authoring form: upload each image via products/upload-image (multipart file), retain returned storage_path as photo_path, collect up to20 product entries, POST /pdf-template/export `{products:[{...fields,photo_path}]}` with owner-admin bearer. Response application/pdf download, private/no-store;32MiB total input photos, output<=PDF limit. It reuses the exact v1 generator. Export does not publish/create inventory. Current app flow is catalog-author; no Python/JSON editing required.
- Template v1 is A4 210×297mm. Header `YASH_CATALOG_TEMPLATE_VERSION: 1`; page role GUIDE or PRODUCTS. GUIDE pages, including marker examples, are ignored.
- At most two blocks: (10,22,200,151) and (10,157,200,286)mm. BEGIN/END markers at x12mm and block-top +6/+127mm. Codes match Product Code; no block may span pages.
- Photo interior x16–96mm, y=block-top+20–100mm: **80mm square**, excluding frame stroke/labels. Field column x102–196mm, y=top+12–123mm. PDF points = mm×72/25.4. Supported rotations normalize; altered crop boxes return a full-A4 export error.
- Master1024² PNG and thumbnail320² PNG. No text/neighbor/whole-page crop in template mode. Low-resolution sources warn; upscaling is not detail restoration.
- Required: product_code, title, metal_type, category, photo. Per-product type explicitly silver/gold/diamond; batch metal never overrides it. Optional existing schema fields: description, subcategory, approx_weight, purity, selling_touch, selling_label, stock_status, tags, video_url, visibility, is_new_arrival, is_trending, is_pinned. Separate base_metal and stone_weight_ct describe diamond setting/stone data.
- Metal weight is a positive number/ascending range with `g`; stone carats separate. Silver925/92.5%, gold22K examples normalize without changing meaning. No invented price column. Blank optional values/defaults and row validation are in capabilities/shared contract.
- Unsupported supplier/scanned layouts require **explicit legacy_pages** and manual correction/review. No OCR or silent template-to-whole-page fallback. Sample analysis produces exactly three example products, never auto-published inventory.

### Complete PDF endpoint/response contract

All job, chunk, status, preview, correction, commit and cancellation operations require canonical **admin + owning administrator** authorization.

| Route | Request / response |
|---|---|
| GET `/pdf-template/capabilities` | template includes version/page geometry/fields/required/defaults/master_pixels/thumbnail_pixels; limits includes max_bytes/chunk_bytes/max_pages/page_timeout_seconds/worker_memory_mb/temporary_retention_days/tested_maximum |
| POST `/pdf-upload/init` | `{batch_id,filename,file_size,sha256,total_chunks,mode}` -> `{upload_id,chunk_size,phase,sha256}` |
| POST `/pdf-upload/{id}/chunk?chunk_index=N` | multipart file + X-Chunk-Sha256 -> `{received,sha256}` or `{received,duplicate:true}` |
| GET `/pdf-upload/{id}/status` | upload_id,phase,upload_status,sha256,file_size,filename,bytes_received,received_chunk_indices,total_chunks,total_pages,pages_processed,product_count,error,result,version,updated_at,limits |
| GET `/pdf-upload/{id}/pages/{page}/image?metadata=true` | private owner-admin geometry width_points,height_points,rotation0,coordinate_space; no source PDF |
| GET `/pdf-upload/{id}/pages/{page}/image` | upright900px-wide PNG; fetch with Authorization header, not query token |
| POST `/pdf-upload/{id}/complete` | validates acknowledged manifest then queues analysis; idempotent status response |
| POST `/pdf-upload/{id}/pause` | pauses upload or checkpoints analysis; acknowledged data retained |
| POST `/pdf-upload/{id}/resume` | resumes paused upload or queues checkpointed/failed analysis; clears previous transient error |
| POST `/pdf-upload/{id}/cancel` | terminal cancelled status; later commit forbidden; already committed returns409 |
| GET `/pdf-upload/{id}/preview?page=&limit=` | `{rows,page,limit,total}` |
| GET `/pdf-upload/{id}/rows/{rowId}/image` | private PNG, no-store |
| PATCH `/pdf-upload/{id}/rows/{rowId}` | `{version,fields?,excluded?,duplicate_policy?:"skip"|"update",expected_product_version?,crop_points?:[x0,y0,x1,y1]}` -> `{saved,row_id,version}` |
| POST `/pdf-upload/{id}/commit` | `{version,confirm:true,allow_partial:false,publish:false}` -> `{created,updated,skipped,failed,rows:[{row_id,status,reason?,product_id?}]}` |

Preview row fields: `id,job_id,block_id,page,slot,fields,errors,warnings,crop_points,rotation,template_version,version,excluded,duplicate_policy,existing_product,preview_url,commit_result?`.

Stage UI: choose/download template → select PDF → upload → analyze → review fields/crops/exclusions/duplicates → explicit confirmation → exact result. No analysis-time products. Default hidden drafts; publication explicit. Update Existing requires displayed product version. Valid-only partial commit requires explicit allow_partial, reports every unimported row. Repeated commit recovers stored outcomes instead of duplicates.

Use returned limits, not old300MB/1000MB labels. Current configured cap64MiB/200pages, chunks1MiB; this is not a proven maximum. Persist minimal uploadID/file SHA/length securely, reject different-file resume, distinguish byte progress/page progress/product counts. Bounded network retries; Pause is not Cancel. Do not treat dismissing UI as cancellation. Source/chunks/previews remain private.

Backend uses durable Mongo checkpoints/leases, managed storage chunks, and resource-limited per-page subprocesses. Worker task is a runner, not the only job state. Local abandoned temporary files expire after7days. Managed provider DELETE is unavailable: remote purge is BLOCKED, not completed. Old direct `/batches/{id}/import-pdf` returns410 REVIEWED_IMPORT_REQUIRED.

Normal row review must use labelled inputs and draggable/resizable squares. Fetch owner-private page geometry first, then PNG without query credentials. Map screen displacement by width_points/displayed_width and use x0,y0,x1,y1 in unrotated PDF points. PATCH row uses returned version. Keep GET preview activity separate from mutation state;409 OPERATION_IN_PROGRESS is retryable contention,409 VERSION_CONFLICT requires reload/review. Do not auto-overwrite a colleague's changes. Crops must stay square, inside page/photo and outside text. The server rejects invalid regions. Source PDF itself is never a public URL.

### Shared storage, delivery and cost guardrails

One canonical Mongo stores references/metadata; one existing managed store holds media. No website-local photo library or binary/base64 product fields. Manual upload now returns thumbnail_path; prefer thumbnails on lists. All /files responses private,no-store; published bytes may be cached only inside backend16MiB/60second LRU after current authorization. BFF must not put private objects into public CDN/cache, must not override no-store, and must refetch after unpublish; old downloaded copies cannot be recalled. Formats remain PNG import variants/JPEG manual variants. Offline WebP/JPEG estimates are NOT a serving-format rollout.

GET /api/admin/media/usage (admin bearer) supplies tracked bytes/objects/purpose groups/high_watermark/application budgets and explicitly incomplete inventory. POST /api/admin/media/lifecycle-audit returns audited=true,remote_deletions=0,status=blocked_provider_unsupported. Preserve referenced old scans/shared assets/active review/source chunks. Unknown PUT outcomes stay in ledger. No website project can treat these records as proof of remote deletion. STORAGE_CAPACITY.md has measured usage/10k estimates; actual account limits and deletion capability remain owner/provider inputs.

## Configuration and cutover

Server-only secrets: strong JWT_SECRET, MSG91_AUTHKEY, ENROLLMENT_INTEGRATION_KEY, separate STAFF_SERVICE_KEY, existing storage/AI credentials. Provider template/sender/variable config must match the working Flow/DLT setup. **STAFF_SERVICE_KEY is currently missing locally**, so portal login/exchange intentionally fail closed until privately configured.

Exact names for the later BFF configuration (NOT configured in that project here):

| App backend variable | Website backend variable | Use |
|---|---|---|
| STAFF_SERVICE_KEY | STAFF_SERVICE_KEY (matching private value) | BFF sends X-Staff-Service-Key for portal OTP and same-subject exchange |
| ENROLLMENT_INTEGRATION_KEY | ENROLLMENT_INTEGRATION_KEY (matching private value, DIFFERENT from staff key) | BFF sends X-Integration-Key for enrollment/deletion-grant routes |
| Canonical API origin/configuration | CANONICAL_API_BASE_URL | Non-secret base ending /api; no token/key in URL; stage before live |
| JWT_SECRET | NOT shared with website | Canonical backend signs/verifies JWTs; BFF uses issued sessions, not minting authority |
| MSG91_AUTHKEY,MSG91_TEMPLATE_ID,MSG91_SENDER_ID,MSG91_OTP_VAR | NOT shared with website | App owns dispatch/verification; no second website SMS flow |
| MONGO_URL,DB_NAME,EMERGENT_LLM_KEY / existing storage credential | NOT shared with website | Website calls canonical APIs; no direct canonical DB/photo-library copy |
| BUILD_COMMIT | Website's own BUILD_COMMIT | Each artifact records its own actual commit; do not copy app SHA onto website build |

The website must also have its own private session/cookie signing configuration. No NEXT_PUBLIC/EXPO_PUBLIC/client bundle should contain either integration key, signing key, storage key or refresh token. Secret-value presence/rotation receipts are private; publish only names/status/outcomes. There is no authorized private production secret-management tool available to this app session, so provisioning is an explicit gate rather than an invented success.

Rotate exposed/default integration/JWT values across both systems. No new fallback secret or fixed-OTP mechanism exists. Old OTP_DEMO_MODE/OTP_DEMO_PHONES cannot enable a bypass. Legacy seed records were not blindly deleted; establish a genuine authorized admin through approved reconciliation before retiring them.

Origin allowlist is explicit, not wildcard. Website domains: `https://register.yashsilver.com`, `https://yash-register.emergent.host`. Browser should use same-origin BFF; canonical calls are server-to-server. Preview allowed-origin and untrusted-origin rejection checks passed. Current Expo supervisor uses tunnel mode; that container configuration must be independently checked on the target runtime.

Do not modify protected Expo proxy/hostname variables. App uses EXPO_PUBLIC_BACKEND_URL and EXPO_PUBLIC_ENROLLMENT_URL (REGISTRATION_URL accepted by config adapter). Non-secret configuration names, limits and capabilities are listed in the shared contract.

### Rollout order
1. Save/review the final app implementation commit, docs, OpenAPI and evidence. Do not enable breaking contracts in live production.
2. The later website agent implements BFF/UI/outbox against THIS contract in staging. Stage the app client and website against the SAME canonical backend build; record exact commit provenance. No website-local role/product/media authority.
3. Obtain minimum private website/app identity exports and a tested restorable production backup; create conflict report. Obtain specific report-hash/per-ID owner approval separately from code approval. Confirm the genuine existing owner remains usable. Do not merge/promote from export alone.
4. Authorized operators privately configure/rotate separate keys and test staged auth/grants/refresh, roles, query events/metrics, media/PDF and deletion acknowledgements. Clear reviewer/device/provider/resource gates. Test real OTP only with an approved owner-controlled recipient; check dispatch AND receipt.
5. Agree the maintenance window and rollback checkpoint. Pause affected writes; apply ONLY separately approved reconciliation and coordinate backend+both prepared clients' activation. Revoke legacy sessions and require fresh OTP; do not expose breaking v1 session/grant/OTP behavior to an old live BFF.
6. Verify genuine admin continuity, reference/business counts, all roles and shared workflows on both website domains/app before resuming writes. Record each running artifact's commit independently. Retire compatibility only after consumer inventory and cross-system sign-off.

Rollback: stop writes/workers, retain checkpoints/tombstones/outbox, preserve a private affected-record export. Restore approved backup/code artifact only under owner/operator approval. Never revive old sessions, exposed secrets or fixed OTPs. Do not roll back canonical authority into independent website roles. No rollback was executed here.

## Evidence, unverified work and provenance

- **54 tests passed together**, including5 authenticated mobile-web journeys, `test_reports/pytest/followup_combined_after_races.xml`. Browser calls real ASGI logic against isolated Mongo; external SMS/storage are fixture stubs, not production verification. Test bridge serializes the actual selected multipart File bytes because Chromium's intercepted post_data_buffer omits them; this does not validate live-network/native upload providers. Additional controlled chunk/commit/cancel races, partial-thumbnail-write retry and expired-lease checkpoint recovery pass; these are simulations, not real cloud restarts.
- Actual sample download/chooser/upload/review/exclusion/hidden commit verified. Test worker runs after acknowledged full upload; no claim of a real process-kill or device-background test.
- Current crop MAE silver2.4390/gold1.6606/diamond1.2307; sample exactly3 rows/no errors. Current32page/60product subprocess benchmark4,128,423bytes/54.641s/235,646,976bytes parent+child peak (excludes full HTTP/authoring/Mongo load).10k synthetic rows,100 pages,10000 unique IDs verified; list100 payload62040bytes; current timings in catalog_10k_benchmark_iteration16.json. Native/provider failure checks remain separate gates.
- Remaining gates: full negative/chaos PDF matrix, physical Android/iOS/Expo Go/release-build providers/share/background/navigation checks, real storage outage/restart behavior, review-account isolation, provider/global deletion and privacy/Data Safety audit.
- Play review identities/sample dataset and private external credentials handoff are **not provisioned**. No universal OTP or public reviewer account list was added.
- Local branch **main**; verified pre-follow-up baseline **30796997d3484594c6c5f53965e1c71dd5ed1c86**. No Git remote/write credential is configured in this container; the user-controlled Save to GitHub operation is required to obtain/verify the NEW implementation commit and pinned links. Then stage both clients against that exact contract, record BUILD_COMMIT, confirm genuine owner continuity/backup/secrets/reviewer/device/provider gates, agree maintenance window, apply only separately approved reconciliation, revoke old client sessions and require fresh OTP. Never deploy breaking v1 OTP/grant/session behavior to the unprepared live website merely to fill a report field.