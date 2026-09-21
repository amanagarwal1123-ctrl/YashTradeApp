"""Iteration 39 - Independent-review closeout browser Playwright.
Runs C7 (admin composer + customer inbox), C3 (complete->reopen->recomplete),
C5 (staff disable cascade), C4 (customer delete step-up), C6 (discovery dedup).
Reviewer keys are read from /tmp/yash-private/e2e-review-keys.json in code only
- never printed, logged, screenshotted, nor written to any report.
"""
import asyncio, json, re, time, os, sys, traceback
from pathlib import Path
from playwright.async_api import async_playwright

BASE = "https://app-first-signin.preview.emergentagent.com"
REPORT_DIR = Path("/app/test_reports")
KEY_FILE = Path("/tmp/yash-private/e2e-review-keys.json")
VIEWPORT = {"width": 390, "height": 844}

RESULTS = {}

def keys():
    return json.loads(KEY_FILE.read_text())

async def dialog_handler(dialog):
    try:
        await dialog.accept()
    except Exception:
        pass

async def reviewer_sign_in(page, reviewer_id, land_selector, note=""):
    await page.goto(f"{BASE}/login", wait_until="domcontentloaded")
    await page.wait_for_selector("#root", timeout=15000)
    await page.wait_for_selector('[data-testid=login-help-link]', timeout=15000)
    await page.click('[data-testid=login-help-link]', force=True)
    await page.wait_for_selector('[data-testid=help-review-access-link]', timeout=15000)
    await page.click('[data-testid=help-review-access-link]', force=True)
    await page.wait_for_selector('[data-testid=reviewer-id-input]', timeout=15000)
    await page.fill('[data-testid=reviewer-id-input]', reviewer_id)
    await page.fill('[data-testid=reviewer-key-input]', keys()[reviewer_id])
    await page.click('[data-testid=review-login-btn]', force=True)
    # Wait for banner text
    await page.wait_for_function(
        "() => document.body && document.body.innerText.includes('STORE-REVIEW ENVIRONMENT')",
        timeout=25000,
    )
    if land_selector:
        await page.wait_for_selector(land_selector, timeout=20000)

async def open_context(pw, role, land_selector):
    ctx = await pw.chromium.launch_persistent_context(
        user_data_dir=f"/tmp/pw_{role}_{int(time.time())}",
        headless=True,
        viewport=VIEWPORT,
        ignore_https_errors=True,
    ) if False else None
    browser = await pw.chromium.launch(headless=True)
    ctx = await browser.new_context(viewport=VIEWPORT)
    page = await ctx.new_page()
    page.on("dialog", lambda d: asyncio.create_task(dialog_handler(d)))
    await reviewer_sign_in(page, role, land_selector)
    return browser, ctx, page

async def screenshot(page, name):
    p = REPORT_DIR / f"iter39_{name}.jpeg"
    try:
        await page.screenshot(path=str(p), quality=40, full_page=False, type="jpeg")
    except Exception as e:
        print(f"[screenshot fail {name}] {e}")

def record(check, status, details=None):
    RESULTS[check] = {"status": status, "details": details or {}}
    print(f"::{check}:: {status} :: {json.dumps(details or {})[:400]}")

# ---------------- C7 ----------------
async def run_c7(pw):
    print("=== C7 admin notifications composer ===")
    admin_browser, admin_ctx, admin = await open_context(pw, "store-review-admin", '[data-testid=panel-tab-requests]')
    # Track network
    filters_status = {}
    products_status = {}
    audience_resp = {}
    save_resp = {}
    put_resp = {}
    send_resp = {}
    detail_resp = {}
    async def on_response(resp):
        try:
            u = resp.url
            if "/api/admin/notifications/filters" in u:
                filters_status["s"] = resp.status
            elif "/api/products?limit=24" in u:
                products_status["s"] = resp.status
            elif "/api/admin/notifications/audience" in u and resp.request.method == "POST":
                audience_resp["s"] = resp.status
                try: audience_resp["j"] = await resp.json()
                except: pass
            elif re.search(r"/api/admin/notifications/campaigns$", u) and resp.request.method == "POST":
                save_resp["s"] = resp.status
                try: save_resp["j"] = await resp.json()
                except: pass
            elif re.search(r"/api/admin/notifications/campaigns/[^/]+/send$", u) and resp.request.method == "POST":
                send_resp["s"] = resp.status
                try: send_resp["j"] = await resp.json()
                except: pass
            elif re.search(r"/api/admin/notifications/campaigns/[^/]+$", u) and resp.request.method == "PUT":
                put_resp["s"] = resp.status
            elif re.search(r"/api/admin/notifications/campaigns/[^/]+$", u) and resp.request.method == "GET":
                detail_resp["s"] = resp.status
        except Exception:
            pass
    admin.on("response", on_response)

    # Click panel-tab-notifications
    try:
        await admin.wait_for_selector('[data-testid=panel-tab-notifications]', timeout=15000)
        await admin.click('[data-testid=panel-tab-notifications]', force=True)
    except Exception as e:
        record("C7", "FAIL", {"reason": f"panel-tab-notifications not clickable: {e}"})
        await admin_browser.close()
        return

    try:
        await admin.wait_for_selector('[data-testid=admin-notifications-title]', timeout=15000)
    except Exception as e:
        # Check for OTP gate
        otp_visible = await admin.is_visible('[data-testid=panel-send-otp]')
        record("C7_composer_reach", "FAIL", {"reason": f"admin-notifications-title not visible: {e}", "panel_otp_gate": otp_visible})
        await screenshot(admin, "c7_composer_gate")
        await admin_browser.close()
        return
    # Ensure OTP gate NOT present
    otp_gate = await admin.is_visible('[data-testid=panel-send-otp]')
    await screenshot(admin, "c7_composer")

    ts = int(time.time())
    title = f"Recheck C7 {ts}"
    await admin.fill('[data-testid=notif-title]', title)
    await admin.fill('[data-testid=notif-body]', "Synthetic campaign (store review)")
    # inspect
    await admin.click('[data-testid=notif-inspect]', force=True)
    try:
        await admin.wait_for_selector('[data-testid=notif-audience-count]', timeout=15000)
        aud_txt = await admin.text_content('[data-testid=notif-audience-count]')
    except Exception as e:
        aud_txt = None
    # save draft
    await admin.click('[data-testid=notif-save-draft]', force=True)
    await admin.wait_for_timeout(2000)
    campaign_id = None
    if save_resp.get("j"):
        campaign_id = save_resp["j"].get("id") or save_resp["j"].get("campaign_id") or save_resp["j"].get("_id")
    # send
    try:
        await admin.click('[data-testid=notif-send]', force=True)
        await admin.wait_for_timeout(4500)
    except Exception as e:
        record("C7_send_click", "FAIL", {"reason": str(e)})
    # If campaign id not from save, try from send response
    if not campaign_id and send_resp.get("j"):
        campaign_id = send_resp["j"].get("id") or send_resp["j"].get("campaign_id")
    await screenshot(admin, "c7_history")
    if campaign_id:
        try:
            await admin.wait_for_selector(f'[data-testid=notif-campaign-{campaign_id}]', timeout=8000)
            row_visible = True
        except Exception:
            row_visible = False
        try:
            await admin.click(f'[data-testid=notif-campaign-detail-{campaign_id}]', force=True)
            await admin.wait_for_timeout(1500)
        except Exception:
            pass
    else:
        row_visible = None

    record("C7_admin_composer", "PASS" if filters_status.get("s") == 200 and save_resp.get("s") == 200 else "FAIL", {
        "panel_otp_gate_visible": otp_gate,
        "filters_status": filters_status.get("s"),
        "products_status": products_status.get("s"),
        "audience_status": audience_resp.get("s"),
        "audience_count_text": aud_txt,
        "save_status": save_resp.get("s"),
        "put_status": put_resp.get("s"),
        "send_status": send_resp.get("s"),
        "send_response": send_resp.get("j"),
        "detail_status": detail_resp.get("s"),
        "campaign_id": campaign_id,
        "history_row_visible": row_visible,
    })
    await admin_browser.close()

    # customer inbox
    cust_browser, cust_ctx, cust = await open_context(pw, "store-review-customer", '[data-testid=notifications-btn]')
    inbox_status = {}
    def on_r2(resp):
        if "/api/notifications/inbox" in resp.url:
            inbox_status["s"] = resp.status
    cust.on("response", on_r2)
    await cust.click('[data-testid=notifications-btn]', force=True)
    await cust.wait_for_timeout(4000)
    # Find notification row with "Recheck C7"
    found = False
    try:
        rows = await cust.query_selector_all('[data-testid^=notification-]')
        for r in rows:
            t = await r.text_content()
            if t and "Recheck C7" in t:
                found = True
                break
    except Exception as e:
        pass
    await screenshot(cust, "c7_customer_inbox")
    record("C7_customer_inbox", "PASS" if found else "FAIL", {"inbox_status": inbox_status.get("s"), "row_found": found, "campaign_title": title})
    await cust_browser.close()

# ---------------- C3 ----------------
async def run_c3(pw):
    print("=== C3 complete->reopen->recomplete ===")
    t2_browser, _, t2 = await open_context(pw, "store-review-telecaller-2", '[data-testid=requests-title]')
    # Grab first non-held request row
    await t2.wait_for_timeout(1500)
    rid = None
    rows = await t2.query_selector_all('[data-testid^=request-row-]')
    for r in rows:
        tid = await r.get_attribute("data-testid")
        candidate = tid.replace("request-row-", "") if tid else None
        # click it
        await r.click(force=True)
        await t2.wait_for_timeout(1500)
        held = await t2.is_visible('[data-testid=request-held-by-other]')
        if held:
            # go back if there is a back button; otherwise close via clicking outside
            back = await t2.query_selector('[data-testid=request-detail-back]')
            if back:
                await back.click(force=True)
                await t2.wait_for_timeout(600)
            continue
        rid = candidate
        break
    if not rid:
        record("C3", "FAIL", {"reason": "no unheld pending row"})
        await t2_browser.close()
        return

    patch_events = []
    def on_resp(resp):
        try:
            u = resp.url
            m = re.search(r"/api/requests/([^/?]+)(\?|$)", u)
            if m and resp.request.method == "PATCH":
                body = None
                try: body = resp.request.post_data_json
                except: pass
                patch_events.append({"rid": m.group(1), "status": resp.status, "body": body})
        except Exception:
            pass
    t2.on("response", on_resp)

    # claim
    await t2.click('[data-testid=request-claim]', force=True)
    await t2.wait_for_selector('[data-testid=request-work-card]', timeout=15000)
    # outcome converted
    await t2.click('[data-testid=request-outcome-converted]', force=True)
    await t2.wait_for_timeout(700)
    # complete
    await t2.click('[data-testid=request-complete]', force=True)
    # wait for PATCH action=complete on this rid
    end = time.time() + 20
    complete_ok = False
    while time.time() < end:
        for ev in patch_events:
            if ev["rid"] == rid and (ev.get("body") or {}).get("action") == "complete" and ev["status"] == 200:
                complete_ok = True
                break
        if complete_ok:
            break
        await t2.wait_for_timeout(500)
    await t2.wait_for_timeout(1500)
    await screenshot(t2, "c3_completed")
    head_txt = ""
    try:
        head_txt = await t2.text_content('[data-testid=request-detail-head]') or ""
    except Exception:
        pass
    record("C3_t2_complete", "PASS" if complete_ok else "FAIL", {"rid": rid, "head_text": head_txt[:160]})
    await t2_browser.close()

    # ---- admin verifies today total N1, reopens ----
    adm_browser, _, adm = await open_context(pw, "store-review-admin", '[data-testid=panel-tab-requests]')
    a_patch = []
    def on_a(resp):
        try:
            m = re.search(r"/api/requests/([^/?]+)(\?|$)", resp.url)
            if m and resp.request.method == "PATCH":
                body = None
                try: body = resp.request.post_data_json
                except: pass
                a_patch.append({"rid": m.group(1), "status": resp.status, "body": body})
        except Exception:
            pass
    adm.on("response", on_a)
    await adm.click('[data-testid=panel-tab-reports]', force=True)
    await adm.wait_for_selector('[data-testid=report-today]', timeout=15000)
    await adm.click('[data-testid=report-today]', force=True)
    await adm.wait_for_timeout(2000)
    total_before = await adm.text_content('[data-testid=report-total]') or ""
    n1_m = re.search(r"(\d+)", total_before)
    N1 = int(n1_m.group(1)) if n1_m else None
    row_vis = await adm.is_visible('[data-testid=report-row-review-telecaller-0002]')
    await screenshot(adm, "c3_report_before")

    # Go to requests -> find rid row (open by clicking)
    await adm.click('[data-testid=panel-tab-requests]', force=True)
    await adm.wait_for_timeout(1500)
    # Try to filter completed - just try clicking the row directly if visible
    reopen_ok = False
    row = await adm.query_selector(f'[data-testid=request-row-{rid}]')
    if not row:
        # try to find a filter button
        for tid in ["requests-filter-completed", "requests-filter-resolved", "requests-filter-all", "requests-filter-history"]:
            btn = await adm.query_selector(f'[data-testid={tid}]')
            if btn:
                await btn.click(force=True)
                await adm.wait_for_timeout(1200)
                row = await adm.query_selector(f'[data-testid=request-row-{rid}]')
                if row:
                    break
    if row:
        await row.click(force=True)
        await adm.wait_for_selector('[data-testid=request-admin-card]', timeout=10000)
        await adm.fill('[data-testid=request-admin-reason]', "customer called back (recheck)")
        await adm.click('[data-testid=request-reopen]', force=True)
        # wait for PATCH action=reopen
        end = time.time() + 15
        while time.time() < end:
            for ev in a_patch:
                if ev["rid"] == rid and (ev.get("body") or {}).get("action") == "reopen" and ev["status"] == 200:
                    reopen_ok = True
                    break
            if reopen_ok:
                break
            await adm.wait_for_timeout(500)
    else:
        record("C3_admin_find_row", "FAIL", {"reason": f"row for rid {rid} not found in admin requests"})
    # Recount
    await adm.click('[data-testid=panel-tab-reports]', force=True)
    await adm.wait_for_timeout(1200)
    await adm.click('[data-testid=report-today]', force=True)
    await adm.wait_for_timeout(2500)
    total_after = await adm.text_content('[data-testid=report-total]') or ""
    n2_m = re.search(r"(\d+)", total_after)
    N2 = int(n2_m.group(1)) if n2_m else None
    await screenshot(adm, "c3_report_after_reopen")
    record("C3_admin_reopen", "PASS" if reopen_ok and (N1 is not None and N2 == N1 - 1) else "FAIL", {
        "rid": rid, "N1": N1, "N2_after_reopen": N2, "row_visible_before": row_vis,
        "reopen_ok": reopen_ok,
    })
    await adm_browser.close()

    # ---- t2 re-completes ----
    t2b_browser, _, t2b = await open_context(pw, "store-review-telecaller-2", '[data-testid=requests-title]')
    p2 = []
    def on_t(resp):
        try:
            m = re.search(r"/api/requests/([^/?]+)(\?|$)", resp.url)
            if m and resp.request.method == "PATCH":
                body = None
                try: body = resp.request.post_data_json
                except: pass
                p2.append({"rid": m.group(1), "status": resp.status, "body": body})
        except Exception: pass
    t2b.on("response", on_t)
    await t2b.wait_for_timeout(1500)
    row = await t2b.query_selector(f'[data-testid=request-row-{rid}]')
    recomplete_ok = False
    if row:
        await row.click(force=True)
        await t2b.wait_for_timeout(1500)
        claim_btn = await t2b.query_selector('[data-testid=request-claim]')
        if claim_btn:
            await claim_btn.click(force=True)
            await t2b.wait_for_selector('[data-testid=request-work-card]', timeout=15000)
        await t2b.click('[data-testid=request-outcome-converted]', force=True)
        await t2b.wait_for_timeout(700)
        await t2b.click('[data-testid=request-complete]', force=True)
        end = time.time() + 20
        while time.time() < end:
            for ev in p2:
                if ev["rid"] == rid and (ev.get("body") or {}).get("action") == "complete" and ev["status"] == 200:
                    recomplete_ok = True
                    break
            if recomplete_ok: break
            await t2b.wait_for_timeout(500)
    await t2b_browser.close()

    # verify admin sees N1 again
    adm2_browser, _, adm2 = await open_context(pw, "store-review-admin", '[data-testid=panel-tab-requests]')
    await adm2.click('[data-testid=panel-tab-reports]', force=True)
    await adm2.wait_for_selector('[data-testid=report-today]', timeout=15000)
    await adm2.click('[data-testid=report-today]', force=True)
    await adm2.wait_for_timeout(2500)
    total_final = await adm2.text_content('[data-testid=report-total]') or ""
    n3_m = re.search(r"(\d+)", total_final)
    N3 = int(n3_m.group(1)) if n3_m else None
    await screenshot(adm2, "c3_report_after_recomplete")
    record("C3_recomplete", "PASS" if recomplete_ok and N3 == N1 else "FAIL", {
        "rid": rid, "N1": N1, "N3_after_recomplete": N3, "recomplete_patch_ok": recomplete_ok,
    })
    await adm2_browser.close()

# ---------------- C5 ----------------
async def run_c5(pw):
    print("=== C5 staff disable cascade ===")
    t2_browser, _, t2 = await open_context(pw, "store-review-telecaller-2", '[data-testid=requests-title]')
    t2_401 = {"seen": False}
    def on_r(resp):
        if resp.status == 401 and "/api/" in resp.url:
            t2_401["seen"] = True
    t2.on("response", on_r)
    # admin disables
    adm_browser, _, adm = await open_context(pw, "store-review-admin", '[data-testid=panel-tab-requests]')
    disable_status = None
    enable_status = None
    def on_a(resp):
        nonlocal disable_status, enable_status
        u = resp.url
        if "/api/integrations/staff/review-telecaller-0002" in u and resp.request.method == "PATCH":
            body = None
            try: body = resp.request.post_data_json
            except: pass
            if (body or {}).get("status") == "inactive":
                disable_status = resp.status
            elif (body or {}).get("status") == "active":
                enable_status = resp.status
    adm.on("response", on_a)
    await adm.click('[data-testid=panel-tab-executives]', force=True)
    await adm.wait_for_selector('[data-testid=exec-card-review-telecaller-0002]', timeout=15000)
    await adm.click('[data-testid=account-disable-review-telecaller-0002]', force=True)
    await adm.wait_for_timeout(3000)
    stat = ""
    try: stat = await adm.text_content('[data-testid=exec-status-review-telecaller-0002]') or ""
    except: pass
    await screenshot(adm, "c5_disabled")

    # trigger action on t2
    try:
        alerts_btn = await t2.query_selector('[data-testid=requests-alerts]')
        if alerts_btn:
            await alerts_btn.click(force=True)
        else:
            rows = await t2.query_selector_all('[data-testid^=request-row-]')
            if rows:
                await rows[0].click(force=True)
    except Exception:
        pass
    await t2.wait_for_timeout(5000)
    forced_out = await t2.is_visible('[data-testid=login-help-link]')
    await screenshot(t2, "c5_forced_signout")
    await t2_browser.close()

    # re-enable
    await adm.click('[data-testid=account-enable-review-telecaller-0002]', force=True)
    await adm.wait_for_timeout(3000)
    stat2 = ""
    try: stat2 = await adm.text_content('[data-testid=exec-status-review-telecaller-0002]') or ""
    except: pass
    await screenshot(adm, "c5_reenabled")
    await adm_browser.close()

    # new context signs in again
    signin_ok = False
    try:
        t2b_browser, _, t2b = await open_context(pw, "store-review-telecaller-2", '[data-testid=requests-title]')
        signin_ok = True
        await t2b_browser.close()
    except Exception as e:
        record("C5_reenable_signin", "FAIL", {"reason": str(e)})
    record("C5", "PASS" if (disable_status == 200 and forced_out and t2_401["seen"] and enable_status == 200 and signin_ok) else "FAIL", {
        "disable_status": disable_status, "exec_status_after_disable": stat[:80],
        "t2_saw_401": t2_401["seen"], "t2_login_visible": forced_out,
        "enable_status": enable_status, "exec_status_after_enable": stat2[:80],
        "t2_reenable_signin_ok": signin_ok,
    })

# ---------------- C4 ----------------
async def run_c4(pw):
    print("=== C4 customer delete step-up ===")
    c_browser, _, c = await open_context(pw, "store-review-customer", '[data-testid=notifications-btn]')
    req_status = {}
    conf_status = {}
    def on_r(resp):
        if "/api/auth/delete-account/request" in resp.url and resp.request.method == "POST":
            req_status["s"] = resp.status
        elif "/api/auth/delete-account/confirm" in resp.url and resp.request.method == "POST":
            conf_status["s"] = resp.status
    c.on("response", on_r)
    # tap Profile tab
    prof = await c.query_selector('[data-testid=tab-profile]') or await c.query_selector('text="Profile"')
    if prof:
        await prof.click(force=True)
    await c.wait_for_selector('[data-testid=delete-account-btn]', timeout=15000)
    await c.click('[data-testid=delete-account-btn]', force=True)
    await c.wait_for_selector('[data-testid=delete-send-otp]', timeout=15000)
    await c.click('[data-testid=delete-send-otp]', force=True)
    await c.wait_for_selector('[data-testid=delete-simulated-otp]', timeout=15000)
    otp_block_txt = await c.text_content('[data-testid=delete-simulated-otp]') or ""
    m = re.search(r"(\d{4})", otp_block_txt)
    otp = m.group(1) if m else None
    # never print otp
    await screenshot(c, "c4_stepup")
    if not otp:
        record("C4", "FAIL", {"reason": "no 4-digit otp in delete-simulated-otp block"})
        await c_browser.close()
        return
    await c.fill('[data-testid=delete-otp-input]', otp)
    await c.click('[data-testid=delete-confirm]', force=True)
    await c.wait_for_timeout(4000)
    await screenshot(c, "c4_after_delete_login")
    login_visible = await c.is_visible('[data-testid=login-help-link]')
    # sign in again
    await c_browser.close()

    c2_browser = await pw.chromium.launch(headless=True)
    ctx2 = await c2_browser.new_context(viewport=VIEWPORT)
    page2 = await ctx2.new_page()
    page2.on("dialog", lambda d: asyncio.create_task(dialog_handler(d)))
    login_body = {}
    def on_r2(resp):
        if "/api/auth/review/login" in resp.url and resp.request.method == "POST":
            async def cap():
                try:
                    login_body["j"] = await resp.json()
                    login_body["s"] = resp.status
                except: pass
            asyncio.create_task(cap())
    page2.on("response", on_r2)
    try:
        await reviewer_sign_in(page2, "store-review-customer", None)
        await page2.wait_for_timeout(3500)
        await screenshot(page2, "c4_recreated_home")
        home_banner = await page2.evaluate("() => document.body.innerText.includes('STORE-REVIEW ENVIRONMENT')")
    except Exception as e:
        home_banner = False
    profile_recreated = (login_body.get("j") or {}).get("profile_recreated")
    record("C4", "PASS" if req_status.get("s") == 200 and conf_status.get("s") == 200 and login_visible and profile_recreated is True and home_banner else "FAIL", {
        "delete_request_status": req_status.get("s"),
        "delete_confirm_status": conf_status.get("s"),
        "login_visible_after_delete": login_visible,
        "profile_recreated": profile_recreated,
        "home_banner_after_recreate": home_banner,
    })
    await c2_browser.close()

# ---------------- C6 ----------------
async def run_c6(pw):
    print("=== C6 discovery impressions ===")
    c_browser = await pw.chromium.launch(headless=True)
    ctx = await c_browser.new_context(viewport=VIEWPORT)
    page = await ctx.new_page()
    page.on("dialog", lambda d: asyncio.create_task(dialog_handler(d)))

    sess1 = {}
    imp_posts = []
    def on_r(resp):
        u = resp.url
        if "/api/discovery/sessions" in u and resp.request.method == "POST":
            async def cap():
                try:
                    sess1["j"] = await resp.json()
                    sess1["s"] = resp.status
                except: pass
            asyncio.create_task(cap())
        elif "/api/discovery/impressions" in u and resp.request.method == "POST":
            body = None
            try: body = resp.request.post_data_json
            except: pass
            imp_posts.append({"status": resp.status, "body": body})
    page.on("response", on_r)
    await reviewer_sign_in(page, "store-review-customer", None)
    # Wait for home discovery note
    try:
        await page.wait_for_selector('[data-testid=home-discovery-note]', timeout=15000)
    except Exception:
        pass
    note_txt = await page.text_content('[data-testid=home-discovery-note]') if await page.query_selector('[data-testid=home-discovery-note]') else ""
    await page.wait_for_timeout(2500)
    S1 = sess1.get("j", {}) or {}
    s1_id = S1.get("session_id")
    U1 = S1.get("unseen")
    Se1 = S1.get("seen")
    s1_products = S1.get("products") or []
    # dwell
    await page.wait_for_timeout(2500)
    for _ in range(3):
        await page.evaluate("window.scrollBy(0, 300)")
        await page.wait_for_timeout(1500)
    await page.evaluate("window.scrollTo(0, 0)")
    await page.wait_for_timeout(4000)
    await screenshot(page, "c6_session1")

    posted_ids = []
    for p in imp_posts:
        for pid in (p.get("body") or {}).get("product_ids", []) or []:
            posted_ids.append(pid)
    all_in_s1 = all(any(pr.get("id") == pid for pr in s1_products) for pid in posted_ids) if posted_ids else False
    no_dup = len(posted_ids) == len(set(posted_ids))
    session_ids_ok = all((p.get("body") or {}).get("session_id") == s1_id for p in imp_posts)
    seen_before_map = {pr.get("id"): pr.get("discovery", {}).get("seen_before") for pr in s1_products}
    K = sum(1 for pid in set(posted_ids) if seen_before_map.get(pid) is False)

    # logout via profile tab
    prof = await page.query_selector('[data-testid=tab-profile]')
    if prof:
        await prof.click(force=True)
        await page.wait_for_timeout(1000)
    lg = await page.query_selector('[data-testid=logout-btn]')
    if lg:
        await lg.click(force=True)
        await page.wait_for_timeout(2500)
    # sign in again
    sess2 = {}
    def on_r2(resp):
        u = resp.url
        if "/api/discovery/sessions" in u and resp.request.method == "POST":
            async def cap():
                try:
                    sess2["j"] = await resp.json()
                    sess2["s"] = resp.status
                except: pass
            asyncio.create_task(cap())
    page.on("response", on_r2)
    await reviewer_sign_in(page, "store-review-customer", None)
    await page.wait_for_timeout(4000)
    await screenshot(page, "c6_session2")
    S2 = sess2.get("j", {}) or {}
    s2_id = S2.get("session_id")
    U2 = S2.get("unseen")
    Se2 = S2.get("seen")

    posted_now_seen = True
    if posted_ids:
        s2_products = S2.get("products") or []
        s2_map = {pr.get("id"): pr.get("discovery", {}).get("seen_before") for pr in s2_products}
        posted_now_seen = all(s2_map.get(pid) is True for pid in set(posted_ids) if pid in s2_map)

    passed = (
        sess1.get("s") == 200 and sess2.get("s") == 200
        and (len(posted_ids) == 0 or (all_in_s1 and no_dup and session_ids_ok))
        and s1_id != s2_id
    )
    detail = {
        "s1_status": sess1.get("s"), "s1_id": s1_id, "U1": U1, "Se1": Se1,
        "impression_posts": len(imp_posts), "posted_unique_ids": len(set(posted_ids)),
        "all_ids_in_s1": all_in_s1, "no_dup": no_dup, "session_ids_consistent": session_ids_ok,
        "K_newly_posted": K, "home_discovery_note_txt": (note_txt or "")[:200],
        "s2_status": sess2.get("s"), "s2_id": s2_id, "U2": U2, "Se2": Se2,
        "expected_Se2_eq_Se1_plus_K": (Se1 or 0) + K, "expected_U2_eq_U1_minus_K": (U1 or 0) - K,
        "posted_ids_now_seen_before_in_s2": posted_now_seen,
    }
    record("C6", "PASS" if passed else ("PARTIAL" if len(imp_posts) == 0 else "FAIL"), detail)
    await c_browser.close()

async def main():
    async with async_playwright() as pw:
        for name, fn in [("C7", run_c7), ("C3", run_c3), ("C5", run_c5), ("C4", run_c4), ("C6", run_c6)]:
            try:
                await fn(pw)
            except Exception as e:
                traceback.print_exc()
                record(f"{name}_exception", "FAIL", {"reason": str(e)})
    print("FINAL:", json.dumps(RESULTS, default=str))
    Path("/app/test_reports/iter39_results.json").write_text(json.dumps(RESULTS, default=str, indent=2))

if __name__ == "__main__":
    asyncio.run(main())
