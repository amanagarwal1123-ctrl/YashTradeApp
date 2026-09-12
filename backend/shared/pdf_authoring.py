"""Owner-only source page preview and bounded form export using the v1 generator."""
import asyncio
import json
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from pydantic import BaseModel, Field

from . import core as c
from .commerce import PRODUCT_FIELDS, validate_product
from .pdf_jobs import assemble, job_for, limits, run_parser

router = APIRouter(prefix="/api", tags=["PDF visual authoring"])


@router.get("/pdf-upload/{jid}/pages/{page}/image")
async def source_page(jid: str, page: int, metadata: bool = False, user=Depends(c.admin)):
    async with c.lock("import-preview:" + jid + ":" + str(page), seconds=60, wait_seconds=10):
        job = await job_for(jid, user)
        if job["phase"] not in {"review", "committed"}:
            c.fail(409, "SOURCE_NOT_REVIEWABLE", "Source pages are available after analysis")
        if not 1 <= page <= job.get("total_pages", 0):
            c.fail(422, "INVALID_PAGE", "Page is outside this document")
        source = await assemble(job)
        result = await run_parser(source, page-1, "source_preview")
        if metadata:
            return {"width_points": result["width_points"], "height_points": result["height_points"], "rotation": 0, "coordinate_space": "unrotated_pdf_points"}
        return Response(Path(result["page_image"]).read_bytes(), media_type="image/png", headers={
            "Cache-Control": "private, no-store", "X-Page-Width-Points": str(result["width_points"]),
            "X-Page-Height-Points": str(result["height_points"]), "X-Page-Rotation": "0", "X-Content-Type-Options": "nosniff"})


class Export(BaseModel):
    products: list[dict] = Field(min_length=1, max_length=20)


@router.post("/pdf-template/export")
async def export(req: Export, user=Depends(c.admin)):
    # Shared lock bounds concurrent memory-heavy form exports across backend processes.
    async with c.lock("pdf-authoring", seconds=180):
        with tempfile.TemporaryDirectory(prefix="yash-author-") as directory:
            root = Path(directory)
            entries, codes, total_bytes = [], set(), 0
            for i, item in enumerate(req.products):
                path = item.get("photo_path")
                values = {k: v for k, v in item.items() if k != "photo_path"}
                if set(values) - (PRODUCT_FIELDS - {"images"}):
                    c.fail(422, "INVALID_FIELD", "Unknown authoring field")
                values, errors = validate_product(values)
                if errors:
                    c.fail(422, "PRODUCT_VALIDATION", "; ".join(errors))
                if values["product_code"] in codes:
                    c.fail(422, "DUPLICATE_CODE", "Each authored product needs a unique code")
                codes.add(values["product_code"])
                asset = await c.db.media_assets.find_one({"path": path, "owner_id": user["id"], "write_state": "stored"}, {"_id": 0}) if isinstance(path, str) else None
                if not asset or not path.startswith("yash-trade/products/manual/"):
                    c.fail(422, "OWNED_PHOTO_REQUIRED", "Select a photograph uploaded by you")
                data, _ = await asyncio.to_thread(c.fetch_object, path)
                total_bytes += len(data)
                if total_bytes > 32 * 1024 * 1024:
                    c.fail(413, "AUTHORING_SIZE_LIMIT", "Export smaller groups (maximum 32 MiB input photos)")
                photo = f"photo-{i}.jpg"
                (root / photo).write_bytes(data)
                entries.append({**values, "photo": photo})
            source, target = root / "authoring.json", root / "catalog.pdf"
            source.write_text(json.dumps({"products": entries}))
            from tools.generate_catalog import generate
            try:
                await asyncio.to_thread(generate, source, target)
            except ValueError:
                c.fail(422, "AUTHORING_TEXT_OVERFLOW", "Text does not fit v1 layout; shorten long fields")
            data = target.read_bytes()
            if len(data) > limits()["max_bytes"]:
                c.fail(413, "AUTHORING_SIZE_LIMIT", "Export fewer products to fit the importer limit")
            return Response(data, media_type="application/pdf", headers={"Content-Disposition": 'attachment; filename="Yash-Catalog-v1.pdf"', "Cache-Control": "private, no-store"})