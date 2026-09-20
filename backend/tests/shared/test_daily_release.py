"""Daily 03:00 Asia/Kolkata release (R13-B/C): fake-clock boundaries, no old-request cutoff, completed/cancelled excluded,
history preserved, idempotent re-run, post-boundary claims respected, stale-worker races, multi-worker leases, catch-up."""
import asyncio
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from shared import core as c
from shared import queue_reset

IST = ZoneInfo("Asia/Kolkata")


def ist(y, m, d, hh, mm, ss=0):
    return datetime(y, m, d, hh, mm, ss, tzinfo=IST).astimezone(timezone.utc)


def test_boundary_math():
    assert queue_reset.boundary_for(ist(2026, 9, 20, 2, 59, 59)) == ("2026-09-19", ist(2026, 9, 19, 3, 0))
    assert queue_reset.boundary_for(ist(2026, 9, 20, 3, 0, 0)) == ("2026-09-20", ist(2026, 9, 20, 3, 0))
    assert queue_reset.boundary_for(ist(2026, 9, 20, 3, 0, 1)) == ("2026-09-20", ist(2026, 9, 20, 3, 0))
    # month / year boundaries, server (UTC) time only
    assert queue_reset.boundary_for(ist(2026, 10, 1, 1, 0)) == ("2026-09-30", ist(2026, 9, 30, 3, 0))
    assert queue_reset.boundary_for(ist(2027, 1, 1, 3, 30)) == ("2027-01-01", ist(2027, 1, 1, 3, 0))
    assert queue_reset.next_boundary(ist(2026, 9, 20, 3, 0, 1)) == ist(2026, 9, 21, 3, 0)


def request(rid, created, status="in_progress", assignee="u_tele1", head="follow_up", **extra):
    return {"id": rid, "request_type": "callback", "user_id": "u_cust1", "status": status, "assignee_id": assignee, "assigned_to": assignee,
            "head": head, "follow_up_at": "2026-09-21T04:30:00+00:00", "created_at": created.isoformat(), "updated_at": created.isoformat(),
            "queue_sort_at": created.isoformat(), "claimed_at": created.isoformat() if assignee else None, "version": 3, "events": [], **extra}


pytestmark = pytest.mark.asyncio


async def test_release_cycle_semantics(isolated_db, seeded_users, monkeypatch):
    db = isolated_db["db"]
    clock = {"now": ist(2026, 9, 20, 3, 0, 1)}
    monkeypatch.setattr(c, "now", lambda: clock["now"])
    boundary = ist(2026, 9, 20, 3, 0)
    await db.requests.insert_many([
        request("old_follow", ist(2026, 3, 1, 10, 0)),                                   # 6 months old: no cutoff
        request("yesterday_contacted", ist(2026, 9, 19, 18, 0), head="contacted"),
        request("unclaimed_interested", ist(2026, 9, 19, 20, 0), assignee="", head="interested", status="pending"),
        request("legacy_no_version", ist(2026, 9, 19, 12, 0), status="contacted"),
        request("done", ist(2026, 9, 19, 9, 0), status="resolved", head="new"),
        request("cancelled", ist(2026, 9, 19, 9, 0), status="cancelled"),
        request("post_boundary_new", ist(2026, 9, 20, 3, 0, 0, ), assignee="", status="pending", head="new"),
        request("claimed_after_boundary", ist(2026, 9, 19, 23, 0), claimed_at=ist(2026, 9, 20, 3, 0, 0).isoformat(), updated_at=ist(2026, 9, 20, 3, 0, 0).isoformat()),
    ])
    await db.requests.update_one({"id": "legacy_no_version"}, {"$unset": {"version": ""}})
    results = await queue_reset.tick()
    assert results and results[0]["completed"] and results[0]["released"] == 4, results
    released = {d["id"]: d async for d in db.requests.find({"reset_cycle": "2026-09-20"}, {"_id": 0})}
    assert set(released) == {"old_follow", "yesterday_contacted", "unclaimed_interested", "legacy_no_version"}
    doc = released["old_follow"]
    assert doc["status"] == "pending" and doc["head"] == "new" and doc["assignee_id"] == "" and doc["claimed_at"] is None
    assert doc["created_at"] == ist(2026, 3, 1, 10, 0).isoformat()                                  # original creation kept
    assert doc["queue_sort_at"] == boundary.isoformat() and doc["fresh_at"] == clock["now"].isoformat()
    assert doc["follow_up_at"] == "2026-09-21T04:30:00+00:00"                                       # follow-up detail retained
    assert doc["previous_assignment"] == {"assignee_id": "u_tele1", "head": "follow_up", "follow_up_at": "2026-09-21T04:30:00+00:00", "released_at": clock["now"].isoformat()}
    assert doc["events"][-1]["type"] == "daily_release" and doc["events"][-1]["previous"]["head"] == "follow_up" and doc["version"] == 4
    assert released["legacy_no_version"]["version"] == 1
    untouched = {d["id"]: d async for d in db.requests.find({"id": {"$in": ["done", "cancelled", "post_boundary_new", "claimed_after_boundary"]}}, {"_id": 0})}
    assert untouched["done"]["status"] == "resolved" and untouched["cancelled"]["status"] == "cancelled"
    assert untouched["claimed_after_boundary"]["assignee_id"] == "u_tele1" and "reset_cycle" not in untouched["claimed_after_boundary"]
    # queue order: post-boundary request first, then the released batch newest-created first (deterministic)
    order = [d["id"] async for d in db.requests.find({"status": "pending"}, {"_id": 0, "id": 1}).sort([("queue_sort_at", -1), ("created_at", -1), ("id", 1)])]
    assert order == ["post_boundary_new", "unclaimed_interested", "yesterday_contacted", "legacy_no_version", "old_follow"]
    # same cycle twice: nothing released again, no duplicate history
    clock["now"] = ist(2026, 9, 20, 9, 0)
    assert await queue_reset.tick() == []
    assert (await db.requests.find_one({"id": "old_follow"}))["reset_count"] == 1
    assert sum(e["type"] == "daily_release" for e in (await db.requests.find_one({"id": "old_follow"}))["events"]) == 1
    # a released query is claimable immediately; a stale write from the old claimant (old version) fails
    stale = await db.requests.update_one({"id": "old_follow", "version": 3}, {"$set": {"status": "resolved"}})
    assert stale.modified_count == 0
    # next day's boundary releases again; completed work in between stays completed
    await db.requests.update_one({"id": "yesterday_contacted"}, {"$set": {"status": "resolved", "resolved_at": clock["now"].isoformat(), "updated_at": clock["now"].isoformat()}, "$inc": {"version": 1}})
    clock["now"] = ist(2026, 9, 21, 3, 0, 0)
    results = await queue_reset.tick()
    assert results[0]["released"] == 5   # old_follow, unclaimed_interested, legacy_no_version, post_boundary_new, claimed_after_boundary (all created before the 21st boundary)
    assert (await db.requests.find_one({"id": "yesterday_contacted"}))["status"] == "resolved"
    assert (await db.requests.find_one({"id": "old_follow"}))["reset_count"] == 2
    status = await queue_reset.status()
    assert status["current_cycle"]["status"] == "completed" and status["current_cycle"]["released"] == 5


async def test_catch_up_after_downtime_and_restart_midway(isolated_db, seeded_users, monkeypatch):
    db = isolated_db["db"]
    clock = {"now": ist(2026, 9, 22, 11, 45)}   # server was down at 03:00; comes back mid-morning
    monkeypatch.setattr(c, "now", lambda: clock["now"])
    await db.requests.insert_many([request(f"r{i}", ist(2026, 9, 21, 10, i)) for i in range(5)] +
                                  [request("worked_after_boundary", ist(2026, 9, 21, 9, 0), updated_at=ist(2026, 9, 22, 8, 0).isoformat())] +
                                  [request("new_today", ist(2026, 9, 22, 9, 0), assignee="", status="pending", head="new")])
    # simulate a crash midway: an earlier worker leased the cycle and released two documents, then died (lease expired)
    cycle_id, boundary = queue_reset.boundary_for(clock["now"])
    assert cycle_id == "2026-09-22"
    for rid in ("r0", "r1"):
        doc = await db.requests.find_one({"id": rid}, {"_id": 0})
        assert await queue_reset.release_one(doc, cycle_id, boundary.isoformat())
    await db.queue_cycles.insert_one({"_id": cycle_id, "status": "running", "worker": "dead", "released": 2, "batches": 1, "attempts": 1,
                                      "lease_until": (clock["now"] - timedelta(minutes=5)).isoformat(), "boundary": boundary.isoformat(), "started_at": "x"})
    results = await queue_reset.tick()
    assert results[0]["completed"] and results[0]["released"] == 2 + 4        # cumulative: two before the crash, four after restart
    ids = {d["id"] async for d in db.requests.find({"reset_cycle": cycle_id}, {"id": 1})}
    # F04: an edit typed after the boundary under YESTERDAY's claim does not keep the assignment; only a post-boundary
    # claim or a post-boundary creation is preserved
    assert ids == {"r0", "r1", "r2", "r3", "r4", "worked_after_boundary"}
    assert all(d["reset_count"] == 1 for d in await db.requests.find({"reset_cycle": cycle_id}).to_list(None))
    assert (await db.requests.find_one({"id": "worked_after_boundary"}))["assignee_id"] == ""
    assert (await db.requests.find_one({"id": "new_today"}))["head"] == "new" and "reset_cycle" not in await db.requests.find_one({"id": "new_today"})


async def test_multi_worker_and_claim_race(isolated_db, seeded_users, monkeypatch):
    db = isolated_db["db"]
    clock = {"now": ist(2026, 9, 23, 3, 0, 5)}
    monkeypatch.setattr(c, "now", lambda: clock["now"])
    await db.requests.insert_many([request(f"m{i}", ist(2026, 9, 22, 10, i % 60)) for i in range(450)])   # > 2 batches
    cycle_id, boundary = queue_reset.boundary_for(clock["now"])
    # a telecaller claims one released-eligible query at exactly the same moment: the reset must not erase that claim
    doc = await db.requests.find_one({"id": "m7"}, {"_id": 0})
    await db.requests.update_one({"id": "m7", "version": doc["version"]}, {"$set": {"assignee_id": "u_tele2", "claimed_at": clock["now"].isoformat(),
                                                                                    "updated_at": clock["now"].isoformat()}, "$inc": {"version": 1}})
    stale_release = await queue_reset.release_one(doc, cycle_id, boundary.isoformat())   # worker read the document before the claim
    assert stale_release is False
    results = await asyncio.gather(queue_reset.run_cycle(cycle_id, boundary), queue_reset.run_cycle(cycle_id, boundary), queue_reset.run_cycle(cycle_id, boundary))
    leased = [r for r in results if r.get("leased")]
    assert len(leased) >= 1 and sum(r.get("released", 0) for r in leased if r.get("completed")) == 449
    assert await db.requests.count_documents({"reset_cycle": cycle_id}) == 449
    assert (await db.requests.find_one({"id": "m7"}))["assignee_id"] == "u_tele2"
    assert await db.requests.count_documents({"reset_count": {"$gt": 1}}) == 0
    marker = await db.queue_cycles.find_one({"_id": cycle_id})
    assert marker["status"] == "completed" and marker["released"] == 449 and marker["batches"] >= 3
