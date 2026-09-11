# Yash website handoff — canonical backend v1

## Delivery status

Workspace build: **`shared-v1-2026-09-11`**. Production backend last inspected at `https://yash-tryon-test.emergent.host/api/health` still reports **`2026.09.09-integration-v7`**, without an exact commit. This implementation has **not** been deployed to production or verified as synced to GitHub.

The website lives in another chat/repository. **No website code changes or cross-deployment synchronization have been completed here.** Do not use the new contract against production until its capabilities advertise v1.

Read together:
- `YASH_SHARED_API_CONTRACT.md` — authoritative behavior, fields, permissions and metrics.
- `contracts/openapi.shared-v1.json` — generated from the actual registered routes (111 paths).
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
- Phone change uses authenticated `/auth/phone-change/request` and `/verify`, preserving the same ID/history, checking uniqueness and revoking sessions. **Never enroll a second record under the new phone.** Reauthenticate after success.
- Admin customer APIs provide paginated search, onboarding/account/login filters, numbered rows and detail. Public profile edits cannot change role/status/timestamps/consent ownership.
- Staff directory/create/edit/disable/convert require canonical **admin bearer authorization**. Service credentials do not replace it. Use explicit conversion for an existing customer; implicit promotion returns 409. Last usable admin is protected.
- Optional staff token exchange requires a valid **same-subject staff session plus the separate staff-service key**. Enrollment credentials cannot impersonate any staff member. `issued_via` is not authentication evidence.

### Requests, metrics, rates and media
- Consume `/requests` as `{requests,total,page,limit,pages,open_counts_by_type,server_time}`. No 200-record ceiling. All authorized staff can read unassigned enquiries, regardless of customer lead assignment.
- Telecaller Requests is primary: All/Mine/Unassigned, claim, own-assignment processing, details/history. Keep lead CRM separate. Billing reads all query types/history, default open backlog oldest first; billing cannot claim, add internal notes or change query status.
- Canonical query statuses: pending/in_progress/contacted/no_response/resolved/cancelled. Legacy completed/done map to resolved; assigned maps to in_progress. UI may label resolved **Completed**. Terminal reopening is explicit action=reopen/status=pending. Use version/idempotency on mutations and surface 409 conflicts.
- Read `{request,history:[]}`. Internal notes stay staff-only. Last editor is separate from resolver; admin note edits do not steal completion credit.
- Follow the shared IST metrics definitions exactly: received cohort partition vs period throughput, last qualifying resolution per request in interval, explicit team/assigned denominators, active work dates—not attendance. Highest nonzero ties get green plus text/icon; all-zero rows have no winner. Status chips affect table only. Use `period_resolver,period_start,period_end` drilldown to match event attribution, not current resolver alone.
- Admin and billing may update both metals and slabs with version checks and actor history. Physical/MCX are INR/g; dollar reference is USD/troy_oz and cannot silently become an INR physical base. Preserve the other metal; show purity, unit, effective time and stale failures.
- Additional photos use permanent `POST /products/upload-image`, not banner expiry. PUT product with version and images[]; preserve original scan. Private hidden/import media must be fetched through authorized BFF requests, not public token-bearing URLs.
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

Backend uses durable Mongo checkpoints/leases, managed storage chunks, and resource-limited per-page subprocesses. Worker task is a runner, not the only job state. Local abandoned temporary files expire after7days; remote managed-object purge needs operational confirmation. Old direct `/batches/{id}/import-pdf` returns410 REVIEWED_IMPORT_REQUIRED.

## Configuration and cutover

Server-only secrets: strong JWT_SECRET, MSG91_AUTHKEY, ENROLLMENT_INTEGRATION_KEY, separate STAFF_SERVICE_KEY, existing storage/AI credentials. Provider template/sender/variable config must match the working Flow/DLT setup. **STAFF_SERVICE_KEY is currently missing locally**, so portal login/exchange intentionally fail closed until privately configured.

Rotate exposed/default integration/JWT values across both systems. No new fallback secret or fixed-OTP mechanism exists. Old OTP_DEMO_MODE/OTP_DEMO_PHONES cannot enable a bypass. Legacy seed records were not blindly deleted; establish a genuine authorized admin through approved reconciliation before retiring them.

Origin allowlist is explicit, not wildcard. Website domains: `https://register.yashsilver.com`, `https://yash-register.emergent.host`. Browser should use same-origin BFF; canonical calls are server-to-server. Preview allowed-origin and untrusted-origin rejection checks passed. Current Expo supervisor uses tunnel mode; that container configuration must be independently checked on the target runtime.

Do not modify protected Expo proxy/hostname variables. App uses EXPO_PUBLIC_BACKEND_URL and EXPO_PUBLIC_ENROLLMENT_URL (REGISTRATION_URL accepted by config adapter). Non-secret configuration names, limits and capabilities are listed in the shared contract.

### Rollout order
1. Review code/evidence and remaining release gates. Obtain private restorable production backup and verify genuine admin continuity. Do not run reconciliation yet.
2. Privately configure/rotate secrets and provenance; coordinate enrollment write pause and forced reauthentication. Old JWTs and unsafe verified-boolean/direct-PDF paths deliberately fail closed—this is not a silent compatibility switch.
3. Deploy canonical support first only after readiness/approval; record exact artifact in BUILD_COMMIT. Check capabilities, then real OTP to an owner-controlled number, not arbitrary phones.
4. Obtain the private website export, generate conflict report, get owner approval for the specific backup/report hash/mapping. Preserve canonical IDs/history, normalize reviewed references, revoke sessions.
5. Website agent updates BFF/UI/outbox and both website domains. Verify all roles, enquiries from both surfaces, rates/slabs, photo add/remove, shared PDF import, phone revocation and deletion acknowledgements.
6. Retire old unsafe compatibility only after consumer inventory and successful cross-system verification.

Rollback: stop writes/workers, retain checkpoints/tombstones/outbox, preserve a private affected-record export. Restore approved backup/code artifact only under owner/operator approval. Never revive old sessions, exposed secrets or fixed OTPs. Do not roll back canonical authority into independent website roles. No rollback was executed here.

## Evidence, unverified work and provenance

- **31 tests passed together**:27 backend +4 authenticated mobile-web journeys, `test_reports/pytest/shared_final.xml`. Browser calls real ASGI logic against isolated Mongo; external SMS/storage are fixture stubs, not production verification.
- Actual sample download/chooser/upload/review/exclusion/hidden commit verified. Test worker runs after acknowledged full upload; no claim of a real process-kill or device-background test.
- Square crop pixel MAE1.23–2.44; measured32pages/60products/4,127,720bytes/39.321s/447,312KB peak RSS. Not proof of configured maximum or native performance.
- Remaining gates: full negative/chaos PDF matrix, physical Android/iOS/Expo Go/release-build providers/share/background/navigation checks, real storage outage/restart behavior, review-account isolation, provider/global deletion and privacy/Data Safety audit.
- Play review identities/sample dataset and private external credentials handoff are **not provisioned**. No universal OTP or public reviewer account list was added.
- Local branch **main**; observed committed HEAD **`1d18a772c6c058e8917d969615f1495ad2c6345d`** is the **pre-change baseline**, not this implementation. No Git remote is configured in the container and no push/commit was performed by the agent. Use the normal Save-to-GitHub workflow, obtain the resulting implementation commit, then compare deployed BUILD_COMMIT. Production v7 does not expose an exact commit; it remains unverified.