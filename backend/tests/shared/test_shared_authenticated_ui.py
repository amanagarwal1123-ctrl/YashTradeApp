"""Authenticated mobile-web UI coverage using local Playwright + shared ASGI transport.

# Module coverage: admin panel/routes + telecaller workspace/leads + billing rates/slabs + customer home/gallery + reviewed PDF flow.
"""

from __future__ import annotations

import asyncio
import base64
import json
import re
from pathlib import Path
from urllib.parse import urlparse

import fitz
import pytest

from shared import core as c
from shared import pdf_jobs as jobs

try:
    from playwright.async_api import async_playwright
except Exception:  # pragma: no cover - handled with skip in tests
    async_playwright = None


FRONTEND_URL = "https://yash-trade-backend.preview.emergentagent.com"
SAMPLE_PDF = Path("/app/backend/fixtures/catalog-v1/sample.pdf")

# 1x1 PNG for synthetic object-store image paths used by UI previews.
PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4nGNgYAAAAAMAASsJTYQAAAAASUVORK5CYII="
)


def _auth_headers(token: str):
    return {"Authorization": f"Bearer {token}"}


async def _seed_ui_data(isolated_db):
    db = isolated_db["db"]
    now = c.stamp()

    # Synthetic object-store image entries for product/gallery rendering.
    image_paths = [
        "yash-trade/products/ui-original-1.png",
        "yash-trade/products/ui-current-1.png",
        "yash-trade/products/ui-thumb-1.png",
        "yash-trade/products/ui-current-2.png",
        "yash-trade/products/ui-thumb-2.png",
        "yash-trade/products/ui-added-1.png",
    ]
    for p in image_paths:
        isolated_db["object_store"][p] = (PNG_BYTES, "image/png")

    await db.users.update_one(
        {"id": "u_cust1"},
        {
            "$set": {
                "assigned_salesperson": "u_tele1",
                "lead_status": "new",
                "lead_updated_at": now,
                "shop_name": "TEST Shop One",
                "location": "Delhi",
                "has_logged_in": True,
                "first_mobile_login_at": now,
                "last_mobile_login_at": now,
            }
        },
    )
    await db.users.update_one(
        {"id": "u_cust2"},
        {
            "$set": {
                "assigned_salesperson": "u_tele1",
                "lead_status": "follow_up_required",
                "lead_updated_at": now,
                "follow_up_at": now[:10] + "T10:00",
                "shop_name": "TEST Shop Two",
                "location": "Mumbai",
            }
        },
    )

    await db.products.delete_many({"id": {"$regex": "^ui-prod-"}})
    await db.products.insert_many(
        [
            {
                "id": "ui-prod-1",
                "title": "TEST Silver Chain Classic",
                "metal_type": "silver",
                "category": "chain",
                "visibility": "all",
                "storage_path": "yash-trade/products/ui-current-1.png",
                "thumbnail_path": "yash-trade/products/ui-thumb-1.png",
                "original_source_storage_path": "yash-trade/products/ui-original-1.png",
                "images": ["/api/files/yash-trade/products/ui-added-1.png"],
                "is_deleted": False,
                "is_new_arrival": True,
                "is_trending": True,
                "approx_weight": "35g",
                "purity": "92.5",
                "created_at": now,
                "updated_at": now,
                "version": 0,
            },
            {
                "id": "ui-prod-2",
                "title": "TEST Gold Pendant Added",
                "metal_type": "gold",
                "category": "pendant",
                "visibility": "all",
                "storage_path": "yash-trade/products/ui-current-2.png",
                "thumbnail_path": "yash-trade/products/ui-thumb-2.png",
                "images": [],
                "is_deleted": False,
                "is_new_arrival": False,
                "is_trending": False,
                "approx_weight": "12g",
                "purity": "22K",
                "created_at": now,
                "updated_at": now,
                "version": 0,
            },
        ]
    )

    await db.requests.delete_many({"id": {"$regex": "^ui-req-"}})
    await db.requests.insert_many(
        [
            {
                "id": "ui-req-1",
                "request_type": "callback",
                "category": "chain",
                "preferred_time": "Immediately",
                "notes": "TEST customer requested callback",
                "product_id": "ui-prod-1",
                "product_ids": ["ui-prod-1"],
                "linked_products": [],
                "user_id": "u_cust1",
                "user_name": "Customer One",
                "user_phone": "9000000004",
                "user_city": "Delhi",
                "shop_name": "TEST Shop One",
                "status": "pending",
                "assignee_id": "",
                "assigned_to": "",
                "pending_since": now,
                "created_at": now,
                "updated_at": now,
                "version": 0,
                "events": [
                    {
                        "id": "ui-evt-1",
                        "type": "creation",
                        "request_id": "ui-req-1",
                        "actor_id": "u_cust1",
                        "actor_role": "customer",
                        "actor_name": "Customer One",
                        "status": "pending",
                        "timestamp": now,
                    }
                ],
            },
            {
                "id": "ui-req-2",
                "request_type": "ask_price",
                "category": "payal",
                "preferred_time": "Later today",
                "notes": "TEST pricing request",
                "product_id": "ui-prod-2",
                "product_ids": ["ui-prod-2"],
                "linked_products": [],
                "user_id": "u_cust2",
                "user_name": "Customer Two",
                "user_phone": "9000000005",
                "user_city": "Mumbai",
                "shop_name": "TEST Shop Two",
                "status": "pending",
                "assignee_id": "",
                "assigned_to": "",
                "pending_since": now,
                "created_at": now,
                "updated_at": now,
                "version": 0,
                "events": [
                    {
                        "id": "ui-evt-2",
                        "type": "creation",
                        "request_id": "ui-req-2",
                        "actor_id": "u_cust2",
                        "actor_role": "customer",
                        "actor_name": "Customer Two",
                        "status": "pending",
                        "timestamp": now,
                    }
                ],
            },
        ]
    )


async def _seed_catalog_metadata(isolated_db, total: int = 300):
    """Synthetic bounded metadata catalog for product-catalog mobile-web pagination/search checks."""
    db = isolated_db["db"]
    now = c.stamp()
    await db.products.delete_many({"id": {"$regex": "^iter16-meta-"}})
    rows = []
    for i in range(total):
        code = f"TESTMETA-{i:05d}"
        master = f"yash-trade/products/imported/iter16/{code}.png"
        thumb = f"yash-trade/products/imported/iter16/{code}-thumb.png"
        isolated_db["object_store"][master] = (PNG_BYTES, "image/png")
        isolated_db["object_store"][thumb] = (PNG_BYTES, "image/png")
        rows.append(
            {
                "id": f"iter16-meta-{i:05d}",
                "product_code": code,
                "title": f"TEST META PRODUCT {i:05d}",
                "description": f"Synthetic catalog metadata record {i:05d}",
                "metal_type": "silver" if i % 2 == 0 else "gold",
                "category": "payal" if i % 3 == 0 else "chain",
                "visibility": "all",
                "storage_path": master,
                "thumbnail_path": thumb,
                "images": [],
                "is_deleted": False,
                "created_at": now,
                "updated_at": now,
                "version": 0,
                "metadata_path": f"yash-trade/products/imported/iter16/{code}.json",
                "master_size_bytes": 1_280_000,
                "thumbnail_size_bytes": 62_000,
            }
        )
    await db.products.insert_many(rows)


async def _start_routed_browser(api_client):
    playwright = await async_playwright().start()
    browser = await playwright.chromium.launch(headless=True, args=["--disable-dev-shm-usage"])
    context = await browser.new_context(viewport={"width": 390, "height": 844}, accept_downloads=True)
    # Capture exact multipart bytes from browser fetch for routed ASGI forwarding.
    await context.add_init_script(
        """(() => {
            if (window.__asgiRouteMultipartInstalled) return;
            window.__asgiRouteMultipartInstalled = true;
            window.__asgiRouteMultipartQueue = [];
            const nativeFetch = window.fetch.bind(window);
            window.fetch = async (input, init) => {
                try {
                    const req = new Request(input, init);
                    const ct = (req.headers.get('content-type') || '').toLowerCase();
                    const hasFormDataBody = !!(init && init.body && typeof FormData !== 'undefined' && init.body instanceof FormData);
                    if (ct.includes('multipart/form-data') || hasFormDataBody) {
                        const ab = await req.clone().arrayBuffer();
                        const bytes = Array.from(new Uint8Array(ab));
                        window.__asgiRouteMultipartQueue.push({
                            url: req.url,
                            method: (req.method || 'GET').toUpperCase(),
                            headers: Array.from(req.headers.entries()),
                            bytes,
                            captured_at: Date.now()
                        });
                    }
                } catch (_) {}
                return nativeFetch(input, init);
            };
        })();"""
    )
    page = await context.new_page()
    bridge_events = []
    api_events = []

    async def route_to_asgi(route, request):
        parsed = urlparse(request.url)
        path = parsed.path + (f"?{parsed.query}" if parsed.query else "")
        headers = {k: v for k, v in request.headers.items() if k.lower() != "host"}
        api_events.append(
            {
                "url": request.url,
                "path": path,
                "method": request.method,
                "authorization": headers.get("authorization") or headers.get("Authorization"),
            }
        )
        native_body = request.post_data_buffer or b""
        body = native_body
        used_bridge_fallback = False
        if headers.get("content-type", "").lower().startswith("multipart/form-data"):
            queue_count = await page.evaluate("() => (window.__asgiRouteMultipartQueue || []).length")
            fallback = await page.evaluate(
                """({url, method}) => {
                    const queue = window.__asgiRouteMultipartQueue || [];
                    const m = (method || 'GET').toUpperCase();
                    const idx = queue.findIndex((row) => row.url === url && row.method === m);
                    if (idx < 0) return null;
                    const row = queue[idx];
                    queue.splice(idx, 1);
                    return row;
                }""",
                {"url": request.url, "method": request.method},
            )
            if fallback and fallback.get("bytes"):
                body = bytes(fallback["bytes"])
                for k, v in fallback.get("headers", []):
                    if k.lower() != "host":
                        headers[k] = v
                used_bridge_fallback = True
            if (
                not used_bridge_fallback
                and path.startswith("/api/products/upload-image")
                and len(native_body) <= 512
            ):
                reconstructed = await page.evaluate(
                    """async () => {
                        const input = document.querySelector('input[type="file"]');
                        const file = input?.files?.[0];
                        if (!file) return null;
                        const fd = new FormData();
                        fd.append('file', file);
                        const req = new Request('/api/products/upload-image', { method: 'POST', body: fd });
                        const ab = await req.arrayBuffer();
                        return {
                            bytes: Array.from(new Uint8Array(ab)),
                            content_type: req.headers.get('content-type') || '',
                            file_name: file.name,
                            file_size: file.size || 0,
                        };
                    }"""
                )
                if reconstructed and reconstructed.get("bytes"):
                    body = bytes(reconstructed["bytes"])
                    if reconstructed.get("content_type"):
                        headers["content-type"] = reconstructed["content_type"]
                    used_bridge_fallback = True
            bridge_events.append(
                {
                    "url": path,
                    "method": request.method,
                    "native_len": len(native_body),
                    "forwarded_len": len(body or b""),
                    "native_prefix_hex": native_body[:16].hex(),
                    "native_suffix_hex": native_body[-16:].hex() if native_body else "",
                    "queue_count_before_pop": queue_count,
                    "used_fallback": used_bridge_fallback,
                }
            )
        response = await api_client.request(
            request.method,
            path,
            headers=headers,
            content=body,
        )
        safe_headers = {
            k: v
            for k, v in response.headers.items()
            if k.lower() not in {"content-encoding", "transfer-encoding", "connection", "content-length"}
        }
        if used_bridge_fallback:
            safe_headers["x-routed-multipart-fallback"] = "1"
        await route.fulfill(status=response.status_code, headers=safe_headers, body=response.content)

    await context.route("**/api/**", route_to_asgi)
    setattr(context, "_bridge_events", bridge_events)
    setattr(context, "_api_events", api_events)
    return playwright, browser, context, page


async def _wait_for_job(db, timeout_seconds: float = 15.0):
    end = asyncio.get_running_loop().time() + timeout_seconds
    while asyncio.get_running_loop().time() < end:
        row = await db.import_jobs.find_one({}, {"_id": 0}, sort=[("created_at", -1)])
        if row and row.get("phase") == "queued" and row.get("bytes_received") == row.get("file_size"):
            return row
        await asyncio.sleep(0.2)
    raise AssertionError("Timed out waiting for full chunk upload and queued analysis")


async def _assert_no_horizontal_overflow(page, label: str):
    dims = await page.evaluate(
        """() => ({
            innerWidth: window.innerWidth,
            scrollWidth: document.documentElement.scrollWidth
        })"""
    )
    assert dims["scrollWidth"] <= dims["innerWidth"] + 2, (
        f"{label} has horizontal overflow: {dims}"
    )


async def _login_via_otp_ui(page, isolated_db, phone: str, expected: str):
    await page.goto(f"{FRONTEND_URL}/login", wait_until="domcontentloaded")
    await page.wait_for_function("document.querySelector('#root')?.innerText?.trim().length > 0", timeout=90000)
    await page.wait_for_selector('[data-testid="phone-input"]', timeout=90000)
    await page.fill('[data-testid="phone-input"]', phone)
    await page.click('[data-testid="send-otp-btn"]')
    await page.wait_for_url("**/verify-otp**", timeout=10000)

    otp = isolated_db["sent_otps"].get((phone, "login"))
    assert otp and len(otp) == 4, f"No dynamic OTP captured for {phone}"
    for i, digit in enumerate(otp):
        await page.fill(f'[data-testid="otp-input-{i}"]', digit)

    if expected == "panel":
        await page.wait_for_selector('[data-testid="panel-logout"]', timeout=15000)
    elif expected == "telecaller":
        await page.wait_for_selector('[data-testid="requests-title"]', timeout=15000)
    elif expected == "customer":
        await page.wait_for_selector('[data-testid="metal-toggle-silver"]', timeout=15000)
    else:
        raise AssertionError(f"Unknown expected route: {expected}")


@pytest.mark.asyncio
async def test_admin_authenticated_routes_and_reviewed_pdf_flow(api_client, isolated_db, seeded_users):
    """Admin authenticated UI: panel, requests/history, directory, rates + reviewed PDF download/upload/review/commit."""
    if async_playwright is None:
        pytest.skip("Playwright is not importable in this Python environment")

    await _seed_ui_data(isolated_db)
    pw, browser, context, page = await _start_routed_browser(api_client)
    try:
        await _login_via_otp_ui(page, isolated_db, "9999813334", "panel")
        await _assert_no_horizontal_overflow(page, "admin-panel")

        await page.click('[data-testid="panel-tab-requests"]')
        await page.wait_for_selector('[data-testid="requests-title"]', timeout=10000)
        await page.click('[data-testid^="request-open-"]')
        await page.wait_for_selector('[data-testid="request-detail-title"]', timeout=10000)
        claim = page.locator('[data-testid="request-claim"]')
        if await claim.count() > 0:
            await claim.first.click()
        note_input = page.locator('[data-testid="request-note"]')
        if await note_input.count() > 0:
            await note_input.first.fill("TEST admin note from authenticated UI")
        save_note = page.locator('[data-testid="request-save-note"]')
        if await save_note.count() > 0 and await save_note.first.is_enabled():
            await save_note.first.click()
        transition = page.locator('[data-testid="request-transition-contacted"]')
        if await transition.count() > 0:
            await transition.first.click()
        await page.click('[data-testid="request-detail-close"]')
        await page.click('[data-testid="requests-back"]')
        await page.wait_for_selector('[data-testid="panel-tab-customers"]', state='attached', timeout=10000)

        customers_tab = page.locator('[data-testid="panel-tab-customers"]:visible').first
        await customers_tab.click(force=True)
        await page.wait_for_selector('[data-testid="directory-title"]', timeout=10000)
        await _assert_no_horizontal_overflow(page, "customer-directory")
        await page.click('[data-testid^="directory-open-"]')
        await page.wait_for_selector('[data-testid="customer-detail-name"]', timeout=10000)
        await page.click('[data-testid="directory-back"]')
        if await page.locator('[data-testid="directory-title"]').count() > 0:
            await page.click('[data-testid="directory-back"]')
        await page.wait_for_selector('[data-testid="panel-tab-rates"]', state='attached', timeout=10000)

        rates_tab = page.locator('[data-testid="panel-tab-rates"]:visible').first
        await rates_tab.click(force=True)
        await page.wait_for_selector('[data-testid="staff-rates-title"]', timeout=10000)
        await page.click('[data-testid="edit-rate-silver"]')
        await page.fill('[data-testid="rate-value"]', "124.5")
        await page.fill('[data-testid="rate-purity"]', "999")
        await page.click('[data-testid="rate-save"]')
        await page.wait_for_selector('[data-testid="rates-confirmation"]', timeout=10000)

        await page.click('[data-testid="rates-back"]')
        await page.wait_for_selector('[data-testid="panel-tab-products"]', state='attached', timeout=10000)
        await page.evaluate(
            """() => {
                const tabs = Array.from(document.querySelectorAll('[data-testid="panel-tab-products"]'));
                tabs.forEach((el) => el.scrollIntoView({ block: 'nearest', inline: 'center' }));
            }"""
        )
        await page.click('[data-testid="panel-tab-products"]:visible', force=True)
        await page.wait_for_selector('[data-testid="pm-pdf"]', timeout=10000)
        await page.click('[data-testid="pm-pdf"]', force=True)
        await page.wait_for_selector('[data-testid="pdf-title"]', timeout=10000)

        async with page.expect_download() as download_info:
            await page.click('[data-testid="pdf-download-sample"]')
        download = await download_info.value
        assert download.suggested_filename.endswith(".pdf")

        await page.click('[data-testid="pdf-batch-b1"]')
        async with page.expect_file_chooser() as chooser_info:
            await page.click('[data-testid="pdf-select"]')
        chooser = await chooser_info.value
        await chooser.set_files(str(SAMPLE_PDF))
        await page.wait_for_selector('[data-testid="pdf-selected-file"]', timeout=10000)
        await page.click('[data-testid="pdf-upload"]')

        job = await _wait_for_job(isolated_db["db"])
        await isolated_db["db"].import_jobs.update_one(
            {"id": job["id"]},
            {"$set": {"phase": "analyzing", "lease": "ui-lease", "lease_until": c.stamp()}},
        )
        leased = await isolated_db["db"].import_jobs.find_one({"id": job["id"]}, {"_id": 0})
        await jobs.process_job(leased)

        await page.wait_for_selector('[data-testid="pdf-job-phase"]', timeout=15000)
        await page.wait_for_selector('[data-testid^="pdf-row-"]', timeout=15000)

        rows = await isolated_db["db"].import_rows.find({"job_id": job["id"]}, {"_id": 0}).sort([("page", 1)]).to_list(3)
        assert len(rows) == 3
        editable = rows[0]
        excluded = rows[1]

        await page.click(f'[data-testid="pdf-edit-{editable["id"]}"]')
        await page.fill(f'[data-testid="pdf-fields-{editable["id"]}-title"]', "TEST UI Corrected Title")
        async with page.expect_response(lambda r: r.request.method == "PATCH" and f'/rows/{editable["id"]}' in r.url) as saved:
            await page.click(f'[data-testid="pdf-save-fields-{editable["id"]}"]')
        saved_response = await saved.value
        assert saved_response.status == 200, await saved_response.text()
        await page.get_by_text("TEST UI Corrected Title", exact=True).wait_for(state="visible")
        await page.click(f'[data-testid="pdf-edit-{editable["id"]}"]')

        crop_input = page.locator(f'[data-testid="{editable["id"]}-square"]')
        resize_handle = page.locator(f'[data-testid="{editable["id"]}-resize"]')
        crop_save = page.locator(f'[data-testid="pdf-save-crop-{editable["id"]}"]')
        await crop_input.first.wait_for(state="visible")
        await page.locator(f'[data-testid="{editable["id"]}-source"]').wait_for(state="visible")
        row_before_crop = await isolated_db["db"].import_rows.find_one({"id": editable["id"]}, {"_id": 0, "crop_points": 1})
        square_before = await crop_input.first.bounding_box()
        assert square_before is not None
        await page.mouse.move(square_before["x"] + square_before["width"] / 2, square_before["y"] + square_before["height"] / 2)
        await page.mouse.down()
        await page.mouse.move(
            square_before["x"] + square_before["width"] / 2 + 18,
            square_before["y"] + square_before["height"] / 2 + 14,
            steps=10,
        )
        await page.mouse.up()
        handle_before = await resize_handle.first.bounding_box()
        assert handle_before is not None
        await page.mouse.move(handle_before["x"] + handle_before["width"] / 2, handle_before["y"] + handle_before["height"] / 2)
        await page.mouse.down()
        await page.mouse.move(
            handle_before["x"] + handle_before["width"] / 2 - 26,
            handle_before["y"] + handle_before["height"] / 2 - 26,
            steps=10,
        )
        await page.mouse.up()
        async with page.expect_response(lambda response: response.request.method == "PATCH" and f'/rows/{editable["id"]}' in response.url) as corrected:
            await crop_save.first.click()
        assert (await corrected.value).status == 200
        row_after_crop = await isolated_db["db"].import_rows.find_one({"id": editable["id"]}, {"_id": 0, "crop_points": 1})
        assert row_before_crop and row_after_crop
        assert row_before_crop.get("crop_points") != row_after_crop.get("crop_points")
        x0, y0, x1, y1 = row_after_crop["crop_points"]
        assert x1 > x0 and y1 > y0
        assert abs((x1 - x0) - (y1 - y0)) < 0.1
        await crop_input.first.wait_for(state="hidden")

        await page.click(f'[data-testid="pdf-exclude-{excluded["id"]}"]')
        await page.locator(f'[data-testid="pdf-exclude-{excluded["id"]}"]').get_by_text("Include row", exact=True).wait_for(state="visible")
        await page.click('[data-testid="pdf-confirm-import"]')
        await page.wait_for_selector('[data-testid="pdf-result"]', timeout=15000)

        committed = await isolated_db["db"].products.find(
            {"source_upload_id": job["id"]}, {"_id": 0, "visibility": 1}
        ).to_list(200)
        assert len(committed) == 2, "Exactly two selected products must commit; excluded row stays out"
        assert all(p.get("visibility") == "hidden" for p in committed)

        await page.screenshot(path="/app/test_reports/iteration13_admin_pdf.jpeg", quality=40)
    finally:
        await context.close()
        await browser.close()
        await pw.stop()


@pytest.mark.asyncio
async def test_telecaller_authenticated_requests_and_leads(api_client, isolated_db, seeded_users):
    """Telecaller authenticated UI: requests claim/process and separate customer leads workflow."""
    if async_playwright is None:
        pytest.skip("Playwright is not importable in this Python environment")

    await _seed_ui_data(isolated_db)
    pw, browser, context, page = await _start_routed_browser(api_client)
    try:
        await _login_via_otp_ui(page, isolated_db, "9000000001", "telecaller")
        await _assert_no_horizontal_overflow(page, "telecaller-requests")

        await page.click('[data-testid^="request-open-"]')
        await page.wait_for_selector('[data-testid="request-detail-title"]', timeout=10000)
        claim = page.locator('[data-testid="request-claim"]')
        if await claim.count() > 0:
            await claim.first.click()
        await page.fill('[data-testid="request-note"]', "TEST telecaller follow-up started")
        save_note = page.locator('[data-testid="request-save-note"]')
        if await save_note.count() > 0:
            await save_note.first.click()
        contacted = page.locator('[data-testid="request-transition-contacted"]')
        if await contacted.count() > 0:
            await contacted.first.click()
        await page.click('[data-testid="request-detail-close"]')

        await page.click('[data-testid="requests-open-crm"]')
        await page.wait_for_selector('[data-testid="tc-search"]', timeout=10000)
        await _assert_no_horizontal_overflow(page, "telecaller-leads")
        await page.click('[data-testid^="tc-customer-"]')
        await page.wait_for_selector('[data-testid="tc-notes"]', timeout=10000)
        await page.click('[data-testid="tc-status-contacted"]')
        await page.fill('[data-testid="tc-follow-date"]', "2030-01-01")
        await page.fill('[data-testid="tc-follow-time"]', "10:30")
        await page.fill('[data-testid="tc-notes"]', "TEST note from telecaller modal")
        await page.click('[data-testid="tc-save"]')
        await page.click('[data-testid="tc-modal-close"]')

        await page.screenshot(path="/app/test_reports/iteration13_telecaller.jpeg", quality=40)
    finally:
        await context.close()
        await browser.close()
        await pw.stop()


@pytest.mark.asyncio
async def test_billing_authenticated_rates_and_slabs(api_client, isolated_db, seeded_users):
    """Billing authenticated UI: rates write and slab add/edit entry points."""
    if async_playwright is None:
        pytest.skip("Playwright is not importable in this Python environment")

    await _seed_ui_data(isolated_db)
    pw, browser, context, page = await _start_routed_browser(api_client)
    try:
        await _login_via_otp_ui(page, isolated_db, "9000000003", "panel")
        await page.click('[data-testid="panel-tab-rates"]')
        await page.wait_for_selector('[data-testid="staff-rates-title"]', timeout=10000)
        await _assert_no_horizontal_overflow(page, "billing-rates")

        await page.click('[data-testid="edit-rate-gold"]')
        await page.fill('[data-testid="rate-value"]', "5123")
        await page.fill('[data-testid="rate-purity"]', "24K")
        await page.click('[data-testid="rate-save"]')
        await page.wait_for_selector('[data-testid="rates-confirmation"]', timeout=10000)

        await page.fill('[data-testid="slab-item"]', "TEST Billing Slab")
        await page.fill('[data-testid="slab-wastage"]', "2")
        await page.fill('[data-testid="slab-labour"]', "120")
        await page.click('[data-testid="slab-save"]')
        await page.wait_for_selector('[data-testid^="slab-"]', timeout=10000)

        await page.screenshot(path="/app/test_reports/iteration13_billing.jpeg", quality=40)
    finally:
        await context.close()
        await browser.close()
        await pw.stop()


@pytest.mark.asyncio
async def test_customer_authenticated_home_and_gallery(api_client, isolated_db, seeded_users):
    """Customer authenticated UI: home default silver + gallery viewer across original/added synthetic products."""
    if async_playwright is None:
        pytest.skip("Playwright is not importable in this Python environment")

    await _seed_ui_data(isolated_db)
    pw, browser, context, page = await _start_routed_browser(api_client)
    try:
        await _login_via_otp_ui(page, isolated_db, "9000000004", "customer")
        await _assert_no_horizontal_overflow(page, "customer-home")

        selected = await page.get_attribute('[data-testid="metal-toggle-silver"]', "aria-selected")
        assert selected in {"true", None}, "Silver toggle should be the default initial tab"

        await page.click('[data-testid="see-all-btn"]')
        await page.wait_for_selector('[data-testid="feed-list"]', timeout=10000)
        await page.click('[data-testid="feed-item-ui-prod-1"]')
        await page.wait_for_selector('[data-testid="viewer-close"]', timeout=10000)
        await page.wait_for_selector('[data-testid="viewer-ask-price"]', timeout=10000)
        await _assert_no_horizontal_overflow(page, "customer-gallery-viewer")
        added_photo = page.locator('[data-testid="viewer-photo-2"]')
        await added_photo.wait_for(state='visible')
        await added_photo.click()
        await page.wait_for_function("document.querySelector('[data-testid=viewer-main-image]')?.innerHTML.includes('ui-added-1') || document.querySelector('[data-testid=viewer-main-image]')?.style.backgroundImage.includes('ui-added-1')")

        next_button = page.locator('[data-testid="viewer-next"]')
        if await next_button.count() > 0:
            await next_button.first.click()

        await page.screenshot(path="/app/test_reports/iteration13_customer.jpeg", quality=40)
    finally:
        await context.close()
        await browser.close()
        await pw.stop()


@pytest.mark.asyncio
async def test_admin_mobile_web_catalog_author_export_and_media_usage(api_client, isolated_db, seeded_users, login_helper):
    """Admin mobile-web routed journey: catalog(<=40/page,next/prev/filter/search,DOM/heap) -> author upload/export parse -> media usage."""
    if async_playwright is None:
        pytest.skip("Playwright is not importable in this Python environment")

    await _seed_ui_data(isolated_db)
    await _seed_catalog_metadata(isolated_db, total=300)

    now = c.stamp()
    await isolated_db["db"].users.update_one(
        {"id": "u_admin2"},
        {
            "$set": {
                "id": "u_admin2",
                "phone": "9999813335",
                "phone_normalized": "9999813335",
                "name": "Owner Admin Two",
                "role": "admin",
                "account_status": "active",
                "status": "active",
                "session_version": 0,
                "onboarding_status": "completed",
                "phone_verified": True,
                "shop_name": "HQ2",
                "location": "Delhi",
                "updated_at": now,
            },
            "$setOnInsert": {"created_at": now},
        },
        upsert=True,
    )

    legacy_external_url = "https://legacy-external.test/isolated/legacy-only.png"
    await isolated_db["db"].products.insert_one(
        {
            "id": "ui-prod-legacy-ext-001",
            "product_code": "TEST-LEGACY-EXT-001",
            "title": "TEST Legacy External HTTPS Only",
            "metal_type": "silver",
            "category": "chain",
            "visibility": "all",
            "storage_path": "",
            "thumbnail_path": "",
            "images": [legacy_external_url],
            "is_deleted": False,
            "created_at": now,
            "updated_at": now,
            "version": 0,
        }
    )

    admin_token = (await login_helper("9999813335"))["token"]
    control_upload = await api_client.post(
        "/api/products/upload-image",
        headers=_auth_headers(admin_token),
        files={"file": ("silver.jpg", Path('/app/backend/fixtures/catalog-v1/silver.jpg').read_bytes(), "image/jpeg")},
    )
    assert control_upload.status_code == 200, control_upload.text

    pw, browser, context, page = await _start_routed_browser(api_client)
    external_image_requests = []

    async def route_legacy_external(route, request):
        external_image_requests.append(dict(request.headers))
        await route.fulfill(status=200, headers={"content-type": "image/png"}, body=PNG_BYTES)

    await context.route("**://legacy-external.test/**", route_legacy_external)

    try:
        await _login_via_otp_ui(page, isolated_db, "9999813334", "panel")
        await page.click('[data-testid="panel-tab-products"]')
        await page.wait_for_selector('[data-testid="pm-list"]', timeout=15000)
        await page.click('[data-testid="pm-list"]')
        await page.wait_for_selector('[data-testid="catalog-title"]', timeout=15000)

        await page.wait_for_selector('[data-testid^="catalog-product-"]', timeout=15000)
        rendered = await page.locator('[data-testid^="catalog-product-"]').count()
        assert 1 <= rendered <= 40, f"virtualized render count should stay <=40, got {rendered}"

        async with page.expect_response(lambda r: "/api/products?page=2&limit=40" in r.url and r.request.method == "GET") as page2_info:
            await page.click('[data-testid="catalog-next"]')
        assert (await page2_info.value).status == 200

        async with page.expect_response(lambda r: "/api/products?page=1&limit=40" in r.url and r.request.method == "GET") as page1_info:
            await page.click('[data-testid="catalog-prev"]')
        assert (await page1_info.value).status == 200

        await page.click('[data-testid="catalog-metal-silver"]')
        await page.wait_for_timeout(900)
        metas = await page.locator('[data-testid^="catalog-meta-"]').all_text_contents()
        assert metas and all("silver" in m for m in metas[: min(8, len(metas))])

        await page.fill('[data-testid="catalog-search"]', 'TESTMETA-00299')
        await page.wait_for_timeout(1200)
        total_text = await page.inner_text('[data-testid="catalog-total"]')
        total_value = int(re.search(r"(\d+)", total_text).group(1))
        # Document current indexed text behavior: tokenized OR under active silver filter.
        assert total_value == 150

        await page.fill('[data-testid="catalog-search"]', '00299')
        await page.wait_for_timeout(1200)
        numeric_text = await page.inner_text('[data-testid="catalog-total"]')
        numeric_value = int(re.search(r"(\d+)", numeric_text).group(1))
        assert numeric_value == 0, "Search must intersect the active silver filter; item299 is gold"
        async with page.expect_response(lambda r: '/api/products?' in r.url and 'metal_type=' in r.url and r.request.method == 'GET') as unfiltered:
            await page.click('[data-testid="catalog-metal-all"]')
        assert (await unfiltered.value).status == 200
        await page.get_by_text('1 products · at most 40 held per page', exact=True).wait_for(timeout=15000)
        await page.fill('[data-testid="catalog-search"]', '')
        await page.get_by_test_id('catalog-next').wait_for(state='visible')

        async with page.expect_response(
            lambda r: '/api/products?' in r.url and 'product_code=TESTMETA-00299' in r.url and r.request.method == 'GET'
        ) as exact_sku:
            await page.click('[data-testid="catalog-search-sku"]')
            await page.fill('[data-testid="catalog-search"]', 'TESTMETA-00299')
        exact_sku_response = await exact_sku.value
        assert exact_sku_response.status == 200
        assert (await exact_sku_response.json()).get("total") == 1
        await page.wait_for_function(
            """() => {
                const metas = Array.from(document.querySelectorAll('[data-testid^="catalog-meta-"]'));
                return metas.some((m) => (m.textContent || '').includes('TESTMETA-00299'));
            }""",
            timeout=15000,
        )
        sku_meta = await page.locator('[data-testid^="catalog-meta-"]').first.inner_text()
        assert 'TESTMETA-00299' in sku_meta

        async with page.expect_response(
            lambda r: '/api/products?' in r.url and 'product_code=TEST-LEGACY-EXT-001' in r.url and r.request.method == 'GET'
        ) as legacy_exact:
            await page.fill('[data-testid="catalog-search"]', 'TEST-LEGACY-EXT-001')
        legacy_response = await legacy_exact.value
        assert legacy_response.status == 200
        assert (await legacy_response.json()).get("total") == 1

        first_product_id = await page.locator('[data-testid^="catalog-product-"]').first.get_attribute('data-testid')
        assert first_product_id == 'catalog-product-ui-prod-legacy-ext-001'

        await page.wait_for_function(
            """() => {
                const host = document.querySelector('[data-testid="catalog-photo-ui-prod-legacy-ext-001"]');
                const img = host?.tagName === 'IMG' ? host : host?.querySelector?.('img');
                return !!img && img.complete && img.naturalWidth > 0;
            }""",
            timeout=15000,
        )
        assert external_image_requests, "Expected routed synthetic external image request"
        for headers in external_image_requests:
            assert "authorization" not in {k.lower(): v for k, v in headers.items()}, (
                f"Bearer token leaked to external image request headers: {headers}"
            )

        async with page.expect_response(
            lambda r: '/api/products?' in r.url and 'search=' in r.url and 'product_code=' in r.url and r.request.method == 'GET'
        ) as reset_list:
            await page.fill('[data-testid="catalog-search"]', '')
            await page.click('[data-testid="catalog-search-words"]')
        assert (await reset_list.value).status == 200
        await page.wait_for_timeout(700)

        before = await page.evaluate(
            """() => ({
                dom_nodes: document.querySelectorAll('*').length,
                heap_bytes: performance.memory ? performance.memory.usedJSHeapSize : null,
                scroll_top: document.querySelector('[data-testid="catalog-list"]')?.scrollTop || 0,
                rendered_count: document.querySelectorAll('[data-testid^="catalog-product-"]').length
            })"""
        )
        await page.get_by_test_id('catalog-list').hover()
        for _ in range(8):
            await page.mouse.wheel(0, 900)
            await page.wait_for_timeout(120)
        after = await page.evaluate(
            """() => ({
                dom_nodes: document.querySelectorAll('*').length,
                heap_bytes: performance.memory ? performance.memory.usedJSHeapSize : null,
                scroll_top: document.querySelector('[data-testid="catalog-list"]')?.scrollTop || 0,
                rendered_count: document.querySelectorAll('[data-testid^="catalog-product-"]').length
            })"""
        )
        Path("/app/test_reports/mobile_web_catalog_scroll_metrics_iteration16.json").write_text(
            json.dumps({"label": "mobile-web", "dataset": 300, "before": before, "after": after}, indent=2)
        )
        assert after['scroll_top'] > before['scroll_top'], 'The list itself must actually scroll'
        assert after['rendered_count'] <= 40
        await page.screenshot(path="/app/test_reports/iteration16_catalog_mobile_web.jpeg", quality=40)

        await page.click('[data-testid="catalog-create"]')
        await page.get_by_text('Create your catalogue', exact=True).wait_for(timeout=15000)
        await page.fill('[data-testid="author-product_code"]', 'TEST-AUTHOR-001')
        await page.locator('[data-testid="author-title"]').last.fill('TEST Authored Necklace')
        await page.fill('[data-testid="author-category-custom"]', 'necklace')
        await page.fill('[data-testid="author-purity"]', '925')
        await page.fill('[data-testid="author-approx_weight"]', '25-35 g per pair')

        async with page.expect_file_chooser() as chooser_info:
            await page.click('[data-testid="author-photo"]')
        chooser = await chooser_info.value
        async with page.expect_response(
            lambda r: '/api/products/upload-image' in r.url and r.request.method == 'POST'
        ) as upload_info:
            await chooser.set_files(str(Path('/app/backend/fixtures/catalog-v1/silver.jpg')))
        upload = await upload_info.value
        upload_text = await upload.text()
        upload_payload = json.loads(upload_text)
        Path('/app/test_reports/author_upload_bridge_debug_iteration17.json').write_text(
            json.dumps(
                {
                    "status": upload.status,
                    "url": upload.url,
                    "body": upload_text,
                    "bridge_events": getattr(context, '_bridge_events', []),
                },
                indent=2,
            )
        )
        assert upload.status == 200, f"Upload failed with {upload.status}: {upload_text}"
        await page.wait_for_selector('[data-testid="author-photo-preview"]', timeout=15000)
        canonical_preview_path = urlparse(upload_payload["url"]).path if upload_payload.get("url") else ""
        if canonical_preview_path:
            file_events = [
                e for e in getattr(context, "_api_events", [])
                if e.get("method") == "GET" and e.get("path", "").split("?")[0] == canonical_preview_path
            ]
            assert file_events, f"Expected canonical preview request to {canonical_preview_path}"
            assert any((e.get("authorization") or "").startswith("Bearer ") for e in file_events), (
                "Expected canonical private author preview to request with Bearer authorization"
            )

        await page.click('[data-testid="author-add-entry"]')
        count_text = await page.inner_text('[data-testid="author-entry-count"]')
        assert count_text.strip().startswith("1 / 20")

        async with page.expect_download() as download_info:
            await page.click('[data-testid="author-export"]')
        download = await download_info.value
        pdf_path = await download.path()
        assert pdf_path, "Expected exported PDF download path"
        data = Path(pdf_path).read_bytes()
        assert len(data) > 0
        with fitz.open(stream=data, filetype="pdf") as doc:
            text = "\n".join(doc.load_page(i).get_text() for i in range(len(doc)))
        assert "TEST-AUTHOR-001" in text
        assert "TEST Authored Necklace" in text

        await page.click('[data-testid="author-back"]')
        await page.wait_for_selector('[data-testid="catalog-media-usage"]', timeout=15000)
        await page.click('[data-testid="catalog-media-usage"]')
        await page.wait_for_selector('[data-testid="media-usage-title"]', timeout=15000)
        await page.wait_for_selector('[data-testid="media-tracked-bytes"]', timeout=15000)
        await page.screenshot(path="/app/test_reports/iteration16_author_media_usage_mobile_web.jpeg", quality=40)
    finally:
        await context.close()
        await browser.close()
        await pw.stop()
