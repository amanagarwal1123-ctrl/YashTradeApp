# Shared media capacity and lifecycle — measured, not an entitlement guarantee

## Approved direction preserved

One canonical app MongoDB holds product/customer/staff/query/rate metadata and stable paths. Existing managed object storage holds binary photos/variants/source chunks; website consumes canonical APIs/media and may hold sessions/drafts/outbox/cache only. No base64 library in Mongo, no duplicate website photo authority, no provider provisioning/migration/purchase.

## Read-only genuine inventory

`backend/tools/inventory_media.py --samples-per-kind 3 --output test_reports/media_inventory_followup.json` reads workspace canonical metadata and a bounded existing-asset sample; writes only aggregate local evidence. It does NOT prove that this workspace snapshot equals production or list all objects in a shared bucket.

424 master references +424 thumbnail references =848 distinct referenced managed objects. Six real reads succeeded (3each),0failed: masters590882bytes,thumbs17716bytes,total608598bytes. Sizes of421masters+421thumbs remain unknown.12external URL references are not copied/fetched. No source/chunk/current-preview/superseded/orphan entries were identified by this snapshot's job/ledger scans; **that is not proof that none exist upstream**. Backups and unreferenced historical provider objects are un-inventoried. Display variants separate from master/thumb and retained old scans need production inventory if present. Do not quote608598bytes as total library usage.

Upstream read latencies (3each, no CDN/browser path): masters391.628/205.853/208.243ms; thumbs291.074/169.049/255.773ms. Separate total elapsed includes offline transcoding. No live writes, key rotation or remote deletions tested. Synthetic tests use an object-store double.

## 10,000-photo projection (decimal GB)

| Basis | Master+thumbnail projection | Important exclusions |
|---|---:|---|
| Three genuine already-JPEG master/thumb pairs | 2.02866GB | Sample may not represent full-detail catalog; source/preview/backup excluded |
| Three v1 PNG sample master/thumb pairs | 13.33691GB | 12.05569GB masters +1.28122GB thumbnails; excludes sources/previews/backups |
| Offline sample JPEG92 master+thumb equivalents | 1.69199GB | Sizing only, not approved master replacement/equal-detail claim |
| Offline sample WebP92 equivalents | 1.01662GB | Same qualification; not a served-format change |

Detailed aggregate sample bytes/MAE: test_reports/followup_pdf_measurements.json. The independent13.3GB estimate is reproduced. Keeping PNG masters and adding JPEG/WebP display variants INCREASES durable bytes while potentially reducing read bandwidth; it does not yield the replacement totals above. Jewellery detail must be owner-reviewed before any serving-format change. Genuine JPEG samples re-encoded at92 grew (JPEG total835159bytes vs original608598; WebP678588), so blanket recompression is not justified. Originals were not changed.

10000photos means at least20000 master+thumb objects; add10000current previews, possibly10000display variants, retained old scans, superseded previews, source chunk count=ceil(source_bytes/1MiB), sources/backups and orphan candidates. Import currently stores chunks rather than a second remote assembled PDF. Keep committed source chunks for re-review. Storage/traffic formulas must include all variants and reads, not just product count.

Example traffic estimate formula (not measured demand): monthly thumbnail views × measured average thumbnail bytes + full-photo views × selected display bytes + source/review reads; add protocol/cache misses. No invented visitor count, quota or price. Unknown provider charges prevent a reliable currency quote.

## Lifecycle, safeguards and delivery

New writes ledger intent before PUT, actual byte/SHA/type/purpose/job/owner, stored or unknown outcome. Budgets default2,000,000,000tracked bytes and10000tracked objects; these are conservative application guards for NEW tracked objects, NOT included space/remaining quota. Legacy unknown inventory prevents total-quota guarantees. Admin media-usage displays80% high-watermark and blocked purge count. Current defaults will deliberately block a10kphoto expansion before all variants: owner must confirm actual entitlement and approve budget changes first.

After7days, audit up to500 least-recently-checked old assets; retained live/hidden/deleted references, shared assets, active reviews, original scans and committed source chunks remain protected. Others record blocked_provider_unsupported/remote_deleted:false. Local job/cache expiry is distinct. Managed API currently exposes PUT/GET but no supported DELETE; no guessed endpoint, no fake deletion completion or automatic provider migration. The ledger permits future retryable deletion implementation only once capability and policy are approved; actual erasure/readback verification is still pending.

Published variants use indexed reference lookup before every read, then optional16MiB total/60s process byte cache for <=2MiB objects. HTTP cache policy is private,no-store for all variants. No CDN public cache enabled. Hidden products/previews/sources remain private; BFF must preserve headers and never put bearer/service keys in URLs. Unpublish denies later anonymous/customer reads, including warm cached bytes, but cannot recall downloaded copies. Thumbnails are lazy-loaded in virtualized lists. Existing PNG/JPEG paths/content types remain consistent.

## Load measurements and limits

10k metadata100pages/10000unique IDs; no live assets uploaded.100-row payload62040bytes. Current sequential/concurrency8 p50/p95/search timings and TEXT_MATCH explain are in test_reports/catalog_10k_benchmark_iteration16.json. Text full-SKU words are OR semantics and can match all10000; exact product_code lookup returns1. Environment is isolated ASGI/local Mongo, not internet latency.

Final run: sequential list p50/p95=11.236/11.905ms;8-concurrent p50/p95=34.136/48.329ms. Selective numeric text query3.236ms; broad OR-word SKU query44.406ms. The image routes in browser tests are controlled fixtures, so the JS-heap snapshot below is chiefly metadata/virtualization evidence, not realistic full-detail photo decoder memory. Real provider byte/latency samples above are a separate read-only measurement.

Mobile-web300record scrolling snapshot:40metadata/page,scrollTop0→7072,6→14rendered cards,248→361DOM nodes,20.5MB reported JS heap unchanged over short wheel loop. The test explicitly verifies the list scrolled. Not native image decoder memory or a long-duration10k-device soak. Current PDF60product32page benchmark:54.641s,235646976bytes imported-backend-parent+child peak at50ms/concurrency1. Excludes full concurrent HTTP/authoring/DB/provider resource use; workspace8GiB/4CPU is NOT production allocation. Actual production resources unknown;64MiB/200page settings not proven; no1GB promise.

## Entitlements and recommendation

Account settings were not accessible. Support supplied generic knowledge-base figures (5GB/org and chat-upload limits), while integration guidance described per-user storage and different operation limits. **Neither is verified for this project's deployed storage account; conflicting generic figures are not used as quota guarantees.** Exact included MongoGB/objectGB/objectcount/single-upload limits, outboundGB/read/write charges, CPU/RAM/concurrency, backup/restore retention and cost, deletion/lifecycle support and overages remain questions for authorized account support/settings. Development/AI credits do not establish production storage/compute entitlement.

Keep the existing provider for current work; no capacity purchase or migration is justified without confirmed account data and full inventory. Required deletion is a concrete capability gap, not a cosmetic optimization. If provider cannot supply supported erasure OR confirmed capacity/performance is inadequate, propose one S3-compatible service (e.g. R2) behind this adapter for owner review. Future plan must inventory/checksum every object, assign stable logical media IDs, preserve old references during temporary controlled dual-read, verify all copies, define rollback, and never delete the old library before verification+approval. No second permanent photo store, no automatic provisioning.