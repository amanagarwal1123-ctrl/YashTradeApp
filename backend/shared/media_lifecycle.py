"""Managed storage has no supported delete API. Never report remote erasure as done."""
import asyncio
import hashlib
import os
from datetime import timedelta

from fastapi import APIRouter, Depends

from . import core as c

router = APIRouter(prefix="/api/admin/media", tags=["Media accounting and lifecycle"])


async def tracked_put(path, data, content_type, purpose, owner_id, job_id=None):
    # Record intent BEFORE a write so process death after PUT does not hide orphaned bytes.
    async with c.lock("media-budget", seconds=180):
        budget = int(os.environ.get("MEDIA_WRITE_BUDGET_BYTES", 2_000_000_000))
        count_limit = int(os.environ.get("MEDIA_WRITE_OBJECT_LIMIT", 10000))
        old = await c.db.media_assets.find_one({"path": path}, {"_id": 0})
        totals = await usage_totals()
        additional = max(0, len(data) - ((old or {}).get("size_bytes") or 0))
        if totals["bytes"] + additional > budget or not old and totals["objects"] >= count_limit:
            c.fail(413, "MEDIA_WRITE_BUDGET", "Application write budget reached; owner review required")
        record = {"size_bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(), "content_type": content_type,
                  "purpose": purpose, "owner_id": owner_id, "job_id": job_id, "write_state": "pending",
                  "updated_at": c.stamp()}
        await c.db.media_assets.update_one({"path": path}, {"$set": record, "$setOnInsert": {"created_at": c.stamp()}}, upsert=True)
        try:
            receipt = await asyncio.to_thread(c.put_object, path, data, content_type)
            if receipt.get("path", path) != path:
                raise ValueError("Provider returned a different storage path")
        except Exception as exc:
            await c.db.media_assets.update_one({"path": path}, {"$set": {"write_state": "unknown", "last_error": type(exc).__name__}})
            status = getattr(getattr(exc, "response", None), "status_code", None)
            c.fail(402 if status == 402 else 503, "MEDIA_WRITE_FAILED", "Storage did not confirm the write; no publication occurred")
        await c.db.media_assets.update_one({"path": path}, {"$set": {"write_state": "stored"}})
    return receipt


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
    totals = await usage_totals()
    budget = int(os.environ.get("MEDIA_WRITE_BUDGET_BYTES", 2_000_000_000))
    return {"tracked": totals, "groups": [{"purpose": g.pop("_id"), **g} for g in groups],
            "write_budget_bytes": budget, "write_object_limit": int(os.environ.get("MEDIA_WRITE_OBJECT_LIMIT", 10000)),
            "high_watermark": totals["bytes"] >= budget * 0.8 or totals["objects"] >= int(os.environ.get("MEDIA_WRITE_OBJECT_LIMIT", 10000)) * 0.8,
            "blocked_deletions": await c.db.media_assets.count_documents({"deletion_state": "blocked_provider_unsupported"}),
            "inventory_complete": False, "provider_delete_supported": False,
            "warning": "Application budget, not provider entitlement. Legacy objects/backups are not fully inventoried."}


@router.post("/lifecycle-audit")
async def audit(user=Depends(c.admin)):
    await audit_candidates()
    return {"audited": True, "remote_deletions": 0, "status": "blocked_provider_unsupported"}