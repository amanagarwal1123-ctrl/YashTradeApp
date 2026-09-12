"""Synthetic store-review dataset + reviewer accounts. Operator-only; never imported by routes.

Everything here is written ONLY to the isolated review database selected by the caller. Records
are clearly synthetic (names/shops carry "(synthetic)"; product codes start with RVW-) and the
review users carry review_environment=True so sessions can be bound to the review scope.
"""
import io
import secrets
from datetime import timedelta

from . import core as c
from .review import REVIEW_ROLES, hash_secret, new_secret

ACCOUNTS = {
    "customer": {"reviewer_id": "store-review-customer", "user_id": "review-customer-0001", "phone": "9100000101",
                 "name": "Review Customer (synthetic)", "shop_name": "Sample Jewellers (synthetic)", "location": "Delhi"},
    "admin": {"reviewer_id": "store-review-admin", "user_id": "review-admin-0001", "phone": "9100000102",
              "name": "Review Admin (synthetic)", "shop_name": "Yash Trade review desk", "location": "Delhi"},
    "telecaller": {"reviewer_id": "store-review-telecaller", "user_id": "review-telecaller-0001", "phone": "9100000103",
                   "name": "Review Telecaller (synthetic)", "shop_name": "Yash Trade review desk", "location": "Delhi"},
    "billing_executive": {"reviewer_id": "store-review-billing", "user_id": "review-billing-0001", "phone": "9100000104",
                          "name": "Review Billing Executive (synthetic)", "shop_name": "Yash Trade review desk", "location": "Delhi"},
}
EXTRA_CUSTOMERS = [("review-customer-%04d" % n, "91000002%02d" % n, f"Sample Retailer {n} (synthetic)", city)
                   for n, city in zip(range(2, 8), ["Mumbai", "Jaipur", "Ludhiana", "Amritsar", "Pune", "Surat"])]
PRODUCTS = [("Silver Payal Bridal (sample)", "silver", "Payal", "48 g", "925"), ("Silver Italian Chain (sample)", "silver", "Chain", "22 g", "925"),
            ("Silver Heavy Kada (sample)", "silver", "Kada", "110 g", "925"), ("Silver Pooja Thali (sample)", "silver", "Articles", "260 g", "925"),
            ("Silver Coin 10 g (sample)", "silver", "Coins", "10 g", "999"), ("Silver Toe Ring Pair (sample)", "silver", "Toe Ring", "8 g", "925"),
            ("Gold Necklace Set (sample)", "gold", "Necklace", "34 g", "916"), ("Gold Meenakari Bangles (sample)", "gold", "Bangles", "28 g", "916"),
            ("Gold Jhumka Earrings (sample)", "gold", "Earrings", "9 g", "750"), ("Silver Gift Frame (sample)", "silver", "Gifting", "140 g", "925"),
            ("Silver Baby Rattle (sample)", "silver", "Articles", "36 g", "925"), ("Silver Anklet Kids (sample)", "silver", "Payal", "18 g", "925")]
COLOURS = [(196, 168, 92), (160, 160, 170), (120, 130, 150), (170, 140, 110)]


def _png(label, colour, size=(640, 640)):
    from PIL import Image, ImageDraw
    image = Image.new("RGB", size, colour)
    draw = ImageDraw.Draw(image)
    draw.rectangle([40, 40, size[0]-40, size[1]-40], outline=(20, 20, 20), width=6)
    draw.text((60, size[1]//2 - 20), f"SYNTHETIC SAMPLE\n{label}", fill=(10, 10, 10))
    out = io.BytesIO()
    image.save(out, format="PNG", optimize=True)
    return out.getvalue()


def _user(uid, phone, name, role, shop, location, ts, **extra):
    return {"id": uid, "phone": phone, "phone_normalized": phone, "name": name, "role": role, "shop_name": shop,
            "location": location, "city": location, "account_status": "active", "status": "active", "session_version": 0,
            "phone_verified": True, "verified_at": ts, "onboarding_status": "completed", "registration_source": "store_review",
            "registered_at": ts, "created_at": ts, "updated_at": ts, "review_environment": True, "has_logged_in": False,
            "reward_points": 0, "lead_status": "new", "profile_version": 1, **extra}


DATA_COLLECTIONS = ["users", "products", "batches", "rates_current", "rate_slabs", "requests", "telecaller_activity",
                    "reward_transactions", "banners", "schemes", "brands", "cart", "wishlists", "ai_chat_history", "analytics_events",
                    "sms_log", "otp_challenges", "otp_limits", "refresh_tokens", "session_families", "media_assets",
                    "import_jobs", "deletion_requests", "integration_outbox", "deleted_identities", "operation_locks", "review_blobs"]


async def seed_dataset(reset=False):
    """Idempotent synthetic dataset. Must run inside c.scoped(c.REVIEW). Accounts/hashes are untouched."""
    assert c.in_review(), "seed_dataset must run in review scope"
    if reset:
        for name in DATA_COLLECTIONS:
            await c.db[name].delete_many({})
    ts = c.stamp()
    users = [_user(a["user_id"], a["phone"], a["name"], role, a["shop_name"], a["location"], ts,
                   customer_code=f"RVW-{role[:1].upper()}-001", code=f"RVW-{role[:1].upper()}-001",
                   reward_points=120 if role == "customer" else 0) for role, a in ACCOUNTS.items()]
    tele = ACCOUNTS["telecaller"]["user_id"]
    for n, (uid, phone, name, city) in enumerate(EXTRA_CUSTOMERS):
        users.append(_user(uid, phone, name, "customer", f"{name.split(' (')[0]} Shop", city,
                           (c.now() - timedelta(days=n*3)).isoformat(), customer_code=f"RVW-C-{n+2:03d}", code=f"RVW-C-{n+2:03d}",
                           assigned_salesperson=tele if n % 2 == 0 else "", reward_points=40*n))
    for u in users:
        await c.db.users.update_one({"id": u["id"]}, {"$setOnInsert": u}, upsert=True)
    await c.db.batches.update_one({"id": "review-batch-1"}, {"$setOnInsert": {"id": "review-batch-1", "name": "Review sample batch (synthetic)",
        "metal_type": "silver", "status": "visible", "created_at": ts}}, upsert=True)
    for n, (title, metal, category, weight, purity) in enumerate(PRODUCTS):
        pid, code = f"review-product-{n+1:04d}", f"RVW-{n+1:04d}"
        if await c.db.products.find_one({"id": pid}):
            continue
        path = f"yash-trade/review/products/{pid}.png"
        thumb = f"yash-trade/review/products/{pid}.thumb.png"
        c.store_object(path, _png(title, COLOURS[n % 4]), "image/png")
        c.store_object(thumb, _png(title, COLOURS[n % 4], (320, 320)), "image/png")
        await c.db.products.insert_one({"id": pid, "product_code": code, "title": title, "metal_type": metal, "category": category,
            "approx_weight": weight, "purity": purity, "stock_status": "in_stock", "visibility": "visible", "images": [f"/api/files/{path}"],
            "storage_path": path, "thumbnail_path": thumb, "batch_id": "review-batch-1", "tags": ["synthetic", "store-review", category.lower()],
            "is_new_arrival": n < 3, "is_trending": n % 3 == 0, "version": 0, "views": 0, "is_deleted": False,
            "created_at": (c.now() - timedelta(hours=n)).isoformat(), "updated_at": ts, "review_environment": True})
    await c.db.rates_current.update_one({"_id": "canonical"}, {"$setOnInsert": {"_id": "canonical", "version": 0,
        "silver_physical_rate": 98.5, "silver_mcx_rate": 97.2, "silver_dollar_rate": 31.4, "silver_movement": "up",
        "gold_physical_rate": 7850.0, "gold_mcx_rate": 7790.0, "gold_dollar_rate": 2650.0, "gold_movement": "down",
        "created_at": ts, "updated_at": ts, "events": []}}, upsert=True)
    slabs = [("Silver Payal (Anklet)", "silver", "Payal", "850", "kg", 1), ("Silver Chain", "silver", "Chain", "750", "kg", 2),
             ("Silver Articles (Pooja)", "silver", "Articles", "900", "kg", 3), ("Gold Necklace Set", "gold", "Necklace", "3500", "10g", 1),
             ("Gold Earrings", "gold", "Earrings", "4000", "10g", 2), ("Silver Coin", "silver", "Coins", "20", "piece", 4)]
    for n, (item, metal, category, amount, basis, order) in enumerate(slabs):
        sid = f"review-slab-{n+1:03d}"
        await c.db.rate_slabs.update_one({"id": sid}, {"$setOnInsert": {"id": sid, "item_name": f"{item} (sample)", "metal_type": metal,
            "category": category, "purity": "92.5%" if metal == "silver" else "22K", "wastage": "3%", "order": order, "version": 0,
            "labour": {"currency": "INR", "amount": amount, "basis": basis}, "labour_kg": f"INR {amount}/{basis}",
            "is_deleted": False, "created_at": ts, "updated_at": ts}}, upsert=True)
    types = ["video_call", "ask_price", "callback", "similar_products", "hold_item", "quick_reorder", "cart_selection", "callback"]
    owners = [ACCOUNTS["customer"]["user_id"]] * 3 + [row[0] for row in EXTRA_CUSTOMERS[:5]]
    statuses = ["pending", "in_progress", "resolved", "pending", "contacted", "pending", "resolved", "cancelled"]
    for n, (typ, owner, state) in enumerate(zip(types, owners, statuses)):
        rid = f"review-request-{n+1:04d}"
        if await c.db.requests.find_one({"id": rid}):
            continue
        person = await c.db.users.find_one({"id": owner}, {"_id": 0})
        created = (c.now() - timedelta(hours=6*n+1)).isoformat()
        assignee = tele if state in {"in_progress", "contacted", "resolved"} else ""
        events = [{"id": secrets.token_hex(8), "type": "creation", "request_id": rid, "actor_id": owner, "actor_role": "customer",
                   "actor_name": person["name"], "old": None, "new": "pending", "notes": "", "status": "pending", "timestamp": created}]
        doc = {"_id": rid, "id": rid, "request_type": typ, "category": "", "preferred_time": "", "notes": f"Synthetic sample enquiry {n+1}",
               "product_id": "", "product_ids": [f"review-product-{n+1:04d}"], "linked_products": [], "user_id": owner,
               "user_name": person["name"], "user_phone": person["phone"], "user_city": person["city"], "shop_name": person["shop_name"],
               "status": state, "assignee_id": assignee, "assigned_to": assignee, "created_at": created, "updated_at": created,
               "pending_since": created, "version": 1 if assignee else 0, "payload_hash": "", "notes_history": [], "events": events, "review_environment": True}
        if state == "resolved":
            doc.update(resolved_at=ts, resolver_id=tele, resolver_name=ACCOUNTS["telecaller"]["name"], first_response_at=ts)
            events.append({"id": secrets.token_hex(8), "type": "resolution", "request_id": rid, "actor_id": tele, "actor_role": "telecaller",
                           "actor_name": ACCOUNTS["telecaller"]["name"], "old": "pending", "new": "resolved", "notes": "", "status": "resolved", "timestamp": ts})
        await c.db.requests.insert_one(doc)
    cust = ACCOUNTS["customer"]["user_id"]
    if not await c.db.reward_transactions.find_one({"user_id": cust}):
        await c.db.reward_transactions.insert_many([
            {"id": secrets.token_hex(12), "user_id": cust, "points": 100, "type": "credit", "reason": "Welcome bonus (synthetic)", "created_at": ts},
            {"id": secrets.token_hex(12), "user_id": cust, "points": 20, "type": "credit", "reason": "Sample purchase (synthetic)", "created_at": ts}])
    if not await c.db.telecaller_activity.find_one({"customer_id": EXTRA_CUSTOMERS[0][0]}):
        await c.db.telecaller_activity.insert_one({"id": secrets.token_hex(12), "telecaller_id": tele, "telecaller_name": ACCOUNTS["telecaller"]["name"],
            "customer_id": EXTRA_CUSTOMERS[0][0], "customer_name": EXTRA_CUSTOMERS[0][2], "action": "call", "notes": "Synthetic follow-up note",
            "previous_status": "new", "new_status": "follow_up_required", "follow_up_at": "", "created_at": ts})
    if not await c.db.banners.find_one({"id": "review-banner-1"}):
        path = "yash-trade/review/banners/review-banner-1.png"
        c.store_object(path, _png("Festive collection banner", COLOURS[0], (1200, 500)), "image/png")
        await c.db.banners.insert_one({"id": "review-banner-1", "title": "Synthetic festive banner", "subtitle": "Store-review sample",
            "image_url": f"/api/files/{path}", "cta_label": "Browse", "cta_type": "feed", "cta_target": "", "order": 0, "is_active": True, "created_at": ts})
    for coll, doc in (("schemes", {"id": "review-scheme-1", "title": "Sample savings scheme (synthetic)", "description": "Illustrative only.", "is_active": True, "order": 0}),
                      ("brands", {"id": "review-brand-1", "name": "Sample Brand (synthetic)", "description": "Illustrative only.", "order": 0, "is_active": True})):
        await c.db[coll].update_one({"id": doc["id"]}, {"$setOnInsert": {**doc, "created_at": ts}}, upsert=True)
    return {"users": await c.db.users.count_documents({}), "products": await c.db.products.count_documents({}),
            "requests": await c.db.requests.count_documents({}), "rate_slabs": await c.db.rate_slabs.count_documents({})}


async def provision_accounts(only=None):
    """Create missing reviewer accounts; returns {reviewer_id: plaintext secret} for NEW accounts only."""
    assert c.in_review()
    issued = {}
    for role in REVIEW_ROLES:
        if only and role not in only:
            continue
        meta = ACCOUNTS[role]
        if await c.db.review_accounts.find_one({"reviewer_id": meta["reviewer_id"]}):
            continue
        secret = new_secret()
        await c.db.review_accounts.insert_one({"reviewer_id": meta["reviewer_id"], "user_id": meta["user_id"], "role": role,
            "secret_hash": hash_secret(secret), "enabled": True, "revoked_at": None, "created_at": c.stamp(),
            "rotated_at": None, "last_login_at": None})
        issued[meta["reviewer_id"]] = secret
    await c.db.review_accounts.create_index("reviewer_id", unique=True)
    await c.db.review_access_log.create_index([("reviewer_id", 1), ("created_at", -1)])
    return issued


async def rotate(reviewer_id):
    assert c.in_review()
    account = await c.db.review_accounts.find_one({"reviewer_id": reviewer_id}, {"_id": 0})
    if not account:
        raise ValueError("Unknown reviewer account")
    secret = new_secret()
    await c.db.review_accounts.update_one({"reviewer_id": reviewer_id}, {"$set": {"secret_hash": hash_secret(secret),
        "rotated_at": c.stamp(), "enabled": True, "revoked_at": None}})
    await c.revoke(account["user_id"])
    return secret


async def revoke(reviewer_id):
    assert c.in_review()
    account = await c.db.review_accounts.find_one({"reviewer_id": reviewer_id}, {"_id": 0})
    if not account:
        raise ValueError("Unknown reviewer account")
    await c.db.review_accounts.update_one({"reviewer_id": reviewer_id}, {"$set": {"enabled": False, "revoked_at": c.stamp()}})
    await c.revoke(account["user_id"])
    return {"reviewer_id": reviewer_id, "revoked": True}


async def status():
    assert c.in_review()
    rows = await c.db.review_accounts.find({}, {"_id": 0, "secret_hash": 0}).sort("reviewer_id", 1).to_list(50)
    return {"accounts": rows, "dataset": {"users": await c.db.users.count_documents({}), "products": await c.db.products.count_documents({}),
            "requests": await c.db.requests.count_documents({})}}
