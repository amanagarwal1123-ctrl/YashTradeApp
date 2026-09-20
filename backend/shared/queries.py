import re
import secrets
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Header, Query
from pydantic import BaseModel, ConfigDict, Field
from pymongo import ReturnDocument

from . import core as c

router = APIRouter(prefix="/api", tags=["Unified requests"])
# QUERY lifecycle (status): pending = fresh/unclaimed in the shared queue, in_progress = claimed and being worked,
# resolved = explicitly completed, cancelled = historical terminal record (never counted as a completion).
# `contacted` / `no_response` are legacy statuses of older rows: still OPEN, shown through their head.
OPEN = ["pending", "in_progress", "contacted", "no_response"]
TERMINAL = ["resolved", "cancelled"]
STATUSES = OPEN + TERMINAL
ALIASES = {"completed": "resolved", "done": "resolved", "assigned": "in_progress"}
# Work HEAD (disposition) of an open query - distinct from the CUSTOMER lead state kept on the customer record.
# Every head is non-terminal: the query stays in the shared pending list until an explicit Mark Complete.
HEADS = ["new", "contacted", "interested", "follow_up", "unreachable"]
HEAD_ALIASES = {"follow_up_required": "follow_up", "unable_to_reach": "unreachable", "no_response": "unreachable", "fresh": "new"}
HEAD_LABELS = {"new": "New", "contacted": "Contacted", "interested": "Interested", "follow_up": "Follow-up", "unreachable": "Unreachable"}
OUTCOMES = ["converted", "not_interested", "other"]
TYPES = ["video_call", "ask_price", "callback", "similar_products", "hold_item", "quick_reorder", "cart_selection"]
TYPE_ALIASES = {"price_enquiry": "ask_price", "price_inquiry": "ask_price", "call": "callback",
                "hold": "hold_item", "reorder": "quick_reorder"}
IST = ZoneInfo("Asia/Kolkata")
SORTS = {"fresh": [("queue_sort_at", -1), ("created_at", -1), ("id", 1)], "oldest": [("created_at", 1), ("id", 1)],
         "newest": [("created_at", -1), ("id", 1)], "longest_wait": [("pending_since", 1), ("id", 1)],
         "completed": [("resolved_at", -1), ("id", 1)]}


@router.get("/requests/staff-options")
async def staff_options(user=Depends(c.operations)):
    rows = await c.db.users.find({"role": {"$in": ["admin", "telecaller", "executive"]}, "account_status": {"$ne": "deleted"}},
                                 {"_id": 0, "id": 1, "name": 1, "role": 1}).sort([("name", 1), ("id", 1)]).limit(500).to_list(500)
    return {"users": [{**r, "role": c.role(r["role"])} for r in rows], "limit": 500}


def head(raw):
    value = HEAD_ALIASES.get(raw, raw)
    if value not in HEADS:
        c.fail(422, "INVALID_HEAD", "Use new, contacted, interested, follow_up or unreachable")
    return value


def status(raw):
    value = ALIASES.get(raw, raw)
    if value not in STATUSES:
        c.fail(422, "INVALID_QUERY_STATUS", "Use a canonical query status")
    return value


def date_bounds(start="", end=""):
    try:
        today = c.now().astimezone(IST).date().isoformat()
        lower = datetime.strptime(start or today, "%Y-%m-%d").replace(tzinfo=IST)
        upper = datetime.strptime(end or start or today, "%Y-%m-%d").replace(tzinfo=IST) + timedelta(days=1)
    except ValueError:
        c.fail(422, "INVALID_DATE", "Use YYYY-MM-DD calendar dates in Asia/Kolkata")
    days = (upper - lower).days
    if days < 1 or days > 366:
        c.fail(422, "INVALID_DATE_RANGE", "Select 1 to 366 calendar days")
    return lower.astimezone(c.timezone.utc).isoformat(), upper.astimezone(c.timezone.utc).isoformat(), days


def event(kind, actor, request_id, old=None, new=None, notes="", request_status=None):
    return {"id": secrets.token_hex(16), "type": kind, "request_id": request_id,
            "actor_id": actor["id"], "actor_role": c.role(actor["role"]),
            "actor_name": actor.get("name", ""), "old": old, "new": new,
            "notes": notes, "status": request_status, "timestamp": c.stamp()}


def enrich_pipeline():
    return [
        {"$set": {"customer_id": {"$ifNull": ["$user_id", "$customer_id"]},
                  "status": {"$switch": {"branches": [{"case": {"$eq": ["$status", k]}, "then": v}
                                                           for k, v in ALIASES.items()], "default": "$status"}},
                  "version": {"$ifNull": ["$version", 0]}, "assignee_id": {"$ifNull": ["$assignee_id", "$assigned_to"]},
                  "queue_sort_at": {"$ifNull": ["$queue_sort_at", "$created_at"]}, "head": {"$ifNull": ["$head", "new"]}}},
        {"$lookup": {"from": c.collection_name("users"), "localField": "customer_id", "foreignField": "id", "as": "_customers",
            "pipeline": [{"$project": {"_id": 0, "name": 1, "phone": 1, "shop_name": 1, "location": 1, "city": 1, "lead_status": 1, "account_status": 1}}]}},
        {"$set": {"_customer": {"$arrayElemAt": ["$_customers", 0]}}},
        # A deleted account is a tombstone (phone "deleted:<id>", name "Deleted customer"): it must never surface as a
        # dialable number or personal data in staff views; the anonymized request fields are used instead.
        {"$set": {"_customer": {"$cond": [{"$eq": ["$_customer.account_status", "deleted"]},
                                          {"name": "$_customer.name", "account_status": "deleted"}, "$_customer"]}}},
        {"$set": {"customer_name": {"$ifNull": ["$_customer.name", "$user_name"]},
            "customer_phone": {"$ifNull": ["$_customer.phone", "$user_phone"]},
            "customer_shop_name": {"$ifNull": ["$_customer.shop_name", "$shop_name"]},
            "customer_lead_status": "$_customer.lead_status",
            "customer_deleted": {"$eq": ["$_customer.account_status", "deleted"]},
            "customer_location": {"$ifNull": ["$_customer.location", {"$ifNull": ["$_customer.city", "$user_city"]}]},
            "pending_since": {"$ifNull": ["$pending_since", "$created_at"]}}},
        {"$project": {"_id": 0, "_customer": 0, "_customers": 0}},
    ]


VIEWS = {"all", "mine", "unassigned", "all_pending", "my_pending", "my_completed", "completed"}


def filters(search="", request_type="", assignee="", resolver="", view="all", user=None,
            created_from="", created_to="", resolved_from="", resolved_to="", min_age_minutes=None, max_age_minutes=None, head_filter=""):
    query = {}
    if search:
        term = re.escape(search[:120])
        query["$or"] = [{k: {"$regex": term, "$options": "i"}} for k in
            ["customer_name", "customer_phone", "customer_shop_name", "customer_location", "user_city", "id",
             "linked_products.title", "linked_products.product_code", "cart_items.title", "notes"]]
    if request_type:
        query["request_type"] = TYPE_ALIASES.get(request_type, request_type)
    if head_filter:
        query["head"] = head(head_filter)
    if view not in VIEWS:
        c.fail(422, "INVALID_VIEW", "Use all, all_pending, my_pending, my_completed, completed, mine or unassigned")
    if view in {"mine", "my_pending"}:
        query["assignee_id"] = user["id"]
    elif view == "unassigned":
        query["assignee_id"] = {"$in": [None, ""]}
    elif assignee:
        query["assignee_id"] = assignee
    if view in {"all_pending", "my_pending"}:
        query["status"] = {"$in": OPEN}
    elif view in {"my_completed", "completed"}:
        query["status"] = "resolved"
        if view == "my_completed":
            query["resolver_id"] = user["id"]
    if resolver:
        query["resolver_id"] = resolver
    for field, lower, upper in [("created_at", created_from, created_to), ("resolved_at", resolved_from, resolved_to)]:
        if lower or upper:
            a, b, _ = date_bounds(lower, upper)
            query[field] = {"$gte": a, "$lt": b}
    if min_age_minutes is not None or max_age_minutes is not None:
        query["status"] = {"$in": OPEN}
        query["pending_since"] = {}
        if min_age_minutes is not None:
            query["pending_since"]["$lte"] = (c.now()-timedelta(minutes=min_age_minutes)).isoformat()
        if max_age_minutes is not None:
            query["pending_since"]["$gte"] = (c.now()-timedelta(minutes=max_age_minutes)).isoformat()
    return query


def contact_links(number):
    """Normalized call / WhatsApp targets for the canonical number (never a hardcoded +91 for every country)."""
    if not number:
        return {"tel": "", "whatsapp": ""}
    digits = c.sms_destination(number)  # country code + national digits, no plus
    return {"tel": "+" + digits, "whatsapp": digits}


def view_doc(doc, customer=False):
    doc["status"] = ALIASES.get(doc.get("status"), doc.get("status", "pending"))
    doc.setdefault("version", 0)
    doc.setdefault("customer_id", doc.get("user_id"))
    doc.setdefault("assignee_id", doc.get("assigned_to", ""))
    doc["head"] = HEAD_ALIASES.get(doc.get("head"), doc.get("head")) or "new"
    doc["head_label"] = HEAD_LABELS.get(doc["head"], doc["head"])
    doc.setdefault("queue_sort_at", doc.get("created_at"))
    for key in ("follow_up_at", "claimed_at", "fresh_at", "reset_cycle", "outcome", "completed_by_name"):
        doc.setdefault(key, None)
    doc.setdefault("reset_count", 0)
    doc["user_name"] = doc.get("customer_name", doc.get("user_name", ""))
    doc["user_phone"] = doc.get("customer_phone", doc.get("user_phone", ""))
    doc["user_city"] = doc.get("customer_location", doc.get("user_city", ""))
    doc["claimed"] = bool(doc.get("assignee_id")) and doc["status"] in OPEN
    for key in ("first_response_at", "resolved_at", "resolver_id", "updated_at"):
        doc.setdefault(key, None)
    doc["legacy_timing_unknown"] = doc["status"] == "resolved" and not doc.get("resolved_at")
    doc["pending_since"] = doc.get("pending_since") or doc.get("created_at")
    def seconds(a, b):
        try:
            return max(0, int((datetime.fromisoformat(b) - datetime.fromisoformat(a)).total_seconds()))
        except (ValueError, TypeError):
            return None
    doc["age_seconds"] = seconds(doc.get("created_at"), c.stamp())
    doc["pending_seconds"] = seconds(doc["pending_since"], c.stamp()) if doc["status"] in OPEN else None
    doc["handling_seconds"] = seconds(doc["pending_since"], doc.get("resolved_at")) if doc["status"] == "resolved" else None
    doc["item_count"] = len(doc.get("product_ids") or []) or int(doc.get("cart_count") or 0)
    doc.pop("_id", None)
    if customer:
        for key in ("events", "notes_history", "admin_notes", "handled_by_id", "handled_by_phone", "handled_by_name",
                    "handled_by_code", "resolver_id", "resolver_name", "assignee_id", "assigned_to", "last_editor_id", "mutation_keys",
                    "completed_by_id", "completed_by_name", "outcome", "follow_up_at", "claimed_at", "previous_assignment",
                    "reset_cycle", "reset_count", "fresh_at", "customer_lead_status", "payload_hash"):
            doc.pop(key, None)
        # Customer-facing lifecycle only: the internal head is not shown.
        doc["head"] = "in_progress" if doc["status"] in OPEN and doc.get("claimed") else doc["status"]
        doc.pop("head_label", None)
        doc.pop("claimed", None)
    else:
        doc["contact"] = contact_links(doc.get("user_phone"))
        doc["customer_phone_display"] = c.phone_display(doc["user_phone"]) if doc.get("user_phone") else ""
    return doc


@router.get("/requests/catalog")
async def catalog(user=Depends(c.current_user)):
    return {"types": TYPES, "statuses": STATUSES, "status_aliases": ALIASES, "type_aliases": TYPE_ALIASES,
        "open_statuses": OPEN, "terminal_statuses": TERMINAL, "heads": HEADS, "head_labels": HEAD_LABELS, "head_aliases": HEAD_ALIASES,
        "outcomes": OUTCOMES, "views": sorted(VIEWS), "sorts": sorted(SORTS), "reopen": "administrator action=reopen with reason, back to pending",
        "complete": "claimant or administrator action=complete (idempotent); the query leaves the pending list",
        "daily_release": "03:00 Asia/Kolkata: every open query created before the boundary returns to pending/new at the top of the queue",
        "lead_status_aliases": {"follow_up": "follow_up_required"}}


class NewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_type: str
    category: str = Field("", max_length=120)
    preferred_time: str = Field("", max_length=120)
    notes: str = Field("", max_length=3000)
    product_id: str = ""
    product_ids: list[str] = Field(default_factory=list, max_length=100)


@router.post("/requests")
async def create(req: NewRequest, user=Depends(c.allow("customer")), idempotency_key: str | None = Header(None)):
    c.require_complete_profile(user)  # 428 PROFILE_INCOMPLETE: the app opens the profile form, then re-sends this request
    typ = TYPE_ALIASES.get(req.request_type, req.request_type)
    if typ not in TYPES:
        c.fail(422, "INVALID_REQUEST_TYPE", "Select a type from /api/requests/catalog")
    ids = list(dict.fromkeys(([req.product_id] if req.product_id else []) + req.product_ids))
    products = await c.db.products.find({"id": {"$in": ids}, "visibility": {"$ne": "hidden"}, "is_deleted": {"$ne": True}},
        {"_id": 0, "id": 1, "title": 1, "images": 1, "storage_path": 1, "thumbnail_path": 1, "metal_type": 1}).to_list(100)
    if len(products) != len(ids):
        c.fail(422, "PRODUCT_UNAVAILABLE", "A selected product is unavailable")
    rid = c.digest(user["id"] + ":" + idempotency_key)[:32] if idempotency_key else secrets.token_hex(16)
    ts = c.stamp()
    payload_hash = c.digest(req.model_dump_json())
    doc = {"id": rid, **req.model_dump(), "request_type": typ, "product_ids": ids, "linked_products": products,
        "user_id": user["id"], "user_name": user.get("name", ""), "user_phone": user.get("phone", ""),
        "user_city": user.get("location") or user.get("city", ""), "shop_name": user.get("shop_name", ""),
        "status": "pending", "head": "new", "assignee_id": "", "assigned_to": "", "claimed_at": None, "follow_up_at": None,
        "created_at": ts, "updated_at": ts, "queue_sort_at": ts, "pending_since": ts, "version": 0, "payload_hash": payload_hash,
        "notify_state": "pending", "notes_history": [], "events": [event("creation", user, rid, new="pending", request_status="pending")]}
    # Deterministic _id provides idempotency without relying on a non-unique legacy id index.
    result = await c.db.requests.update_one({"_id": rid}, {"$setOnInsert": doc}, upsert=True)
    stored = await c.db.requests.find_one({"_id": rid}, {"_id": 0})
    if stored.get("payload_hash") != payload_hash:
        c.fail(409, "IDEMPOTENCY_CONFLICT", "This idempotency key was used for different request content")
    if result.upserted_id is not None or stored.get("notify_state") == "pending":
        await notify_created(stored)   # a same-key retry also repairs an alert that could not be queued the first time
    return view_doc(stored, customer=True)


async def notify_created(doc):
    """Every creation path (this endpoint, the cart submission, legacy routes) raises ONE durable operational event
    for the telecallers; a failure to queue never fails the customer's request. The request carries a durable
    `notify_state` marker (F06): `pending` until the event is in the outbox, so the notifications worker can queue it
    later (`reconcile_pending_notifications`) - the alert is never silently lost."""
    from . import notifications
    try:
        result = await notifications.query_created(doc)
    except Exception as exc:  # the request is stored; the marker stays `pending` for the worker to reconcile
        import logging
        logging.getLogger("shared").warning("Query notification not queued (kept pending for the worker): %s", type(exc).__name__)
        await c.db.requests.update_one({"id": doc["id"]}, {"$set": {"notify_state": "pending"}, "$inc": {"notify_attempts": 1},
                                                          "$push": {"notify_errors": {"at": c.stamp(), "error": type(exc).__name__}}})
        return None
    await c.db.requests.update_one({"id": doc["id"]}, {"$set": {"notify_state": "queued", "notified_at": c.stamp()}})
    return result


async def reconcile_pending_notifications(limit=50, min_age_seconds=20):
    """Worker-side repair for query alerts whose enqueue failed at creation time: idempotent on the request id."""
    cutoff = (c.now() - timedelta(seconds=min_age_seconds)).isoformat()
    docs = await c.db.requests.find({"notify_state": "pending", "created_at": {"$lt": cutoff}}, {"_id": 0}).sort("created_at", 1).limit(limit).to_list(limit)
    queued = 0
    for doc in docs:
        if await notify_created(doc) is not None:
            queued += 1
    return queued


@router.get("/requests/my")
async def mine(page: int = Query(1, ge=1), limit: int = Query(30, ge=1, le=100), user=Depends(c.current_user)):
    query = {"user_id": user["id"]}
    rows = await c.db.requests.find(query, {"_id": 0}).sort([("created_at", -1), ("id", 1)]).skip((page-1)*limit).limit(limit).to_list(limit)
    total = await c.db.requests.count_documents(query)
    return {"requests": [view_doc(d, True) for d in rows], "total": total, "page": page, "limit": limit, "pages": (total+limit-1)//limit}


CUSTOMER_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")


async def customer_scope(customer_id):
    """Immutable canonical customer-ID filter (website dependency D3). Malformed values are
    rejected, unknown IDs are 404, deleted customers keep their anonymized history."""
    value = customer_id.strip()
    if not CUSTOMER_ID.match(value):
        c.fail(422, "INVALID_FILTER", "customer_id must be a canonical customer identifier")
    person = await c.db.users.find_one({"id": value}, {"_id": 0, "id": 1, "role": 1})
    if not person:
        c.fail(404, "CUSTOMER_NOT_FOUND", "No customer exists with this canonical ID")
    return value


@router.get("/requests")
async def listing(page: int = Query(1, ge=1), limit: int = Query(30, ge=1, le=100), search: str = "",
    status: str = "", request_type: str = "", view: str = "all", assignee: str = "", resolver: str = "",
    assigned_to: str = "", handled_by: str = "", city: str = "", created_from: str = "", created_to: str = "",
    resolved_from: str = "", resolved_to: str = "", min_age_minutes: int | None = Query(None, ge=0),
    max_age_minutes: int | None = Query(None, ge=0), sort: str = "", period_resolver: str = "",
    period_start: str = "", period_end: str = "", customer_id: str = "", head: str = "", user=Depends(c.operations)):
    """Central query workspace (admin, telecaller, billing). No implicit date window and no hidden record cutoff: the
    filters narrow the FULL authorized history and pages continue until `pages`. Default order is fresh-first
    (`queue_sort_at` desc: released and newly created queries on top), deterministic tie-breaker created_at desc, id."""
    query = filters(search or city, request_type, assignee or assigned_to, resolver or handled_by, view, user,
        created_from, created_to, resolved_from, resolved_to, min_age_minutes, max_age_minutes, head)
    if customer_id:
        # Matched AFTER enrichment, so legacy user_id-backed rows and customer_id rows both qualify.
        query["customer_id"] = await customer_scope(customer_id)
    if status and status != "all":
        query["status"] = {"$in": OPEN} if status == "open" else globals()["status"](status)
    elif not status and view in {"all", "mine", "unassigned"} and user["role"] == "billing_executive":
        query["status"] = {"$in": OPEN}
    sort = sort or ("completed" if view in {"my_completed", "completed"} else "fresh")
    order = SORTS.get(sort)
    if not order:
        c.fail(422, "INVALID_SORT", "Use fresh, oldest, newest, longest_wait or completed")
    pipeline = enrich_pipeline()
    if period_resolver:
        if user["role"] == "billing_executive" or user["role"] == "telecaller" and period_resolver != user["id"]:
            c.fail(403, "METRICS_PERMISSION_DENIED", "Only authorized personal/team metrics may be requested")
        lower, upper, _ = date_bounds(period_start, period_end)
        pipeline += [{"$set": {"_period_events": {"$filter": {"input": {"$ifNull": ["$events", []]}, "as": "e",
            "cond": {"$and": [{"$eq": ["$$e.type", "resolution"]}, {"$gte": ["$$e.timestamp", lower]}, {"$lt": ["$$e.timestamp", upper]}]}}}}},
            {"$set": {"_last_resolution": {"$reduce": {"input": "$_period_events", "initialValue": {"timestamp": "", "id": ""},
                "in": {"$cond": [{"$gt": [["$$this.timestamp", "$$this.id"], ["$$value.timestamp", "$$value.id"]]}, "$$this", "$$value"]}}}}},
            {"$match": {"_last_resolution.actor_id": period_resolver}}, {"$project": {"_period_events": 0, "_last_resolution": 0}}]
    output = await c.db.requests.aggregate(pipeline + [{"$match": query}, {"$facet": {
        "items": [{"$sort": dict(order)}, {"$skip": (page-1)*limit}, {"$limit": limit}], "count": [{"$count": "n"}],
        "by_type": [{"$match": {"status": {"$in": OPEN}}}, {"$group": {"_id": "$request_type", "n": {"$sum": 1}}}],
        "by_head": [{"$match": {"status": {"$in": OPEN}}}, {"$group": {"_id": "$head", "n": {"$sum": 1}}}]}}]).to_list(1)
    data = output[0]
    total = data["count"][0]["n"] if data["count"] else 0
    ids = {d.get("assignee_id") for d in data["items"]} | {d.get("resolver_id") for d in data["items"]}
    names = {u["id"]: u.get("name", "") async for u in c.db.users.find({"id": {"$in": list(ids - {None, ""})}}, {"_id": 0, "id": 1, "name": 1})}
    items = [{**view_doc(d), "assignee_name": names.get(d.get("assignee_id"), ""),
              "resolver_name": names.get(d.get("resolver_id"), d.get("resolver_name", ""))} for d in data["items"]]
    mine = await c.db.requests.count_documents({"assignee_id": user["id"], "status": {"$in": OPEN}})
    pending = await c.db.requests.count_documents({"status": {"$in": OPEN}})
    return {"requests": items, "total": total, "page": page, "limit": limit, "pages": (total+limit-1)//limit, "sort": sort, "view": view,
            "open_counts_by_type": {r["_id"]: r["n"] for r in data["by_type"]}, "open_counts_by_head": {(r["_id"] or "new"): r["n"] for r in data["by_head"]},
            "counts": {"all_pending": pending, "my_pending": mine}, "server_time": c.stamp(),
            "permissions": {"can_work": user["role"] in {"admin", "telecaller"}, "can_assign": user["role"] == "admin", "can_reopen": user["role"] == "admin"},
            **({"customer_id": query["customer_id"]} if customer_id else {})}


async def product_snapshots(doc):
    """Requested items with their CURRENT availability: the stored snapshot (title, first image) is kept so the record
    survives unpublishing/deletion; `available` is false and the image blank when the product is gone or hidden."""
    ids = list(dict.fromkeys(doc.get("product_ids") or [p.get("product_id") for p in doc.get("cart_items") or []]))
    if not ids:
        return []
    current = {p["id"]: p async for p in c.db.products.find({"id": {"$in": ids}}, {"_id": 0, "id": 1, "title": 1, "images": 1, "storage_path": 1,
        "thumbnail_path": 1, "visibility": 1, "is_deleted": 1, "weight": 1, "gross_weight": 1, "net_weight": 1, "product_code": 1, "metal_type": 1})}
    snap = {p.get("id"): p for p in doc.get("linked_products") or []}
    cart = {p.get("product_id"): p for p in doc.get("cart_items") or []}
    items = []
    for pid in ids:
        live, stored, line = current.get(pid) or {}, snap.get(pid) or {}, cart.get(pid) or {}
        available = bool(live) and live.get("visibility") != "hidden" and not live.get("is_deleted")
        source = live if available else stored
        items.append({"product_id": pid, "title": source.get("title") or line.get("title") or "Product no longer listed",
                      "product_code": source.get("product_code", ""), "metal_type": source.get("metal_type") or line.get("metal_type", ""),
                      "weight": source.get("net_weight") or source.get("weight") or source.get("gross_weight"),
                      "thumbnail_path": source.get("thumbnail_path", "") if available else "", "storage_path": source.get("storage_path", "") if available else "",
                      "images": (source.get("images") or []) if available else [], "available": available,
                      "quantity": line.get("quantity", 1), "notes": line.get("notes", ""),
                      "image_state": "current" if available else "unavailable"})
    return items


@router.get("/requests/queue/status")
async def queue_status(user=Depends(c.operations)):
    from . import queue_reset
    return await queue_reset.status()


@router.get("/requests/reports/completions")
async def completion_report(date: str = "", start: str = "", end: str = "", telecaller: str = "", page: int = Query(1, ge=1),
                            limit: int = Query(50, ge=1, le=200), user=Depends(c.allow("admin", "telecaller"))):
    """Distinct completed queries per completing telecaller in an Asia/Kolkata calendar interval (both dates inclusive,
    1-366 days). Counts come from the immutable completion ledger: a retried completion is one record, a completion that
    was later reopened is excluded (`superseded`), a re-completion after reopening is a new record."""
    lower, upper, days = date_bounds(start or date, end or date)
    await reconcile_completion_ledger(since_iso=lower)   # F03: counts never miss a completion whose ledger write was interrupted
    query = {"completed_at": {"$gte": lower, "$lt": upper}, "superseded_at": None}
    if user["role"] == "telecaller":
        telecaller = user["id"]
    if telecaller:
        query["actor_id"] = telecaller
    per = {r["_id"]: r async for r in c.db.request_completions.aggregate([{"$match": query},
        {"$group": {"_id": "$actor_id", "name": {"$last": "$actor_name"}, "requests": {"$addToSet": "$request_id"}, "records": {"$sum": 1}}}])}
    staff = {u["id"]: u async for u in c.db.users.find({"role": {"$in": ["telecaller", "executive", "admin"]}}, {"_id": 0, "id": 1, "name": 1, "role": 1, "account_status": 1})}
    rows = []
    for actor_id, agg in per.items():
        person = staff.get(actor_id, {})
        rows.append({"id": actor_id, "name": person.get("name") or agg.get("name") or "(former staff)", "role": c.role(person["role"]) if person.get("role") else "unknown",
                     "completed": len(agg["requests"]), "records": agg["records"], "account_status": c.account_status(person) if person else "deleted"})
    rows.sort(key=lambda r: (-r["completed"], r["name"]))
    records = await c.db.request_completions.find(query, {"_id": 0}).sort([("completed_at", -1), ("id", 1)]).skip((page-1)*limit).limit(limit).to_list(limit)
    total = await c.db.request_completions.count_documents(query)
    return {"timezone": "Asia/Kolkata", "start_utc": lower, "end_exclusive_utc": upper, "calendar_days": days, "inclusive": "start and end dates inclusive",
            "telecallers": rows, "total_completed": sum(r["completed"] for r in rows), "records": records, "total_records": total,
            "page": page, "limit": limit, "pages": (total+limit-1)//limit,
            "semantics": {"completed": "distinct requests whose latest completion by this actor lies in the interval and was not reopened",
                          "retry": "a repeated Mark Complete on a resolved request adds no record", "reopen": "marks the completion superseded; a later re-completion is a new record",
                          "cancelled": "never counted as completed"}}


@router.get("/requests/{rid}")
async def detail(rid: str, user=Depends(c.operations)):
    raw = await c.db.requests.find_one({"id": rid}, {"_id": 0})
    if not raw:
        c.fail(404, "REQUEST_NOT_FOUND", "Request not found")
    from .queue_reset import release_if_due
    await release_if_due(raw)   # F04: the screen never shows yesterday's claimant as the current owner after 03:00
    await ensure_completion_ledger(raw)
    rows = await c.db.requests.aggregate([{"$match": {"id": rid}}] + enrich_pipeline()).to_list(1)
    doc = rows[0]
    names = {u["id"]: u.get("name", "") async for u in c.db.users.find({"id": {"$in": [x for x in (doc.get("assignee_id"), doc.get("resolver_id")) if x]}}, {"_id": 0, "id": 1, "name": 1})}
    completions = await c.db.request_completions.find({"request_id": rid}, {"_id": 0}).sort("completed_at", -1).to_list(20)
    customer = await c.db.users.find_one({"id": doc.get("customer_id")}, {"_id": 0, "id": 1, "name": 1, "shop_name": 1, "location": 1, "city": 1,
                                                                            "lead_status": 1, "follow_up_at": 1, "customer_type": 1, "assigned_salesperson": 1})
    others = await c.db.requests.count_documents({"user_id": doc.get("customer_id"), "id": {"$ne": rid}}) if doc.get("customer_id") else 0
    return {**view_doc(doc), "assignee_name": names.get(doc.get("assignee_id"), ""), "resolver_name": names.get(doc.get("resolver_id"), doc.get("resolver_name", "")),
            "items": await product_snapshots(doc), "completions": completions, "customer": customer or {}, "other_requests": others,
            "permissions": {"can_work": user["role"] in {"admin", "telecaller"} and (user["role"] == "admin" or doc.get("assignee_id") == user["id"]),
                            "can_claim": user["role"] in {"admin", "telecaller"} and not doc.get("assignee_id") and doc.get("status") in OPEN,
                            "can_assign": user["role"] == "admin", "can_reopen": user["role"] == "admin"}}


class Mutation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str | None = None
    head: str | None = None
    follow_up_at: str | None = Field(None, max_length=40)
    outcome: str | None = None
    notes: str = Field("", max_length=3000)
    reason: str = Field("", max_length=500)
    version: int | None = Field(None, ge=0)
    action: str = "update"
    assigned_to: str | None = None
    idempotency_key: str | None = Field(None, max_length=120)


ACTIONS = {"update", "claim", "assign", "reopen", "response", "complete", "release"}


def follow_up_value(raw):
    if raw is None or raw == "":
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(c.timezone.utc).isoformat()
    except ValueError:
        c.fail(422, "INVALID_FOLLOW_UP", "Use an ISO-8601 date-time for the follow-up")


@router.patch("/requests/{rid}")
async def mutate(rid: str, req: Mutation, user=Depends(c.query_workers)):
    """Single atomic work mutation. Ownership is enforced server-side: only the current claimant (or an administrator)
    may change head, notes, follow-up or complete; a telecaller can only claim an unclaimed open query. Every write
    is an atomic predicate on the version read here, so a stale screen or a concurrent worker gets 409."""
    old = await c.db.requests.find_one({"id": rid}, {"_id": 0})
    if not old:
        c.fail(404, "REQUEST_NOT_FOUND", "Request not found")
    from .queue_reset import release_if_due
    old = await release_if_due(old)   # F04: an assignment from before today's 03:00 boundary is released before any edit
    key = c.digest(user["id"] + ":" + req.idempotency_key) if req.idempotency_key else None
    if key and key in old.get("mutation_keys", []):
        await ensure_completion_ledger(old)   # a retried completion whose ledger write was interrupted is repaired here
        return view_doc(old)
    version = old.get("version", 0)
    if req.version is not None and req.version != version:
        c.fail(409, "VERSION_CONFLICT", "Request changed; refresh before updating")
    assignee = old.get("assignee_id", old.get("assigned_to", ""))
    before = status(old["status"])
    if req.action not in ACTIONS:
        c.fail(422, "INVALID_ACTION", "Use update, claim, assign, reopen, response, complete or release")
    after = status(req.status or old["status"])
    if req.action == "complete":
        after = "resolved"
    if req.action == "claim":
        if assignee == user["id"] and before in OPEN:
            return {**view_doc(old), "already_claimed": True}  # idempotent double tap
        if before in TERMINAL:
            c.fail(409, "ALREADY_COMPLETED", "This query is already completed")
        if assignee:
            # Includes administrators: a takeover is an explicit `assign` with a reason, never a silent claim.
            owner = await c.db.users.find_one({"id": assignee}, {"_id": 0, "name": 1})
            raise c.HTTPException(409, {"code": "ALREADY_ASSIGNED", "detail": f"{(owner or {}).get('name') or 'Another telecaller'} already took this query",
                                        "assignee_id": assignee, "assignee_name": (owner or {}).get("name", ""), "version": version})
        after = "in_progress" if before == "pending" else before
    elif user["role"] == "telecaller":
        if req.action in {"assign", "release"} or req.assigned_to is not None:
            c.fail(403, "ASSIGNMENT_DENIED", "Only administrators can reassign or release queries")
        if req.action == "reopen":
            c.fail(403, "REOPEN_DENIED", "Only administrators can reopen a completed query")
        if assignee != user["id"]:
            c.fail(403, "CLAIM_REQUIRED", "Take the query first; another telecaller's query cannot be edited or completed")
    if req.action in {"assign", "reopen", "release"} and len(req.reason.strip()) < 5:
        c.fail(422, "REASON_REQUIRED", "Give a short reason for this administrator action (it is recorded in the audit history)")
    if before in TERMINAL and after != before:
        if req.action != "reopen" or after != "pending":
            c.fail(409, "EXPLICIT_REOPEN_REQUIRED", "Reopen completed queries explicitly to pending")
    elif req.action == "reopen":
        c.fail(409, "NOT_TERMINAL", "Only completed or cancelled queries can be reopened")
    if before in TERMINAL and req.action == "complete":
        await ensure_completion_ledger(old)   # F03: a missing ledger row (partial write) is recovered by any retry
        return {**view_doc(old), "already_completed": True}  # idempotent retry: no second event, no second ledger row
    if req.action == "complete" and not assignee and user["role"] != "admin":
        c.fail(403, "CLAIM_REQUIRED", "Take the query before completing it")
    if req.outcome is not None and req.outcome not in OUTCOMES:
        c.fail(422, "INVALID_OUTCOME", "Use converted, not_interested or other")
    ts = c.stamp()
    changes = {"updated_at": ts, "last_editor_id": user["id"], "status": after}
    events = []
    if req.action == "claim" or (req.assigned_to is not None and req.action in {"assign", "update"}):
        target = user["id"] if req.action == "claim" else req.assigned_to
        if target:
            staff_user = await c.db.users.find_one({"id": target}, {"_id": 0})
            c.usable(staff_user)
            if c.role(staff_user["role"]) not in {"admin", "telecaller"}:
                c.fail(422, "INVALID_ASSIGNEE", "Assign a telecaller or administrator")
        changes.update(assignee_id=target, assigned_to=target, claimed_at=ts if target else None)
        if target and after == "pending":
            after = changes["status"] = "in_progress"
        events.append(event("claim" if req.action == "claim" else "assignment", user, rid, assignee, target, notes=req.reason, request_status=after))
    if req.action == "release":
        changes.update(assignee_id="", assigned_to="", claimed_at=None, status="pending")
        after = "pending"
        events.append(event("release", user, rid, assignee, "", notes=req.reason, request_status="pending"))
    if req.head is not None:
        new_head = head(req.head)
        if new_head != (old.get("head") or "new"):
            changes["head"] = new_head
            events.append(event("head_change", user, rid, old.get("head", "new"), new_head, request_status=after))
    if req.follow_up_at is not None:
        changes["follow_up_at"] = follow_up_value(req.follow_up_at)
        events.append(event("follow_up", user, rid, old.get("follow_up_at"), changes["follow_up_at"], request_status=after))
    if before != after:
        kind = "resolution" if after == "resolved" else "reopening" if req.action == "reopen" else "status_change"
        events.append(event(kind, user, rid, before, after, notes=req.reason if req.action == "reopen" else "", request_status=after))
        if after == "resolved":
            changes.update(resolved_at=ts, resolver_id=user["id"], resolver_name=user.get("name", ""), completed_by_id=user["id"],
                           completed_by_name=user.get("name", ""), completed_by_role=user["role"], handled_by_id=user["id"],
                           handled_by_name=user.get("name", ""), outcome=req.outcome or old.get("outcome") or "other")
        if req.action == "reopen":
            changes.update(pending_since=ts, resolved_at=None, resolver_id=None, completed_by_id=None, assignee_id="", assigned_to="",
                           claimed_at=None, head="new", queue_sort_at=ts)
    elif req.outcome is not None:
        changes["outcome"] = req.outcome
    if req.notes:
        events.append(event("note", user, rid, notes=req.notes, request_status=after))
    if req.action == "response":
        events.append(event("response", user, rid, request_status=after))
    if not events:
        return view_doc(old)
    if not old.get("first_response_at") and (before != after or req.action == "response"):
        changes["first_response_at"] = ts
    predicate = {"id": rid, "version": version if "version" in old else {"$exists": False}}
    update = {"$set": changes, "$inc": {"version": 1}, "$push": {"events": {"$each": events}}}
    if after == "resolved" and before != after:
        update["$inc"]["completion_count"] = 1
    if key:
        update["$addToSet"] = {"mutation_keys": key}
    doc = await c.db.requests.find_one_and_update(predicate, update, projection={"_id": 0}, return_document=ReturnDocument.AFTER)
    if not doc:
        c.fail(409, "VERSION_CONFLICT", "Another staff member updated the request; refresh and retry")
    if after == "resolved" and before != after:
        await record_completion(doc, user, ts)
    if req.action == "reopen":
        # Scoped to the completion being reopened (sequence read under this version): a delayed reopen can never
        # supersede a LATER completion, and the reopened completion's row is written first if it was missing.
        await ensure_completion_ledger(old)
        await c.db.request_completions.update_many({"request_id": rid, "superseded_at": None, "sequence": {"$lte": int(old.get("completion_count") or 1)}},
            {"$set": {"superseded_at": ts, "superseded_by": user["id"], "reopen_reason": req.reason}})
    return view_doc(doc)


async def record_completion(doc, user, ts):
    """Immutable completion ledger row (one per completion; keyed by the request's completion sequence so a replayed
    write cannot add a second row). Attribution is snapshotted so reports survive later staff changes."""
    await ensure_completion_ledger({**doc, "completed_by_id": user["id"], "completed_by_name": user.get("name", ""),
                                    "completed_by_role": user["role"], "resolved_at": ts})


async def ensure_completion_ledger(doc):
    """The resolved request document is the source of truth (resolver, time, sequence, outcome); the ledger row is
    derived from it and inserted if missing (F03). Safe to call on every retry / report / startup: the unique key
    `<request id>:<completion sequence>` makes it idempotent. Returns True when a row was added."""
    from pymongo.errors import DuplicateKeyError
    if status(doc.get("status")) != "resolved" or not doc.get("completed_by_id") or not doc.get("resolved_at"):
        return False
    seq = int(doc.get("completion_count") or 1)
    ts = doc["resolved_at"]
    try:
        await c.db.request_completions.insert_one({"id": secrets.token_hex(12), "key": f"{doc['id']}:{seq}", "request_id": doc["id"], "sequence": seq,
            "actor_id": doc["completed_by_id"], "actor_name": doc.get("completed_by_name", ""), "actor_role": doc.get("completed_by_role", "telecaller"),
            "completed_at": ts, "completed_date_ist": datetime.fromisoformat(ts).astimezone(IST).date().isoformat(), "request_type": doc.get("request_type"),
            "customer_id": doc.get("user_id") or doc.get("customer_id"), "customer_name": doc.get("user_name") or doc.get("customer_name", ""),
            "shop_name": doc.get("shop_name") or doc.get("customer_shop_name", ""), "item_count": len(doc.get("product_ids") or []),
            "created_at": doc.get("created_at"), "outcome": doc.get("outcome", "other"), "superseded_at": None})
        return True
    except DuplicateKeyError:
        return False


async def reconcile_completion_ledger(since_iso=None, limit=500):
    """Repairs missing ledger rows for resolved requests (crash between the request update and the ledger write)."""
    query = {"status": "resolved", "completed_by_id": {"$nin": [None, ""]}, "resolved_at": {"$ne": None}}
    if since_iso:
        query["resolved_at"] = {"$gte": since_iso}
    repaired = 0
    async for doc in c.db.requests.find(query, {"_id": 0}).sort("resolved_at", -1).limit(limit):
        if not await c.db.request_completions.find_one({"key": f"{doc['id']}:{int(doc.get('completion_count') or 1)}"}, {"_id": 0, "id": 1}):
            repaired += int(await ensure_completion_ledger(doc))
    return repaired


@router.post("/requests/{rid}/claim")
async def claim(rid: str, user=Depends(c.query_workers)):
    """Take Query: the first successful explicit claim wins (atomic predicate on the version read); everyone else sees
    the winner in the 409 body. Receiving or viewing a notification never claims anything."""
    return await mutate(rid, Mutation(action="claim"), user)


class Completion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    outcome: str | None = None
    notes: str = Field("", max_length=3000)
    version: int | None = Field(None, ge=0)
    idempotency_key: str | None = Field(None, max_length=120)


@router.post("/requests/{rid}/complete")
async def complete(rid: str, req: Completion, user=Depends(c.query_workers)):
    return await mutate(rid, Mutation(action="complete", outcome=req.outcome, notes=req.notes, version=req.version, idempotency_key=req.idempotency_key), user)


async def release_assignments(staff_id, actor, reason):
    """Every open query held by a disabled / deleted staff account returns to the shared queue (pending, no assignee,
    head kept) with an audit event - nothing is silently completed or lost. Idempotent."""
    released = 0
    async for doc in c.db.requests.find({"assignee_id": staff_id, "status": {"$in": OPEN}}, {"_id": 0, "id": 1, "version": 1, "status": 1}):
        ts = c.stamp()
        result = await c.db.requests.update_one({"id": doc["id"], "version": doc["version"] if "version" in doc else {"$exists": False}},
            {"$set": {"assignee_id": "", "assigned_to": "", "claimed_at": None, "status": "pending", "pending_since": ts, "updated_at": ts, "queue_sort_at": ts},
             "$inc": {"version": 1}, "$push": {"events": event("release", actor, doc["id"], staff_id, "", notes=reason, request_status="pending")}})
        released += result.modified_count
    return released


@router.get("/requests/{rid}/history")
async def history(rid: str, user=Depends(c.current_user)):
    rows = await c.db.requests.aggregate([{"$match": {"id": rid}}] + enrich_pipeline()).to_list(1)
    if not rows:
        c.fail(404, "REQUEST_NOT_FOUND", "Request not found")
    doc = rows[0]
    customer = user["role"] == "customer"
    if customer and doc["customer_id"] != user["id"]:
        c.fail(403, "PERMISSION_DENIED", "This is not your request")
    events = doc.get("events", [])
    legacy = [{"id": f"legacy-{rid}-{i}", "type": "legacy_note", "status": ALIASES.get(e.get("status"), e.get("status")),
               "actor_id": e.get("by_id"), "actor_name": e.get("by"), "notes": e.get("note", ""),
               "timestamp": e.get("at"), "provenance": "legacy_notes_history", "resolution_credit": False}
              for i, e in enumerate(doc.get("notes_history", []))]
    if customer:
        events = [{k: e.get(k) for k in ("id", "type", "status", "timestamp")}
                  for e in events if e["type"] in {"creation", "status_change", "resolution", "reopening"}]
        legacy = []
    return {"request": view_doc(doc, customer), "history": legacy + events}


@router.get("/requests/metrics/summary")
async def metrics(start: str = "", end: str = "", search: str = "", request_type: str = "", user=Depends(c.allow("admin", "telecaller"))):
    lower, upper, days = date_bounds(start, end)
    cohort = {"received": 0, "open": 0, "resolved": 0, "cancelled": 0}
    rows = {u["id"]: {"id": u["id"], "name": u.get("name", ""), "resolved": 0, "assigned_workload": 0,
        "open_workload": 0, "resolved_from_assigned": 0, "active_dates": set(), "daily": {}}
        async for u in c.db.users.find({"role": {"$in": ["telecaller", "executive"]}}, {"_id": 0, "id": 1, "name": 1})}
    team_resolved, unknown_legacy = 0, 0
    pipeline = enrich_pipeline() + [{"$match": filters(search=search, request_type=request_type)}]
    async for q in c.db.requests.aggregate(pipeline):
        received = lower <= (q.get("created_at") or "") < upper
        state = q.get("status")
        if received:
            cohort["received"] += 1
            bucket = "open" if state in OPEN else "resolved" if state == "resolved" else "cancelled" if state == "cancelled" else None
            if bucket:
                cohort[bucket] += 1
            if state == "resolved" and not q.get("resolved_at"):
                unknown_legacy += 1
        assignee = rows.get(q.get("assignee_id"))
        if assignee and received:
            assignee["assigned_workload"] += 1
            assignee["open_workload"] += int(state in OPEN)
        resolutions = []
        for e in q.get("events", []):
            ts = e.get("timestamp") or ""
            if not lower <= ts < upper:
                continue
            actor = rows.get(e.get("actor_id"))
            day = datetime.fromisoformat(ts).astimezone(IST).date().isoformat()
            if actor:
                actor["active_dates"].add(day)
                actor["daily"].setdefault(day, {"work_events": 0, "resolved": 0})["work_events"] += 1
            if e["type"] == "resolution":
                resolutions.append(e)
        if resolutions:
            last = max(resolutions, key=lambda e: (e["timestamp"], e["id"]))
            team_resolved += 1
            actor = rows.get(last.get("actor_id"))
            if actor:
                actor["resolved"] += 1
                actor["resolved_from_assigned"] += int(received and assignee is actor)
                day = datetime.fromisoformat(last["timestamp"]).astimezone(IST).date().isoformat()
                actor["daily"][day]["resolved"] += 1
    maximum = max((r["resolved"] for r in rows.values()), default=0)
    for row in rows.values():
        row.update(team_resolved=team_resolved, calendar_days=days, active_days=len(row.pop("active_dates")),
                   top_performer=maximum > 0 and row["resolved"] == maximum)
    visible = list(rows.values()) if user["role"] == "admin" else [rows[user["id"]]] if user["id"] in rows else []
    return {"timezone": "Asia/Kolkata", "start_utc": lower, "end_exclusive_utc": upper, "calendar_days": days,
        "received_cohort": cohort, "period_throughput": team_resolved, "legacy_resolution_timing_unknown": unknown_legacy,
        "telecallers": visible, "status_chips_affect": "table_only", "denominators": {
            "resolved": "distinct team resolutions in period, last resolution per request wins",
            "assigned": "requests created in period currently assigned to this telecaller",
            "active_days": "distinct IST dates with ledger work, not attendance"}}