"""Unseen-first Home discovery.

A refresh opens a discovery SESSION: the server partitions the eligible catalogue (same visibility / metal / category
rules as the catalogue) into products this signed-in user has not yet actually seen and products already seen, shuffles
the unseen part with a fresh seed, orders the seen fallback least-recently-seen first, and stores ONLY the ordered ids
(bounded) for that session. Pages are stable slices of that order (no duplicates, no re-randomised pages); a new refresh
is a new session, so late responses of the old one can be discarded by their session id. What counts as "seen" is a
real viewability impression reported by the app (item mostly visible for a dwell time), never a download/prefetch.
"""
import random
import secrets
from datetime import timedelta

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field

from . import core as c

router = APIRouter(prefix="/api", tags=["Discovery"])
MAX_SESSION_IDS = 4000      # ids only (~36 bytes each): bounded per session, never the catalogue itself
WALK_CHUNK = 1000           # catalogue ids examined per indexed step of the unseen walk
SESSION_HOURS = 6
PAGE_LIMIT = 50


class Start(BaseModel):
    model_config = ConfigDict(extra="forbid")
    metal_type: str = Field("", max_length=40)
    category: str = Field("", max_length=80)
    post_type: str = Field("", max_length=40)
    limit: int = Field(20, ge=1, le=PAGE_LIMIT)


def eligible_query(metal_type="", category="", post_type=""):
    query = {"is_deleted": {"$ne": True}, "visibility": {"$ne": "hidden"}}
    for key, value in {"metal_type": metal_type, "category": category, "post_type": post_type}.items():
        if value:
            query[key] = value
    return query


def filter_key(req: Start):
    return f"{req.metal_type}|{req.category}|{req.post_type}"


CATALOGUE_ORDER = [("created_at", -1), ("id", 1)]   # the stable catalogue order the walk follows (indexed)


def after_position(pos):
    """Catalogue documents strictly AFTER `pos` in CATALOGUE_ORDER (older, or same instant with a greater id)."""
    return {"$or": [{"created_at": {"$lt": pos["created_at"]}}, {"created_at": pos["created_at"], "id": {"$gt": pos["id"]}}]}


def up_to_position(pos):
    """Catalogue documents at or BEFORE `pos` in CATALOGUE_ORDER."""
    return {"$or": [{"created_at": {"$gt": pos["created_at"]}}, {"created_at": pos["created_at"], "id": {"$lte": pos["id"]}}]}


async def unseen_of(user_id, chunk):
    """Ids of `chunk` (catalogue rows in order) this account has no impression for - one indexed lookup per chunk."""
    seen = {row["product_id"] async for row in c.db.product_impressions.find(
        {"user_id": user_id, "product_id": {"$in": [p["id"] for p in chunk]}}, {"_id": 0, "product_id": 1})}
    return [p["id"] for p in chunk if p["id"] not in seen]


async def unseen_walk(user_id, query, cursor, want, fresh_since=None):
    """Walks the eligible catalogue in its stable order from this account's continuation point (G03), testing each
    chunk of ids against the account's impression history with an indexed lookup - never a bounded list of recent
    impressions - until `want` unseen ids were collected or the WHOLE catalogue was covered once (wrapping around at the
    end and stopping where the walk began). Every eligible product is therefore examined within one full rotation: an
    old unseen product can wait at most one rotation, never forever, and a product this account has seen is never
    offered as unseen because its impression fell out of a window. Stock added since the previous session
    (`fresh_since`) leads, so new arrivals are discoverable at once. Returns (unseen ids, position of the last
    examined product, covered_whole_catalogue)."""
    unseen, position, wrapped = [], cursor, False
    if cursor and fresh_since:
        fresh = await c.db.products.find({"$and": [query, {"created_at": {"$gt": fresh_since}}]}, {"_id": 0, "id": 1}).sort(CATALOGUE_ORDER).limit(want).to_list(want)
        unseen.extend(await unseen_of(user_id, fresh))
    collected = set(unseen)
    while len(unseen) < want:
        clauses = [query]
        if position:
            clauses.append(after_position(position))
        if wrapped and cursor:
            clauses.append(up_to_position(cursor))
        chunk = await c.db.products.find({"$and": clauses}, {"_id": 0, "id": 1, "created_at": 1}).sort(CATALOGUE_ORDER).limit(WALK_CHUNK).to_list(WALK_CHUNK)
        if not chunk:
            if wrapped or not cursor:
                return unseen, position, True          # the whole catalogue was covered once
            wrapped, position = True, None             # reached the end: continue from the beginning up to the start point
            continue
        fresh_ids = set(await unseen_of(user_id, chunk))
        for product in chunk:
            position = {"created_at": product.get("created_at"), "id": product["id"]}
            if product["id"] in fresh_ids and product["id"] not in collected:
                unseen.append(product["id"])
                collected.add(product["id"])
                if len(unseen) == want:
                    break
    return unseen, position, False


async def page_of(session, page, limit):
    order = session["order"]
    total = len(order)
    start = (page - 1) * limit
    wanted = order[start:start + limit]
    docs = {p["id"]: p async for p in c.db.products.find({"id": {"$in": wanted}, **eligible_query()}, {"_id": 0})}
    seen_from = session["unseen_count"]
    items = []
    for index, pid in enumerate(wanted, start=start):
        if pid in docs:
            docs[pid].setdefault("version", 0)
            items.append({**docs[pid], "discovery": {"seen_before": index >= seen_from, "position": index}})
    return {"session_id": session["id"], "products": items, "page": page, "limit": limit, "total": total,
            "pages": max(1, (total + limit - 1) // limit), "unseen": session["unseen_count"], "seen": total - session["unseen_count"],
            "exhausted": session["unseen_count"] == 0, "truncated": bool(session.get("truncated")), "expires_at": session["expires_at"].isoformat() if hasattr(session["expires_at"], "isoformat") else session["expires_at"],
            "mode": "discovery_session", "sort": "unseen shuffled first, then least-recently-seen"}


@router.post("/discovery/sessions")
async def start(req: Start, user=Depends(c.current_user)):
    """Unseen candidates come from the COMPLETE eligible catalogue through an indexed walk that continues from where
    this account's previous session (same filters) stopped and wraps around (F05 / G03): with any catalogue size and
    any impression history, every unseen product is offered within one full rotation and a seen product is never
    re-offered as unseen. The session itself stays bounded: at most MAX_SESSION_IDS unseen ids (`truncated` tells the
    client the catalogue held more; the next refresh continues the rotation), then the seen fallback least-recently-seen
    first. Pages are stable slices of the stored order."""
    query = eligible_query(req.metal_type, req.category, req.post_type)
    key = filter_key(req)
    cursor_doc = await c.db.discovery_cursors.find_one({"user_id": user["id"], "filter_key": key}, {"_id": 0}) or {}
    unseen, position, covered = await unseen_walk(user["id"], query, cursor_doc.get("after"), MAX_SESSION_IDS, cursor_doc.get("updated_at"))
    await c.db.discovery_cursors.update_one({"user_id": user["id"], "filter_key": key},
        {"$set": {"after": position, "updated_at": c.stamp(), "covered_whole_catalogue": covered}, "$inc": {"sessions": 1}}, upsert=True)
    truncated = len(unseen) == MAX_SESSION_IDS and not covered
    seen = []
    if len(unseen) < MAX_SESSION_IDS:
        # Least-recently-seen first from the indexed impression history (oldest impressions, not a recent window),
        # filtered to the currently eligible catalogue; bounded like the unseen part.
        room = MAX_SESSION_IDS - len(unseen)
        oldest = [row["product_id"] async for row in c.db.product_impressions.find({"user_id": user["id"]}, {"_id": 0, "product_id": 1})
                  .sort([("seen_at", 1), ("product_id", 1)]).limit(room * 2)]
        if oldest:
            eligible_seen = {p["id"] async for p in c.db.products.find({**query, "id": {"$in": oldest}}, {"_id": 0, "id": 1})}
            seen = [pid for pid in oldest if pid in eligible_seen][:room]
    random.Random(secrets.randbits(64)).shuffle(unseen)
    doc = {"id": secrets.token_hex(12), "user_id": user["id"], "filters": {"metal_type": req.metal_type, "category": req.category, "post_type": req.post_type},
           "order": unseen + seen, "unseen_count": len(unseen), "created_at": c.stamp(), "expires_at": c.now() + timedelta(hours=SESSION_HOURS),
           "truncated": truncated}
    await c.db.discovery_sessions.insert_one(dict(doc))
    return await page_of(doc, 1, req.limit)


@router.get("/discovery/sessions/{sid}")
async def page(sid: str, page: int = Query(1, ge=1), limit: int = Query(20, ge=1, le=PAGE_LIMIT), user=Depends(c.current_user)):
    session = await c.db.discovery_sessions.find_one({"id": sid, "user_id": user["id"]})
    if not session:
        c.fail(404, "DISCOVERY_SESSION_EXPIRED", "Refresh to start a new discovery session")
    return await page_of(session, page, limit)


class Impressions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    product_ids: list[str] = Field(min_length=1, max_length=50)
    session_id: str = Field("", max_length=64)


@router.post("/discovery/impressions")
async def impressions(req: Impressions, user=Depends(c.current_user)):
    """Meaningful visibility only (the app reports an item after it was mostly on screen for the dwell time)."""
    ts = c.stamp()
    recorded = 0
    for pid in dict.fromkeys(req.product_ids):
        result = await c.db.product_impressions.update_one({"user_id": user["id"], "product_id": pid},
            {"$set": {"seen_at": ts, "session_id": req.session_id}, "$inc": {"count": 1}, "$setOnInsert": {"first_seen_at": ts}}, upsert=True)
        recorded += int(bool(result.upserted_id) or bool(result.modified_count))
    return {"recorded": recorded, "seen_total": await c.db.product_impressions.count_documents({"user_id": user["id"]})}


@router.get("/discovery/impressions/summary")
async def summary(user=Depends(c.current_user)):
    return {"seen_total": await c.db.product_impressions.count_documents({"user_id": user["id"]}),
            "eligible_total": await c.db.products.count_documents(eligible_query()),
            "retention": "kept while the account exists; deleted with the account (part of the personal-data cleanup)"}
