import asyncio
import hashlib
import io
import json
import math
import os
import secrets
import shutil
import sys
import tempfile
from datetime import timedelta
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, File, Header, Query, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from . import core as c
from .commerce import validate_product
from .pdf_parser import thumbnail
from .pdf_schema import contract
from .media_lifecycle import tracked_put, adopt_stored, audit_candidates

router = APIRouter(prefix="/api", tags=["Reviewed PDF import v1"])
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures/catalog-v1"
TEMP = Path(os.environ.get("PDF_WORK_DIR", tempfile.gettempdir())) / "yash-import-v1"
TEMP.mkdir(parents=True, exist_ok=True)
WORKER = Path(__file__).resolve().parents[1] / "tools/parse_catalog_page.py"


def limits():
    return {"max_bytes": int(os.environ.get("PDF_MAX_BYTES", 64*1024*1024)),
        "chunk_bytes": 1024*1024, "max_pages": int(os.environ.get("PDF_MAX_PAGES", 200)),
        "page_timeout_seconds": 25, "worker_memory_mb": 512, "temporary_retention_days": 7,
        "tested_maximum": "See PDF_VALIDATION_EVIDENCE.md; configured limits are not performance claims"}


@router.get("/pdf-template/capabilities")
async def capabilities(user=Depends(c.content)):
    return {"template": contract(), "limits": limits(), "sample_url": "/api/pdf-template/sample.pdf",
            "authoring_url": "/api/pdf-template/authoring.json", "default_mode": "template_v1"}


@router.post("/batches/{batch_id}/import-pdf")
async def retired_direct_import(batch_id: str, user=Depends(c.content)):
    c.fail(410, "REVIEWED_IMPORT_REQUIRED", "Use the capability endpoint and chunked reviewed import service")


@router.get("/pdf-template/sample.pdf")
async def sample(user=Depends(c.content)):
    path = FIXTURES / "sample.pdf"
    if not path.exists():
        c.fail(503, "TEMPLATE_NOT_BUILT", "Sample template has not been generated")
    return FileResponse(path, media_type="application/pdf", filename="Yash-Catalog-Template-v1.pdf")


@router.get("/pdf-template/authoring.json")
async def authoring(user=Depends(c.content)):
    return FileResponse(FIXTURES / "authoring.json", media_type="application/json", filename="Yash-Catalog-v1.json")


async def job_for(jid, user):
    job = await c.db.import_jobs.find_one({"id": jid}, {"_id": 0})
    if not job:
        c.fail(404, "IMPORT_NOT_FOUND", "Import not found")
    if job["owner_id"] != user["id"]:
        c.fail(403, "IMPORT_OWNER_REQUIRED", "Only the owning administrator can access this import")
    return job


class Init(BaseModel):
    batch_id: str
    filename: str = Field(min_length=5, max_length=160)
    file_size: int = Field(gt=100)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    total_chunks: int = Field(gt=0)
    mode: Literal["template_v1", "legacy_pages"] = "template_v1"


@router.post("/pdf-upload/init")
async def init(req: Init, user=Depends(c.content)):
    lim = limits()
    if await c.db.import_jobs.count_documents({"owner_id": user["id"], "phase": {"$in": ["uploading", "queued", "analyzing", "review", "paused"]}}) >= 4:
        identity = c.digest(f"{user['id']}:{req.batch_id}:{req.sha256}:{req.mode}")[:32]
        if not await c.db.import_jobs.find_one({"id": identity}, {"_id": 0}):
            c.fail(429, "ACTIVE_IMPORT_LIMIT", "Finish or cancel an active import (maximum four)")
    if not req.filename.lower().endswith(".pdf"):
        c.fail(422, "PDF_REQUIRED", "Select a PDF file")
    if req.file_size > lim["max_bytes"]:
        c.fail(413, "PDF_SIZE_LIMIT", f"Configured limit: {lim['max_bytes']} bytes")
    if req.total_chunks != math.ceil(req.file_size/lim["chunk_bytes"]):
        c.fail(422, "CHUNK_MANIFEST_INVALID", "Declared chunk count does not match file length")
    if not await c.db.batches.find_one({"id": req.batch_id, "status": {"$ne": "archived"}}):
        c.fail(404, "BATCH_NOT_FOUND", "Choose an existing batch")
    identity = c.digest(f"{user['id']}:{req.batch_id}:{req.sha256}:{req.mode}")
    jid = identity[:32]
    ts = c.stamp()
    await c.db.import_jobs.update_one({"_id": jid}, {"$setOnInsert": {"id": jid, "owner_id": user["id"],
        **req.model_dump(), "phase": "uploading", "created_at": ts, "updated_at": ts,
        "manifest": {}, "bytes_received": 0, "next_page": 0, "version": 0}}, upsert=True)
    old = await job_for(jid, user)
    if old["file_size"] != req.file_size:
        c.fail(409, "FILE_IDENTITY_MISMATCH", "This resume does not match the original file")
    if old["phase"] in {"cancelled", "expired"}:
        c.fail(409, "IMPORT_CANCELLED", "This import was cancelled; create a new batch to restart")
    return {"upload_id": jid, "chunk_size": lim["chunk_bytes"], "phase": old["phase"], "sha256": req.sha256}


@router.post("/pdf-upload/{jid}/chunk")
async def chunk(jid: str, chunk_index: int = Query(ge=0), file: UploadFile = File(...),
                x_chunk_sha256: str | None = Header(None), user=Depends(c.content)):
    job = await job_for(jid, user)
    if job["phase"] != "uploading":
        c.fail(409, "IMPORT_NOT_UPLOADING", "Resume the upload before sending chunks")
    size = limits()["chunk_bytes"]
    if chunk_index >= job["total_chunks"]:
        c.fail(422, "CHUNK_INDEX_INVALID", "Chunk index exceeds declared manifest")
    expected = min(size, job["file_size"]-chunk_index*size)
    data = await file.read(size+1)
    checksum = hashlib.sha256(data).hexdigest()
    if len(data) != expected or checksum != x_chunk_sha256:
        c.fail(422, "CHUNK_CHECKSUM_INVALID", "Chunk size or SHA-256 does not match")
    async with c.lock(f"chunk:{jid}:{chunk_index}", seconds=180):
        job = await job_for(jid, user)
        entry = job.get("manifest", {}).get(str(chunk_index))
        if entry:
            if entry["sha256"] != checksum:
                c.fail(409, "CHUNK_CONFLICT", "Previously acknowledged chunk differs")
            return {"received": chunk_index, "duplicate": True}
        path = f"yash-trade/imports/{jid}/chunks/{chunk_index}"
        await tracked_put(path, data, "application/octet-stream", "pdf_chunk", user["id"], jid)
        result = await c.db.import_jobs.update_one({"id": jid, "phase": "uploading", f"manifest.{chunk_index}": {"$exists": False}},
            {"$set": {f"manifest.{chunk_index}": {"path": path, "sha256": checksum, "size": len(data)}, "updated_at": c.stamp()},
             "$inc": {"bytes_received": len(data)}})
        if not result.modified_count:
            c.fail(409, "IMPORT_STATE_CHANGED", "Import paused or cancelled while uploading; refresh status")
    return {"received": chunk_index, "sha256": checksum}


@router.get("/pdf-upload/{jid}/status")
async def status(jid: str, user=Depends(c.content)):
    job = await job_for(jid, user)
    rows = await c.db.import_rows.count_documents({"job_id": jid})
    return {"upload_id": jid, "phase": job["phase"], "upload_status": job["phase"], "sha256": job["sha256"],
        "file_size": job["file_size"], "filename": job["filename"], "bytes_received": job.get("bytes_received", 0),
        "received_chunk_indices": sorted(int(i) for i in job.get("manifest", {})), "total_chunks": job["total_chunks"],
        "total_pages": job.get("total_pages"), "pages_processed": job.get("next_page", 0), "product_count": rows,
        "error": job.get("error"), "result": job.get("result"), "version": job.get("version", 0),
        "updated_at": job["updated_at"], "limits": limits()}


@router.post("/pdf-upload/{jid}/complete")
async def complete(jid: str, user=Depends(c.content)):
    job = await job_for(jid, user)
    if job["phase"] in {"queued", "analyzing", "review", "committed"}:
        return await status(jid, user)
    if job["phase"] != "uploading" or len(job.get("manifest", {})) != job["total_chunks"] or job["bytes_received"] != job["file_size"]:
        c.fail(409, "UPLOAD_INCOMPLETE", "Upload all declared chunks before analysis")
    await c.db.import_jobs.update_one({"id": jid, "phase": "uploading"}, {"$set": {"phase": "queued", "updated_at": c.stamp()}})
    return await status(jid, user)


@router.post("/pdf-upload/{jid}/pause")
async def pause(jid: str, user=Depends(c.content)):
    await job_for(jid, user)
    await c.db.import_jobs.update_one({"id": jid, "phase": {"$in": ["uploading", "queued", "analyzing"]}},
        [{"$set": {"resume_phase": "$phase", "phase": "paused", "updated_at": c.stamp()}}])
    return await status(jid, user)


@router.post("/pdf-upload/{jid}/resume")
async def resume(jid: str, user=Depends(c.content)):
    job = await job_for(jid, user)
    phase = "uploading" if job["phase"] == "paused" and job.get("resume_phase") == "uploading" else "queued"
    await c.db.import_jobs.update_one({"id": jid, "phase": {"$in": ["paused", "error"]}},
        {"$set": {"phase": phase, "updated_at": c.stamp()}, "$unset": {"error": ""}})
    return await status(jid, user)


@router.post("/pdf-upload/{jid}/cancel")
async def cancel(jid: str, user=Depends(c.content)):
    await job_for(jid, user)
    async with c.lock("import:" + jid, seconds=180):
        job = await job_for(jid, user)
        if job["phase"] == "committed":
            c.fail(409, "ALREADY_COMMITTED", "Committed imports cannot be cancelled; manage catalog products instead")
        await c.db.import_jobs.update_one({"id": jid}, {"$set": {"phase": "cancelled", "updated_at": c.stamp()}})
    return await status(jid, user)


@router.get("/pdf-upload/{jid}/preview")
async def preview(jid: str, page: int = Query(1, ge=1), limit: int = Query(20, ge=1, le=100), user=Depends(c.content)):
    await job_for(jid, user)
    rows = await c.db.import_rows.find({"job_id": jid}, {"_id": 0, "preview_path": 0}).sort([("page", 1), ("id", 1)]).skip((page-1)*limit).limit(limit).to_list(limit)
    for row in rows:
        existing = await c.db.products.find_one({"product_code": row["fields"].get("product_code")}, {"_id": 0, "id": 1, "title": 1, "version": 1}) if row["fields"].get("product_code") else None
        row["existing_product"] = existing
        row["preview_url"] = f"/api/pdf-upload/{jid}/rows/{row['id']}/image"
    return {"rows": rows, "page": page, "limit": limit, "total": await c.db.import_rows.count_documents({"job_id": jid})}


@router.get("/pdf-upload/{jid}/rows/{rid}/image")
async def preview_image(jid: str, rid: str, user=Depends(c.content)):
    await job_for(jid, user)
    row = await c.db.import_rows.find_one({"id": rid, "job_id": jid}, {"_id": 0})
    if not row:
        c.fail(404, "ROW_NOT_FOUND", "Import row not found")
    data, _ = await asyncio.to_thread(c.fetch_object, row["preview_path"])
    return Response(data, media_type="image/png", headers={"Cache-Control": "private, no-store"})


class Correction(BaseModel):
    version: int = Field(ge=0)
    fields: dict | None = None
    excluded: bool | None = None
    duplicate_policy: Literal["skip", "update"] | None = None
    expected_product_version: int | None = None
    crop_points: list[float] | None = Field(None, min_length=4, max_length=4)


@router.patch("/pdf-upload/{jid}/rows/{rid}")
async def correct(jid: str, rid: str, req: Correction, user=Depends(c.content)):
    async with c.lock("import:" + jid, seconds=180):
        job = await job_for(jid, user)
        if job["phase"] != "review":
            c.fail(409, "IMPORT_NOT_REVIEWABLE", "Wait for analysis to finish before review")
        row = await c.db.import_rows.find_one({"id": rid, "job_id": jid}, {"_id": 0})
        if not row or row["version"] != req.version:
            c.fail(409, "VERSION_CONFLICT", "Import row changed; reload")
        changes = req.model_dump(exclude_none=True, exclude={"version", "crop_points"})
        if req.fields is not None:
            from .commerce import PRODUCT_FIELDS
            if set(req.fields) - (PRODUCT_FIELDS - {"images"}):
                c.fail(422, "INVALID_FIELD", "Unknown product fields in correction")
            values, errors = validate_product({**row["fields"], **req.fields})
            changes.update(fields=values, errors=errors + [e for e in row.get("errors", []) if e.startswith("photo:")])
        if req.crop_points:
            source = await assemble(job)
            try:
                result = await run_parser(source, row["page"]-1, job["mode"], req.crop_points)
            except ValueError as exc:
                c.fail(422, "INVALID_CROP", str(exc) if re_safe_error(str(exc)) else "Invalid square crop")
            image_path = result["crop_image"]
            data = Path(image_path).read_bytes()
            path = f"yash-trade/imports/{jid}/previews/{rid}-{req.version+1}.png"
            await tracked_put(path, data, "image/png", "pdf_preview", user["id"], jid)
            changes.update(preview_path=path, crop_points=req.crop_points)
            values, errors = validate_product(changes.get("fields", row["fields"]))
            changes.update(fields=values, errors=errors)
        await c.db.import_rows.update_one({"id": rid, "version": req.version}, {"$set": changes, "$inc": {"version": 1}})
        await c.db.import_jobs.update_one({"id": jid}, {"$inc": {"version": 1}})
    return {"saved": True, "row_id": rid, "version": req.version+1}


class Commit(BaseModel):
    version: int = Field(ge=0)
    confirm: Literal[True]
    allow_partial: bool = False
    publish: bool = False


@router.post("/pdf-upload/{jid}/commit")
async def commit(jid: str, req: Commit, user=Depends(c.content)):
    async with c.lock("import:" + jid, seconds=180):
        job = await job_for(jid, user)
        if job["phase"] == "committed":
            return job["result"]
        if job["phase"] != "review" or job.get("version", 0) != req.version:
            c.fail(409, "IMPORT_STATE_CHANGED", "Reload the reviewed import before confirming")
        rows = await c.db.import_rows.find({"job_id": jid}, {"_id": 0}).to_list(limits()["max_pages"]*2)
        invalid = [r for r in rows if not r.get("excluded") and r.get("errors")]
        if invalid and not req.allow_partial:
            c.fail(409, "INVALID_ROWS_REMAIN", "Fix/exclude invalid rows or explicitly confirm valid rows only")
        result = {"created": 0, "updated": 0, "skipped": 0, "failed": 0, "rows": []}
        for row in rows:
            prior = row.get("commit_result")
            if prior:
                outcome = prior
            elif row.get("excluded"):
                outcome = {"status": "skipped", "reason": "Excluded by administrator"}
            elif row.get("errors"):
                outcome = {"status": "failed", "reason": "; ".join(row["errors"])}
            else:
                try:
                    outcome = await commit_row(job, row, req.publish, user)
                except Exception:
                    outcome = {"status": "failed", "reason": "Storage/database operation failed; row remains recoverable"}
            if outcome["status"] != "failed":
                await c.db.import_rows.update_one({"id": row["id"]}, {"$set": {"commit_result": outcome}})
            result[outcome["status"]] += 1
            result["rows"].append({"row_id": row["id"], **outcome})
        phase = "review" if result["failed"] else "committed"
        await c.db.import_jobs.update_one({"id": jid}, {"$set": {"phase": phase, "result": result, "updated_at": c.stamp()}})
        await c.db.batches.update_one({"id": job["batch_id"]}, {"$set": {"image_count": await c.db.products.count_documents({"batch_id": job["batch_id"], "is_deleted": {"$ne": True}})}})
        return result


async def commit_row(job, row, publish, user):
    fields, errors = validate_product(row["fields"])
    if errors:
        return {"status": "failed", "reason": "; ".join(errors)}
    code, fingerprint = fields["product_code"], c.digest(f"{job['sha256']}:{row['block_id']}")
    async with c.lock("product-code:" + code, seconds=180):
        old = await c.db.products.find_one({"product_code": code}, {"_id": 0})
        if old and old.get("last_import_row") == row["id"]:
            return {"status": old.get("last_import_action", "created"), "product_id": old["id"], "reason": "Recovered committed row"}
        if old and row.get("duplicate_policy", "skip") == "skip":
            return {"status": "skipped", "product_id": old["id"], "reason": "Existing product code; skip selected"}
        if old and row.get("expected_product_version") != old.get("version", 0):
            return {"status": "failed", "reason": "Update Existing requires confirmation of the displayed product version"}
        data, _ = await asyncio.to_thread(c.fetch_object, row["preview_path"])
        prefix = f"yash-trade/products/imported/{row['id']}"
        thumb = prefix + "-thumb.png"
        # The reviewed preview IS the product photo: when the ledger confirms the stored object equals the bytes just read
        # back it becomes the permanent master (no second copy of identical bytes); an uncertain preview is copied instead.
        if await adopt_stored(row["preview_path"], data, "import_master"):
            master = row["preview_path"]
        else:
            master = prefix + ".png"
            await tracked_put(master, data, "image/png", "import_master", user["id"], job["id"])
        await tracked_put(thumb, thumbnail(data), "image/png", "thumbnail", user["id"], job["id"])
        action = "updated" if old else "created"
        fields.update(storage_path=master, thumbnail_path=thumb, visibility="all" if publish else "hidden",
            source_type="pdf_template" if job["mode"] == "template_v1" else "pdf_legacy_reviewed",
            source_upload_id=job["id"], source_page=row["page"], source_block_id=row["block_id"],
            source_fingerprint=fingerprint, source_crop_points=row.get("crop_points"), template_version=row.get("template_version"),
            batch_id=job["batch_id"], updated_at=c.stamp(), last_import_row=row["id"], last_import_action=action,
            is_deleted=False)
        if old:
            fields["original_source_storage_path"] = old.get("original_source_storage_path") or old.get("storage_path")
            changed = await c.db.products.update_one({"id": old["id"], "version": old["version"] if "version" in old else {"$exists": False}},
                {"$set": fields, "$inc": {"version": 1}})
            if not changed.modified_count:
                return {"status": "failed", "reason": "Product was edited concurrently"}
            pid = old["id"]
        else:
            pid = c.digest("import-product:" + code)[:32]
            await c.db.products.insert_one({"id": pid, **fields, "images": [], "version": 0, "created_at": c.stamp(), "views": 0})
        return {"status": action, "product_id": pid}


async def assemble(job):
    async with c.lock("import-source:" + job["id"], seconds=180, wait_seconds=10):
        return await assemble_locked(job)


async def assemble_locked(job):
    manifest = job.get("manifest", {})
    if (len(manifest) != job["total_chunks"] or job.get("bytes_received") != job["file_size"]
            or any(str(i) not in manifest for i in range(job["total_chunks"]))):
        raise ValueError("UPLOAD_INCOMPLETE: declared chunks must be acknowledged before source reconstruction")
    directory = TEMP / job["id"]; directory.mkdir(parents=True, exist_ok=True)
    target = directory / "source.pdf"
    if target.exists():
        with target.open("rb") as file:
            if hashlib.file_digest(file, "sha256").hexdigest() == job["sha256"]:
                return target
    digest, count = hashlib.sha256(), 0
    with target.open("wb") as output:
        for i in range(job["total_chunks"]):
            manifest = job["manifest"].get(str(i))
            if not manifest:
                raise ValueError("UPLOAD_INCOMPLETE: missing chunk")
            data, _ = await asyncio.to_thread(c.fetch_object, manifest["path"])
            if len(data) != manifest["size"] or hashlib.sha256(data).hexdigest() != manifest["sha256"]:
                raise ValueError("CHUNK_CORRUPT: re-upload required")
            count += len(data); digest.update(data); output.write(data)
    if count != job["file_size"] or digest.hexdigest() != job["sha256"]:
        target.unlink(missing_ok=True)
        raise ValueError("FILE_IDENTITY_MISMATCH: complete file SHA-256 or length differs")
    return target


async def run_parser(source, page=-1, mode="template_v1", crop=None):
    args = [sys.executable, str(WORKER), str(source), str(page), mode, str(limits()["max_pages"])]
    if crop:
        args.append(json.dumps(crop))
    process = await asyncio.create_subprocess_exec(*args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try:
        out, _ = await asyncio.wait_for(process.communicate(), limits()["page_timeout_seconds"])
    except asyncio.TimeoutError:
        process.kill(); await process.wait()
        raise ValueError("RENDER_TIMEOUT: page exceeds the resource budget")
    try:
        data = json.loads(out)
    except (ValueError, UnicodeError):
        raise ValueError("RENDER_RESOURCE_LIMIT: page exceeded memory or processing budget")
    if data.get("error"):
        raise ValueError(data["error"])
    return data


async def heartbeat(jid, lease):
    while True:
        await asyncio.sleep(10)
        await c.db.import_jobs.update_one({"id": jid, "lease": lease},
            {"$set": {"lease_until": (c.now()+timedelta(seconds=90)).isoformat()}})


async def process_job(job):
    jid, lease = job["id"], job["lease"]
    beat = asyncio.create_task(heartbeat(jid, lease))
    try:
        source = await assemble(job)
        info = await run_parser(source)
        total = info["pages"]
        await c.db.import_jobs.update_one({"id": jid, "lease": lease}, {"$set": {"total_pages": total}})
        for page in range(job.get("next_page", 0), total):
            current = await c.db.import_jobs.find_one({"id": jid, "lease": lease}, {"_id": 0})
            if not current or current["phase"] != "analyzing":
                return
            result = await run_parser(source, page, job["mode"])
            for row in result["rows"]:
                rid = c.digest(f"{jid}:{page}:{row['block_id']}")[:32]
                path = f"yash-trade/imports/{jid}/previews/{rid}.png"
                await tracked_put(path, Path(row.pop("image_file")).read_bytes(), "image/png", "pdf_preview", job["owner_id"], jid)
                await c.db.import_rows.update_one({"_id": rid}, {"$setOnInsert": {"id": rid, "job_id": jid,
                    **row, "preview_path": path, "version": 0, "excluded": False, "duplicate_policy": "skip"}}, upsert=True)
            await c.db.import_jobs.update_one({"id": jid, "lease": lease}, {"$set": {"next_page": page+1, "updated_at": c.stamp()}})
        duplicates = await c.db.import_rows.aggregate([{"$match": {"job_id": jid, "fields.product_code": {"$nin": [None, ""]}}},
            {"$group": {"_id": "$fields.product_code", "count": {"$sum": 1}}}, {"$match": {"count": {"$gt": 1}}}]).to_list(None)
        for d in duplicates:
            await c.db.import_rows.update_many({"job_id": jid, "fields.product_code": d["_id"]},
                {"$addToSet": {"errors": "Duplicate product code within source PDF; correct code or exclude row"}})
        await c.db.import_jobs.update_one({"id": jid, "lease": lease, "phase": "analyzing"},
            {"$set": {"phase": "review", "updated_at": c.stamp()}, "$unset": {"lease": "", "lease_until": ""}})
    except Exception as exc:
        message = str(exc)
        safe = message if re_safe_error(message) else "IMPORT_PROCESSING_FAILED: retry after correcting the source or storage configuration"
        await c.db.import_jobs.update_one({"id": jid, "lease": lease, "phase": "analyzing"},
            {"$set": {"phase": "error", "error": safe, "updated_at": c.stamp()}})
    finally:
        beat.cancel()
        try:
            await beat
        except asyncio.CancelledError:
            pass


def re_safe_error(message):
    return any(message.startswith(s) for s in ["INVALID_PDF:", "PAGE_LIMIT:", "ENCRYPTED_OR_INVALID:", "CROPBOX_UNSUPPORTED:",
        "UNSUPPORTED_LAYOUT:", "BOUNDARY_ERROR:", "BOUNDARY_GEOMETRY:", "PAGE_ROLE_REQUIRED:", "RENDER_TIMEOUT:",
        "RENDER_RESOURCE_LIMIT:", "FILE_IDENTITY_MISMATCH:", "CHUNK_CORRUPT:", "UPLOAD_INCOMPLETE:", "BAD_PHOTO_REGION:"])


async def worker_loop():
    last_cleanup = 0
    while True:
        try:
            worked = False
            for data_scope in c.scopes():
                with c.scoped(data_scope):
                    if c.now().timestamp() - last_cleanup > 3600 and data_scope is None:
                        await cleanup_temporary()
                        last_cleanup = c.now().timestamp()
                    lease = secrets.token_hex(16)
                    job = await c.db.import_jobs.find_one_and_update({"$or": [{"phase": "queued"},
                        {"phase": "analyzing", "lease_until": {"$lt": c.stamp()}}]},
                        {"$set": {"phase": "analyzing", "lease": lease, "lease_until": (c.now()+timedelta(seconds=90)).isoformat()}},
                        projection={"_id": 0}, return_document=ReturnDocument.AFTER)
                    if job:
                        worked = True
                        await process_job(job)
            if not worked:
                await asyncio.sleep(2)
        except asyncio.CancelledError:
            raise
        except Exception:
            await asyncio.sleep(5)


async def cleanup_temporary():
    cutoff = (c.now()-timedelta(days=limits()["temporary_retention_days"])).isoformat()
    await c.db.import_jobs.update_many({"phase": {"$in": ["uploading", "paused", "error"]}, "updated_at": {"$lt": cutoff}},
        {"$set": {"phase": "expired", "updated_at": c.stamp()}})
    await audit_candidates()
    for directory in TEMP.iterdir():
        if not directory.is_dir() or directory.is_symlink():
            continue
        if directory.stat().st_mtime < c.now().timestamp() - 7*86400:
            job = await c.db.import_jobs.find_one({"id": directory.name}, {"_id": 0, "phase": 1})
            if not job or job["phase"] in {"expired", "cancelled", "committed"}:
                shutil.rmtree(directory)