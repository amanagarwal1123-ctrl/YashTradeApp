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
MAX_SEEN = 5000             # most recent impressions consulted per session
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
    """Unseen candidates are selected across the COMPLETE eligible catalogue (indexed `id $nin <seen ids>` query), not
    from a newest-N window, so an old product this account never saw always becomes discoverable (F05). The session
    itself stays bounded: at most MAX_SESSION_IDS unseen ids (a later refresh reaches the rest once these were seen),
    then the seen fallback least-recently-seen first. `truncated` tells the client when the catalogue exceeded the bound."""
    query = eligible_query(req.metal_type, req.category, req.post_type)
    seen_at = {row["product_id"]: row["seen_at"] async for row in
               c.db.product_impressions.find({"user_id": user["id"]}, {"_id": 0, "product_id": 1, "seen_at": 1}).sort("seen_at", -1).limit(MAX_SEEN)}
    unseen = [p["id"] async for p in c.db.products.find({**query, "id": {"$nin": list(seen_at)}}, {"_id": 0, "id": 1})
              .sort([("created_at", -1), ("id", 1)]).limit(MAX_SESSION_IDS)]
    truncated = len(unseen) == MAX_SESSION_IDS
    seen = []
    if len(unseen) < MAX_SESSION_IDS and seen_at:
        eligible_seen = {p["id"] async for p in c.db.products.find({**query, "id": {"$in": list(seen_at)}}, {"_id": 0, "id": 1})}
        seen = sorted(eligible_seen, key=lambda pid: (seen_at[pid], pid))[:MAX_SESSION_IDS - len(unseen)]  # least recently seen first
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
