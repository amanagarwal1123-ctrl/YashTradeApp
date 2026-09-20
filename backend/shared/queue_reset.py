"""Daily 03:00 Asia/Kolkata release of unfinished customer queries.

Every query that is still open (any non-terminal head, claimed or not) and was created before the boundary is returned
to the shared queue: status `pending`, head `new`, no assignee, `queue_sort_at` = the boundary, so the released batch
sits at the top of the fresh-first queue (deterministic tie-breaker: created_at desc, id asc) while queries created
after the boundary keep sorting ahead by their own creation time. `created_at`, previous head, assignee, follow-up
and notes are preserved in the document history and in the appended `daily_release` event.

Durable cycle marker + lease in `queue_cycles`, idempotent per document (atomic predicate on version, status, last
activity), bounded batches, catch-up after downtime (only the latest missed boundary matters), safe with several
worker processes. Server time only - never the phone's clock.
"""
import asyncio
import logging
import secrets
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from pymongo import ReturnDocument

from . import core as c

log = logging.getLogger("shared.queue_reset")
IST = ZoneInfo("Asia/Kolkata")
RELEASE_AT = time(3, 0)
BATCH = 200
LEASE_SECONDS = 60
OPEN = ["pending", "in_progress", "contacted", "no_response"]
SYSTEM_ACTOR = {"id": "system:daily-release", "role": "admin", "name": "Daily 03:00 release"}
state = {"running": False, "last_tick": None, "last_cycle": None, "last_released": 0, "last_error": None}


def boundary_for(moment):
    """Latest 03:00 IST boundary at or before `moment` (UTC-aware datetime), as (cycle_id, boundary_utc)."""
    local = moment.astimezone(IST)
    day = local.date() if local.time() >= RELEASE_AT else local.date() - timedelta(days=1)
    boundary = datetime.combine(day, RELEASE_AT, tzinfo=IST).astimezone(c.timezone.utc)
    return day.isoformat(), boundary


def next_boundary(moment):
    day, boundary = boundary_for(moment)
    return boundary + timedelta(days=1)


def release_event(doc, cycle_id):
    return {"id": secrets.token_hex(16), "type": "daily_release", "request_id": doc["id"], "actor_id": SYSTEM_ACTOR["id"],
            "actor_role": "system", "actor_name": SYSTEM_ACTOR["name"], "old": doc.get("status"), "new": "pending",
            "notes": "", "status": "pending", "timestamp": c.stamp(), "cycle": cycle_id,
            "previous": {"head": doc.get("head", "new"), "assignee_id": doc.get("assignee_id") or doc.get("assigned_to") or "",
                         "follow_up_at": doc.get("follow_up_at"), "claimed_at": doc.get("claimed_at")}}


def candidate_query(cycle_id, boundary_iso):
    """Eligible for this cycle: still open, created before the boundary, not yet released in this cycle, and NOT holding
    a claim made at/after the boundary. Eligibility is decided by the ASSIGNMENT's age (`claimed_at`), never by
    `updated_at`: a note or head change typed by yesterday's claimant after 03:00 cannot extend that assignment (F04).
    A genuinely new post-boundary claim (claimed_at >= boundary) is respected; a completion is excluded by status."""
    return {"status": {"$in": OPEN}, "created_at": {"$lt": boundary_iso}, "reset_cycle": {"$ne": cycle_id},
            "$or": [{"claimed_at": None}, {"claimed_at": {"$lt": boundary_iso}}]}


async def release_if_due(doc, moment=None):
    """Inline release used by the work mutations and the detail view (F04): if `doc` still carries an assignment from
    before the current 03:00 boundary that the worker has not released yet (worker poll gap, catch-up after downtime),
    release it now with the same atomic predicate the worker uses and return the refreshed document. Unclaimed
    documents are left to the worker (their ordering is the worker's job); nothing happens when not due."""
    if not doc or doc.get("status") not in OPEN or not (doc.get("assignee_id") or doc.get("assigned_to")):
        return doc
    cycle_id, boundary = boundary_for(moment or c.now())
    boundary_iso = boundary.isoformat()
    claimed_at = doc.get("claimed_at")
    if doc.get("reset_cycle") == cycle_id or not (doc.get("created_at") or "") < boundary_iso or (claimed_at and claimed_at >= boundary_iso):
        return doc
    if await release_one(doc, cycle_id, boundary_iso):
        return await c.db.requests.find_one({"id": doc["id"]}, {"_id": 0}) or doc
    return await c.db.requests.find_one({"id": doc["id"]}, {"_id": 0}) or doc


async def release_one(doc, cycle_id, boundary_iso):
    ts = c.stamp()
    predicate = {"id": doc["id"], "version": doc["version"] if "version" in doc else {"$exists": False}, **candidate_query(cycle_id, boundary_iso)}
    update = {"$set": {"status": "pending", "head": "new", "assignee_id": "", "assigned_to": "", "claimed_at": None,
                       "queue_sort_at": boundary_iso, "fresh_at": ts, "reset_cycle": cycle_id, "pending_since": ts, "updated_at": ts,
                       "last_editor_id": SYSTEM_ACTOR["id"],
                       "previous_assignment": {"assignee_id": doc.get("assignee_id") or doc.get("assigned_to") or "",
                                               "head": doc.get("head", "new"), "follow_up_at": doc.get("follow_up_at"), "released_at": ts}},
              "$inc": {"version": 1, "reset_count": 1}, "$push": {"events": release_event(doc, cycle_id)}}
    result = await c.db.requests.update_one(predicate, update)
    return bool(result.modified_count)


async def acquire(cycle_id, boundary):
    """Lease the cycle for this worker; None when another live worker holds it or the cycle is complete."""
    now = c.stamp()
    worker = secrets.token_hex(8)
    doc = await c.db.queue_cycles.find_one_and_update(
        {"_id": cycle_id, "status": {"$ne": "completed"}, "$or": [{"lease_until": None}, {"lease_until": {"$lt": now}}]},
        {"$set": {"lease_until": (c.now() + timedelta(seconds=LEASE_SECONDS)).isoformat(), "worker": worker, "status": "running"},
         "$setOnInsert": {"boundary": boundary.isoformat(), "started_at": now, "released": 0, "batches": 0, "runs": 0}, "$inc": {"attempts": 1}},
        upsert=True, return_document=ReturnDocument.AFTER)
    return worker if doc and doc.get("worker") == worker else None


async def run_cycle(cycle_id, boundary):
    """Idempotent: re-running a finished or half-finished cycle releases only what is still eligible."""
    worker = None
    try:
        worker = await acquire(cycle_id, boundary)
    except Exception:
        # A concurrent upsert of the same _id raises a duplicate key on one side: that side simply did not win the lease.
        return {"cycle": cycle_id, "leased": False}
    if not worker:
        return {"cycle": cycle_id, "leased": False}
    boundary_iso = boundary.isoformat()
    try:
        while True:
            docs = await c.db.requests.find(candidate_query(cycle_id, boundary_iso), {"_id": 0}).sort([("created_at", 1), ("id", 1)]).limit(BATCH).to_list(BATCH)
            if not docs:
                break
            released = sum([int(await release_one(doc, cycle_id, boundary_iso)) for doc in docs])
            await c.db.queue_cycles.update_one({"_id": cycle_id, "worker": worker},
                {"$set": {"lease_until": (c.now() + timedelta(seconds=LEASE_SECONDS)).isoformat()}, "$inc": {"released": released, "batches": 1}})
            if len(docs) < BATCH or not released:
                # `not released`: every candidate changed concurrently (claimed/worked after the boundary) - they are no
                # longer eligible and the next pass re-evaluates; never spin on the same batch.
                if not released and len(docs) == BATCH:
                    await c.db.queue_cycles.update_one({"_id": cycle_id, "worker": worker}, {"$set": {"lease_until": None, "status": "partial"}})
                    return {"cycle": cycle_id, "leased": True, "completed": False}
                break
        await c.db.queue_cycles.update_one({"_id": cycle_id, "worker": worker},
            {"$set": {"status": "completed", "completed_at": c.stamp(), "lease_until": None}, "$inc": {"runs": 1}})
        final = await c.db.queue_cycles.find_one({"_id": cycle_id})
        state.update(last_cycle=cycle_id, last_released=final.get("released", 0))
        return {"cycle": cycle_id, "leased": True, "completed": True, "released": final.get("released", 0), "batches": final.get("batches", 0)}
    except Exception as exc:
        state["last_error"] = type(exc).__name__
        await c.db.queue_cycles.update_one({"_id": cycle_id, "worker": worker}, {"$set": {"lease_until": None, "status": "interrupted"},
                                                                                "$push": {"errors": {"at": c.stamp(), "error": type(exc).__name__}}})
        raise


async def tick(moment=None):
    """Runs the latest due cycle in every usable data scope when it has not completed yet (startup catch-up included)."""
    moment = moment or c.now()
    cycle_id, boundary = boundary_for(moment)
    results = []
    for scope in c.scopes():
        with c.scoped(scope):
            existing = await c.db.queue_cycles.find_one({"_id": cycle_id}, {"status": 1})
            if existing and existing.get("status") == "completed":
                continue
            results.append(await run_cycle(cycle_id, boundary))
    state["last_tick"] = c.stamp()
    return results


async def worker_loop(interval=30):
    state["running"] = True
    try:
        while True:
            try:
                await tick()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                state["last_error"] = type(exc).__name__
                log.warning("Daily release pass failed: %s", type(exc).__name__)
            await asyncio.sleep(interval)
    finally:
        state["running"] = False


async def status():
    cycle_id, boundary = boundary_for(c.now())
    current = await c.db.queue_cycles.find_one({"_id": cycle_id}) or {}
    last = await c.db.queue_cycles.find_one({"status": "completed"}, sort=[("completed_at", -1)]) or {}
    return {"timezone": "Asia/Kolkata", "release_time": "03:00", "worker_running": state["running"], "last_tick": state["last_tick"],
            "current_cycle": {"id": cycle_id, "boundary_utc": boundary.isoformat(), "status": current.get("status", "not_started"),
                              "released": current.get("released", 0), "completed_at": current.get("completed_at")},
            "last_completed_cycle": {k: last.get(k) for k in ("_id", "boundary", "released", "batches", "completed_at")} if last else None,
            "next_boundary_utc": next_boundary(c.now()).isoformat(), "last_error": state["last_error"]}
