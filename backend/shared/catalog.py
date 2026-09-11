"""Bounded canonical catalog. Discovery is deliberately not a paginated catalog."""
import math
import secrets
from typing import Literal

from fastapi import APIRouter, Depends, Header, Query
from pymongo.errors import DuplicateKeyError

from . import core as c
from .commerce import PRODUCT_FIELDS, validate_product

router = APIRouter(prefix="/api", tags=["Canonical catalog"])


@router.get("/products")
async def products(page: int = Query(1, ge=1), limit: int = Query(50, ge=1, le=100),
                   category: str = "", metal_type: str = "", search: str = Query("", max_length=120),
                   post_type: str = "", include_hidden: bool = False, ids: str = "", batch_id: str = "", product_code: str = Query("", max_length=80),
                   mode: Literal["catalog", "discovery"] = "catalog", authorization: str | None = Header(None)):
    query = {"is_deleted": {"$ne": True}}
    if include_hidden:
        user = await c.current_user(authorization)
        if user["role"] != "admin":
            c.fail(403, "PERMISSION_DENIED", "Admin access required for hidden products")
    else:
        query["visibility"] = {"$ne": "hidden"}
    for key, value in {"category": category, "metal_type": metal_type, "post_type": post_type, "batch_id": batch_id, "product_code": product_code}.items():
        if value:
            query[key] = value
    if search.strip():
        query["$text"] = {"$search": search.strip()}
    id_list = list(dict.fromkeys(i.strip() for i in ids.split(",") if i.strip()))
    if len(id_list) > 100:
        c.fail(422, "IDS_LIMIT", "At most 100 product IDs per request")
    if id_list:
        query["id"] = {"$in": id_list}
        limit = len(id_list)
    total = await c.db.products.count_documents(query)
    if mode == "discovery":
        if page != 1 or id_list:
            c.fail(422, "DISCOVERY_NOT_PAGINATED", "Discovery is a separate single random sample")
        docs = await c.db.products.aggregate([{"$match": query}, {"$sample": {"size": limit}}, {"$project": {"_id": 0}}]).to_list(limit)
    else:
        docs = await c.db.products.find(query, {"_id": 0}).sort([("created_at", -1), ("id", 1)]).skip((page-1)*limit).limit(limit).to_list(limit)
    if id_list:
        mapped = {p["id"]: p for p in docs}
        docs = [mapped[i] for i in id_list if i in mapped]
    for doc in docs:
        doc.setdefault("version", 0)
    return {"products": docs, "total": total, "page": page, "limit": limit,
            "pages": 1 if mode == "discovery" else math.ceil(total/limit), "mode": mode,
            "sort": "created_at:desc,id:asc" if mode == "catalog" else "random_sample"}


@router.post("/products")
async def create(fields: dict, user=Depends(c.admin)):
    if set(fields) - PRODUCT_FIELDS:
        c.fail(422, "READ_ONLY_FIELD", "Unsupported product field")
    values, errors = validate_product(fields)
    if errors:
        c.fail(422, "PRODUCT_VALIDATION", "; ".join(errors))
    thumb = ""
    for url in values.get("images", []):
        if not isinstance(url, str) or not url.startswith("/api/files/yash-trade/products/"):
            c.fail(422, "MEDIA_UPLOAD_REQUIRED", "Upload product photographs first")
        asset = await c.db.media_assets.find_one({"path": url.removeprefix("/api/files/"), "owner_id": user["id"]}, {"_id": 0})
        if not asset:
            c.fail(422, "INVALID_MEDIA", "Photo is not an owned upload")
        if not thumb:
            thumb = asset.get("thumbnail_path", "")
    doc = {"id": secrets.token_hex(16), "visibility": "hidden", "stock_status": "in_stock", "images": [],
           **values, "thumbnail_path": thumb, "version": 0, "views": 0, "is_deleted": False, "created_at": c.stamp(), "updated_at": c.stamp()}
    try:
        await c.db.products.insert_one(dict(doc))
    except DuplicateKeyError:
        c.fail(409, "PRODUCT_CODE_CONFLICT", "Product code already exists")
    return doc