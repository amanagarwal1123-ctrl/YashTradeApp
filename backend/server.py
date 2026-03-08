from fastapi import FastAPI, APIRouter, Depends, HTTPException, Query, Header, File, UploadFile
from fastapi.responses import Response
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import io
import logging
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import uuid
from datetime import datetime, timezone
import jwt
import asyncio
import requests as http_requests
from PIL import Image as PILImage

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ.get('DB_NAME', 'jewellers_app')]

app = FastAPI()
api_router = APIRouter(prefix="/api")

JWT_SECRET = os.environ.get('JWT_SECRET', 'aman-jewellers-secret-key-2024-prod-v1')
JWT_ALGORITHM = 'HS256'
EMERGENT_KEY = os.environ.get('EMERGENT_LLM_KEY', '')

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ===================== OBJECT STORAGE =====================

STORAGE_URL = "https://integrations.emergentagent.com/objstore/api/v1/storage"
APP_NAME = "yash-trade"
storage_key = None

def init_storage():
    global storage_key
    if storage_key:
        return storage_key
    resp = http_requests.post(f"{STORAGE_URL}/init", json={"emergent_key": EMERGENT_KEY}, timeout=30)
    resp.raise_for_status()
    storage_key = resp.json()["storage_key"]
    logger.info("Object storage initialized successfully")
    return storage_key

def put_object(path: str, data: bytes, content_type: str) -> dict:
    key = init_storage()
    resp = http_requests.put(
        f"{STORAGE_URL}/objects/{path}",
        headers={"X-Storage-Key": key, "Content-Type": content_type},
        data=data, timeout=120
    )
    resp.raise_for_status()
    return resp.json()

def get_object(path: str):
    key = init_storage()
    resp = http_requests.get(
        f"{STORAGE_URL}/objects/{path}",
        headers={"X-Storage-Key": key}, timeout=60
    )
    resp.raise_for_status()
    return resp.content, resp.headers.get("Content-Type", "application/octet-stream")

def process_image(data: bytes, max_size: int = 1600, quality: int = 85) -> bytes:
    img = PILImage.open(io.BytesIO(data))
    if img.mode in ('RGBA', 'P', 'LA'):
        img = img.convert('RGB')
    if max(img.size) > max_size:
        img.thumbnail((max_size, max_size), PILImage.Resampling.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format='JPEG', quality=quality, optimize=True)
    return buf.getvalue()

def create_thumbnail(data: bytes, size: int = 800, quality: int = 80) -> bytes:
    img = PILImage.open(io.BytesIO(data))
    if img.mode in ('RGBA', 'P', 'LA'):
        img = img.convert('RGB')
    img.thumbnail((size, size), PILImage.Resampling.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format='JPEG', quality=quality, optimize=True)
    return buf.getvalue()

# ===================== MODELS =====================

class SendOTPRequest(BaseModel):
    phone: str

class VerifyOTPRequest(BaseModel):
    phone: str
    otp: str

class ProductCreate(BaseModel):
    title: str
    description: str = ""
    metal_type: str = "silver"
    category: str = ""
    subcategory: str = ""
    images: List[str] = []
    video_url: str = ""
    approx_weight: str = ""
    purity: str = ""
    selling_touch: str = ""
    selling_label: str = ""
    stock_status: str = "in_stock"
    tags: List[str] = []
    is_pinned: bool = False
    is_new_arrival: bool = True
    is_trending: bool = False
    visibility: str = "all"
    post_type: str = "product"

class RateUpdate(BaseModel):
    silver_dollar_rate: float = 0
    silver_mcx_rate: float = 0
    silver_physical_rate: float = 0
    silver_physical_mode: str = "manual"
    silver_physical_premium: float = 0
    silver_physical_base: str = "mcx"
    silver_movement: str = "stable"
    gold_dollar_rate: float = 0
    gold_mcx_rate: float = 0
    gold_physical_rate: float = 0
    gold_physical_mode: str = "manual"
    gold_physical_premium: float = 0
    gold_physical_base: str = "mcx"
    gold_movement: str = "stable"
    market_summary: str = ""

class BulkUploadRequest(BaseModel):
    image_urls: List[str]
    metal_type: str = "silver"
    category: str = ""
    batch_name: str = ""
    visibility: str = "all"

class RequestCreate(BaseModel):
    request_type: str
    category: str = ""
    preferred_time: str = ""
    notes: str = ""
    product_id: str = ""
    product_ids: List[str] = []

class RewardConfigUpdate(BaseModel):
    points_per_1000: int = 10
    welcome_bonus: int = 100
    first_purchase_bonus: int = 50
    first_video_bonus: int = 25
    eligible_types: List[str] = ["retailer", "mixed"]

class RewardCreditRequest(BaseModel):
    user_id: str
    points: int
    reason: str = ""

class RedeemRequest(BaseModel):
    points: int = Field(gt=0, description="Must be a positive integer")
    reward_name: str = ""

class AIChatRequest(BaseModel):
    message: str
    session_id: str = ""
    language: str = "en"

class KnowledgeCreate(BaseModel):
    title: str
    content: str
    category: str = "silver_care"
    card_type: str = "article"
    image_url: str = ""
    tags: List[str] = []

class StoryCreate(BaseModel):
    title: str
    image_url: str
    link_type: str = ""
    link_id: str = ""
    category: str = ""

class CustomerUpdate(BaseModel):
    customer_type: str = ""
    city: str = ""
    category_interests: List[str] = []
    is_eligible_rewards: bool = True
    assigned_salesperson: str = ""
    status: str = "active"

class RequestStatusUpdate(BaseModel):
    status: str
    assigned_to: str = ""
    notes: str = ""

class BatchCreate(BaseModel):
    name: str
    metal_type: str = "silver"
    category: str = ""

class BatchUpdate(BaseModel):
    name: str = ""
    metal_type: str = ""
    category: str = ""
    status: str = ""

class BatchImageDelete(BaseModel):
    image_ids: List[str]

class CartAddRequest(BaseModel):
    product_id: str
    quantity: int = 1
    notes: str = ""

class CartSubmitRequest(BaseModel):
    notes: str = ""

# ===================== AUTH HELPERS =====================

def create_token(user_id: str, role: str = "customer"):
    return jwt.encode({"user_id": user_id, "role": role, "exp": datetime.now(timezone.utc).timestamp() + 86400 * 30}, JWT_SECRET, algorithm=JWT_ALGORITHM)

async def get_current_user(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(authorization.split(" ")[1], JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user = await db.users.find_one({"id": payload["user_id"]}, {"_id": 0})
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")

async def get_admin_user(user=Depends(get_current_user)):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user

async def get_executive_or_admin(user=Depends(get_current_user)):
    if user.get("role") not in ("admin", "executive"):
        raise HTTPException(status_code=403, detail="Executive or admin access required")
    return user

async def get_billing_or_admin(user=Depends(get_current_user)):
    if user.get("role") not in ("admin", "billing_executive"):
        raise HTTPException(status_code=403, detail="Billing or admin access required")
    return user

# ===================== AUTH ENDPOINTS =====================

@api_router.post("/auth/send-otp")
async def send_otp(req: SendOTPRequest):
    phone = req.phone.strip()
    if len(phone) < 10:
        raise HTTPException(status_code=400, detail="Invalid phone number")
    existing = await db.users.find_one({"phone": phone}, {"_id": 0})
    if not existing:
        user_data = {
            "id": str(uuid.uuid4()),
            "phone": phone,
            "name": "",
            "city": "",
            "customer_code": f"AA{phone[-4:]}",
            "customer_type": "retailer",
            "role": "customer",
            "category_interests": [],
            "is_eligible_rewards": True,
            "assigned_salesperson": "",
            "status": "active",
            "reward_points": 0,
            "is_new": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "last_login": datetime.now(timezone.utc).isoformat()
        }
        await db.users.insert_one(user_data)
    return {"message": "OTP sent successfully", "otp_hint": "Use 1234 for demo"}

@api_router.post("/auth/verify-otp")
async def verify_otp(req: VerifyOTPRequest):
    if req.otp != "1234":
        raise HTTPException(status_code=400, detail="Invalid OTP")
    user = await db.users.find_one({"phone": req.phone.strip()}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    is_new = user.get("is_new", False)
    if is_new:
        welcome_config = await db.reward_config.find_one({}, {"_id": 0})
        bonus = welcome_config.get("welcome_bonus", 100) if welcome_config else 100
        await db.users.update_one({"id": user["id"]}, {"$inc": {"reward_points": bonus}, "$set": {"is_new": False}})
        await db.reward_transactions.insert_one({
            "id": str(uuid.uuid4()), "user_id": user["id"], "points": bonus,
            "type": "credit", "reason": "Welcome bonus", "created_at": datetime.now(timezone.utc).isoformat()
        })
    await db.users.update_one({"id": user["id"]}, {"$set": {"last_login": datetime.now(timezone.utc).isoformat()}})
    fresh_user = await db.users.find_one({"phone": req.phone.strip()}, {"_id": 0})
    token = create_token(fresh_user["id"], fresh_user.get("role", "customer"))
    return {"token": token, "user": {**fresh_user, "is_new": is_new}}

@api_router.get("/auth/me")
async def get_me(user=Depends(get_current_user)):
    fresh = await db.users.find_one({"id": user["id"]}, {"_id": 0})
    return fresh

@api_router.put("/auth/profile")
async def update_profile(updates: Dict[str, Any], user=Depends(get_current_user)):
    allowed = {"name", "city"}
    filtered = {k: v for k, v in updates.items() if k in allowed}
    if filtered:
        await db.users.update_one({"id": user["id"]}, {"$set": filtered})
    return await db.users.find_one({"id": user["id"]}, {"_id": 0})

# ===================== PRODUCT ENDPOINTS =====================

@api_router.get("/products")
async def list_products(
    page: int = Query(1, ge=1), limit: int = Query(20, ge=1, le=50),
    category: str = Query(""), metal_type: str = Query(""),
    search: str = Query(""), post_type: str = Query(""),
    include_hidden: bool = Query(False)
):
    query: Dict[str, Any] = {"is_deleted": {"$ne": True}}
    if not include_hidden:
        query["visibility"] = {"$ne": "hidden"}
    if category:
        query["category"] = category
    if metal_type:
        query["metal_type"] = metal_type
    if post_type:
        query["post_type"] = post_type
    if search:
        query["$or"] = [
            {"title": {"$regex": search, "$options": "i"}},
            {"tags": {"$regex": search, "$options": "i"}}
        ]
    skip = (page - 1) * limit
    total = await db.products.count_documents(query)
    products = await db.products.find(query, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    return {"products": products, "total": total, "page": page, "pages": (total + limit - 1) // limit}

@api_router.get("/products/{product_id}")
async def get_product(product_id: str):
    product = await db.products.find_one({"id": product_id}, {"_id": 0})
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    await db.products.update_one({"id": product_id}, {"$inc": {"views": 1}})
    return product

@api_router.post("/products")
async def create_product(req: ProductCreate, user=Depends(get_admin_user)):
    product = {
        "id": str(uuid.uuid4()),
        **req.dict(),
        "views": 0,
        "is_deleted": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    await db.products.insert_one(product)
    return {k: v for k, v in product.items() if k != "_id"}

@api_router.post("/products/bulk")
async def bulk_upload(req: BulkUploadRequest, user=Depends(get_admin_user)):
    if not req.image_urls:
        raise HTTPException(status_code=400, detail="No image URLs provided")
    now = datetime.now(timezone.utc).isoformat()
    batch_id = str(uuid.uuid4())
    batch_label = req.batch_name or f"Batch {batch_id[:8]}"
    # Create a batch record for URL uploads too
    batch_doc = {
        "id": batch_id,
        "name": batch_label,
        "metal_type": req.metal_type or "silver",
        "category": req.category or "",
        "status": "visible",
        "image_count": 0,
        "upload_type": "url",
        "created_by": user["id"],
        "created_at": now,
        "updated_at": now,
    }
    await db.batches.insert_one(batch_doc)
    products = []
    for i, url in enumerate(req.image_urls):
        url = url.strip()
        if not url:
            continue
        products.append({
            "id": str(uuid.uuid4()),
            "title": f"{batch_label} #{i+1}",
            "description": "",
            "metal_type": req.metal_type or "silver",
            "category": req.category or "",
            "subcategory": "",
            "images": [url],
            "video_url": "",
            "approx_weight": "",
            "stock_status": "in_stock",
            "tags": [req.metal_type or "silver", "bulk_upload", batch_id[:8]],
            "is_pinned": False,
            "is_new_arrival": True,
            "is_trending": False,
            "visibility": req.visibility or "all",
            "post_type": "product",
            "batch_id": batch_id,
            "batch_name": batch_label,
            "views": 0,
            "is_deleted": False,
            "created_at": now,
            "updated_at": now,
        })
    if products:
        await db.products.insert_many(products)
    await db.batches.update_one({"id": batch_id}, {"$set": {"image_count": len(products)}})
    return {"message": f"Uploaded {len(products)} images", "count": len(products), "batch_id": batch_id, "batch_name": batch_label}

@api_router.put("/products/{product_id}")
async def update_product(product_id: str, updates: Dict[str, Any], user=Depends(get_admin_user)):
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    updates.pop("_id", None)
    updates.pop("id", None)
    await db.products.update_one({"id": product_id}, {"$set": updates})
    return await db.products.find_one({"id": product_id}, {"_id": 0})

@api_router.delete("/products/{product_id}")
async def delete_product(product_id: str, user=Depends(get_admin_user)):
    await db.products.delete_one({"id": product_id})
    return {"message": "Deleted"}

@api_router.get("/categories")
async def get_categories():
    cats = await db.products.distinct("category")
    metals = await db.products.distinct("metal_type")
    return {"categories": [c for c in cats if c], "metal_types": [m for m in metals if m]}

# ===================== BATCH MANAGEMENT =====================

@api_router.post("/batches")
async def create_batch(req: BatchCreate, user=Depends(get_admin_user)):
    now = datetime.now(timezone.utc).isoformat()
    batch = {
        "id": str(uuid.uuid4()),
        "name": req.name,
        "metal_type": req.metal_type,
        "category": req.category,
        "status": "visible",
        "image_count": 0,
        "upload_type": "file",
        "created_by": user["id"],
        "created_at": now,
        "updated_at": now,
    }
    await db.batches.insert_one(batch)
    return {k: v for k, v in batch.items() if k != "_id"}

@api_router.get("/batches")
async def list_batches(
    status: str = Query(""),
    search: str = Query(""),
    user=Depends(get_admin_user)
):
    query: Dict[str, Any] = {"status": {"$ne": "archived"}}
    if status:
        query["status"] = status
    if search:
        query["name"] = {"$regex": search, "$options": "i"}
    batches = await db.batches.find(query, {"_id": 0}).sort("created_at", -1).to_list(200)
    return {"batches": batches}

@api_router.get("/batches/{batch_id}")
async def get_batch(batch_id: str, user=Depends(get_admin_user)):
    batch = await db.batches.find_one({"id": batch_id}, {"_id": 0})
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    return batch

@api_router.get("/batches/{batch_id}/images")
async def get_batch_images(
    batch_id: str,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    user=Depends(get_admin_user)
):
    query = {"batch_id": batch_id, "is_deleted": {"$ne": True}}
    total = await db.products.count_documents(query)
    skip = (page - 1) * limit
    products = await db.products.find(query, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    return {"images": products, "total": total, "page": page, "pages": (total + limit - 1) // limit}

@api_router.put("/batches/{batch_id}")
async def update_batch(batch_id: str, req: BatchUpdate, user=Depends(get_admin_user)):
    updates: Dict[str, Any] = {"updated_at": datetime.now(timezone.utc).isoformat()}
    if req.name:
        updates["name"] = req.name
    if req.metal_type:
        updates["metal_type"] = req.metal_type
    if req.category:
        updates["category"] = req.category
    if req.status:
        updates["status"] = req.status
        visibility = "all" if req.status == "visible" else "hidden"
        await db.products.update_many({"batch_id": batch_id, "is_deleted": {"$ne": True}}, {"$set": {"visibility": visibility}})
    await db.batches.update_one({"id": batch_id}, {"$set": updates})
    # Also update products metadata if metal/category changed
    prod_updates = {}
    if req.metal_type:
        prod_updates["metal_type"] = req.metal_type
    if req.category:
        prod_updates["category"] = req.category
    if prod_updates:
        await db.products.update_many({"batch_id": batch_id, "is_deleted": {"$ne": True}}, {"$set": prod_updates})
    return await db.batches.find_one({"id": batch_id}, {"_id": 0})

@api_router.delete("/batches/{batch_id}")
async def delete_batch(batch_id: str, user=Depends(get_admin_user)):
    await db.batches.update_one({"id": batch_id}, {"$set": {"status": "archived", "updated_at": datetime.now(timezone.utc).isoformat()}})
    await db.products.update_many({"batch_id": batch_id}, {"$set": {"visibility": "hidden", "is_deleted": True}})
    return {"message": "Batch deleted"}

@api_router.patch("/batches/{batch_id}/visibility")
async def toggle_batch_visibility(batch_id: str, user=Depends(get_admin_user)):
    batch = await db.batches.find_one({"id": batch_id}, {"_id": 0})
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    new_status = "hidden" if batch["status"] == "visible" else "visible"
    visibility = "all" if new_status == "visible" else "hidden"
    await db.batches.update_one({"id": batch_id}, {"$set": {"status": new_status, "updated_at": datetime.now(timezone.utc).isoformat()}})
    await db.products.update_many({"batch_id": batch_id, "is_deleted": {"$ne": True}}, {"$set": {"visibility": visibility}})
    return {"status": new_status}

# ===================== FILE UPLOAD =====================

@api_router.post("/batches/{batch_id}/upload")
async def upload_to_batch(
    batch_id: str,
    files: List[UploadFile] = File(...),
    user=Depends(get_admin_user)
):
    batch = await db.batches.find_one({"id": batch_id}, {"_id": 0})
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    results = []
    current_count = batch.get("image_count", 0)
    for file in files:
        try:
            data = await file.read()
            if len(data) > 20 * 1024 * 1024:
                results.append({"filename": file.filename, "status": "error", "detail": "File too large (max 20MB)"})
                continue
            if len(data) < 100:
                results.append({"filename": file.filename, "status": "error", "detail": "File too small or empty"})
                continue
            file_id = str(uuid.uuid4())
            # Process images
            original_data = process_image(data, max_size=1600, quality=85)
            thumb_data = create_thumbnail(data, size=400, quality=60)
            # Upload to storage
            original_path = f"{APP_NAME}/originals/{file_id}.jpg"
            thumb_path = f"{APP_NAME}/thumbs/{file_id}.jpg"
            put_object(original_path, original_data, "image/jpeg")
            put_object(thumb_path, thumb_data, "image/jpeg")
            # Create product record
            now = datetime.now(timezone.utc).isoformat()
            current_count += 1
            product = {
                "id": file_id,
                "title": f"{batch['name']} #{current_count}",
                "description": "",
                "metal_type": batch.get("metal_type", "silver"),
                "category": batch.get("category", ""),
                "subcategory": "",
                "images": [],
                "storage_path": original_path,
                "thumbnail_path": thumb_path,
                "original_filename": file.filename,
                "file_size": len(data),
                "video_url": "",
                "approx_weight": "",
                "stock_status": "in_stock",
                "tags": [batch.get("metal_type", "silver"), "upload", batch["id"][:8]],
                "is_pinned": False,
                "is_new_arrival": True,
                "is_trending": False,
                "visibility": "all" if batch.get("status") == "visible" else "hidden",
                "post_type": "product",
                "batch_id": batch["id"],
                "batch_name": batch["name"],
                "views": 0,
                "is_deleted": False,
                "created_at": now,
                "updated_at": now,
            }
            await db.products.insert_one(product)
            results.append({"filename": file.filename, "status": "ok", "id": file_id})
        except Exception as e:
            logger.error(f"Upload error for {file.filename}: {e}")
            results.append({"filename": file.filename, "status": "error", "detail": str(e)})
    # Update batch count
    uploaded = sum(1 for r in results if r["status"] == "ok")
    if uploaded > 0:
        await db.batches.update_one(
            {"id": batch_id},
            {"$set": {"image_count": current_count, "updated_at": datetime.now(timezone.utc).isoformat()}}
        )
    return {"results": results, "uploaded": uploaded, "failed": len(results) - uploaded, "batch_image_count": current_count}

@api_router.post("/batches/{batch_id}/images/delete")
async def delete_batch_images(batch_id: str, req: BatchImageDelete, user=Depends(get_admin_user)):
    count = 0
    for img_id in req.image_ids:
        result = await db.products.update_one(
            {"id": img_id, "batch_id": batch_id},
            {"$set": {"is_deleted": True, "visibility": "hidden"}}
        )
        if result.modified_count:
            count += 1
    if count > 0:
        await db.batches.update_one({"id": batch_id}, {"$inc": {"image_count": -count}})
    return {"deleted": count}

# ===================== FILE SERVING =====================

@api_router.get("/files/{file_path:path}")
async def serve_file(file_path: str):
    try:
        data, content_type = get_object(file_path)
        return Response(
            content=data,
            media_type=content_type,
            headers={"Cache-Control": "public, max-age=86400"}
        )
    except Exception as e:
        logger.error(f"File serve error for {file_path}: {e}")
        raise HTTPException(status_code=404, detail="File not found")

# ===================== RATE ENDPOINTS =====================

@api_router.get("/rates/latest")
async def get_latest_rates():
    rate = await db.rates.find_one({}, {"_id": 0}, sort=[("created_at", -1)])
    if not rate:
        return {"silver_dollar_rate": 0, "silver_mcx_rate": 0, "silver_physical_rate": 0,
                "gold_dollar_rate": 0, "gold_mcx_rate": 0, "gold_physical_rate": 0,
                "silver_movement": "stable", "gold_movement": "stable", "market_summary": "No data",
                "silver_physical_mode": "manual", "gold_physical_mode": "manual",
                "silver_physical_premium": 0, "gold_physical_premium": 0}
    for metal in ["silver", "gold"]:
        mode = rate.get(f"{metal}_physical_mode", "manual")
        if mode == "calculated":
            base_src = rate.get(f"{metal}_physical_base", "mcx")
            base_val = rate.get(f"{metal}_{base_src}_rate", 0) if base_src in ("dollar", "mcx") else 0
            premium = rate.get(f"{metal}_physical_premium", 0)
            rate[f"{metal}_physical_rate"] = base_val + premium
    rate["silver_rate"] = rate.get("silver_physical_rate", rate.get("silver_rate", 0))
    rate["gold_rate"] = rate.get("gold_physical_rate", rate.get("gold_rate", 0))
    return rate

@api_router.post("/rates")
async def update_rates(req: RateUpdate, user=Depends(get_admin_user)):
    data = req.dict()
    for metal in ["silver", "gold"]:
        if data.get(f"{metal}_physical_mode") == "calculated":
            base_src = data.get(f"{metal}_physical_base", "mcx")
            base_val = data.get(f"{metal}_{base_src}_rate", 0) if base_src in ("dollar", "mcx") else 0
            data[f"{metal}_physical_rate"] = base_val + data.get(f"{metal}_physical_premium", 0)
    rate_data = {"id": str(uuid.uuid4()), **data, "updated_by": user["id"], "created_at": datetime.now(timezone.utc).isoformat()}
    await db.rates.insert_one(rate_data)
    return {k: v for k, v in rate_data.items() if k != "_id"}

@api_router.get("/rates/history")
async def rate_history(days: int = Query(7, ge=1, le=90)):
    rates = await db.rates.find({}, {"_id": 0}).sort("created_at", -1).limit(days * 3).to_list(days * 3)
    return {"rates": rates}

# ===================== REQUEST ENDPOINTS =====================

@api_router.post("/requests")
async def create_request(req: RequestCreate, user=Depends(get_current_user)):
    all_product_ids = req.product_ids or []
    if req.product_id and req.product_id not in all_product_ids:
        all_product_ids.insert(0, req.product_id)
    # Fetch product details for linked products
    linked_products = []
    if all_product_ids:
        prods = await db.products.find({"id": {"$in": all_product_ids}}, {"_id": 0, "id": 1, "title": 1, "metal_type": 1, "category": 1, "images": 1, "thumbnail_path": 1, "storage_path": 1, "approx_weight": 1, "purity": 1}).to_list(50)
        prod_map = {p["id"]: p for p in prods}
        for pid in all_product_ids:
            if pid in prod_map:
                linked_products.append(prod_map[pid])
    request_data = {
        "id": str(uuid.uuid4()),
        "request_type": req.request_type,
        "category": req.category,
        "preferred_time": req.preferred_time,
        "notes": req.notes,
        "product_id": req.product_id,
        "product_ids": all_product_ids,
        "linked_products": linked_products,
        "user_id": user["id"],
        "user_phone": user.get("phone", ""),
        "user_name": user.get("name", ""),
        "user_city": user.get("city", ""),
        "status": "pending",
        "assigned_to": "",
        "admin_notes": "",
        "notes_history": [],
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.requests.insert_one(request_data)
    return {k: v for k, v in request_data.items() if k != "_id"}

@api_router.get("/requests/my")
async def my_requests(user=Depends(get_current_user)):
    reqs = await db.requests.find({"user_id": user["id"]}, {"_id": 0}).sort("created_at", -1).limit(50).to_list(50)
    return {"requests": reqs}

@api_router.get("/requests")
async def list_requests(
    status: str = Query(""),
    request_type: str = Query(""),
    city: str = Query(""),
    assigned_to: str = Query(""),
    user=Depends(get_executive_or_admin)
):
    query: Dict[str, Any] = {}
    if status:
        query["status"] = status
    if request_type:
        query["request_type"] = request_type
    if city:
        query["user_city"] = {"$regex": city, "$options": "i"}
    if assigned_to:
        query["assigned_to"] = assigned_to
    reqs = await db.requests.find(query, {"_id": 0}).sort("created_at", -1).limit(200).to_list(200)
    return {"requests": reqs}

CANONICAL_STATUSES = {"pending", "in_progress", "contacted", "resolved", "no_response"}
STATUS_ALIASES = {"done": "resolved", "assigned": "in_progress"}

@api_router.patch("/requests/{request_id}")
async def update_request(request_id: str, req: RequestStatusUpdate, user=Depends(get_executive_or_admin)):
    existing = await db.requests.find_one({"id": request_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Request not found")
    normalized_status = STATUS_ALIASES.get(req.status, req.status)
    updates: Dict[str, Any] = {"status": normalized_status, "updated_at": datetime.now(timezone.utc).isoformat()}
    if req.assigned_to:
        updates["assigned_to"] = req.assigned_to
    if req.notes:
        updates["admin_notes"] = req.notes
        # Append to notes history
        note_entry = {
            "note": req.notes,
            "by": user.get("name", user.get("phone", "")),
            "by_id": user["id"],
            "status": req.status,
            "at": datetime.now(timezone.utc).isoformat()
        }
        await db.requests.update_one({"id": request_id}, {"$push": {"notes_history": note_entry}})
    await db.requests.update_one({"id": request_id}, {"$set": updates})
    return await db.requests.find_one({"id": request_id}, {"_id": 0})

@api_router.get("/requests/{request_id}/history")
async def get_request_history(request_id: str, user=Depends(get_executive_or_admin)):
    req = await db.requests.find_one({"id": request_id}, {"_id": 0})
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    # Get customer's other requests
    customer_requests = await db.requests.find(
        {"user_id": req["user_id"], "id": {"$ne": request_id}},
        {"_id": 0}
    ).sort("created_at", -1).limit(10).to_list(10)
    # Get customer details
    customer = await db.users.find_one({"id": req["user_id"]}, {"_id": 0})
    return {"request": req, "customer": customer, "past_requests": customer_requests}

# ===================== REWARD ENDPOINTS =====================

@api_router.get("/rewards/wallet")
async def get_wallet(user=Depends(get_current_user)):
    fresh = await db.users.find_one({"id": user["id"]}, {"_id": 0})
    points = fresh.get("reward_points", 0)
    total_earned = 0
    total_redeemed = 0
    txns = await db.reward_transactions.find({"user_id": user["id"]}, {"_id": 0}).sort("created_at", -1).limit(50).to_list(50)
    for t in txns:
        if t.get("type") == "credit":
            total_earned += t.get("points", 0)
        else:
            total_redeemed += t.get("points", 0)
    return {
        "current_points": points, "total_earned": total_earned, "total_redeemed": total_redeemed,
        "points_value_inr": points, "recent_transactions": txns[:10]
    }

@api_router.post("/rewards/redeem")
async def redeem_points(req: RedeemRequest, user=Depends(get_current_user)):
    if req.points <= 0:
        raise HTTPException(status_code=400, detail="Points must be greater than zero")
    fresh = await db.users.find_one({"id": user["id"]}, {"_id": 0})
    if fresh.get("reward_points", 0) < req.points:
        raise HTTPException(status_code=400, detail="Insufficient points")
    await db.users.update_one({"id": user["id"]}, {"$inc": {"reward_points": -req.points}})
    txn = {
        "id": str(uuid.uuid4()), "user_id": user["id"], "points": req.points,
        "type": "debit", "reason": req.reward_name or "Redemption",
        "status": "pending_approval", "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.reward_transactions.insert_one(txn)
    return {"message": "Redemption request submitted", "transaction": {k: v for k, v in txn.items() if k != "_id"}}

@api_router.get("/rewards/config")
async def get_reward_config(user=Depends(get_admin_user)):
    config = await db.reward_config.find_one({}, {"_id": 0})
    return config or {"points_per_1000": 10, "welcome_bonus": 100, "first_purchase_bonus": 50, "first_video_bonus": 25, "eligible_types": ["retailer", "mixed"]}

@api_router.post("/rewards/config")
async def update_reward_config(req: RewardConfigUpdate, user=Depends(get_admin_user)):
    await db.reward_config.update_one({}, {"$set": req.dict()}, upsert=True)
    return req.dict()

@api_router.post("/rewards/credit")
async def credit_points(req: RewardCreditRequest, user=Depends(get_billing_or_admin)):
    target = await db.users.find_one({"id": req.user_id}, {"_id": 0})
    if not target:
        raise HTTPException(status_code=404, detail="Customer not found")
    await db.users.update_one({"id": req.user_id}, {"$inc": {"reward_points": req.points}})
    txn = {
        "id": str(uuid.uuid4()), "user_id": req.user_id, "points": req.points,
        "type": "credit", "reason": req.reason or "Manual credit",
        "performed_by": user.get("name", user.get("phone", "")),
        "performed_by_id": user["id"],
        "performed_by_role": user.get("role", ""),
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.reward_transactions.insert_one(txn)
    fresh = await db.users.find_one({"id": req.user_id}, {"_id": 0, "reward_points": 1})
    return {"message": f"Credited {req.points} points", "new_balance": fresh.get("reward_points", 0)}

@api_router.post("/rewards/deduct")
async def deduct_points(req: RewardCreditRequest, user=Depends(get_billing_or_admin)):
    target = await db.users.find_one({"id": req.user_id}, {"_id": 0})
    if not target:
        raise HTTPException(status_code=404, detail="Customer not found")
    if target.get("reward_points", 0) < req.points:
        raise HTTPException(status_code=400, detail="Insufficient points")
    await db.users.update_one({"id": req.user_id}, {"$inc": {"reward_points": -req.points}})
    txn = {
        "id": str(uuid.uuid4()), "user_id": req.user_id, "points": req.points,
        "type": "debit", "reason": req.reason or "Manual deduction",
        "performed_by": user.get("name", user.get("phone", "")),
        "performed_by_id": user["id"],
        "performed_by_role": user.get("role", ""),
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.reward_transactions.insert_one(txn)
    fresh = await db.users.find_one({"id": req.user_id}, {"_id": 0, "reward_points": 1})
    return {"message": f"Deducted {req.points} points", "new_balance": fresh.get("reward_points", 0)}

@api_router.get("/rewards/customer/{customer_id}")
async def customer_reward_history(customer_id: str, user=Depends(get_billing_or_admin)):
    customer = await db.users.find_one({"id": customer_id}, {"_id": 0})
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    txns = await db.reward_transactions.find({"user_id": customer_id}, {"_id": 0}).sort("created_at", -1).limit(100).to_list(100)
    total_earned = sum(t["points"] for t in txns if t.get("type") == "credit")
    total_deducted = sum(t["points"] for t in txns if t.get("type") == "debit")
    return {
        "customer": {"id": customer["id"], "name": customer.get("name", ""), "phone": customer.get("phone", ""), "city": customer.get("city", ""), "customer_code": customer.get("customer_code", ""), "reward_points": customer.get("reward_points", 0)},
        "total_earned": total_earned, "total_deducted": total_deducted,
        "transactions": txns
    }

@api_router.get("/customers/search")
async def search_customers(q: str = Query(""), user=Depends(get_billing_or_admin)):
    if not q or len(q) < 2:
        return {"customers": []}
    query = {"role": "customer", "$or": [
        {"phone": {"$regex": q, "$options": "i"}},
        {"name": {"$regex": q, "$options": "i"}},
        {"customer_code": {"$regex": q, "$options": "i"}},
        {"city": {"$regex": q, "$options": "i"}},
    ]}
    customers = await db.users.find(query, {"_id": 0}).limit(20).to_list(20)
    return {"customers": customers}

@api_router.get("/rewards/history")
async def reward_history(user=Depends(get_current_user)):
    txns = await db.reward_transactions.find({"user_id": user["id"]}, {"_id": 0}).sort("created_at", -1).limit(50).to_list(50)
    return {"transactions": txns}

# ===================== AI ENDPOINTS =====================

@api_router.post("/ai/chat")
async def ai_chat(req: AIChatRequest, user=Depends(get_current_user)):
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        session_id = req.session_id or f"jeweller-{user['id']}"
        lang_instruction = ""
        if req.language == "hi":
            lang_instruction = "\n\nIMPORTANT: Respond in HINDI (हिंदी) language. Use Devanagari script."
        elif req.language == "pa":
            lang_instruction = "\n\nIMPORTANT: Respond in PUNJABI (ਪੰਜਾਬੀ) language. Use Gurmukhi script."
        system_msg = (
            "You are the AI business assistant for Yash Trade Jewellers, a leading wholesale and retail jewellery business "
            "specializing in silver, gold, and diamond. You help jewellers with:\n"
            "- Selling tips: How to pitch silver anklets, chains, articles, gifting items to their own customers\n"
            "- Silver knowledge: Why silver turns black, cleaning methods, storage tips, benefits\n"
            "- Trend suggestions: What categories are trending, seasonal recommendations\n"
            "- Business advice: Stocking decisions, festive season preparations, customer education\n"
            "- Content for retailers: WhatsApp messages, product pitches, care instructions they can share\n\n"
            "Keep responses SHORT, practical, and business-oriented. Use bullet points. "
            "Speak as a knowledgeable trade insider. Help jewellers sell more and educate their customers."
            f"{lang_instruction}"
        )
        history = await db.ai_chat_history.find(
            {"session_id": session_id}, {"_id": 0}
        ).sort("created_at", -1).limit(10).to_list(10)
        history.reverse()
        chat = LlmChat(
            api_key=EMERGENT_KEY,
            session_id=session_id,
            system_message=system_msg
        ).with_model("anthropic", "claude-sonnet-4-5-20250929")
        for h in history:
            if h.get("role") == "user":
                chat._messages.append({"role": "user", "content": h["content"]})
            elif h.get("role") == "assistant":
                chat._messages.append({"role": "assistant", "content": h["content"]})
        user_message = UserMessage(text=req.message)
        response = await chat.send_message(user_message)
        now = datetime.now(timezone.utc).isoformat()
        await db.ai_chat_history.insert_one({"session_id": session_id, "role": "user", "content": req.message, "created_at": now})
        await db.ai_chat_history.insert_one({"session_id": session_id, "role": "assistant", "content": response, "created_at": now})
        return {"response": response, "session_id": session_id}
    except Exception as e:
        logger.error(f"AI chat error: {e}")
        return {"response": "I'm having trouble connecting right now. Please try again.", "session_id": req.session_id or "", "error": True}

@api_router.get("/ai/suggestions")
async def ai_suggestions():
    suggestions = [
        {"title": "How to pitch silver anklets?", "icon": "trending-up"},
        {"title": "Silver cleaning tips for customers", "icon": "sparkles"},
        {"title": "Best gifting items under 5000", "icon": "gift"},
        {"title": "Why does silver turn black?", "icon": "help-circle"},
        {"title": "Festive season stock recommendations", "icon": "calendar"},
        {"title": "WhatsApp message for new collection", "icon": "message-circle"},
    ]
    return {"suggestions": suggestions}

# ===================== KNOWLEDGE ENDPOINTS =====================

@api_router.get("/knowledge")
async def list_knowledge(category: str = Query("")):
    query = {}
    if category:
        query["category"] = category
    articles = await db.knowledge.find(query, {"_id": 0}).sort("created_at", -1).limit(50).to_list(50)
    return {"articles": articles}

@api_router.get("/knowledge/{article_id}")
async def get_knowledge(article_id: str):
    article = await db.knowledge.find_one({"id": article_id}, {"_id": 0})
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    return article

@api_router.post("/knowledge")
async def create_knowledge(req: KnowledgeCreate, user=Depends(get_admin_user)):
    article = {
        "id": str(uuid.uuid4()),
        **req.dict(),
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.knowledge.insert_one(article)
    return {k: v for k, v in article.items() if k != "_id"}

# ===================== STORY ENDPOINTS =====================

@api_router.get("/stories")
async def list_stories():
    stories = await db.stories.find({}, {"_id": 0}).sort("created_at", -1).limit(20).to_list(20)
    return {"stories": stories}

@api_router.post("/stories")
async def create_story(req: StoryCreate, user=Depends(get_admin_user)):
    story = {
        "id": str(uuid.uuid4()),
        **req.dict(),
        "is_active": True,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.stories.insert_one(story)
    return {k: v for k, v in story.items() if k != "_id"}

# ===================== WISHLIST ENDPOINTS =====================

@api_router.post("/wishlist/toggle")
async def toggle_wishlist(product_id: str = Query(...), user=Depends(get_current_user)):
    existing = await db.wishlists.find_one({"user_id": user["id"], "product_id": product_id})
    if existing:
        await db.wishlists.delete_one({"user_id": user["id"], "product_id": product_id})
        return {"wishlisted": False}
    await db.wishlists.insert_one({
        "id": str(uuid.uuid4()), "user_id": user["id"], "product_id": product_id,
        "created_at": datetime.now(timezone.utc).isoformat()
    })
    return {"wishlisted": True}

@api_router.get("/wishlist")
async def get_wishlist(user=Depends(get_current_user)):
    items = await db.wishlists.find({"user_id": user["id"]}, {"_id": 0}).sort("created_at", -1).to_list(100)
    product_ids = [i["product_id"] for i in items]
    products = await db.products.find({"id": {"$in": product_ids}}, {"_id": 0}).to_list(100)
    return {"products": products}

# ===================== CART ENDPOINTS =====================

@api_router.post("/cart/add")
async def cart_add(req: CartAddRequest, user=Depends(get_current_user)):
    existing = await db.cart.find_one({"user_id": user["id"], "product_id": req.product_id, "status": "active"})
    if existing:
        await db.cart.update_one({"id": existing["id"]}, {"$inc": {"quantity": req.quantity}})
        return {"message": "Quantity updated", "item_id": existing["id"]}
    item = {
        "id": str(uuid.uuid4()), "user_id": user["id"], "product_id": req.product_id,
        "quantity": req.quantity, "notes": req.notes, "status": "active",
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.cart.insert_one(item)
    return {"message": "Added to cart", "item_id": item["id"]}

@api_router.get("/cart")
async def get_cart(user=Depends(get_current_user)):
    items = await db.cart.find({"user_id": user["id"], "status": "active"}, {"_id": 0}).sort("created_at", -1).to_list(100)
    product_ids = [i["product_id"] for i in items]
    products = await db.products.find({"id": {"$in": product_ids}}, {"_id": 0}).to_list(100)
    prod_map = {p["id"]: p for p in products}
    enriched = []
    for i in items:
        p = prod_map.get(i["product_id"])
        if p:
            enriched.append({**i, "product": p})
    count = len(enriched)
    return {"items": enriched, "count": count}

@api_router.delete("/cart/{item_id}")
async def cart_remove(item_id: str, user=Depends(get_current_user)):
    await db.cart.delete_one({"id": item_id, "user_id": user["id"]})
    return {"message": "Removed from cart"}

@api_router.post("/cart/submit")
async def cart_submit(req: CartSubmitRequest, user=Depends(get_current_user)):
    items = await db.cart.find({"user_id": user["id"], "status": "active"}, {"_id": 0}).to_list(100)
    if not items:
        raise HTTPException(status_code=400, detail="Cart is empty")
    product_ids = [i["product_id"] for i in items]
    products = await db.products.find({"id": {"$in": product_ids}}, {"_id": 0}).to_list(100)
    prod_map = {p["id"]: p for p in products}
    cart_details = []
    for i in items:
        p = prod_map.get(i["product_id"], {})
        cart_details.append({"product_id": i["product_id"], "title": p.get("title", ""), "metal_type": p.get("metal_type", ""), "category": p.get("category", ""), "quantity": i.get("quantity", 1), "notes": i.get("notes", "")})
    now = datetime.now(timezone.utc).isoformat()
    request_data = {
        "id": str(uuid.uuid4()), "request_type": "cart_selection",
        "user_id": user["id"], "user_phone": user.get("phone", ""), "user_name": user.get("name", ""), "user_city": user.get("city", ""),
        "category": "", "notes": req.notes, "product_id": "",
        "cart_items": cart_details, "cart_count": len(cart_details),
        "status": "pending", "assigned_to": "", "admin_notes": "", "notes_history": [],
        "created_at": now
    }
    await db.requests.insert_one(request_data)
    await db.cart.update_many({"user_id": user["id"], "status": "active"}, {"$set": {"status": "submitted"}})
    return {"message": "Cart submitted", "request_id": request_data["id"], "items_count": len(cart_details)}

@api_router.get("/cart/count")
async def cart_count(user=Depends(get_current_user)):
    count = await db.cart.count_documents({"user_id": user["id"], "status": "active"})
    return {"count": count}

# ===================== ANALYTICS ENDPOINTS =====================

@api_router.post("/analytics/event")
async def track_event(event: Dict[str, Any], user=Depends(get_current_user)):
    event_data = {
        "id": str(uuid.uuid4()), "user_id": user["id"],
        "event_type": event.get("event_type", ""),
        "data": event.get("data", {}),
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.analytics.insert_one(event_data)
    return {"tracked": True}

@api_router.get("/analytics/dashboard")
async def analytics_dashboard(user=Depends(get_admin_user)):
    total_users = await db.users.count_documents({"role": "customer"})
    total_products = await db.products.count_documents({"is_deleted": {"$ne": True}})
    total_batches = await db.batches.count_documents({"status": {"$ne": "archived"}})
    total_requests = await db.requests.count_documents({})
    pending_requests = await db.requests.count_documents({"status": "pending"})
    total_points = 0
    async for u in db.users.find({"role": "customer"}, {"reward_points": 1, "_id": 0}):
        total_points += u.get("reward_points", 0)
    # Storage stats
    storage_products = await db.products.count_documents({"storage_path": {"$exists": True}, "is_deleted": {"$ne": True}})
    recent_requests = await db.requests.find({}, {"_id": 0}).sort("created_at", -1).limit(10).to_list(10)
    return {
        "total_users": total_users, "total_products": total_products,
        "total_batches": total_batches, "uploaded_images": storage_products,
        "total_requests": total_requests, "pending_requests": pending_requests,
        "total_reward_points": total_points, "recent_requests": recent_requests
    }

# ===================== CUSTOMER ADMIN ENDPOINTS =====================

@api_router.get("/customers")
async def list_customers(
    page: int = Query(1, ge=1), limit: int = Query(20, ge=1, le=100),
    customer_type: str = Query(""), city: str = Query(""),
    search: str = Query(""), user=Depends(get_admin_user)
):
    query = {"role": "customer"}
    if customer_type:
        query["customer_type"] = customer_type
    if city:
        query["city"] = {"$regex": city, "$options": "i"}
    if search:
        query["$or"] = [
            {"phone": {"$regex": search, "$options": "i"}},
            {"name": {"$regex": search, "$options": "i"}},
            {"customer_code": {"$regex": search, "$options": "i"}}
        ]
    skip = (page - 1) * limit
    total = await db.users.count_documents(query)
    customers = await db.users.find(query, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    return {"customers": customers, "total": total, "page": page}

@api_router.get("/customers/{customer_id}")
async def get_customer(customer_id: str, user=Depends(get_admin_user)):
    customer = await db.users.find_one({"id": customer_id}, {"_id": 0})
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    return customer

@api_router.patch("/customers/{customer_id}")
async def update_customer(customer_id: str, req: CustomerUpdate, user=Depends(get_admin_user)):
    updates = {k: v for k, v in req.dict().items() if v or isinstance(v, bool)}
    if updates:
        await db.users.update_one({"id": customer_id}, {"$set": updates})
    return await db.users.find_one({"id": customer_id}, {"_id": 0})

# ===================== SEED DATA =====================

async def _internal_seed():
    """Internal seed called at startup - no auth needed"""
    # Always ensure system users exist
    for phone, name, code, ctype, role in [
        ("9999999999", "Yash Trade Admin", "ADMIN01", "admin", "admin"),
        ("7777777777", "Priya Executive", "EXEC01", "executive", "executive"),
        ("6666666666", "Billing Executive", "BILL01", "billing_executive", "billing_executive"),
    ]:
        if not await db.users.find_one({"phone": phone}):
            await db.users.insert_one({
                "id": str(uuid.uuid4()), "phone": phone, "name": name,
                "city": "Delhi", "customer_code": code, "customer_type": ctype,
                "role": role, "category_interests": [], "is_eligible_rewards": False,
                "assigned_salesperson": "", "status": "active", "reward_points": 0,
                "is_new": False, "created_at": datetime.now(timezone.utc).isoformat(),
                "last_login": datetime.now(timezone.utc).isoformat()
            })
    # Demo customer
    await db.users.update_one({"phone": "8888888888"}, {"$setOnInsert": {
        "id": str(uuid.uuid4()), "phone": "8888888888", "name": "Rajesh Kumar",
        "city": "Jaipur", "customer_code": "AA8888", "customer_type": "retailer",
        "role": "customer", "category_interests": ["payal", "chain", "articles"],
        "is_eligible_rewards": True, "assigned_salesperson": "", "status": "active",
        "reward_points": 250, "is_new": False, "created_at": datetime.now(timezone.utc).isoformat(),
        "last_login": datetime.now(timezone.utc).isoformat()
    }}, upsert=True)
    existing = await db.products.count_documents({})
    if existing > 0:
        return
    # Indexes
    await db.products.create_index([("created_at", -1)])
    await db.products.create_index([("batch_id", 1)])
    await db.products.create_index([("is_deleted", 1)])
    await db.rates.create_index([("created_at", -1)])
    await db.requests.create_index([("user_id", 1)])
    await db.requests.create_index([("status", 1)])
    await db.users.create_index([("phone", 1)], unique=True)
    await db.batches.create_index([("created_at", -1)])

@api_router.post("/seed")
async def seed_data(user=Depends(get_admin_user)):
    existing = await db.products.count_documents({})
    if existing > 0:
        return {"message": "Data already seeded", "products": existing}

    admin = await db.users.find_one({"phone": "9999999999"})
    if not admin:
        await db.users.insert_one({
            "id": str(uuid.uuid4()), "phone": "9999999999", "name": "Yash Trade Admin",
            "city": "Delhi", "customer_code": "ADMIN01", "customer_type": "admin",
            "role": "admin", "category_interests": [], "is_eligible_rewards": False,
            "assigned_salesperson": "", "status": "active", "reward_points": 0,
            "is_new": False, "created_at": datetime.now(timezone.utc).isoformat(),
            "last_login": datetime.now(timezone.utc).isoformat()
        })

    await db.users.update_one({"phone": "8888888888"}, {"$setOnInsert": {
        "id": str(uuid.uuid4()), "phone": "8888888888", "name": "Rajesh Kumar",
        "city": "Jaipur", "customer_code": "AA8888", "customer_type": "retailer",
        "role": "customer", "category_interests": ["payal", "chain", "articles"],
        "is_eligible_rewards": True, "assigned_salesperson": "", "status": "active",
        "reward_points": 250, "is_new": False, "created_at": datetime.now(timezone.utc).isoformat(),
        "last_login": datetime.now(timezone.utc).isoformat()
    }}, upsert=True)

    products = [
        {"title": "Designer Silver Payal", "description": "Handcrafted silver anklets with intricate jali work.", "metal_type": "silver", "category": "payal", "subcategory": "bridal", "images": ["https://images.unsplash.com/photo-1611652022419-a9419f74343d?w=600"], "approx_weight": "45-55 grams", "stock_status": "in_stock", "tags": ["bridal", "festive", "bestseller"], "is_trending": True, "is_new_arrival": True},
        {"title": "Pure Silver Chain Collection", "description": "Premium Italian-style silver chains.", "metal_type": "silver", "category": "chain", "subcategory": "italian", "images": ["https://images.unsplash.com/photo-1679973296611-82470327c513?w=600"], "approx_weight": "20-80 grams", "stock_status": "in_stock", "tags": ["chain", "daily_wear", "men"], "is_trending": True},
        {"title": "Silver Articles - Pooja Thali Set", "description": "Complete silver pooja thali. 925 hallmarked.", "metal_type": "silver", "category": "articles", "subcategory": "pooja", "images": ["https://images.unsplash.com/photo-1589128784765-a69d61ed9c39?w=600"], "approx_weight": "150-200 grams", "stock_status": "in_stock", "tags": ["pooja", "gifting", "articles"]},
        {"title": "Gold Temple Necklace Set", "description": "Traditional temple design gold necklace. 22K gold.", "metal_type": "gold", "category": "necklace", "subcategory": "temple", "images": ["https://images.unsplash.com/photo-1599643478518-a784e5dc4c8f?w=600"], "approx_weight": "35-45 grams", "stock_status": "in_stock", "tags": ["bridal", "temple", "traditional"], "is_pinned": True},
        {"title": "Diamond Solitaire Ring", "description": "Elegant solitaire diamond ring in 18K white gold.", "metal_type": "diamond", "category": "ring", "subcategory": "solitaire", "images": ["https://images.unsplash.com/photo-1606623546924-a4f3ae5ea3e8?w=600"], "approx_weight": "4.5 grams", "stock_status": "limited", "tags": ["diamond", "engagement", "premium"]},
        {"title": "Silver Toe Rings Set", "description": "Traditional silver toe rings. Set of 6 pairs.", "metal_type": "silver", "category": "toe_rings", "subcategory": "traditional", "images": ["https://images.unsplash.com/photo-1605100804763-247f67b3557e?w=600"], "approx_weight": "8-12 grams", "stock_status": "in_stock", "tags": ["toe_rings", "daily_wear", "women"]},
        {"title": "Gold Bangles - Rajasthani", "description": "Beautiful Rajasthani meenakari gold bangles. 22K.", "metal_type": "gold", "category": "bangles", "subcategory": "meenakari", "images": ["https://images.unsplash.com/photo-1611591437281-460bfbe1220a?w=600"], "approx_weight": "25-35 grams per pair", "stock_status": "in_stock", "tags": ["bangles", "rajasthani", "festive"]},
        {"title": "Silver Baby Gifting Set", "description": "Complete baby gift set in pure silver.", "metal_type": "silver", "category": "gifting", "subcategory": "baby", "images": ["https://images.unsplash.com/photo-1515562141589-67f0d97dc11b?w=600"], "approx_weight": "80-100 grams", "stock_status": "in_stock", "tags": ["gifting", "baby", "premium"]},
    ]
    for p in products:
        p["id"] = str(uuid.uuid4())
        p["post_type"] = "product"
        p["views"] = 0
        p["is_pinned"] = p.get("is_pinned", False)
        p["is_new_arrival"] = p.get("is_new_arrival", True)
        p["is_trending"] = p.get("is_trending", False)
        p["visibility"] = "all"
        p["is_deleted"] = False
        p["video_url"] = ""
        p["created_at"] = datetime.now(timezone.utc).isoformat()
        p["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.products.insert_many(products)

    await db.rates.insert_one({
        "id": str(uuid.uuid4()),
        "silver_dollar_rate": 31.25, "silver_mcx_rate": 95.80, "silver_physical_rate": 96.50,
        "silver_physical_mode": "manual", "silver_physical_premium": 0.70, "silver_physical_base": "mcx",
        "silver_movement": "up",
        "gold_dollar_rate": 2385.00, "gold_mcx_rate": 7380.00, "gold_physical_rate": 7450.00,
        "gold_physical_mode": "manual", "gold_physical_premium": 70.00, "gold_physical_base": "mcx",
        "gold_movement": "stable",
        "market_summary": "Silver up 1.2% today. Gold holding steady near all-time highs.",
        "created_at": datetime.now(timezone.utc).isoformat()
    })

    knowledge_items = [
        {"title": "Why Does Silver Turn Black?", "content": "Silver turns black due to tarnishing. It is natural and does NOT mean the silver is impure.", "category": "silver_care", "card_type": "article", "tags": ["care", "education"]},
        {"title": "How to Clean Silver at Home", "content": "Baking soda paste, toothpaste method, aluminium foil method, lemon + salt.", "category": "silver_care", "card_type": "article", "tags": ["cleaning", "tips"]},
        {"title": "Benefits of Wearing Silver", "content": "Antimicrobial, regulates temperature, hypoallergenic, affordable luxury.", "category": "benefits", "card_type": "article", "tags": ["benefits", "selling_point"]},
    ]
    for k in knowledge_items:
        k["id"] = str(uuid.uuid4())
        k["image_url"] = ""
        k["created_at"] = datetime.now(timezone.utc).isoformat()
    await db.knowledge.insert_many(knowledge_items)

    stories = [
        {"title": "New Silver Collection", "image_url": "https://images.unsplash.com/photo-1679973296611-82470327c513?w=400", "category": "new_arrivals", "link_type": "category", "link_id": "chain"},
        {"title": "Today's Silver Rate", "image_url": "https://images.unsplash.com/photo-1589128784765-a69d61ed9c39?w=400", "category": "rates", "link_type": "rates", "link_id": ""},
        {"title": "Trending: Payal", "image_url": "https://images.unsplash.com/photo-1611652022419-a9419f74343d?w=400", "category": "trending", "link_type": "category", "link_id": "payal"},
    ]
    for s in stories:
        s["id"] = str(uuid.uuid4())
        s["is_active"] = True
        s["created_at"] = datetime.now(timezone.utc).isoformat()
    await db.stories.insert_many(stories)

    await db.reward_config.update_one({}, {"$set": {
        "points_per_1000": 10, "welcome_bonus": 100, "first_purchase_bonus": 50,
        "first_video_bonus": 25, "eligible_types": ["retailer", "mixed"]
    }}, upsert=True)

    await db.products.create_index([("created_at", -1)])
    await db.products.create_index([("category", 1)])
    await db.products.create_index([("metal_type", 1)])
    await db.products.create_index([("batch_id", 1)])
    await db.products.create_index([("is_deleted", 1)])
    await db.rates.create_index([("created_at", -1)])
    await db.requests.create_index([("user_id", 1)])
    await db.requests.create_index([("status", 1)])
    await db.users.create_index([("phone", 1)], unique=True)
    await db.batches.create_index([("created_at", -1)])
    await db.batches.create_index([("status", 1)])

    return {"message": "Seed data created successfully", "products": len(products)}

@api_router.post("/seed/expand")
async def seed_expand(user=Depends(get_admin_user)):
    exec_exists = await db.users.find_one({"phone": "7777777777"})
    if not exec_exists:
        await db.users.insert_one({
            "id": str(uuid.uuid4()), "phone": "7777777777", "name": "Priya Executive",
            "city": "Delhi", "customer_code": "EXEC01", "customer_type": "executive",
            "role": "executive", "category_interests": [], "is_eligible_rewards": False,
            "assigned_salesperson": "", "status": "active", "reward_points": 0,
            "is_new": False, "created_at": datetime.now(timezone.utc).isoformat(),
            "last_login": datetime.now(timezone.utc).isoformat()
        })
    count = await db.products.count_documents({})
    if count >= 50:
        return {"message": "Already expanded", "products": count}
    imgs = [
        "https://images.unsplash.com/photo-1679973296611-82470327c513?w=600",
        "https://images.unsplash.com/photo-1589128784765-a69d61ed9c39?w=600",
        "https://images.unsplash.com/photo-1611652022419-a9419f74343d?w=600",
        "https://images.unsplash.com/photo-1606623546924-a4f3ae5ea3e8?w=600",
        "https://images.unsplash.com/photo-1599643478518-a784e5dc4c8f?w=600",
        "https://images.unsplash.com/photo-1611591437281-460bfbe1220a?w=600",
        "https://images.unsplash.com/photo-1515562141589-67f0d97dc11b?w=600",
        "https://images.unsplash.com/photo-1605100804763-247f67b3557e?w=600",
        "https://images.unsplash.com/photo-1693213085231-fc580d8916de?w=600",
    ]
    extra = [
        ("Heavy Silver Payal","silver","payal","60-80g","bridal"),
        ("Light Daily Wear Payal","silver","payal","15-25g","daily_wear"),
        ("Oxidized Silver Payal","silver","payal","30-40g","oxidized"),
        ("Italian Silver Chain 22inch","silver","chain","30-50g","italian"),
        ("Rope Silver Chain Heavy","silver","chain","60-100g","mens"),
        ("Silver Pooja Bell","silver","articles","50-80g","pooja"),
        ("Silver Photo Frame","silver","articles","100-150g","gifting"),
        ("Kundan Gold Necklace","gold","necklace","40-55g","bridal"),
        ("Gold Choker Set","gold","necklace","30-40g","festive"),
        ("Polki Diamond Set","diamond","necklace","25-35g","bridal"),
        ("Gold Jhumka Earrings","gold","earrings","10-15g","festive"),
        ("Diamond Studs","diamond","earrings","3-5g","daily_wear"),
        ("Gold Bangles Set of 4","gold","bangles","40-60g","festive"),
        ("Silver Kada Heavy Mens","silver","kadaa","80-120g","mens"),
        ("Silver Coin 50g Ganesh","silver","coins","50g","gifting"),
        ("Gold Coin 10g","gold","coins","10g","investment"),
        ("Silver Bracelet Curb Link","silver","bracelet","30-50g","mens"),
        ("Diamond Tennis Bracelet","diamond","bracelet","8-12g","premium"),
        ("Silver Anklet Ghungroo","silver","payal","25-35g","traditional"),
        ("Gold Mangalsutra","gold","necklace","15-25g","bridal"),
    ]
    new_products = []
    for i, (title, metal, cat, wt, tag) in enumerate(extra):
        new_products.append({
            "id": str(uuid.uuid4()), "title": title, "description": f"Premium quality {metal} {cat}.",
            "metal_type": metal, "category": cat, "subcategory": tag, "images": [imgs[i % len(imgs)]],
            "video_url": "", "approx_weight": wt, "stock_status": "in_stock",
            "tags": [tag, metal, cat], "is_pinned": False, "is_new_arrival": i < 10,
            "is_trending": i % 5 == 0, "visibility": "all", "post_type": "product",
            "is_deleted": False, "views": 0,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        })
    if new_products:
        await db.products.insert_many(new_products)
    total = await db.products.count_documents({})
    return {"message": f"Expanded to {total} products", "products": total}

# ===================== APP SETUP =====================

app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup():
    try:
        await _internal_seed()
        logger.info("Seed data initialized")
    except Exception as e:
        logger.info(f"Seed check: {e}")
    try:
        init_storage()
        logger.info("Object storage ready")
    except Exception as e:
        logger.warning(f"Storage init deferred: {e}")

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
