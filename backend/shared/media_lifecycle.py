"""Managed storage has no supported delete API. Never report remote erasure as done."""
import asyncio
import hashlib
import os
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException

from . import core as c

router = APIRouter(prefix="/api/admin/media", tags=["Media accounting and lifecycle"])


def budget():
    """Application ceiling for NEW tracked objects (backend/.env), not provider entitlement or remaining space."""
    return {"bytes": int(os.environ.get("MEDIA_WRITE_BUDGET_BYTES", 2_000_000_000)),
            "objects": int(os.environ.get("MEDIA_WRITE_OBJECT_LIMIT", 10000))}


def budget_exceeded(limit, unit, used, requested, configured):
    raise HTTPException(413, {"code": "MEDIA_WRITE_BUDGET", "limit": limit, "unit": unit, "used": used,
        "requested": requested, "configured": configured,
        "detail": f"Application write budget reached: {used:,} tracked {unit} + {requested:,} requested exceeds the "
                  f"configured {limit}={configured:,}; owner review required"})


async def tracked_put(path, data, content_type, purpose, owner_id, job_id=None):
    size, sha = len(data), hashlib.sha256(data).hexdigest()
    # Budget decision + intent record form ONE short critical section: every concurrent writer sees the pending bytes
    # of the others (atomic enforcement), while the provider PUT runs outside the lock so analysis previews and chunk
    # uploads never collide on a lock held for a whole transfer. Intent is recorded BEFORE the write so process death
    # after PUT does not hide orphaned bytes.
    async with c.lock("media-budget", seconds=30, wait_seconds=30):
        old = await c.db.media_assets.find_one({"path": path}, {"_id": 0})
        if old and old.get("write_state") == "stored" and old.get("sha256") == sha and old.get("size_bytes") == size:
            # Confirmed identical object already stored: a retried step reuses it instead of paying for a second write.
            # pending/unknown outcomes never qualify - they stay counted and are rewritten until the provider confirms.
            await c.db.media_assets.update_one({"path": path}, {"$set": {"updated_at": c.stamp(), "last_reuse_at": c.stamp()}})
            return {"path": path, "size": size, "reused": True}
        limit, totals = budget(), await usage_totals()
        additional = max(0, size - ((old or {}).get("size_bytes") or 0))
        if totals["bytes"] + additional > limit["bytes"]:
            budget_exceeded("MEDIA_WRITE_BUDGET_BYTES", "bytes", totals["bytes"], additional, limit["bytes"])
        if not old and totals["objects"] >= limit["objects"]:
            budget_exceeded("MEDIA_WRITE_OBJECT_LIMIT", "objects", totals["objects"], 1, limit["objects"])
        record = {"size_bytes": size, "sha256": sha, "content_type": content_type, "purpose": purpose, "owner_id": owner_id,
                  "job_id": job_id, "write_state": "pending", "updated_at": c.stamp()}
        await c.db.media_assets.update_one({"path": path}, {"$set": record, "$setOnInsert": {"created_at": c.stamp()}}, upsert=True)
    try:
        receipt = await asyncio.to_thread(c.store_object, path, data, content_type)
        if receipt.get("path", path) != path:
            raise ValueError("Provider returned a different storage path")
    except Exception as exc:
        await c.db.media_assets.update_one({"path": path}, {"$set": {"write_state": "unknown", "last_error": type(exc).__name__}})
        status = getattr(getattr(exc, "response", None), "status_code", None)
        c.fail(402 if status == 402 else 503, "MEDIA_WRITE_FAILED", "Storage did not confirm the write; no publication occurred")
    await c.db.media_assets.update_one({"path": path}, {"$set": {"write_state": "stored"}})
    return receipt


async def adopt_stored(path, data, purpose):
    """Re-label an already stored object for a permanent purpose instead of writing identical bytes again.
    Only a ledger row in write_state 'stored' whose SHA-256 and length equal the bytes just read back qualifies;
    anything uncertain returns False so the caller writes a fresh copy."""
    asset = await c.db.media_assets.find_one({"path": path}, {"_id": 0, "write_state": 1, "sha256": 1, "size_bytes": 1, "purpose": 1})
    if (not asset or asset.get("write_state") != "stored" or asset.get("size_bytes") != len(data)
            or asset.get("sha256") != hashlib.sha256(data).hexdigest()):
        return False
    await c.db.media_assets.update_one({"path": path}, {"$set": {"purpose": purpose, "permanent": True, "adopted_from": asset.get("purpose"),
                                                                 "adopted_at": c.stamp(), "updated_at": c.stamp()}})
    return True


async def usage_totals():
    rows = await c.db.media_assets.aggregate([{"$group": {"_id": None, "bytes": {"$sum": "$size_bytes"}, "objects": {"$sum": 1}}}]).to_list(1)
    return {"bytes": rows[0]["bytes"], "objects": rows[0]["objects"]} if rows else {"bytes": 0, "objects": 0}


async def referenced(path, job_id=None):
    clauses = [{k: path} for k in ("storage_path", "thumbnail_path", "original_source_storage_path")]
    clauses.append({"images": "/api/files/" + path})
    # Deliberately include hidden/deleted records: retention decisions are separate.
    if await c.db.products.find_one({"$or": clauses}, {"_id": 0, "id": 1}):
        return True
    if await c.db.banners.find_one({"image_url": "/api/files/" + path}, {"_id": 0, "id": 1}):
        return True
    parent = await c.db.media_assets.find_one({"thumbnail_path": path}, {"_id": 0, "path": 1})
    if parent and await c.db.products.find_one({"images": "/api/files/" + parent["path"]}, {"_id": 0, "id": 1}):
        return True
    if job_id:
        job = await c.db.import_jobs.find_one({"id": job_id}, {"_id": 0, "phase": 1})
        if job and job["phase"] not in {"cancelled", "expired", "committed"}:
            # Superseded previews are safe candidates, but current review/source is retained.
            if "/chunks/" in path or await c.db.import_rows.find_one({"job_id": job_id, "preview_path": path}, {"_id": 0, "id": 1}):
                return True
        if "/chunks/" in path and await c.db.products.find_one({"source_upload_id": job_id}, {"_id": 0, "id": 1}):
            return True
    return False


async def audit_candidates():
    cutoff = (c.now() - timedelta(days=7)).isoformat()
    async for asset in c.db.media_assets.find({"created_at": {"$lt": cutoff}}, {"_id": 0}).sort("deletion_checked_at", 1).limit(500):
        if await referenced(asset["path"], asset.get("job_id")):
            state = "retained_reference"
        else:
            state = "blocked_provider_unsupported"
        await c.db.media_assets.update_one({"path": asset["path"]}, {"$set": {
            "deletion_state": state, "deletion_checked_at": c.stamp(), "remote_deleted": False}})


@router.get("/usage")
async def usage(user=Depends(c.admin)):
    groups = await c.db.media_assets.aggregate([{"$group": {"_id": "$purpose", "objects": {"$sum": 1},
        "bytes": {"$sum": "$size_bytes"}, "unknown_size_objects": {"$sum": {"$cond": [{"$eq": [{"$ifNull": ["$size_bytes", None]}, None]}, 1, 0]}}}}]).to_list(100)
    totals, limit = await usage_totals(), budget()
    reached = ("MEDIA_WRITE_BUDGET_BYTES" if totals["bytes"] >= limit["bytes"] else
               "MEDIA_WRITE_OBJECT_LIMIT" if totals["objects"] >= limit["objects"] else None)
    return {"tracked": totals, "groups": [{"purpose": g.pop("_id"), **g} for g in groups],
            "write_budget_bytes": limit["bytes"], "write_object_limit": limit["objects"],
            "remaining": {"bytes": max(0, limit["bytes"] - totals["bytes"]), "objects": max(0, limit["objects"] - totals["objects"])},
            "limit_reached": reached,
            "high_watermark": totals["bytes"] >= limit["bytes"] * 0.8 or totals["objects"] >= limit["objects"] * 0.8,
            "blocked_deletions": await c.db.media_assets.count_documents({"deletion_state": "blocked_provider_unsupported"}),
            "inventory_complete": False, "provider_delete_supported": False,
            "warning": "Application budget, not provider entitlement. Legacy objects/backups are not fully inventoried."}


@router.post("/lifecycle-audit")
async def audit(user=Depends(c.admin)):
    await audit_candidates()
    return {"audited": True, "remote_deletions": 0, "status": "blocked_provider_unsupported"}