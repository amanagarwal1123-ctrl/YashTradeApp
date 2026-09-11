"""Authenticated mobile-web UI coverage using local Playwright + shared ASGI transport.

# Module coverage: admin panel/routes + telecaller workspace/leads + billing rates/slabs + customer home/gallery + reviewed PDF flow.
"""

from __future__ import annotations

import asyncio
import base64
import json
from pathlib import Path
from urllib.parse import urlparse

import pytest

from shared import core as c
from shared import pdf_jobs as jobs

try:
    from playwright.async_api import async_playwright
except Exception:  # pragma: no cover - handled with skip in tests
    async_playwright = None


FRONTEND_URL = "https://yash-tryon-test.preview.emergentagent.com"
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


async def _start_routed_browser(api_client):
    playwright = await async_playwright().start()
    browser = await playwright.chromium.launch(headless=True, args=["--disable-dev-shm-usage"])
    context = await browser.new_context(viewport={"width": 390, "height": 844}, accept_downloads=True)
    page = await context.new_page()

    async def route_to_asgi(route, request):
        parsed = urlparse(request.url)
        path = parsed.path + (f"?{parsed.query}" if parsed.query else "")
        headers = {k: v for k, v in request.headers.items() if k.lower() != "host"}
        response = await api_client.request(
            request.method,
            path,
            headers=headers,
            content=request.post_data_buffer,
        )
        safe_headers = {
            k: v
            for k, v in response.headers.items()
            if k.lower() not in {"content-encoding", "transfer-encoding", "connection", "content-length"}
        }
        await route.fulfill(status=response.status_code, headers=safe_headers, body=response.content)

    await context.route("**/api/**", route_to_asgi)
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
        updated_fields = dict(editable["fields"])
        updated_fields["title"] = "TEST UI Corrected Title"
        await page.fill(f'[data-testid="pdf-fields-{editable["id"]}"]', json.dumps(updated_fields))
        await page.click(f'[data-testid="pdf-save-fields-{editable["id"]}"]')
        await page.get_by_text("TEST UI Corrected Title", exact=True).wait_for(state="visible")
        await page.click(f'[data-testid="pdf-edit-{editable["id"]}"]')

        crop = editable.get("crop_points") or [20, 20, 120, 120]
        crop_input = page.locator(f'[data-testid="pdf-crop-{editable["id"]}"]')
        crop_save = page.locator(f'[data-testid="pdf-save-crop-{editable["id"]}"]')
        await crop_input.first.wait_for(state="visible")
        await crop_input.first.fill(", ".join(str(n) for n in crop))
        async with page.expect_response(lambda response: response.request.method == "PATCH" and f'/rows/{editable["id"]}' in response.url) as corrected:
            await crop_save.first.click()
        assert (await corrected.value).status == 200
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
