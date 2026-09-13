import re
import secrets
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Header, Query
from pydantic import BaseModel, ConfigDict, Field
from pymongo import ReturnDocument

from . import core as c

router = APIRouter(prefix="/api", tags=["Unified requests"])
OPEN = ["pending", "in_progress", "contacted", "no_response"]
TERMINAL = ["resolved", "cancelled"]
STATUSES = OPEN + TERMINAL
ALIASES = {"completed": "resolved", "done": "resolved", "assigned": "in_progress"}
TYPES = ["video_call", "ask_price", "callback", "similar_products", "hold_item", "quick_reorder", "cart_selection"]
TYPE_ALIASES = {"price_enquiry": "ask_price", "price_inquiry": "ask_price", "call": "callback",
                "hold": "hold_item", "reorder": "quick_reorder"}
IST = ZoneInfo("Asia/Kolkata")


@router.get("/requests/staff-options")
async def staff_options(user=Depends(c.staff)):
    rows = await c.db.users.find({"role": {"$in": ["admin", "telecaller", "executive"]}}, {"_id": 0, "id": 1, "name": 1, "role": 1}).sort([("name", 1), ("id", 1)]).limit(500).to_list(500)
    return {"users": [{**r, "role": c.role(r["role"])} for r in rows], "limit": 500}


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
                  "version": {"$ifNull": ["$version", 0]}, "assignee_id": {"$ifNull": ["$assignee_id", "$assigned_to"]}}},
        {"$lookup": {"from": c.collection_name("users"), "localField": "customer_id", "foreignField": "id", "as": "_customers",
            "pipeline": [{"$project": {"_id": 0, "name": 1, "phone": 1, "shop_name": 1, "location": 1, "city": 1}}]}},
        {"$set": {"_customer": {"$arrayElemAt": ["$_customers", 0]}}},
        {"$set": {"customer_name": {"$ifNull": ["$_customer.name", "$user_name"]},
            "customer_phone": {"$ifNull": ["$_customer.phone", "$user_phone"]},
            "customer_shop_name": {"$ifNull": ["$_customer.shop_name", "$shop_name"]},
            "customer_location": {"$ifNull": ["$_customer.location", {"$ifNull": ["$_customer.city", "$user_city"]}]},
            "pending_since": {"$ifNull": ["$pending_since", "$created_at"]}}},
        {"$project": {"_id": 0, "_customer": 0, "_customers": 0}},
    ]


def filters(search="", request_type="", assignee="", resolver="", view="all", user=None,
            created_from="", created_to="", resolved_from="", resolved_to="", min_age_minutes=None, max_age_minutes=None):
    query = {}
    if search:
        query["$or"] = [{k: {"$regex": re.escape(search[:120]), "$options": "i"}} for k in
            ["customer_name", "customer_phone", "customer_shop_name", "customer_location", "user_city"]]
    if request_type:
        query["request_type"] = TYPE_ALIASES.get(request_type, request_type)
    if view not in {"all", "mine", "unassigned"}:
        c.fail(422, "INVALID_VIEW", "Use all, mine or unassigned")
    if view == "mine":
        query["assignee_id"] = user["id"]
    elif view == "unassigned":
        query["assignee_id"] = {"$in": [None, ""]}
    elif assignee:
        query["assignee_id"] = assignee
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


def view_doc(doc, customer=False):
    doc["status"] = ALIASES.get(doc.get("status"), doc.get("status", "pending"))
    doc.setdefault("version", 0)
    doc.setdefault("customer_id", doc.get("user_id"))
    doc.setdefault("assignee_id", doc.get("assigned_to", ""))
    doc["user_name"] = doc.get("customer_name", doc.get("user_name", ""))
    doc["user_phone"] = doc.get("customer_phone", doc.get("user_phone", ""))
    doc["user_city"] = doc.get("customer_location", doc.get("user_city", ""))
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
    doc.pop("_id", None)
    if customer:
        for key in ("events", "notes_history", "admin_notes", "handled_by_id", "handled_by_phone", "handled_by_name",
                    "handled_by_code", "resolver_id", "resolver_name", "assignee_id", "assigned_to", "last_editor_id", "mutation_keys"):
            doc.pop(key, None)
    return doc


@router.get("/requests/catalog")
async def catalog(user=Depends(c.current_user)):
    return {"types": TYPES, "statuses": STATUSES, "status_aliases": ALIASES, "type_aliases": TYPE_ALIASES,
        "open_statuses": OPEN, "terminal_statuses": TERMINAL, "reopen": "explicit action=reopen to pending",
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
        "status": "pending", "assignee_id": "", "assigned_to": "", "created_at": ts, "updated_at": ts,
        "pending_since": ts, "version": 0, "payload_hash": payload_hash, "notes_history": [],
        "events": [event("creation", user, rid, new="pending", request_status="pending")]}
    # Deterministic _id provides idempotency without relying on a non-unique legacy id index.
    await c.db.requests.update_one({"_id": rid}, {"$setOnInsert": doc}, upsert=True)
    stored = await c.db.requests.find_one({"_id": rid}, {"_id": 0})
    if stored.get("payload_hash") != payload_hash:
        c.fail(409, "IDEMPOTENCY_CONFLICT", "This idempotency key was used for different request content")
    return view_doc(stored, customer=True)


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
    max_age_minutes: int | None = Query(None, ge=0), sort: str = "oldest", period_resolver: str = "",
    period_start: str = "", period_end: str = "", customer_id: str = "", user=Depends(c.staff)):
    query = filters(search or city, request_type, assignee or assigned_to, resolver or handled_by, view, user,
        created_from, created_to, resolved_from, resolved_to, min_age_minutes, max_age_minutes)
    if customer_id:
        # Matched AFTER enrichment, so legacy user_id-backed rows and customer_id rows both qualify.
        query["customer_id"] = await customer_scope(customer_id)
    if status and status != "all":
        query["status"] = {"$in": OPEN} if status == "open" else globals()["status"](status)
    elif not status and user["role"] == "billing_executive":
        query["status"] = {"$in": OPEN}
    order = {"oldest": {"created_at": 1, "id": 1}, "newest": {"created_at": -1, "id": 1},
             "longest_wait": {"pending_since": 1, "id": 1}}.get(sort)
    if not order:
        c.fail(422, "INVALID_SORT", "Use oldest, newest or longest_wait")
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
        "items": [{"$sort": order}, {"$skip": (page-1)*limit}, {"$limit": limit}], "count": [{"$count": "n"}],
        "by_type": [{"$match": {"status": {"$in": OPEN}}}, {"$group": {"_id": "$request_type", "n": {"$sum": 1}}}]}}]).to_list(1)
    data = output[0]
    total = data["count"][0]["n"] if data["count"] else 0
    ids = {d.get("assignee_id") for d in data["items"]} | {d.get("resolver_id") for d in data["items"]}
    names = {u["id"]: u.get("name", "") async for u in c.db.users.find({"id": {"$in": list(ids - {None, ""})}}, {"_id": 0, "id": 1, "name": 1})}
    items = [{**view_doc(d), "assignee_name": names.get(d.get("assignee_id"), ""),
              "resolver_name": names.get(d.get("resolver_id"), d.get("resolver_name", ""))} for d in data["items"]]
    return {"requests": items, "total": total, "page": page, "limit": limit, "pages": (total+limit-1)//limit,
            "open_counts_by_type": {r["_id"]: r["n"] for r in data["by_type"]}, "server_time": c.stamp(),
            **({"customer_id": query["customer_id"]} if customer_id else {})}


class Mutation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str | None = None
    notes: str = Field("", max_length=3000)
    version: int | None = Field(None, ge=0)
    action: str = "update"
    assigned_to: str | None = None
    idempotency_key: str | None = Field(None, max_length=120)


@router.patch("/requests/{rid}")
async def mutate(rid: str, req: Mutation, user=Depends(c.allow("admin", "telecaller"))):
    old = await c.db.requests.find_one({"id": rid}, {"_id": 0})
    if not old:
        c.fail(404, "REQUEST_NOT_FOUND", "Request not found")
    key = c.digest(user["id"] + ":" + req.idempotency_key) if req.idempotency_key else None
    if key and key in old.get("mutation_keys", []):
        return view_doc(old)
    version = old.get("version", 0)
    if req.version is not None and req.version != version:
        c.fail(409, "VERSION_CONFLICT", "Request changed; refresh before updating")
    assignee = old.get("assignee_id", old.get("assigned_to", ""))
    before, after = status(old["status"]), status(req.status or old["status"])
    if req.action not in {"update", "claim", "assign", "reopen", "response"}:
        c.fail(422, "INVALID_ACTION", "Use update, claim, assign, reopen or response")
    if user["role"] == "telecaller":
        if req.action == "claim":
            if assignee or before in TERMINAL:
                c.fail(409, "ALREADY_ASSIGNED", "Only open unassigned requests can be claimed")
        elif assignee != user["id"]:
            c.fail(403, "CLAIM_REQUIRED", "Claim the unassigned request first; takeover requires an administrator")
        if req.action == "assign" or req.assigned_to is not None:
            c.fail(403, "ASSIGNMENT_DENIED", "Only administrators can reassign requests")
    if before in TERMINAL and after != before:
        if req.action != "reopen" or after != "pending":
            c.fail(409, "EXPLICIT_REOPEN_REQUIRED", "Reopen terminal requests explicitly to pending")
    elif req.action == "reopen":
        c.fail(409, "NOT_TERMINAL", "Only resolved or cancelled requests can be reopened")
    changes = {"updated_at": c.stamp(), "last_editor_id": user["id"], "status": after}
    events = []
    if req.action == "claim" or req.assigned_to is not None:
        target = user["id"] if req.action == "claim" else req.assigned_to
        if target:
            staff_user = await c.db.users.find_one({"id": target}, {"_id": 0})
            c.usable(staff_user)
            if c.role(staff_user["role"]) not in {"admin", "telecaller"}:
                c.fail(422, "INVALID_ASSIGNEE", "Assign a telecaller or administrator")
        changes.update(assignee_id=target, assigned_to=target)
        events.append(event("claim" if req.action == "claim" else "assignment", user, rid, assignee, target, request_status=after))
    if before != after:
        kind = "resolution" if after == "resolved" else "reopening" if req.action == "reopen" else "status_change"
        events.append(event(kind, user, rid, before, after, request_status=after))
        if after == "resolved":
            changes.update(resolved_at=c.stamp(), resolver_id=user["id"], resolver_name=user.get("name", ""),
                handled_by_id=user["id"], handled_by_name=user.get("name", ""))
        if req.action == "reopen":
            changes.update(pending_since=c.stamp(), resolved_at=None, resolver_id=None)
    if req.notes:
        events.append(event("note", user, rid, notes=req.notes, request_status=after))
    if req.action == "response":
        events.append(event("response", user, rid, request_status=after))
    if not events:
        return view_doc(old)
    if not old.get("first_response_at") and (before != after or req.action == "response"):
        changes["first_response_at"] = c.stamp()
    predicate = {"id": rid, "version": version if "version" in old else {"$exists": False}}
    update = {"$set": changes, "$inc": {"version": 1}, "$push": {"events": {"$each": events}}}
    if key:
        update["$addToSet"] = {"mutation_keys": key}
    doc = await c.db.requests.find_one_and_update(predicate, update, projection={"_id": 0}, return_document=ReturnDocument.AFTER)
    if not doc:
        c.fail(409, "VERSION_CONFLICT", "Another staff member updated the request; refresh and retry")
    return view_doc(doc)


@router.post("/requests/{rid}/claim")
async def claim(rid: str, user=Depends(c.allow("admin", "telecaller"))):
    return await mutate(rid, Mutation(action="claim"), user)


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