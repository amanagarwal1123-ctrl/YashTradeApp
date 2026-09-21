"""Iteration 39 - C3 focused retry. Better row selection.

Approach: after opening each request-row-*, wait briefly and check if
request-claim is visible. If not, go back and try the next row.
Also, if no pending row is available, create one by using the customer
via the reviewer path (in-app: Profile -> Request a call).
"""
import asyncio, json, re, time, traceback
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

async def reviewer_sign_in(page, reviewer_id, land_selector):
    await page.goto(f"{BASE}/login", wait_until="domcontentloaded")
    await page.wait_for_selector('[data-testid=login-help-link]', timeout=15000)
    await page.click('[data-testid=login-help-link]', force=True)
    await page.wait_for_selector('[data-testid=help-review-access-link]', timeout=15000)
    await page.click('[data-testid=help-review-access-link]', force=True)
    await page.wait_for_selector('[data-testid=reviewer-id-input]', timeout=15000)
    await page.fill('[data-testid=reviewer-id-input]', reviewer_id)
    await page.fill('[data-testid=reviewer-key-input]', keys()[reviewer_id])
    await page.click('[data-testid=review-login-btn]', force=True)
    await page.wait_for_function(
        "() => document.body && document.body.innerText.includes('STORE-REVIEW ENVIRONMENT')",
        timeout=25000,
    )
    if land_selector:
        await page.wait_for_selector(land_selector, timeout=20000)

async def open_role(pw, role, land):
    b = await pw.chromium.launch(headless=True)
    ctx = await b.new_context(viewport=VIEWPORT)
    page = await ctx.new_page()
    page.on("dialog", lambda d: asyncio.create_task(dialog_handler(d)))
    await reviewer_sign_in(page, role, land)
    return b, page

async def screenshot(page, name):
    try:
        await page.screenshot(path=str(REPORT_DIR / f"iter39_{name}.jpeg"), quality=40, full_page=False, type="jpeg")
    except Exception:
        pass

def record(k, s, d):
    RESULTS[k] = {"status": s, "details": d}
    print(f"::{k}:: {s} :: {json.dumps(d, default=str)[:300]}")


async def click_visible(page, testid):
    """Click the first visible element matching data-testid."""
    handles = await page.query_selector_all(f'[data-testid={testid}]')
    for h in handles:
        try:
            if await h.is_visible():
                await h.click(force=True)
                return True
        except Exception:
            continue
    # fallback: JS click a visible one
    ok = await page.evaluate(f'''() => {{
        const els = document.querySelectorAll('[data-testid={testid}]');
        for (const el of els) {{
            const r = el.getBoundingClientRect();
            if (r.width > 0 && r.height > 0) {{ el.click(); return true; }}
        }}
        if (els[0]) {{ els[0].click(); return true; }}
        return false;
    }}''')
    return ok

async def ensure_pending_request(pw):
    """Customer creates a call-back request via UI to guarantee pending row."""
    b, page = await open_role(pw, "store-review-customer", None)
    await page.wait_for_timeout(2500)
    rid = None
    req_status = {}
    def on_r(resp):
        if "/api/requests" in resp.url and resp.request.method == "POST":
            async def cap():
                try:
                    req_status["j"] = await resp.json()
                    req_status["s"] = resp.status
                except: pass
            asyncio.create_task(cap())
    page.on("response", on_r)
    try:
        # Tap call-quick-btn on home
        await page.wait_for_selector('[data-testid=call-quick-btn]', timeout=15000)
        await click_visible(page, "call-quick-btn")
        await page.wait_for_selector('[data-testid=submit-request-btn]', timeout=15000)
        # optional: add notes
        notes = await page.query_selector('[data-testid=notes-input]')
        if notes:
            await notes.fill("recheck C3 pending row " + str(int(time.time())))
        await click_visible(page, "submit-request-btn")
        await page.wait_for_timeout(4000)
    except Exception as e:
        print(f"[c3] ensure_pending_request err: {e}")
    await b.close()
    j = req_status.get("j") or {}
    return j.get("id") or j.get("request_id") or j.get("_id")

async def find_pending_row(t2):
    """Iterate request-row-*; open each; if request-claim visible, return rid; else back."""
    await t2.wait_for_timeout(1500)
    rids_tried = []
    for _ in range(3):
        rows = await t2.query_selector_all('[data-testid^=request-row-]')
        for r in rows:
            tid = await r.get_attribute("data-testid")
            if not tid: continue
            rid = tid.replace("request-row-", "")
            if rid in rids_tried: continue
            rids_tried.append(rid)
            try:
                await r.click(force=True)
            except Exception:
                continue
            await t2.wait_for_timeout(1500)
            claim = await t2.query_selector('[data-testid=request-claim]')
            if claim:
                return rid
            # go back
            back = await t2.query_selector('[data-testid=request-detail-back]')
            if back:
                await back.click(force=True)
                await t2.wait_for_timeout(700)
            else:
                # try browser back-like: click header
                header = await t2.query_selector('[data-testid=requests-title]')
                if header:
                    pass
        await t2.wait_for_timeout(1000)
    return None

async def run_c3(pw):
    # Optionally ensure a pending row first
    new_rid = await ensure_pending_request(pw)
    print(f"[c3] ensured request via customer: {new_rid}")

    tb, t2 = await open_role(pw, "store-review-telecaller-2", '[data-testid=requests-title]')
    rid = await find_pending_row(t2)
    if not rid:
        record("C3", "FAIL", {"reason": "no pending row with request-claim visible", "created_rid": new_rid})
        await tb.close()
        return
    print(f"[c3] using rid {rid}")

    patch_events = []
    def on_r(resp):
        try:
            m = re.search(r"/api/requests/([^/?]+)(\?|$)", resp.url)
            if m and resp.request.method == "PATCH":
                body = None
                try: body = resp.request.post_data_json
                except: pass
                patch_events.append({"rid": m.group(1), "status": resp.status, "body": body})
        except Exception: pass
    t2.on("response", on_r)

    await t2.click('[data-testid=request-claim]', force=True)
    await t2.wait_for_selector('[data-testid=request-work-card]', timeout=15000)
    await t2.click('[data-testid=request-outcome-converted]', force=True)
    await t2.wait_for_timeout(700)
    await t2.click('[data-testid=request-complete]', force=True)
    end = time.time() + 20
    complete_ok = False
    while time.time() < end:
        for ev in patch_events:
            if ev["rid"] == rid and (ev.get("body") or {}).get("action") == "complete" and ev["status"] == 200:
                complete_ok = True; break
        if complete_ok: break
        await t2.wait_for_timeout(500)
    await t2.wait_for_timeout(1500)
    await screenshot(t2, "c3_completed")
    head_txt = ""
    try: head_txt = await t2.text_content('[data-testid=request-detail-head]') or ""
    except: pass
    record("C3_t2_complete", "PASS" if complete_ok else "FAIL", {"rid": rid, "head_text": head_txt[:200], "patch_events": patch_events[-3:]})
    await tb.close()

    # Admin: report today, reopen
    ab, adm = await open_role(pw, "store-review-admin", '[data-testid=panel-tab-requests]')
    a_patch = []
    def on_a(resp):
        try:
            m = re.search(r"/api/requests/([^/?]+)(\?|$)", resp.url)
            if m and resp.request.method == "PATCH":
                body = None
                try: body = resp.request.post_data_json
                except: pass
                a_patch.append({"rid": m.group(1), "status": resp.status, "body": body})
        except Exception: pass
    adm.on("response", on_a)
    await click_visible(adm, "panel-tab-reports")
    await adm.wait_for_selector('[data-testid=report-today]', timeout=15000)
    await click_visible(adm, "report-today")
    await adm.wait_for_timeout(2500)
    total_before = await adm.text_content('[data-testid=report-total]') or ""
    N1 = int(re.search(r"(\d+)", total_before).group(1)) if re.search(r"(\d+)", total_before) else None
    row_vis = await adm.is_visible('[data-testid=report-row-review-telecaller-0002]')
    await screenshot(adm, "c3_report_before")

    await adm.evaluate("window.scrollTo(0, 0)")
    await adm.wait_for_timeout(500)
    try:
        await click_visible(adm, "panel-tab-requests")
    except Exception:
        await adm.evaluate('document.querySelector("[data-testid=panel-tab-requests]").click()')
    await adm.wait_for_timeout(1500)
    row = await adm.query_selector(f'[data-testid=request-row-{rid}]')
    if not row:
        # try filters
        for tid in ["request-view-completed", "requests-filter-completed", "requests-filter-resolved", "requests-filter-all", "requests-filter-history", "requests-tab-completed", "requests-tab-all"]:
            btn = await adm.query_selector(f'[data-testid={tid}]')
            if btn:
                try: await btn.click(force=True)
                except Exception: await adm.evaluate(f'document.querySelector("[data-testid={tid}]").click()')
                await adm.wait_for_timeout(2000)
                row = await adm.query_selector(f'[data-testid=request-row-{rid}]')
                if row: break
    reopen_ok = False
    if row:
        await row.click(force=True)
        await adm.wait_for_selector('[data-testid=request-admin-card]', timeout=10000)
        await adm.fill('[data-testid=request-admin-reason]', "customer called back (recheck)")
        await adm.click('[data-testid=request-reopen]', force=True)
        end = time.time() + 15
        while time.time() < end:
            for ev in a_patch:
                if ev["rid"] == rid and (ev.get("body") or {}).get("action") == "reopen" and ev["status"] == 200:
                    reopen_ok = True; break
            if reopen_ok: break
            await adm.wait_for_timeout(500)
    await adm.evaluate("window.scrollTo(0, 0)")
    await adm.wait_for_timeout(400)
    try:
        await click_visible(adm, "panel-tab-reports")
    except Exception:
        await adm.evaluate('document.querySelector("[data-testid=panel-tab-reports]").click()')
    await adm.wait_for_timeout(1000)
    await click_visible(adm, "report-today")
    await adm.wait_for_timeout(2500)
    total_after = await adm.text_content('[data-testid=report-total]') or ""
    N2 = int(re.search(r"(\d+)", total_after).group(1)) if re.search(r"(\d+)", total_after) else None
    await screenshot(adm, "c3_report_after_reopen")
    record("C3_admin_reopen", "PASS" if reopen_ok and N1 is not None and N2 == N1 - 1 else "FAIL",
           {"rid": rid, "N1": N1, "N2": N2, "row_visible_report": row_vis, "reopen_ok": reopen_ok})
    await ab.close()

    # T2 recomplete
    tb2, t2b = await open_role(pw, "store-review-telecaller-2", '[data-testid=requests-title]')
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
        cb = await t2b.query_selector('[data-testid=request-claim]')
        if cb:
            await cb.click(force=True)
            await t2b.wait_for_selector('[data-testid=request-work-card]', timeout=15000)
        await t2b.click('[data-testid=request-outcome-converted]', force=True)
        await t2b.wait_for_timeout(500)
        await t2b.click('[data-testid=request-complete]', force=True)
        end = time.time() + 20
        while time.time() < end:
            for ev in p2:
                if ev["rid"] == rid and (ev.get("body") or {}).get("action") == "complete" and ev["status"] == 200:
                    recomplete_ok = True; break
            if recomplete_ok: break
            await t2b.wait_for_timeout(500)
    await tb2.close()

    ab2, adm2 = await open_role(pw, "store-review-admin", '[data-testid=panel-tab-requests]')
    await click_visible(adm2, "panel-tab-reports")
    await adm2.wait_for_selector('[data-testid=report-today]', timeout=15000)
    await click_visible(adm2, "report-today")
    await adm2.wait_for_timeout(2500)
    total_final = await adm2.text_content('[data-testid=report-total]') or ""
    N3 = int(re.search(r"(\d+)", total_final).group(1)) if re.search(r"(\d+)", total_final) else None
    await screenshot(adm2, "c3_report_after_recomplete")
    record("C3_recomplete", "PASS" if recomplete_ok and N3 == N1 else "FAIL",
           {"rid": rid, "N1": N1, "N3": N3, "recomplete_patch_ok": recomplete_ok})
    await ab2.close()

async def main():
    async with async_playwright() as pw:
        try:
            await run_c3(pw)
        except Exception as e:
            traceback.print_exc()
            record("C3_exception", "FAIL", {"reason": str(e)})
    print("FINAL:", json.dumps(RESULTS, default=str))
    Path("/app/test_reports/iter39_c3_results.json").write_text(json.dumps(RESULTS, default=str, indent=2))

if __name__ == "__main__":
    asyncio.run(main())
