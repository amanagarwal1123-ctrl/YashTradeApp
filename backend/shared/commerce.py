import asyncio
import io
import math
import re
import secrets
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, File, Header, UploadFile
from fastapi.responses import Response
from PIL import Image, UnidentifiedImageError
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from . import core as c
from .units import weight_text, labour_value, slab_view

router = APIRouter(prefix="/api", tags=["Rates and permanent media"])
PRODUCT_FIELDS = set("product_code title description metal_type category subcategory approx_weight purity selling_touch "
    "selling_label stock_status tags video_url visibility is_new_arrival is_trending is_pinned images base_metal stone_weight_ct".split())


def validate_product(fields, required=True):
    data, errors = dict(fields), []
    if required:
        for key in ("product_code", "title", "metal_type", "category"):
            if not str(data.get(key) or "").strip():
                errors.append(f"{key}: required")
    if data.get("product_code") and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", data["product_code"]):
        errors.append("product_code: use 1–64 letters, digits, dot, underscore or hyphen")
    metal = data.get("metal_type")
    if metal and metal not in {"silver", "gold", "diamond"}:
        errors.append("metal_type: gold, silver or diamond required")
    if "approx_weight" in data:
        try:
            data["approx_weight"] = weight_text(data["approx_weight"])
        except ValueError as exc:
            errors.append(str(exc))
    purity = str(data.get("purity", "")).strip()
    if purity:
        base = data.get("base_metal") if metal == "diamond" else metal
        if base == "silver":
            if re.fullmatch(r"[0-9]{2}(?:\.[0-9]+)?%?", purity):
                purity = str(round(float(purity.rstrip("%")) * 10))
            if not re.fullmatch(r"[0-9]{3}", purity) or not 100 <= int(purity) <= 999:
                errors.append("purity: silver uses fineness, e.g. 925 or 92.5%")
        elif base == "gold":
            purity = purity.upper()
            if not re.fullmatch(r"(?:9|10|14|18|20|21|22|23|24)K", purity):
                errors.append("purity: gold uses karats, e.g. 22K")
        else:
            errors.append("purity: diamond jewellery needs a separate base_metal (gold/silver)")
        data["purity"] = purity
    if data.get("base_metal") and data["base_metal"] not in {"gold", "silver", "platinum"}:
        errors.append("base_metal: use gold, silver or platinum")
    if data.get("stone_weight_ct") not in (None, ""):
        try:
            value = float(data["stone_weight_ct"])
            if value <= 0 or not math.isfinite(value):
                raise ValueError()
            data["stone_weight_ct"] = value
        except (TypeError, ValueError):
            errors.append("stone_weight_ct: positive carat number required")
    if data.get("selling_touch") and not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?%?", str(data["selling_touch"])):
        errors.append("selling_touch: numeric percentage or number required")
    for k, values in {"stock_status": {"in_stock", "limited", "out_of_stock"}, "visibility": {"all", "hidden"}}.items():
        if data.get(k) and data[k] not in values:
            errors.append(f"{k}: use {', '.join(sorted(values))}")
    if data.get("video_url"):
        u = urlparse(data["video_url"])
        if u.scheme != "https" or u.hostname not in {"www.youtube.com", "youtube.com", "youtu.be", "vimeo.com", "www.vimeo.com"}:
            errors.append("video_url: use an HTTPS YouTube/Vimeo link; no automatic fetching")
    for k in ("is_new_arrival", "is_trending", "is_pinned"):
        if k in data and not isinstance(data[k], bool):
            errors.append(f"{k}: true or false required")
    if "tags" in data and (not isinstance(data["tags"], list) or any(not isinstance(t, str) for t in data["tags"])):
        errors.append("tags: array of strings required")
    if "images" in data and (not isinstance(data["images"], list) or len(data["images"]) > 20 or any(not isinstance(v, str) for v in data["images"])):
        errors.append("images: at most 20 uploaded image URLs required")
    return data, errors


def image_bytes(data):
    if len(data) > 8 * 1024 * 1024:
        c.fail(413, "IMAGE_TOO_LARGE", "Image limit is 8 MB")
    try:
        with Image.open(io.BytesIO(data)) as im:
            if im.format not in {"JPEG", "PNG", "WEBP", "GIF"} or im.width * im.height > 40_000_000:
                c.fail(422, "INVALID_IMAGE", "Use JPG/PNG/WEBP/GIF below 40 megapixels")
            im.verify()
        with Image.open(io.BytesIO(data)) as im:
            im.seek(0)
            im = im.convert("RGB")
            im.thumbnail((3000, 3000))
            out = io.BytesIO()
            im.save(out, "JPEG", quality=92)
            return out.getvalue()
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError, Image.DecompressionBombError):
        c.fail(422, "INVALID_IMAGE", "The file is not a valid supported image")


@router.post("/products/upload-image")
async def upload_image(file: UploadFile = File(...), user=Depends(c.admin)):
    from .media_lifecycle import tracked_put
    data = image_bytes(await file.read(8 * 1024 * 1024 + 1))
    path = f"yash-trade/products/manual/{secrets.token_hex(16)}.jpg"
    await tracked_put(path, data, "image/jpeg", "manual_master", user["id"])
    with Image.open(io.BytesIO(data)) as image:
        image.thumbnail((320, 320))
        output = io.BytesIO(); image.save(output, "JPEG", quality=90)
    thumb = path.removesuffix(".jpg") + "-thumb.jpg"
    await tracked_put(thumb, output.getvalue(), "image/jpeg", "thumbnail", user["id"])
    await c.db.media_assets.update_one({"path": path}, {"$set": {"thumbnail_path": thumb}})
    return {"url": f"/api/files/{path}", "storage_path": path, "thumbnail_path": thumb, "content_type": "image/jpeg", "permanent": True}


@router.put("/products/{pid}")
async def update_product(pid: str, updates: dict, user=Depends(c.admin)):
    old = await c.db.products.find_one({"id": pid}, {"_id": 0})
    if not old:
        c.fail(404, "PRODUCT_NOT_FOUND", "Product not found")
    expected = updates.pop("version", None)
    if expected is None:
        c.fail(428, "VERSION_REQUIRED", "Send the product version to prevent lost changes")
    if expected != old.get("version", 0):
        c.fail(409, "VERSION_CONFLICT", "Product changed; reload before editing")
    if set(updates) - PRODUCT_FIELDS:
        c.fail(422, "READ_ONLY_FIELD", "Unsupported product field; original scan cannot be replaced here")
    validated, errors = validate_product({**old, **updates}, required=False)
    changed = {k for k, v in updates.items() if v != old.get(k)}
    if changed & {"metal_type", "base_metal"}:
        changed.add("purity")
    errors = [e for e in errors if e.split(":", 1)[0] in changed]
    data = {key: validated[key] for key in updates}
    if errors:
        c.fail(422, "PRODUCT_VALIDATION", "; ".join(errors))
    for url in data.get("images", []):
        if url in old.get("images", []):
            continue
        if not isinstance(url, str) or not url.startswith("/api/files/yash-trade/products/"):
            c.fail(422, "MEDIA_UPLOAD_REQUIRED", "Upload each new image through the permanent product media endpoint")
        asset = await c.db.media_assets.find_one({"path": url.removeprefix("/api/files/")})
        if not asset:
            c.fail(422, "INVALID_MEDIA", "Unknown product image")
    if "images" in data and not old.get("storage_path"):
        first = data["images"][0].removeprefix("/api/files/") if data["images"] else ""
        asset = await c.db.media_assets.find_one({"path": first}, {"_id": 0}) or {}
        data["thumbnail_path"] = asset.get("thumbnail_path", "")
    try:
        doc = await c.db.products.find_one_and_update({"id": pid, "version": expected if "version" in old else {"$exists": False}},
            {"$set": {**data, "updated_at": c.stamp()}, "$inc": {"version": 1}},
            projection={"_id": 0}, return_document=ReturnDocument.AFTER)
    except DuplicateKeyError:
        c.fail(409, "PRODUCT_CODE_CONFLICT", "Product code already exists")
    if not doc:
        c.fail(409, "VERSION_CONFLICT", "Product changed concurrently")
    return doc


# Cache policy. Stored objects are write-once: every upload, import row and thumbnail gets a fresh unique path and a
# replaced photo is a NEW path (identical rewrites are reused, never changed), so a public URL always names the same
# bytes and may be cached by the signed-in device for a day. Anything that is not public catalogue/banner media
# (hidden or deleted products, import previews, admin-only masters) stays `no-store` and is re-authorised every time.
PUBLIC_CACHE = "private, max-age=86400"
PRIVATE_CACHE = "private, no-store"


@router.get("/files/{path:path}")
async def media(path: str, authorization: str | None = Header(None), w: int | None = None, if_none_match: str | None = Header(None)):
    from .media_cache import VARIANT_WIDTHS, cached_get, etag_of
    if ".." in path or not re.fullmatch(r"[A-Za-z0-9_./-]+", path):
        c.fail(404, "MEDIA_NOT_FOUND", "Image not found")
    if w is not None and w not in VARIANT_WIDTHS:
        c.fail(422, "INVALID_VARIANT", f"Supported display widths: {', '.join(map(str, VARIANT_WIDTHS))}")
    # Private uploads and previews never inherit public catalog access.
    product = await c.db.products.find_one({"is_deleted": {"$ne": True}, "$or": [{"storage_path": path}, {"thumbnail_path": path},
        {"original_source_storage_path": path}, {"images": f"/api/files/{path}"}]}, {"_id": 0, "id": 1, "visibility": 1})
    # Source chunks and import previews stay behind the owner-bound job routes until a committed product adopts one as
    # its permanent photo; from then on the ordinary product visibility rules apply.
    if not product and path.startswith("yash-trade/imports/"):
        c.fail(404, "MEDIA_NOT_FOUND", "Use the private owner-authorized import endpoint")
    public = bool(product) and product.get("visibility") != "hidden"
    banner = None if public else await c.db.banners.find_one({"image_url": f"/api/files/{path}", "is_active": True}, {"_id": 0, "id": 1})
    public = public or bool(banner)
    if not public:
        user = await c.current_user(authorization)
        if user["role"] != "admin":
            c.fail(403, "MEDIA_PRIVATE", "This media is private")
    try:
        data, content_type = await cached_get(path, bool(public), w)
    except Exception:
        c.fail(404, "MEDIA_NOT_FOUND", "Image could not be loaded")
    etag = etag_of(data)
    headers = {"Cache-Control": PUBLIC_CACHE if public else PRIVATE_CACHE, "ETag": etag, "X-Content-Type-Options": "nosniff", "Vary": "Authorization"}
    if if_none_match and etag in [tag.strip() for tag in if_none_match.split(",")]:
        return Response(status_code=304, headers=headers)
    return Response(data, media_type=content_type, headers=headers)


async def latest():
    rate = await c.db.rates_current.find_one({"_id": "canonical"}, {"_id": 0, "events": 0})
    if rate is None:
        rate = await c.db.rates.find_one({}, {"_id": 0}, sort=[("created_at", -1)]) or {}
    rate.setdefault("version", 0)
    rate["units"] = {"physical": "INR/g", "mcx": "INR/g", "dollar": "USD/troy_oz"}
    for metal in ["silver", "gold"]:
        for kind in ["dollar", "mcx", "physical"]:
            rate.setdefault(f"{metal}_{kind}_rate", 0)
        rate[f"{metal}_rate"] = rate[f"{metal}_physical_rate"]
    return rate


@router.get("/rates/latest")
async def rates_latest():
    return await latest()


@router.get("/rates/audit")
async def rate_audit(page: int = 1, limit: int = 30, user=Depends(c.billing)):
    if page < 1 or not 1 <= limit <= 100:
        c.fail(422, "INVALID_PAGINATION", "Use page>=1 and limit 1-100")
    doc = await c.db.rates_current.find_one({"_id": "canonical"}, {"_id": 0, "events": 1}) or {}
    events = list(reversed(doc.get("events", [])))
    return {"events": events[(page-1)*limit:page*limit], "page": page, "limit": limit, "total": len(events)}


@router.post("/rates")
async def rates_write(updates: dict, user=Depends(c.billing)):
    expected = updates.pop("version", None)
    if expected is None:
        c.fail(428, "VERSION_REQUIRED", "Send the rates version from the latest read")
    numeric = {f"{m}_{k}" for m in ("gold", "silver") for k in ("dollar_rate", "mcx_rate", "physical_rate", "physical_premium")}
    choices = {f"{m}_{k}" for m in ("gold", "silver") for k in ("physical_mode", "physical_base", "movement", "purity")}
    if set(updates) - (numeric | choices | {"market_summary"}):
        c.fail(422, "INVALID_RATE_FIELD", "Unknown rate field")
    for k in numeric & set(updates):
        if not isinstance(updates[k], (int, float)) or isinstance(updates[k], bool) or not math.isfinite(updates[k]) or updates[k] < 0:
            c.fail(422, "INVALID_RATE", "Rates must be finite non-negative numbers in the documented units")
    for metal in ("silver", "gold"):
        key = f"{metal}_purity"
        if key in updates:
            normalized, errors = validate_product({"metal_type": metal, "purity": updates[key]}, required=False)
            if errors or not str(updates[key]).strip():
                c.fail(422, "INVALID_PURITY", "; ".join(errors) or "Purity cannot be blank")
            updates[key] = normalized["purity"]
    for k in choices & set(updates):
        allowed = {"physical_mode": {"manual", "calculated"}, "physical_base": {"mcx"}, "movement": {"up", "down", "stable"}}
        suffix = k.split("_", 1)[1]
        if suffix in allowed and updates[k] not in allowed[suffix]:
            c.fail(422, "INVALID_RATE_MODE", "Calculated rates must use the INR/g MCX base, not USD")
    old = await latest()
    if old["version"] != expected:
        c.fail(409, "VERSION_CONFLICT", "Rates changed; refresh before saving")
    merged = {**old, **updates}
    for metal in ("silver", "gold"):
        if merged.get(f"{metal}_physical_mode") == "calculated":
            merged[f"{metal}_physical_rate"] = merged[f"{metal}_mcx_rate"] + merged.get(f"{metal}_physical_premium", 0)
    merged.pop("version", None)
    merged.update(updated_by=user["id"], updated_at=c.stamp(), effective_at=c.stamp())
    event = {"id": secrets.token_hex(16), "actor_id": user["id"], "actor_role": user["role"], "at": c.stamp(), "changes": updates}
    try:
        result = await c.db.rates_current.update_one({"_id": "canonical", "version": expected if expected else {"$in": [0, None]}},
            {"$set": merged, "$inc": {"version": 1}, "$push": {"events": event}}, upsert=expected == 0)
    except DuplicateKeyError:
        c.fail(409, "VERSION_CONFLICT", "Rates changed concurrently")
    if not result.modified_count and not result.upserted_id:
        c.fail(409, "VERSION_CONFLICT", "Rates changed concurrently")
    return await latest()


@router.post("/rate-list")
async def slab_create(fields: dict, user=Depends(c.billing)):
    allowed = {"metal_type", "item_name", "category", "subcategory", "purity", "wastage", "labour_kg", "labour", "order"}
    if set(fields) - allowed or not str(fields.get("item_name", "")).strip() or fields.get("metal_type") not in {"silver", "gold", "diamond"}:
        c.fail(422, "INVALID_SLAB", "Supply valid rate-list fields and product type")
    validate_slab(fields)
    normalize_slab_write(fields)
    doc = {"id": secrets.token_hex(16), **fields, "version": 0, "created_at": c.stamp(),
           "events": [{"actor_id": user["id"], "at": c.stamp(), "type": "created"}]}
    await c.db.rate_slabs.insert_one(dict(doc))
    return slab_view(doc)


@router.put("/rate-list/{sid}")
async def slab_update(sid: str, fields: dict, user=Depends(c.billing)):
    expected = fields.pop("version", None)
    if expected is None:
        c.fail(428, "VERSION_REQUIRED", "Send the rate-list item version")
    allowed = {"metal_type", "item_name", "category", "subcategory", "purity", "wastage", "labour_kg", "labour", "order", "is_deleted"}
    if set(fields) - allowed:
        c.fail(422, "INVALID_SLAB", "Unknown rate-list field")
    old = await c.db.rate_slabs.find_one({"id": sid}, {"_id": 0})
    if not old:
        c.fail(404, "SLAB_NOT_FOUND", "Rate-list item not found")
    changed = {k for k, v in fields.items() if v != old.get(k)}
    validate_slab({**old, **fields}, changed)
    if changed & {"labour", "labour_kg"}:
        normalize_slab_write(fields)
    doc = await c.db.rate_slabs.find_one_and_update({"id": sid, "version": expected if "version" in old else {"$exists": False}},
        {"$set": {**fields, "updated_at": c.stamp()}, "$inc": {"version": 1}, "$push": {"events": {
            "actor_id": user["id"], "at": c.stamp(), "changes": fields}}}, projection={"_id": 0}, return_document=ReturnDocument.AFTER)
    if not doc:
        c.fail(409, "VERSION_CONFLICT", "Rate-list item changed; refresh")
    return slab_view(doc)


@router.delete("/rate-list/{sid}")
async def slab_delete(sid: str, version: int, user=Depends(c.billing)):
    return await slab_update(sid, {"version": version, "is_deleted": True}, user)


def validate_slab(fields, changed=None):
    keys = set(fields) if changed is None else changed
    if "item_name" in keys and not str(fields.get("item_name", "")).strip():
        c.fail(422, "INVALID_SLAB", "Rate-list item name is required")
    if "metal_type" in keys and fields.get("metal_type") not in {"silver", "gold", "diamond"}:
        c.fail(422, "INVALID_SLAB", "Invalid product type")
    value = fields.get("wastage")
    if "wastage" in keys and value not in (None, "") and not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?%?", str(value)):
        c.fail(422, "INVALID_SLAB", "wastage must be non-negative numeric text")
    for key in keys & {"labour", "labour_kg"}:
        try:
            labour_value(fields.get(key))
        except ValueError as exc:
            c.fail(422, "AMBIGUOUS_LABOUR_UNIT", str(exc))


def normalize_slab_write(fields):
    if "labour" in fields or "labour_kg" in fields:
        try:
            value = labour_value(fields.get("labour", fields.get("labour_kg")))
            if "labour" in fields and "labour_kg" in fields and labour_value(fields["labour_kg"]) != value:
                c.fail(422, "LABOUR_UNIT_CONFLICT", "Send one consistent labour amount/basis")
        except ValueError as exc:
            c.fail(422, "AMBIGUOUS_LABOUR_UNIT", str(exc))
        fields["labour"] = value
        fields["labour_kg"] = f"INR {value['amount']}/{value['basis']}" if value else ""


@router.get("/rate-list")
async def slabs(metal_type: str = ""):
    query = {"is_deleted": {"$ne": True}}
    if metal_type:
        query["metal_type"] = metal_type
    docs = await c.db.rate_slabs.find(query, {"_id": 0, "events": 0}).sort([("order", 1), ("id", 1)]).limit(1000).to_list(1000)
    return {"slabs": [slab_view(doc) for doc in docs]}