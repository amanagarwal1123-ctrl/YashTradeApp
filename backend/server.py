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
import fitz  # PyMuPDF for PDF processing
import shutil
import tempfile

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ.get('DB_NAME', 'jewellers_app')]

app = FastAPI()
api_router = APIRouter(prefix="/api")

JWT_SECRET = os.environ.get('JWT_SECRET', '')
if not JWT_SECRET or len(JWT_SECRET) < 16:
    JWT_SECRET = 'aman-jewellers-secret-key-2024-prod-v1'
    print("WARNING: JWT_SECRET is weak or missing — using built-in default. Set a strong JWT_SECRET in .env for production.")
JWT_ALGORITHM = 'HS256'
EMERGENT_KEY = os.environ.get('EMERGENT_LLM_KEY', '')

# CORS origins from env (comma-separated), falls back to permissive for dev
CORS_ORIGINS = [o.strip() for o in os.environ.get('CORS_ORIGINS', '').split(',') if o.strip()]

# ===================== OTP STORE =====================
# OTP store with expiry and rate limiting.
# Real OTPs are delivered via MSG91 OTP API; demo phones bypass MSG91 and accept 1234.
import time as _time
import hashlib

_otp_store: Dict[str, Dict[str, Any]] = {}  # phone -> {otp, expires_at, attempts}
_otp_rate: Dict[str, list] = {}  # phone -> [timestamp, ...]
OTP_EXPIRY_SECONDS = 300  # 5 minutes
OTP_MAX_ATTEMPTS = 5
OTP_RATE_LIMIT = 5  # max OTP sends per phone per 10 min
OTP_RATE_WINDOW = 600  # 10 minutes

# MSG91 OTP configuration
MSG91_AUTHKEY = os.environ.get('MSG91_AUTHKEY', '')
MSG91_TEMPLATE_ID = os.environ.get('MSG91_TEMPLATE_ID', '')  # optional — account default OTP template used if empty
MSG91_BASE_URL = os.environ.get('MSG91_BASE_URL', 'https://control.msg91.com/api/v5').rstrip('/')

# Phones that always use the fixed demo OTP 1234 (admin/executive/test accounts)
DEMO_PHONES = {p.strip() for p in os.environ.get('OTP_DEMO_PHONES', '').split(',') if p.strip()}

def _is_demo_phone(phone: str) -> bool:
    if os.environ.get('OTP_DEMO_MODE', 'false').lower() == 'true':
        return True
    return phone in DEMO_PHONES

def _sms_available() -> bool:
    return bool(MSG91_AUTHKEY)

def _msg91_mobile(phone: str) -> str:
    """Normalize to MSG91 format: 91 + 10-digit number (no plus sign)."""
    digits = ''.join(c for c in phone if c.isdigit())
    if len(digits) == 10:
        return f"91{digits}"
    if digits.startswith('91') and len(digits) == 12:
        return digits
    return digits

def _msg91_headers() -> Dict[str, str]:
    return {"authkey": MSG91_AUTHKEY, "Accept": "application/json", "Content-Type": "application/json"}

async def _send_sms_otp(phone: str):
    """Dispatch an OTP to a phone (demo store or real MSG91 SMS). Raises HTTPException on failure."""
    if _is_demo_phone(phone) or not _sms_available():
        _store_otp(phone, '1234')
        logger.info(f"Demo OTP issued for ...{phone[-4:]}")
        return
    # MSG91 accepts almost any 12-digit number, so validate Indian mobiles locally first
    digits = ''.join(c for c in phone if c.isdigit())[-10:]
    if len(digits) != 10 or digits[0] not in '6789':
        raise HTTPException(status_code=400, detail="Invalid phone number. Please check and try again.")
    try:
        def _send():
            params = {"mobile": _msg91_mobile(phone), "otp_length": 4, "otp_expiry": 5}
            if MSG91_TEMPLATE_ID:
                params["template_id"] = MSG91_TEMPLATE_ID
            return http_requests.post(f"{MSG91_BASE_URL}/otp", params=params, headers=_msg91_headers(), json={}, timeout=15)
        resp = await asyncio.to_thread(_send)
        try:
            body = resp.json()
        except ValueError:
            body = {}
        if resp.status_code >= 300 or str(body.get("type", "")).lower() == "error":
            msg = str(body.get("message", "")).lower()
            logger.error(f"MSG91 send-otp error for ...{phone[-4:]}: status={resp.status_code} msg={body.get('message')}")
            if 'mobile' in msg or 'invalid' in msg:
                raise HTTPException(status_code=400, detail="Invalid phone number. Please check and try again.")
            raise HTTPException(status_code=502, detail="Could not send OTP right now. Please try again shortly.")
        # Count this send against the local rate limit as well
        timestamps = _otp_rate.get(phone, [])
        timestamps.append(_time.time())
        _otp_rate[phone] = timestamps
        logger.info(f"MSG91 OTP sent to ...{phone[-4:]} (request_id={body.get('request_id')})")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"MSG91 send-otp failure for ...{phone[-4:]}: {e}")
        raise HTTPException(status_code=502, detail="Could not send OTP right now. Please try again shortly.")

async def _check_sms_otp(phone: str, otp: str):
    """Verify an OTP (demo store or MSG91). Raises HTTPException if invalid."""
    if _is_demo_phone(phone) or not _sms_available():
        success, err_msg = _verify_otp(phone, otp)
        if not success:
            raise HTTPException(status_code=400, detail=err_msg)
        return
    try:
        def _check():
            return http_requests.get(f"{MSG91_BASE_URL}/otp/verify",
                                params={"mobile": _msg91_mobile(phone), "otp": otp},
                                headers=_msg91_headers(), timeout=15)
        resp = await asyncio.to_thread(_check)
        try:
            body = resp.json()
        except ValueError:
            body = {}
        if str(body.get("type", "")).lower() != "success":
            msg = str(body.get("message", "")).lower()
            logger.warning(f"MSG91 verify-otp rejected for ...{phone[-4:]}: {body.get('message')}")
            if 'not match' in msg or 'invalid' in msg:
                raise HTTPException(status_code=400, detail="Invalid OTP")
            if 'expire' in msg or 'not found' in msg or 'already verified' in msg:
                raise HTTPException(status_code=400, detail="OTP expired or not found. Please request a new OTP.")
            raise HTTPException(status_code=400, detail="Invalid OTP")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"MSG91 verify-otp failure for ...{phone[-4:]}: {e}")
        raise HTTPException(status_code=502, detail="Could not verify OTP right now. Please try again.")

# Pending phone-change requests: user_id -> {new_phone, expires_at}
_phone_change_store: Dict[str, Dict[str, Any]] = {}

def _account_status(user: Dict[str, Any]) -> str:
    return user.get("account_status", user.get("status", "active"))

def _check_otp_rate(phone: str) -> bool:
    """Returns True if under rate limit."""
    now = _time.time()
    timestamps = _otp_rate.get(phone, [])
    timestamps = [t for t in timestamps if now - t < OTP_RATE_WINDOW]
    _otp_rate[phone] = timestamps
    return len(timestamps) < OTP_RATE_LIMIT

def _store_otp(phone: str, otp: str):
    now = _time.time()
    _otp_store[phone] = {"otp": otp, "expires_at": now + OTP_EXPIRY_SECONDS, "attempts": 0}
    timestamps = _otp_rate.get(phone, [])
    timestamps.append(now)
    _otp_rate[phone] = timestamps

def _verify_otp(phone: str, otp: str) -> tuple:
    """Returns (success: bool, error_msg: str)"""
    entry = _otp_store.get(phone)
    if not entry:
        return False, "OTP not found. Please request a new OTP."
    if _time.time() > entry["expires_at"]:
        del _otp_store[phone]
        return False, "OTP expired. Please request a new OTP."
    if entry["attempts"] >= OTP_MAX_ATTEMPTS:
        del _otp_store[phone]
        return False, "Too many failed attempts. Please request a new OTP."
    entry["attempts"] += 1
    if entry["otp"] != otp:
        return False, "Invalid OTP"
    # Success — remove used OTP
    del _otp_store[phone]
    return True, ""

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
    points: int = Field(gt=0, description="Must be a positive integer")
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
    name: str = ""
    shop_name: str = ""
    location: str = ""
    customer_type: str = ""
    city: str = ""
    category_interests: List[str] = []
    is_eligible_rewards: bool = True
    assigned_salesperson: Optional[str] = None
    status: str = ""
    account_status: str = ""

class PhoneChangeRequest(BaseModel):
    new_phone: str

class PhoneChangeVerify(BaseModel):
    new_phone: str
    otp: str

class TelecallerAction(BaseModel):
    action: str = "note"  # status_change | note | call | whatsapp | follow_up
    new_status: str = ""
    notes: str = ""
    follow_up_at: str = ""

class RequestStatusUpdate(BaseModel):
    status: str
    assigned_to: str = ""
    notes: str = ""

class ExecutiveCreate(BaseModel):
    name: str
    phone: str
    code: str
    role: str = "executive"  # executive or billing_executive

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
    quantity: int = Field(1, gt=0, description="Must be a positive integer")
    notes: str = ""

class CartSubmitRequest(BaseModel):
    notes: str = ""

class AboutContentUpdate(BaseModel):
    section: str
    content_en: str = ""
    content_hi: str = ""
    content_pa: str = ""

class RateSlabCreate(BaseModel):
    metal_type: str
    item_name: str = ""
    category: str = ""
    subcategory: str = ""
    purity: str = ""
    wastage: str = ""
    labour_kg: str = ""
    order: int = 0

class SchemeCreate(BaseModel):
    title: str
    title_hi: str = ""
    title_pa: str = ""
    description: str = ""
    description_hi: str = ""
    description_pa: str = ""
    poster_url: str = ""
    is_active: bool = True
    order: int = 0

class BrandCreate(BaseModel):
    name: str
    logo_url: str = ""
    description: str = ""
    order: int = 0
    is_active: bool = True

class ShowroomFloorCreate(BaseModel):
    floor_name: str
    floor_name_hi: str = ""
    floor_name_pa: str = ""
    description: str = ""
    description_hi: str = ""
    description_pa: str = ""
    products_available: str = ""
    products_available_hi: str = ""
    products_available_pa: str = ""
    photos: List[str] = []
    order: int = 0

class ExhibitionCreate(BaseModel):
    title: str
    title_hi: str = ""
    title_pa: str = ""
    description: str = ""
    description_hi: str = ""
    description_pa: str = ""
    poster_url: str = ""
    photos: List[str] = []
    date: str = ""
    location: str = ""
    is_upcoming: bool = True
    is_active: bool = True

class BannerCreate(BaseModel):
    title: str
    subtitle: str = ""
    image_url: str = ""
    cta_label: str = ""
    cta_type: str = "none"  # none | feed | product | url
    cta_target: str = ""
    order: int = 0
    is_active: bool = True
    start_date: str = ""  # YYYY-MM-DD (optional)
    end_date: str = ""    # YYYY-MM-DD (optional)

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
        if user.get("account_status", user.get("status", "active")) != "active":
            raise HTTPException(status_code=403, detail="Your account is inactive. Please contact Yash Trade support.")
        return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except HTTPException:
        raise
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
    if not _check_otp_rate(phone):
        raise HTTPException(status_code=429, detail="Too many OTP requests. Please wait before trying again.")
    # Registered numbers only — enrollment happens on the Yash Ornaments website
    user = await db.users.find_one({"phone": phone}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=404, detail="This number is not registered. Please enroll on the Yash Ornaments website first.")
    if _account_status(user) != "active":
        raise HTTPException(status_code=403, detail="Your account is inactive. Please contact Yash Trade support.")
    await _send_sms_otp(phone)
    return {"message": "OTP sent successfully"}

@api_router.post("/auth/verify-otp")
async def verify_otp(req: VerifyOTPRequest):
    phone = req.phone.strip()
    otp = req.otp.strip()
    user = await db.users.find_one({"phone": phone}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=404, detail="This number is not registered. Please enroll on the Yash Ornaments website first.")
    if _account_status(user) != "active":
        raise HTTPException(status_code=403, detail="Your account is inactive. Please contact Yash Trade support.")
    await _check_sms_otp(phone, otp)
    is_new = user.get("is_new", False)
    if is_new:
        welcome_config = await db.reward_config.find_one({}, {"_id": 0})
        bonus = welcome_config.get("welcome_bonus", 100) if welcome_config else 100
        await db.users.update_one({"id": user["id"]}, {"$inc": {"reward_points": bonus}, "$set": {"is_new": False}})
        await db.reward_transactions.insert_one({
            "id": str(uuid.uuid4()), "user_id": user["id"], "points": bonus,
            "type": "credit", "reason": "Welcome bonus", "created_at": datetime.now(timezone.utc).isoformat()
        })
    # Login tracking — only on successful OTP verification
    now = datetime.now(timezone.utc).isoformat()
    login_updates = {
        "last_login": now,
        "last_login_at": now,
        "has_logged_in": True,
        "phone_verified": True,
    }
    if not user.get("first_login_at"):
        login_updates["first_login_at"] = now
    await db.users.update_one({"id": user["id"]}, {"$set": login_updates})
    fresh_user = await db.users.find_one({"phone": phone}, {"_id": 0})
    token = create_token(fresh_user["id"], fresh_user.get("role", "customer"))
    return {"token": token, "user": {**fresh_user, "is_new": is_new}}

@api_router.get("/auth/me")
async def get_me(user=Depends(get_current_user)):
    fresh = await db.users.find_one({"id": user["id"]}, {"_id": 0})
    return fresh

@api_router.put("/auth/profile")
async def update_profile(updates: Dict[str, Any], user=Depends(get_current_user)):
    allowed = {"name", "city", "shop_name", "location"}
    filtered = {k: str(v).strip() for k, v in updates.items() if k in allowed and isinstance(v, (str, int, float))}
    if "location" in filtered and "city" not in filtered:
        filtered["city"] = filtered["location"]  # keep legacy city field in sync
    if filtered:
        filtered["updated_at"] = datetime.now(timezone.utc).isoformat()
        await db.users.update_one({"id": user["id"]}, {"$set": filtered})
    return await db.users.find_one({"id": user["id"]}, {"_id": 0})

@api_router.post("/auth/phone-change/request")
async def phone_change_request(req: PhoneChangeRequest, user=Depends(get_current_user)):
    """Start a verified phone-number change: OTP is sent to the NEW number."""
    digits = ''.join(c for c in req.new_phone.strip() if c.isdigit())[-10:]
    if len(digits) != 10 or digits[0] not in '6789':
        raise HTTPException(status_code=400, detail="Please enter a valid 10-digit mobile number.")
    if digits == user["phone"]:
        raise HTTPException(status_code=400, detail="This is already your registered number.")
    existing = await db.users.find_one({"phone": digits}, {"_id": 0, "id": 1})
    if existing:
        raise HTTPException(status_code=409, detail="This number is already registered to another account.")
    if not _check_otp_rate(digits):
        raise HTTPException(status_code=429, detail="Too many OTP requests. Please wait before trying again.")
    await _send_sms_otp(digits)
    _phone_change_store[user["id"]] = {"new_phone": digits, "expires_at": _time.time() + OTP_EXPIRY_SECONDS}
    return {"message": "OTP sent to the new number"}

@api_router.post("/auth/phone-change/verify")
async def phone_change_verify(req: PhoneChangeVerify, user=Depends(get_current_user)):
    """Complete the phone change after OTP re-verification on the new number."""
    new_phone = ''.join(c for c in req.new_phone.strip() if c.isdigit())[-10:]
    pending = _phone_change_store.get(user["id"])
    if not pending or pending["new_phone"] != new_phone:
        raise HTTPException(status_code=400, detail="No pending phone change for this number. Please request an OTP first.")
    if _time.time() > pending["expires_at"]:
        _phone_change_store.pop(user["id"], None)
        raise HTTPException(status_code=400, detail="OTP expired. Please request a new one.")
    await _check_sms_otp(new_phone, req.otp.strip())
    # Re-check duplicates in case the number registered in the meantime
    existing = await db.users.find_one({"phone": new_phone}, {"_id": 0, "id": 1})
    if existing and existing["id"] != user["id"]:
        raise HTTPException(status_code=409, detail="This number is already registered to another account.")
    await db.users.update_one({"id": user["id"]}, {"$set": {
        "phone": new_phone, "phone_verified": True,
        "updated_at": datetime.now(timezone.utc).isoformat()
    }})
    _phone_change_store.pop(user["id"], None)
    logger.info(f"Phone changed for user {user['id']} to ...{new_phone[-4:]}")
    return await db.users.find_one({"id": user["id"]}, {"_id": 0})

# ===================== PRODUCT ENDPOINTS =====================

@api_router.get("/products")
async def list_products(
    page: int = Query(1, ge=1), limit: int = Query(50, ge=1, le=100000),
    category: str = Query(""), metal_type: str = Query(""),
    search: str = Query(""), post_type: str = Query(""),
    include_hidden: bool = Query(False),
    ids: str = Query(""),
    authorization: Optional[str] = Header(None)
):
    # Stable ordered fetch by explicit ID list (used by image viewer for product continuity)
    if ids:
        id_list = [i.strip() for i in ids.split(",") if i.strip()][:300]
        docs = await db.products.find(
            {"id": {"$in": id_list}, "is_deleted": {"$ne": True}, "visibility": {"$ne": "hidden"}},
            {"_id": 0}
        ).to_list(len(id_list))
        doc_map = {d["id"]: d for d in docs}
        ordered = [doc_map[i] for i in id_list if i in doc_map]
        return {"products": ordered, "total": len(ordered), "page": 1, "pages": 1}
    query: Dict[str, Any] = {"is_deleted": {"$ne": True}}
    if include_hidden:
        # Require admin auth for include_hidden
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Admin authentication required to view hidden products")
        try:
            payload = jwt.decode(authorization.split(" ")[1], JWT_SECRET, algorithms=[JWT_ALGORITHM])
            u = await db.users.find_one({"id": payload["user_id"]}, {"_id": 0})
            if not u or u.get("role") != "admin":
                raise HTTPException(status_code=403, detail="Admin access required to view hidden products")
        except jwt.PyJWTError:
            raise HTTPException(status_code=401, detail="Invalid token")
    else:
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
    # POINT 3: Randomize product order using MongoDB $sample for first page
    if page == 1 and not search:
        pipeline = [{"$match": query}, {"$sample": {"size": min(limit, total)}}, {"$project": {"_id": 0}}]
        products = await db.products.aggregate(pipeline).to_list(limit)
    else:
        products = await db.products.find(query, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    return {"products": products, "total": total, "page": page, "pages": (total + limit - 1) // limit}

@api_router.get("/products/{product_id}")
async def get_product(product_id: str, authorization: Optional[str] = Header(None)):
    product = await db.products.find_one({"id": product_id}, {"_id": 0})
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    # Check if product is hidden/deleted — only admin can see those
    is_hidden = product.get("visibility") == "hidden" or product.get("is_deleted")
    if is_hidden:
        is_admin = False
        if authorization and authorization.startswith("Bearer "):
            try:
                payload = jwt.decode(authorization.split(" ")[1], JWT_SECRET, algorithms=[JWT_ALGORITHM])
                u = await db.users.find_one({"id": payload["user_id"]}, {"_id": 0})
                is_admin = u and u.get("role") == "admin"
            except Exception:
                pass
        if not is_admin:
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
    limit: int = Query(50, ge=1, le=100000),
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

# ===================== CHUNKED PDF UPLOAD SYSTEM (1GB support) =====================

PDF_UPLOAD_DIR = Path(tempfile.gettempdir()) / "pdf_uploads"
PDF_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
PDF_MAX_SIZE = 1000 * 1024 * 1024  # 1000MB = 1GB
PDF_CHUNK_SIZE = 25 * 1024 * 1024  # 25MB per chunk — fewer roundtrips for mobile

class PdfUploadInit(BaseModel):
    batch_id: str
    filename: str
    file_size: int
    total_chunks: int

@api_router.post("/pdf-upload/init")
async def pdf_upload_init(req: PdfUploadInit, user=Depends(get_admin_user)):
    """Initialize a chunked PDF upload session"""
    batch = await db.batches.find_one({"id": req.batch_id}, {"_id": 0})
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    if req.file_size > PDF_MAX_SIZE:
        raise HTTPException(status_code=413, detail=f"PDF file too large ({req.file_size / (1024*1024):.0f}MB). Maximum allowed is 1000MB.")
    if req.file_size < 100:
        raise HTTPException(status_code=400, detail="File is too small to be a valid PDF.")
    if not req.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted. Use 'Upload Images' for JPG/PNG files.")

    upload_id = str(uuid.uuid4())
    upload_dir = PDF_UPLOAD_DIR / upload_id
    upload_dir.mkdir(parents=True, exist_ok=True)

    job = {
        "upload_id": upload_id,
        "batch_id": req.batch_id,
        "filename": req.filename,
        "file_size": req.file_size,
        "total_chunks": req.total_chunks,
        "chunks_received": 0,
        "upload_status": "uploading",  # uploading -> uploaded -> processing -> done -> error
        "process_status": None,
        "total_pages": 0,
        "pages_processed": 0,
        "imported": 0,
        "failed": 0,
        "skipped": 0,
        "error": None,
        "results": [],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "user_id": user.get("id", ""),
    }
    await db.pdf_jobs.insert_one(job)
    logger.info(f"PDF upload init: {upload_id}, file={req.filename}, size={req.file_size/(1024*1024):.1f}MB, chunks={req.total_chunks}")
    return {"upload_id": upload_id, "chunk_size": PDF_CHUNK_SIZE, "status": "ready"}

@api_router.post("/pdf-upload/{upload_id}/chunk")
async def pdf_upload_chunk(
    upload_id: str,
    chunk_index: int = Query(...),
    file: UploadFile = File(...),
    user=Depends(get_admin_user)
):
    """Upload a single chunk of the PDF file"""
    # Retry DB lookup to handle brief disconnects during hot-reload
    job = None
    for attempt in range(3):
        job = await db.pdf_jobs.find_one({"upload_id": upload_id}, {"_id": 0})
        if job:
            break
        if attempt < 2:
            logger.warning(f"PDF chunk: upload_id={upload_id} not found in DB (attempt {attempt+1}/3), retrying...")
            await asyncio.sleep(0.5)
    if not job:
        logger.error(f"PDF chunk: upload_id={upload_id} not found after 3 attempts")
        raise HTTPException(status_code=404, detail=f"Upload session not found (id: {upload_id[:12]}...). Please start a new import.")
    if job["upload_status"] not in ("uploading",):
        raise HTTPException(status_code=400, detail=f"Upload session is in '{job['upload_status']}' state. Cannot accept more chunks.")
    if chunk_index < 0 or chunk_index >= job["total_chunks"]:
        raise HTTPException(status_code=400, detail=f"Invalid chunk index {chunk_index}. Expected 0-{job['total_chunks']-1}.")

    upload_dir = PDF_UPLOAD_DIR / upload_id
    upload_dir.mkdir(parents=True, exist_ok=True)  # Recreate if missing after restart
    chunk_path = upload_dir / f"chunk_{chunk_index:06d}"

    try:
        data = await file.read()
        with open(chunk_path, "wb") as f:
            f.write(data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save chunk {chunk_index}: {str(e)}")

    # Count how many chunks we actually have on disk
    received = len(list(upload_dir.glob("chunk_*")))
    await db.pdf_jobs.update_one(
        {"upload_id": upload_id},
        {"$set": {"chunks_received": received, "updated_at": datetime.now(timezone.utc).isoformat()}}
    )

    return {"chunk_index": chunk_index, "received": received, "total": job["total_chunks"]}

@api_router.post("/pdf-upload/{upload_id}/complete")
async def pdf_upload_complete(upload_id: str, user=Depends(get_admin_user)):
    """Signal that all chunks have been uploaded. Assembles the file and starts background processing."""
    job = await db.pdf_jobs.find_one({"upload_id": upload_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Upload session not found.")
    if job["upload_status"] != "uploading":
        raise HTTPException(status_code=400, detail=f"Upload is in '{job['upload_status']}' state.")

    upload_dir = PDF_UPLOAD_DIR / upload_id
    received = len(list(upload_dir.glob("chunk_*")))
    if received < job["total_chunks"]:
        raise HTTPException(status_code=400, detail=f"Missing chunks: received {received} of {job['total_chunks']}. Upload incomplete.")

    # Assemble chunks into single PDF file
    pdf_path = upload_dir / "full.pdf"
    try:
        with open(pdf_path, "wb") as out:
            for i in range(job["total_chunks"]):
                chunk_file = upload_dir / f"chunk_{i:06d}"
                if not chunk_file.exists():
                    raise HTTPException(status_code=400, detail=f"Chunk {i} is missing. Please re-upload.")
                with open(chunk_file, "rb") as cf:
                    shutil.copyfileobj(cf, out)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to assemble PDF: {str(e)}")

    # Validate assembled file
    assembled_size = pdf_path.stat().st_size
    if assembled_size < 100:
        raise HTTPException(status_code=400, detail="Assembled file is empty or too small.")

    # Quick PDF header check
    with open(pdf_path, "rb") as f:
        header = f.read(5)
    if header != b'%PDF-':
        await db.pdf_jobs.update_one({"upload_id": upload_id}, {"$set": {"upload_status": "error", "error": "Not a valid PDF file. The uploaded file does not have a PDF header."}})
        shutil.rmtree(upload_dir, ignore_errors=True)
        raise HTTPException(status_code=400, detail="Not a valid PDF file. The uploaded file does not have a PDF header. Please ensure you are uploading a .pdf file.")

    await db.pdf_jobs.update_one(
        {"upload_id": upload_id},
        {"$set": {"upload_status": "uploaded", "updated_at": datetime.now(timezone.utc).isoformat()}}
    )

    # Delete chunk files to free disk space (keep only assembled pdf)
    for chunk_file in upload_dir.glob("chunk_*"):
        chunk_file.unlink(missing_ok=True)

    logger.info(f"PDF upload complete: {upload_id}, assembled {assembled_size/(1024*1024):.1f}MB")

    # Start background processing
    asyncio.create_task(_process_pdf_job(upload_id))

    return {"status": "processing", "upload_id": upload_id, "assembled_size_mb": round(assembled_size / (1024 * 1024), 1)}

@api_router.get("/pdf-upload/{upload_id}/status")
async def pdf_upload_status(upload_id: str, user=Depends(get_admin_user)):
    """Get the current status of a PDF upload/processing job"""
    job = await db.pdf_jobs.find_one({"upload_id": upload_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Upload session not found.")
    status = {
        "upload_id": job["upload_id"],
        "batch_id": job["batch_id"],
        "filename": job["filename"],
        "file_size": job["file_size"],
        "upload_status": job["upload_status"],
        "chunks_received": job["chunks_received"],
        "total_chunks": job["total_chunks"],
        "total_pages": job["total_pages"],
        "pages_processed": job["pages_processed"],
        "imported": job["imported"],
        "failed": job["failed"],
        "skipped": job["skipped"],
        "error": job["error"],
    }
    # For uploading state, include which chunk indices exist on disk (for resume)
    if job["upload_status"] == "uploading":
        upload_dir = PDF_UPLOAD_DIR / upload_id
        if upload_dir.exists():
            status["received_chunk_indices"] = sorted([
                int(f.name.split("_")[1]) for f in upload_dir.glob("chunk_*") if f.name.split("_")[1].isdigit()
            ])
        else:
            status["received_chunk_indices"] = []
    # Only include full results when done
    if job["upload_status"] in ("done", "error"):
        status["results"] = job.get("results", [])
    return status

async def _process_pdf_job(upload_id: str):
    """Background task: open assembled PDF, extract pages, create products"""
    try:
        job = await db.pdf_jobs.find_one({"upload_id": upload_id}, {"_id": 0})
        if not job:
            return
        batch = await db.batches.find_one({"id": job["batch_id"]}, {"_id": 0})
        if not batch:
            await db.pdf_jobs.update_one({"upload_id": upload_id}, {"$set": {"upload_status": "error", "error": "Batch not found"}})
            return

        pdf_path = PDF_UPLOAD_DIR / upload_id / "full.pdf"
        if not pdf_path.exists():
            await db.pdf_jobs.update_one({"upload_id": upload_id}, {"$set": {"upload_status": "error", "error": "Assembled PDF file not found on disk"}})
            return

        await db.pdf_jobs.update_one({"upload_id": upload_id}, {"$set": {"upload_status": "processing", "updated_at": datetime.now(timezone.utc).isoformat()}})

        try:
            pdf_doc = fitz.open(str(pdf_path))
        except Exception as e:
            await db.pdf_jobs.update_one({"upload_id": upload_id}, {"$set": {"upload_status": "error", "error": f"Cannot open PDF: {str(e)}. File may be corrupted or password-protected."}})
            shutil.rmtree(PDF_UPLOAD_DIR / upload_id, ignore_errors=True)
            return

        total_pages = len(pdf_doc)
        if total_pages == 0:
            pdf_doc.close()
            await db.pdf_jobs.update_one({"upload_id": upload_id}, {"$set": {"upload_status": "error", "error": "PDF has 0 pages. Document appears empty."}})
            shutil.rmtree(PDF_UPLOAD_DIR / upload_id, ignore_errors=True)
            return

        await db.pdf_jobs.update_one({"upload_id": upload_id}, {"$set": {"total_pages": total_pages}})
        logger.info(f"PDF processing started: {upload_id}, {total_pages} pages, batch={job['batch_id']}")

        results = []
        current_count = batch.get("image_count", 0)
        now = datetime.now(timezone.utc).isoformat()
        imported = 0
        failed = 0
        skipped = 0

        for page_num in range(total_pages):
            try:
                page = pdf_doc[page_num]
                mat = fitz.Matrix(2.0, 2.0)
                pix = page.get_pixmap(matrix=mat, alpha=False)
                img_data = pix.tobytes("jpeg")

                if len(img_data) < 500:
                    results.append({"page": page_num + 1, "status": "skipped", "detail": "Page rendered too small or blank"})
                    skipped += 1
                else:
                    file_id = str(uuid.uuid4())
                    original_data = process_image(img_data, max_size=1600, quality=85)
                    thumb_data = create_thumbnail(img_data, size=400, quality=60)
                    original_path = f"{APP_NAME}/originals/{file_id}.jpg"
                    thumb_path = f"{APP_NAME}/thumbs/{file_id}.jpg"
                    put_object(original_path, original_data, "image/jpeg")
                    put_object(thumb_path, thumb_data, "image/jpeg")

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
                        "original_filename": f"{job['filename']}_page_{page_num + 1}",
                        "file_size": len(img_data),
                        "source_type": "pdf_import",
                        "source_page": page_num + 1,
                        "video_url": "",
                        "approx_weight": "",
                        "stock_status": "in_stock",
                        "tags": [batch.get("metal_type", "silver"), "pdf_import", batch["id"][:8]],
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
                    results.append({"page": page_num + 1, "status": "ok", "id": file_id})
                    imported += 1

                # Update progress every page
                await db.pdf_jobs.update_one(
                    {"upload_id": upload_id},
                    {"$set": {
                        "pages_processed": page_num + 1,
                        "imported": imported,
                        "failed": failed,
                        "skipped": skipped,
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    }}
                )
                if (page_num + 1) % 10 == 0:
                    logger.info(f"PDF processing {upload_id}: {page_num + 1}/{total_pages} pages")

            except Exception as e:
                logger.error(f"PDF page {page_num + 1} error ({upload_id}): {e}")
                results.append({"page": page_num + 1, "status": "error", "detail": str(e)})
                failed += 1

        pdf_doc.close()

        if imported > 0:
            await db.batches.update_one(
                {"id": job["batch_id"]},
                {"$set": {"image_count": current_count, "updated_at": datetime.now(timezone.utc).isoformat()}}
            )

        await db.pdf_jobs.update_one(
            {"upload_id": upload_id},
            {"$set": {
                "upload_status": "done",
                "results": results,
                "imported": imported,
                "failed": failed,
                "skipped": skipped,
                "pages_processed": total_pages,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }}
        )
        logger.info(f"PDF processing done: {upload_id}, imported={imported}, failed={failed}, skipped={skipped}/{total_pages}")

    except Exception as e:
        logger.error(f"PDF processing fatal error ({upload_id}): {e}")
        await db.pdf_jobs.update_one(
            {"upload_id": upload_id},
            {"$set": {"upload_status": "error", "error": f"Processing failed: {str(e)}", "updated_at": datetime.now(timezone.utc).isoformat()}}
        )
    finally:
        # Cleanup temp files
        upload_dir = PDF_UPLOAD_DIR / upload_id
        if upload_dir.exists():
            shutil.rmtree(upload_dir, ignore_errors=True)

# Keep legacy endpoint for backward compatibility (small PDFs)
@api_router.post("/batches/{batch_id}/import-pdf")
async def import_pdf_to_batch(
    batch_id: str,
    file: UploadFile = File(...),
    user=Depends(get_admin_user)
):
    """Legacy: Import a small PDF file directly (for backward compat). Redirects to chunked system internally."""
    batch = await db.batches.find_one({"id": batch_id}, {"_id": 0})
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    chunks = []
    total_size = 0
    max_size = PDF_MAX_SIZE
    try:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            total_size += len(chunk)
            if total_size > max_size:
                raise HTTPException(status_code=413, detail=f"PDF file too large. Maximum size is 1000MB. Your file is {total_size / (1024*1024):.0f}MB.")
            chunks.append(chunk)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error reading uploaded file: {str(e)}")

    data = b''.join(chunks)
    if len(data) < 100:
        raise HTTPException(status_code=400, detail="File is empty or too small to be a valid PDF.")
    if not data[:5] == b'%PDF-':
        raise HTTPException(status_code=400, detail="Not a valid PDF file. Please use 'Upload Images' for image files.")

    try:
        pdf_doc = fitz.open(stream=data, filetype="pdf")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Cannot open PDF. File may be corrupted. Error: {str(e)}")

    total_pages = len(pdf_doc)
    if total_pages == 0:
        pdf_doc.close()
        raise HTTPException(status_code=400, detail="PDF has 0 pages.")

    results = []
    current_count = batch.get("image_count", 0)
    now = datetime.now(timezone.utc).isoformat()

    for page_num in range(total_pages):
        try:
            page = pdf_doc[page_num]
            mat = fitz.Matrix(2.0, 2.0)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            img_data = pix.tobytes("jpeg")
            if len(img_data) < 500:
                results.append({"page": page_num + 1, "status": "skipped", "detail": "Page too small or blank"})
                continue
            file_id = str(uuid.uuid4())
            original_data = process_image(img_data, max_size=1600, quality=85)
            thumb_data = create_thumbnail(img_data, size=400, quality=60)
            original_path = f"{APP_NAME}/originals/{file_id}.jpg"
            thumb_path = f"{APP_NAME}/thumbs/{file_id}.jpg"
            put_object(original_path, original_data, "image/jpeg")
            put_object(thumb_path, thumb_data, "image/jpeg")
            current_count += 1
            product = {
                "id": file_id, "title": f"{batch['name']} #{current_count}", "description": "",
                "metal_type": batch.get("metal_type", "silver"), "category": batch.get("category", ""),
                "subcategory": "", "images": [], "storage_path": original_path, "thumbnail_path": thumb_path,
                "original_filename": f"{file.filename}_page_{page_num + 1}", "file_size": len(img_data),
                "source_type": "pdf_import", "source_page": page_num + 1, "video_url": "", "approx_weight": "",
                "stock_status": "in_stock", "tags": [batch.get("metal_type", "silver"), "pdf_import", batch["id"][:8]],
                "is_pinned": False, "is_new_arrival": True, "is_trending": False,
                "visibility": "all" if batch.get("status") == "visible" else "hidden",
                "post_type": "product", "batch_id": batch["id"], "batch_name": batch["name"],
                "views": 0, "is_deleted": False, "created_at": now, "updated_at": now,
            }
            await db.products.insert_one(product)
            results.append({"page": page_num + 1, "status": "ok", "id": file_id})
        except Exception as e:
            results.append({"page": page_num + 1, "status": "error", "detail": str(e)})

    pdf_doc.close()
    imported = sum(1 for r in results if r["status"] == "ok")
    failed = sum(1 for r in results if r["status"] == "error")
    skipped = sum(1 for r in results if r["status"] == "skipped")
    if imported > 0:
        await db.batches.update_one({"id": batch_id}, {"$set": {"image_count": current_count, "updated_at": datetime.now(timezone.utc).isoformat()}})
    return {
        "message": f"PDF imported: {imported} pages converted to product images",
        "total_pages": total_pages, "imported": imported, "failed": failed, "skipped": skipped,
        "file_size_mb": round(total_size / (1024 * 1024), 1), "results": results,
        "batch_image_count": current_count, "filename": file.filename
    }

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
    handled_by: str = Query(""),
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
    if handled_by:
        query["handled_by_id"] = handled_by
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
    if normalized_status not in CANONICAL_STATUSES:
        raise HTTPException(status_code=422, detail=f"Invalid status '{req.status}'. Allowed: {', '.join(sorted(CANONICAL_STATUSES))}")
    now = datetime.now(timezone.utc).isoformat()
    updates: Dict[str, Any] = {
        "status": normalized_status,
        "updated_at": now,
        # Track which executive handled this
        "handled_by_id": user["id"],
        "handled_by_name": user.get("name", user.get("phone", "")),
        "handled_by_phone": user.get("phone", ""),
        "handled_by_code": user.get("customer_code", ""),
        "last_action_at": now,
    }
    if req.assigned_to:
        updates["assigned_to"] = req.assigned_to
    if req.notes:
        updates["admin_notes"] = req.notes
        # Append to notes history with full executive identity
        note_entry = {
            "note": req.notes,
            "by": user.get("name", user.get("phone", "")),
            "by_id": user["id"],
            "by_phone": user.get("phone", ""),
            "by_code": user.get("customer_code", ""),
            "status": normalized_status,
            "at": now
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
    if req.points <= 0:
        raise HTTPException(status_code=400, detail="Points must be greater than zero")
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
    if req.points <= 0:
        raise HTTPException(status_code=400, detail="Points must be greater than zero")
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
    # Validate product exists and is visible
    product = await db.products.find_one({"id": req.product_id}, {"_id": 0})
    if not product or product.get("is_deleted") or product.get("visibility") == "hidden":
        raise HTTPException(status_code=400, detail="Product not found or unavailable")
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

@api_router.get("/cart/orders")
async def cart_orders(user=Depends(get_current_user)):
    """Get all submitted cart orders for the current user"""
    orders = await db.requests.find(
        {"user_id": user["id"], "request_type": "cart_selection"},
        {"_id": 0}
    ).sort("created_at", -1).limit(50).to_list(50)
    result = []
    for o in orders:
        result.append({
            "id": o.get("id", ""),
            "status": o.get("status", "pending"),
            "item_count": o.get("cart_count", 0),
            "items": o.get("cart_items", []),
            "notes": o.get("notes", ""),
            "created_at": o.get("created_at", ""),
        })
    return {"orders": result}

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
    search: str = Query(""), account_status: str = Query(""),
    login_state: str = Query(""), assigned_to: str = Query(""),
    user=Depends(get_admin_user)
):
    query: Dict[str, Any] = {"role": "customer"}
    if customer_type:
        query["customer_type"] = customer_type
    if city:
        query["city"] = {"$regex": city, "$options": "i"}
    if account_status:
        query["account_status"] = account_status
    if login_state == "never":
        query["has_logged_in"] = {"$ne": True}
    elif login_state == "logged_in":
        query["has_logged_in"] = True
    if assigned_to:
        query["assigned_salesperson"] = assigned_to
    if search:
        query["$or"] = [
            {"phone": {"$regex": search, "$options": "i"}},
            {"name": {"$regex": search, "$options": "i"}},
            {"customer_code": {"$regex": search, "$options": "i"}},
            {"shop_name": {"$regex": search, "$options": "i"}},
            {"location": {"$regex": search, "$options": "i"}}
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
    updates = {k: v for k, v in req.dict().items() if (v or isinstance(v, bool)) and v is not None}
    # assigned_salesperson may legitimately be cleared with an empty string
    if req.assigned_salesperson is not None:
        updates["assigned_salesperson"] = req.assigned_salesperson
    # Keep legacy `status` and canonical `account_status` in sync
    if updates.get("account_status"):
        updates["status"] = updates["account_status"]
    elif updates.get("status"):
        updates["account_status"] = updates["status"]
    if updates.get("location") and not updates.get("city"):
        updates["city"] = updates["location"]
    if updates:
        updates["updated_at"] = datetime.now(timezone.utc).isoformat()
        await db.users.update_one({"id": customer_id}, {"$set": updates})
    return await db.users.find_one({"id": customer_id}, {"_id": 0})

# ===================== TELECALLER CRM =====================

TELECALLER_STATUSES = ["new", "contacted", "interested", "follow_up_required", "converted", "not_interested", "unable_to_reach"]

async def get_telecaller_user(user=Depends(get_current_user)):
    if user.get("role") not in ("executive", "admin"):
        raise HTTPException(status_code=403, detail="Telecaller access required")
    return user

def _telecaller_scope(user: Dict[str, Any]) -> Dict[str, Any]:
    """Telecallers only see customers assigned to them; admins see all."""
    query: Dict[str, Any] = {"role": "customer"}
    if user.get("role") != "admin":
        query["assigned_salesperson"] = user["id"]
    return query

@api_router.get("/telecaller/customers")
async def telecaller_customers(
    page: int = Query(1, ge=1), limit: int = Query(20, ge=1, le=100),
    search: str = Query(""), lead_status: str = Query(""),
    user=Depends(get_telecaller_user)
):
    query = _telecaller_scope(user)
    if lead_status:
        if lead_status == "new":
            query["$and"] = [{"$or": [{"lead_status": "new"}, {"lead_status": {"$exists": False}}]}]
        else:
            query["lead_status"] = lead_status
    if search:
        search_or = [
            {"name": {"$regex": search, "$options": "i"}},
            {"phone": {"$regex": search, "$options": "i"}},
            {"shop_name": {"$regex": search, "$options": "i"}},
            {"location": {"$regex": search, "$options": "i"}}
        ]
        if "$and" in query:
            query["$and"].append({"$or": search_or})
        else:
            query["$or"] = search_or
    skip = (page - 1) * limit
    total = await db.users.count_documents(query)
    customers = await db.users.find(
        query,
        {"_id": 0, "id": 1, "name": 1, "phone": 1, "shop_name": 1, "location": 1, "city": 1,
         "lead_status": 1, "follow_up_at": 1, "telecaller_last_note": 1, "lead_updated_at": 1,
         "has_logged_in": 1, "last_login_at": 1, "account_status": 1, "customer_code": 1}
    ).sort([("lead_updated_at", -1), ("created_at", -1)]).skip(skip).limit(limit).to_list(limit)
    return {"customers": customers, "total": total, "page": page, "pages": (total + limit - 1) // limit}

@api_router.post("/telecaller/customers/{customer_id}/action")
async def telecaller_action(customer_id: str, req: TelecallerAction, user=Depends(get_telecaller_user)):
    customer = await db.users.find_one({"id": customer_id, "role": "customer"}, {"_id": 0})
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    if user.get("role") != "admin" and customer.get("assigned_salesperson") != user["id"]:
        raise HTTPException(status_code=403, detail="This customer is not assigned to you")
    if req.action not in ("status_change", "note", "call", "whatsapp", "follow_up"):
        raise HTTPException(status_code=422, detail="Invalid action")
    if req.new_status and req.new_status not in TELECALLER_STATUSES:
        raise HTTPException(status_code=422, detail=f"Status must be one of: {', '.join(TELECALLER_STATUSES)}")
    now = datetime.now(timezone.utc).isoformat()
    prev_status = customer.get("lead_status", "new")
    updates: Dict[str, Any] = {"lead_updated_at": now}
    if req.new_status:
        updates["lead_status"] = req.new_status
    if req.follow_up_at:
        updates["follow_up_at"] = req.follow_up_at
    if req.notes:
        updates["telecaller_last_note"] = req.notes
    await db.users.update_one({"id": customer_id}, {"$set": updates})
    activity = {
        "id": str(uuid.uuid4()),
        "telecaller_id": user["id"],
        "telecaller_name": user.get("name", ""),
        "customer_id": customer_id,
        "customer_name": customer.get("name", ""),
        "action": req.action,
        "notes": req.notes,
        "previous_status": prev_status,
        "new_status": req.new_status or prev_status,
        "follow_up_at": req.follow_up_at,
        "created_at": now,
    }
    await db.telecaller_activity.insert_one(activity)
    fresh = await db.users.find_one({"id": customer_id}, {"_id": 0})
    return {"customer": fresh, "activity": {k: v for k, v in activity.items() if k != "_id"}}

@api_router.get("/telecaller/customers/{customer_id}/activity")
async def telecaller_activity(customer_id: str, user=Depends(get_telecaller_user)):
    customer = await db.users.find_one({"id": customer_id, "role": "customer"}, {"_id": 0, "id": 1, "assigned_salesperson": 1})
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    if user.get("role") != "admin" and customer.get("assigned_salesperson") != user["id"]:
        raise HTTPException(status_code=403, detail="This customer is not assigned to you")
    activities = await db.telecaller_activity.find(
        {"customer_id": customer_id}, {"_id": 0}
    ).sort("created_at", -1).to_list(100)
    return {"activities": activities}

@api_router.get("/telecaller/summary")
async def telecaller_summary(user=Depends(get_telecaller_user)):
    base = _telecaller_scope(user)
    total = await db.users.count_documents(base)
    by_status: Dict[str, int] = {}
    for st in TELECALLER_STATUSES:
        q = dict(base)
        if st == "new":
            q["$or"] = [{"lead_status": "new"}, {"lead_status": {"$exists": False}}]
        else:
            q["lead_status"] = st
        by_status[st] = await db.users.count_documents(q)
    today = datetime.now(timezone.utc).date().isoformat()
    q_due = dict(base)
    q_due["follow_up_at"] = {"$gt": "", "$lte": f"{today}T23:59:59"}
    follow_ups_due = await db.users.count_documents(q_due)
    act_query: Dict[str, Any] = {"created_at": {"$gte": f"{today}T00:00:00"}}
    if user.get("role") != "admin":
        act_query["telecaller_id"] = user["id"]
    actions_today = await db.telecaller_activity.count_documents(act_query)
    return {"total_customers": total, "by_status": by_status, "follow_ups_due": follow_ups_due, "actions_today": actions_today}

# ===================== EXECUTIVE MANAGEMENT =====================

@api_router.post("/executives")
async def create_executive(req: ExecutiveCreate, user=Depends(get_admin_user)):
    """Admin creates a new executive/telecaller user."""
    phone = req.phone.strip()
    if len(phone) < 10:
        raise HTTPException(status_code=400, detail="Invalid phone number")
    if req.role not in ("executive", "billing_executive"):
        raise HTTPException(status_code=400, detail="Role must be executive or billing_executive")
    existing = await db.users.find_one({"phone": phone}, {"_id": 0})
    if existing:
        if existing.get("role") in ("executive", "billing_executive"):
            raise HTTPException(status_code=400, detail=f"An executive with phone {phone} already exists")
        # Upgrade existing customer to executive
        await db.users.update_one({"phone": phone}, {"$set": {
            "name": req.name, "customer_code": req.code, "role": req.role,
            "customer_type": req.role, "status": "active",
            "updated_at": datetime.now(timezone.utc).isoformat()
        }})
        updated = await db.users.find_one({"phone": phone}, {"_id": 0})
        return updated
    exec_user = {
        "id": str(uuid.uuid4()), "phone": phone, "name": req.name,
        "city": "", "customer_code": req.code, "customer_type": req.role,
        "role": req.role, "category_interests": [], "is_eligible_rewards": False,
        "assigned_salesperson": "", "status": "active", "reward_points": 0,
        "is_new": False, "created_at": datetime.now(timezone.utc).isoformat(),
        "last_login": datetime.now(timezone.utc).isoformat()
    }
    await db.users.insert_one(exec_user)
    return {k: v for k, v in exec_user.items() if k != "_id"}

@api_router.get("/executives")
async def list_executives(user=Depends(get_admin_user)):
    """List all executive and billing_executive users."""
    execs = await db.users.find(
        {"role": {"$in": ["executive", "billing_executive"]}, "status": {"$ne": "disabled"}},
        {"_id": 0}
    ).sort("name", 1).to_list(100)
    return {"executives": execs}

@api_router.put("/executives/{exec_id}")
async def update_executive(exec_id: str, updates: Dict[str, Any], user=Depends(get_admin_user)):
    """Admin updates executive details (name, code, role, status)."""
    existing = await db.users.find_one({"id": exec_id}, {"_id": 0})
    if not existing or existing.get("role") not in ("executive", "billing_executive"):
        raise HTTPException(status_code=404, detail="Executive not found")
    allowed = {"name", "customer_code", "role", "status", "city", "phone"}
    filtered = {k: v for k, v in updates.items() if k in allowed and v is not None}
    if "role" in filtered and filtered["role"] not in ("executive", "billing_executive"):
        raise HTTPException(status_code=400, detail="Role must be executive or billing_executive")
    if filtered:
        filtered["updated_at"] = datetime.now(timezone.utc).isoformat()
        if "role" in filtered:
            filtered["customer_type"] = filtered["role"]
        if "status" in filtered:
            filtered["account_status"] = filtered["status"]
        await db.users.update_one({"id": exec_id}, {"$set": filtered})
    return await db.users.find_one({"id": exec_id}, {"_id": 0})

@api_router.delete("/executives/{exec_id}")
async def disable_executive(exec_id: str, user=Depends(get_admin_user)):
    """Disable an executive (soft delete)."""
    existing = await db.users.find_one({"id": exec_id}, {"_id": 0})
    if not existing or existing.get("role") not in ("executive", "billing_executive"):
        raise HTTPException(status_code=404, detail="Executive not found")
    await db.users.update_one({"id": exec_id}, {"$set": {"status": "disabled", "account_status": "disabled", "updated_at": datetime.now(timezone.utc).isoformat()}})
    return {"message": f"Executive {existing.get('name', '')} disabled"}

@api_router.get("/executives/performance")
async def executive_performance(user=Depends(get_admin_user)):
    """Get request handling stats per executive."""
    execs = await db.users.find(
        {"role": {"$in": ["executive", "billing_executive"]}, "status": {"$ne": "disabled"}},
        {"_id": 0, "id": 1, "name": 1, "phone": 1, "customer_code": 1, "role": 1}
    ).to_list(100)
    result = []
    for e in execs:
        total = await db.requests.count_documents({"handled_by_id": e["id"]})
        resolved = await db.requests.count_documents({"handled_by_id": e["id"], "status": "resolved"})
        result.append({
            "id": e["id"], "name": e["name"], "phone": e["phone"], "code": e.get("customer_code", ""),
            "role": e["role"], "total_handled": total, "resolved": resolved
        })
    return {"executives": result}

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

    # One-time backfill: website-parity fields on existing user records
    await db.users.update_many(
        {"account_status": {"$exists": False}},
        [{"$set": {
            "account_status": {"$ifNull": ["$status", "active"]},
            "shop_name": {"$ifNull": ["$shop_name", ""]},
            "location": {"$ifNull": ["$location", {"$ifNull": ["$city", ""]}]},
            "phone_verified": {"$ifNull": ["$phone_verified", True]},
            "onboarding_status": {"$ifNull": ["$onboarding_status", "completed"]},
            "registration_source": {"$ifNull": ["$registration_source", "app"]},
            "registered_at": {"$ifNull": ["$registered_at", "$created_at"]},
            "has_logged_in": {"$ifNull": ["$has_logged_in", {"$toBool": {"$ifNull": ["$last_login", False]}}]},
            "first_login_at": {"$ifNull": ["$first_login_at", {"$ifNull": ["$last_login", ""]}]},
            "last_login_at": {"$ifNull": ["$last_login_at", {"$ifNull": ["$last_login", ""]}]},
            "lead_status": {"$ifNull": ["$lead_status", "new"]},
        }}]
    )

    # Demo website-registered customers (dev/staging only — same shape the enrollment website creates)
    exec_user = await db.users.find_one({"phone": "7777777777"}, {"_id": 0, "id": 1})
    exec_id = exec_user["id"] if exec_user else ""
    now = datetime.now(timezone.utc).isoformat()
    for phone, name, shop, loc, acct in [
        ("8888800001", "Suresh Verma", "Verma Jewellers", "Ludhiana", "active"),
        ("8888800002", "Inactive Tester", "Old Shop", "Amritsar", "inactive"),
    ]:
        if not await db.users.find_one({"phone": phone}):
            await db.users.insert_one({
                "id": str(uuid.uuid4()), "phone": phone, "name": name,
                "shop_name": shop, "location": loc, "city": loc,
                "customer_code": f"AA{phone[-4:]}", "customer_type": "retailer",
                "role": "customer", "category_interests": [],
                "is_eligible_rewards": True,
                "assigned_salesperson": exec_id if acct == "active" else "",
                "status": acct, "account_status": acct,
                "phone_verified": True, "onboarding_status": "completed",
                "has_logged_in": False, "first_login_at": "", "last_login_at": "",
                "registration_source": "website", "registered_at": now,
                "lead_status": "new", "reward_points": 0, "is_new": True,
                "created_at": now,
            })
    # Assign the main demo customer to the demo executive for telecaller testing
    if exec_id:
        await db.users.update_one(
            {"phone": "8888888888", "assigned_salesperson": {"$in": ["", None]}},
            {"$set": {"assigned_salesperson": exec_id}}
        )
    await db.telecaller_activity.create_index([("customer_id", 1), ("created_at", -1)])
    await db.telecaller_activity.create_index([("telecaller_id", 1), ("created_at", -1)])
    await db.users.create_index([("assigned_salesperson", 1)])

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

# ===================== ABOUT CONTENT MANAGEMENT =====================

@api_router.get("/about")
async def get_about_content(lang: str = Query("en")):
    sections = await db.about_content.find({}, {"_id": 0}).sort("order", 1).to_list(100)
    result = []
    for s in sections:
        content = s.get(f"content_{lang}") or s.get("content_en", "")
        result.append({"section": s.get("section", ""), "content": content, "order": s.get("order", 0)})
    return {"sections": result, "raw": sections}

@api_router.post("/about")
async def upsert_about_content(req: AboutContentUpdate, user=Depends(get_admin_user)):
    now = datetime.now(timezone.utc).isoformat()
    existing = await db.about_content.find_one({"section": req.section})
    data = req.dict()
    data["updated_at"] = now
    if existing:
        await db.about_content.update_one({"section": req.section}, {"$set": data})
    else:
        data["id"] = str(uuid.uuid4())
        data["order"] = 0
        data["created_at"] = now
        await db.about_content.insert_one(data)
    result = await db.about_content.find_one({"section": req.section}, {"_id": 0})
    return result

@api_router.delete("/about/{section}")
async def delete_about_section(section: str, user=Depends(get_admin_user)):
    await db.about_content.delete_one({"section": section})
    return {"message": "Deleted"}

# ===================== RATE LIST MANAGEMENT =====================

@api_router.get("/rate-list")
async def get_rate_list(metal_type: str = Query("")):
    query: Dict[str, Any] = {}
    if metal_type:
        query["metal_type"] = metal_type
    slabs = await db.rate_slabs.find(query, {"_id": 0}).sort([("metal_type", 1), ("order", 1)]).to_list(200)
    return {"slabs": slabs}

@api_router.post("/rate-list")
async def create_rate_slab(req: RateSlabCreate, user=Depends(get_admin_user)):
    now = datetime.now(timezone.utc).isoformat()
    slab = {"id": str(uuid.uuid4()), **req.dict(), "created_at": now, "updated_at": now}
    await db.rate_slabs.insert_one(slab)
    return {k: v for k, v in slab.items() if k != "_id"}

@api_router.put("/rate-list/{slab_id}")
async def update_rate_slab(slab_id: str, updates: Dict[str, Any], user=Depends(get_admin_user)):
    updates.pop("_id", None)
    updates.pop("id", None)
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.rate_slabs.update_one({"id": slab_id}, {"$set": updates})
    return await db.rate_slabs.find_one({"id": slab_id}, {"_id": 0})

@api_router.delete("/rate-list/{slab_id}")
async def delete_rate_slab(slab_id: str, user=Depends(get_admin_user)):
    await db.rate_slabs.delete_one({"id": slab_id})
    return {"message": "Deleted"}

# ===================== SCHEMES MANAGEMENT =====================

@api_router.get("/schemes")
async def get_schemes(active_only: bool = Query(True)):
    query: Dict[str, Any] = {}
    if active_only:
        query["is_active"] = True
    schemes = await db.schemes.find(query, {"_id": 0}).sort("order", 1).to_list(100)
    return {"schemes": schemes}

@api_router.post("/schemes")
async def create_scheme(req: SchemeCreate, user=Depends(get_admin_user)):
    now = datetime.now(timezone.utc).isoformat()
    scheme = {"id": str(uuid.uuid4()), **req.dict(), "created_at": now, "updated_at": now}
    await db.schemes.insert_one(scheme)
    return {k: v for k, v in scheme.items() if k != "_id"}

@api_router.put("/schemes/{scheme_id}")
async def update_scheme(scheme_id: str, updates: Dict[str, Any], user=Depends(get_admin_user)):
    updates.pop("_id", None)
    updates.pop("id", None)
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.schemes.update_one({"id": scheme_id}, {"$set": updates})
    return await db.schemes.find_one({"id": scheme_id}, {"_id": 0})

@api_router.delete("/schemes/{scheme_id}")
async def delete_scheme(scheme_id: str, user=Depends(get_admin_user)):
    await db.schemes.delete_one({"id": scheme_id})
    return {"message": "Deleted"}

# ===================== BRANDS MANAGEMENT =====================

@api_router.get("/brands")
async def get_brands(active_only: bool = Query(True)):
    query: Dict[str, Any] = {}
    if active_only:
        query["is_active"] = True
    brands = await db.brands.find(query, {"_id": 0}).sort("order", 1).to_list(100)
    return {"brands": brands}

@api_router.post("/brands")
async def create_brand(req: BrandCreate, user=Depends(get_admin_user)):
    now = datetime.now(timezone.utc).isoformat()
    brand = {"id": str(uuid.uuid4()), **req.dict(), "created_at": now, "updated_at": now}
    await db.brands.insert_one(brand)
    return {k: v for k, v in brand.items() if k != "_id"}

@api_router.put("/brands/{brand_id}")
async def update_brand(brand_id: str, updates: Dict[str, Any], user=Depends(get_admin_user)):
    updates.pop("_id", None)
    updates.pop("id", None)
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.brands.update_one({"id": brand_id}, {"$set": updates})
    return await db.brands.find_one({"id": brand_id}, {"_id": 0})

@api_router.delete("/brands/{brand_id}")
async def delete_brand(brand_id: str, user=Depends(get_admin_user)):
    await db.brands.delete_one({"id": brand_id})
    return {"message": "Deleted"}

# ===================== SHOWROOM MANAGEMENT =====================

@api_router.get("/showroom")
async def get_showroom():
    floors = await db.showroom_floors.find({}, {"_id": 0}).sort("order", 1).to_list(100)
    return {"floors": floors}

@api_router.post("/showroom")
async def create_showroom_floor(req: ShowroomFloorCreate, user=Depends(get_admin_user)):
    now = datetime.now(timezone.utc).isoformat()
    floor = {"id": str(uuid.uuid4()), **req.dict(), "created_at": now, "updated_at": now}
    await db.showroom_floors.insert_one(floor)
    return {k: v for k, v in floor.items() if k != "_id"}

@api_router.put("/showroom/{floor_id}")
async def update_showroom_floor(floor_id: str, updates: Dict[str, Any], user=Depends(get_admin_user)):
    updates.pop("_id", None)
    updates.pop("id", None)
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.showroom_floors.update_one({"id": floor_id}, {"$set": updates})
    return await db.showroom_floors.find_one({"id": floor_id}, {"_id": 0})

@api_router.delete("/showroom/{floor_id}")
async def delete_showroom_floor(floor_id: str, user=Depends(get_admin_user)):
    await db.showroom_floors.delete_one({"id": floor_id})
    return {"message": "Deleted"}

# ===================== EXHIBITION MANAGEMENT =====================

@api_router.get("/exhibitions")
async def get_exhibitions():
    exhbs = await db.exhibitions.find({"is_active": True}, {"_id": 0}).sort("created_at", -1).to_list(50)
    upcoming = [e for e in exhbs if e.get("is_upcoming")]
    past = [e for e in exhbs if not e.get("is_upcoming")]
    return {"upcoming": upcoming, "past": past, "all": exhbs}

@api_router.post("/exhibitions")
async def create_exhibition(req: ExhibitionCreate, user=Depends(get_admin_user)):
    now = datetime.now(timezone.utc).isoformat()
    exhb = {"id": str(uuid.uuid4()), **req.dict(), "created_at": now, "updated_at": now}
    await db.exhibitions.insert_one(exhb)
    return {k: v for k, v in exhb.items() if k != "_id"}

@api_router.put("/exhibitions/{exhb_id}")
async def update_exhibition(exhb_id: str, updates: Dict[str, Any], user=Depends(get_admin_user)):
    updates.pop("_id", None)
    updates.pop("id", None)
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.exhibitions.update_one({"id": exhb_id}, {"$set": updates})
    return await db.exhibitions.find_one({"id": exhb_id}, {"_id": 0})

@api_router.delete("/exhibitions/{exhb_id}")
async def delete_exhibition(exhb_id: str, user=Depends(get_admin_user)):
    await db.exhibitions.delete_one({"id": exhb_id})
    return {"message": "Deleted"}

# ===================== BANNERS MANAGEMENT =====================

@api_router.get("/banners")
async def get_banners():
    """Public: active banners in display order, within date window if set."""
    today = datetime.now(timezone.utc).date().isoformat()
    banners = await db.banners.find({"is_active": True}, {"_id": 0}).sort("order", 1).to_list(50)
    visible = [
        b for b in banners
        if (not b.get("start_date") or b["start_date"][:10] <= today)
        and (not b.get("end_date") or b["end_date"][:10] >= today)
    ]
    return {"banners": visible}

@api_router.get("/banners/all")
async def get_all_banners(user=Depends(get_admin_user)):
    banners = await db.banners.find({}, {"_id": 0}).sort("order", 1).to_list(100)
    return {"banners": banners}

@api_router.post("/banners")
async def create_banner(req: BannerCreate, user=Depends(get_admin_user)):
    if not req.title.strip():
        raise HTTPException(status_code=422, detail="Banner title is required")
    now = datetime.now(timezone.utc).isoformat()
    banner = {"id": str(uuid.uuid4()), **req.dict(), "created_at": now, "updated_at": now}
    await db.banners.insert_one(banner)
    return {k: v for k, v in banner.items() if k != "_id"}

@api_router.put("/banners/{banner_id}")
async def update_banner(banner_id: str, updates: Dict[str, Any], user=Depends(get_admin_user)):
    existing = await db.banners.find_one({"id": banner_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Banner not found")
    updates.pop("_id", None)
    updates.pop("id", None)
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.banners.update_one({"id": banner_id}, {"$set": updates})
    return await db.banners.find_one({"id": banner_id}, {"_id": 0})

@api_router.delete("/banners/{banner_id}")
async def delete_banner(banner_id: str, user=Depends(get_admin_user)):
    result = await db.banners.delete_one({"id": banner_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Banner not found")
    return {"message": "Deleted"}

@api_router.post("/banners/upload")
async def upload_banner_image(file: UploadFile = File(...), user=Depends(get_admin_user)):
    """Upload a banner image to object storage. Returns the served URL."""
    data = await file.read()
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Image too large (max 10MB)")
    if len(data) < 100:
        raise HTTPException(status_code=400, detail="File is empty or too small")
    try:
        processed = process_image(data, max_size=1600, quality=85)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid image file. Use JPG, PNG or WebP.")
    file_id = str(uuid.uuid4())
    path = f"{APP_NAME}/banners/{file_id}.jpg"
    put_object(path, processed, "image/jpeg")
    return {"image_url": f"/api/files/{path}", "storage_path": path}

# ===================== SEED ABOUT/DEMO DATA =====================

async def seed_new_features():
    """Seed initial data for new features"""
    # About content
    about_exists = await db.about_content.count_documents({})
    if about_exists == 0:
        about_sections = [
            {"section": "brand_intro", "content_en": "Yash Ornaments is one of the leading wholesale jewellery houses based in Chandni Chowk, Delhi. With decades of experience in silver, gold, and diamond jewellery, we serve over 40,000 retailers and wholesalers across India.", "content_hi": "यश ऑर्नामेंट्स चांदनी चौक, दिल्ली में स्थित अग्रणी थोक ज्वेलरी हाउस में से एक है। चांदी, सोना और हीरे के आभूषणों में दशकों के अनुभव के साथ, हम पूरे भारत में 40,000 से अधिक खुदरा विक्रेताओं और थोक विक्रेताओं की सेवा करते हैं।", "content_pa": "ਯਸ਼ ਔਰਨਾਮੈਂਟਸ ਚਾਂਦਨੀ ਚੌਕ, ਦਿੱਲੀ ਵਿੱਚ ਸਥਿਤ ਮੋਹਰੀ ਥੋਕ ਗਹਿਣਿਆਂ ਦੇ ਘਰਾਂ ਵਿੱਚੋਂ ਇੱਕ ਹੈ।", "order": 1},
            {"section": "why_buy", "content_en": "One Stop Shop|Accuracy in Purity|Fast Billing|Online Live Video Calling|India's Biggest Online Jewellery Catalogue|Cheapest Rate Guaranteed|Compulsory Gift|Original Brand Guaranteed|Sunday Open", "content_hi": "वन स्टॉप शॉप|शुद्धता में सटीकता|तेज बिलिंग|ऑनलाइन लाइव वीडियो कॉलिंग|भारत का सबसे बड़ा ऑनलाइन ज्वेलरी कैटलॉग|सबसे सस्ती दर की गारंटी|अनिवार्य उपहार|ओरिजिनल ब्रांड की गारंटी|रविवार खुला", "content_pa": "ਵਨ ਸਟਾਪ ਸ਼ਾਪ|ਸ਼ੁੱਧਤਾ ਵਿੱਚ ਸਟੀਕਤਾ|ਤੇਜ਼ ਬਿਲਿੰਗ|ਔਨਲਾਈਨ ਲਾਈਵ ਵੀਡੀਓ ਕਾਲਿੰਗ|ਭਾਰਤ ਦਾ ਸਭ ਤੋਂ ਵੱਡਾ ਔਨਲਾਈਨ ਗਹਿਣਿਆਂ ਦਾ ਕੈਟਾਲਾਗ|ਸਭ ਤੋਂ ਸਸਤੀ ਦਰ ਦੀ ਗਾਰੰਟੀ|ਲਾਜ਼ਮੀ ਤੋਹਫ਼ਾ|ਅਸਲ ਬ੍ਰਾਂਡ ਦੀ ਗਾਰੰਟੀ|ਐਤਵਾਰ ਖੁੱਲ੍ਹਾ", "order": 2},
            {"section": "new_shop_benefits", "content_en": "Full Range ki Guarantee|Latest Running Range ki Guarantee|0% Dead Stock|Market ki Knowledge", "content_hi": "फुल रेंज की गारंटी|लेटेस्ट रनिंग रेंज की गारंटी|0% डेड स्टॉक|मार्केट की नॉलेज", "content_pa": "ਫੁੱਲ ਰੇਂਜ ਦੀ ਗਾਰੰਟੀ|ਲੇਟੈਸਟ ਰਨਿੰਗ ਰੇਂਜ ਦੀ ਗਾਰੰਟੀ|0% ਡੈੱਡ ਸਟਾਕ|ਮਾਰਕੀਟ ਦੀ ਨਾਲੇਜ", "order": 3},
            {"section": "b2b_benefits", "content_en": "Wide Product Variety across Silver, Gold & Diamond|Reliable Supply Chain with Pan-India Delivery|Dedicated Retailer Support Team|Fast Service & Quick Turnaround|Repeat Stock Availability Guaranteed|Strong Long-term Business Relationships|Deep Range in Every Category|Trend-Based Stock Support & Market Insights", "content_hi": "चांदी, सोना और हीरे में व्यापक उत्पाद विविधता|पैन-इंडिया डिलीवरी के साथ विश्वसनीय आपूर्ति श्रृंखला|समर्पित रिटेलर सपोर्ट टीम|तेज सेवा और त्वरित टर्नअराउंड|रिपीट स्टॉक उपलब्धता की गारंटी|मजबूत दीर्घकालिक व्यापारिक संबंध|हर श्रेणी में गहरी रेंज|ट्रेंड-आधारित स्टॉक सपोर्ट और मार्केट इनसाइट्स", "content_pa": "ਚਾਂਦੀ, ਸੋਨੇ ਅਤੇ ਹੀਰੇ ਵਿੱਚ ਵਿਆਪਕ ਉਤਪਾਦ ਵਿਭਿੰਨਤਾ|ਭਰੋਸੇਯੋਗ ਸਪਲਾਈ ਚੇਨ|ਸਮਰਪਿਤ ਰਿਟੇਲਰ ਸਪੋਰਟ ਟੀਮ|ਤੇਜ਼ ਸੇਵਾ|ਰਿਪੀਟ ਸਟਾਕ ਦੀ ਗਾਰੰਟੀ|ਮਜ਼ਬੂਤ ਕਾਰੋਬਾਰੀ ਰਿਸ਼ਤੇ|ਹਰ ਸ਼੍ਰੇਣੀ ਵਿੱਚ ਡੂੰਘੀ ਰੇਂਜ|ਟ੍ਰੈਂਡ-ਅਧਾਰਿਤ ਸਟਾਕ ਸਪੋਰਟ", "order": 4},
            {"section": "location_chandni_chowk", "content_en": "Chandni Chowk Showroom|4168, Dariba Kalan, Chandni Chowk, Delhi - 110006|Near Jain Mandir, Old Delhi|Open: Mon-Sat 10:00 AM - 8:00 PM, Sunday 11:00 AM - 6:00 PM|Phone: +91-11-4056XXXX", "content_hi": "चांदनी चौक शोरूम|4168, दरीबा कलां, चांदनी चौक, दिल्ली - 110006|जैन मंदिर के पास, पुरानी दिल्ली|खुला: सोम-शनि सुबह 10:00 बजे - शाम 8:00 बजे, रविवार सुबह 11:00 बजे - शाम 6:00 बजे", "content_pa": "ਚਾਂਦਨੀ ਚੌਕ ਸ਼ੋਅਰੂਮ|4168, ਦਰੀਬਾ ਕਲਾਂ, ਚਾਂਦਨੀ ਚੌਕ, ਦਿੱਲੀ - 110006|ਜੈਨ ਮੰਦਿਰ ਕੋਲ, ਪੁਰਾਣੀ ਦਿੱਲੀ", "order": 5},
            {"section": "location_karol_bagh", "content_en": "Karol Bagh Office|WZ-XX, Karol Bagh, New Delhi - 110005|Near Metro Station, Karol Bagh|Open: Mon-Sat 10:00 AM - 7:00 PM|Phone: +91-11-2573XXXX", "content_hi": "करोल बाग कार्यालय|WZ-XX, करोल बाग, नई दिल्ली - 110005|मेट्रो स्टेशन के पास, करोल बाग|खुला: सोम-शनि सुबह 10:00 बजे - शाम 7:00 बजे", "content_pa": "ਕਰੋਲ ਬਾਗ ਦਫ਼ਤਰ|WZ-XX, ਕਰੋਲ ਬਾਗ, ਨਵੀਂ ਦਿੱਲੀ - 110005|ਮੈਟਰੋ ਸਟੇਸ਼ਨ ਕੋਲ, ਕਰੋਲ ਬਾਗ", "order": 6},
        ]
        for s in about_sections:
            s["id"] = str(uuid.uuid4())
            s["created_at"] = datetime.now(timezone.utc).isoformat()
            s["updated_at"] = datetime.now(timezone.utc).isoformat()
        await db.about_content.insert_many(about_sections)

    # Rate slabs
    slabs_exist = await db.rate_slabs.count_documents({})
    # Drop old quantity-slab data and reseed with item-wise structure
    old_style = await db.rate_slabs.find_one({"slab_name": {"$exists": True}})
    if old_style:
        await db.rate_slabs.delete_many({})
        slabs_exist = 0
    if slabs_exist == 0:
        slabs = [
            {"metal_type": "silver", "item_name": "Silver Payal (Anklet)", "category": "Payal", "subcategory": "Bridal", "purity": "92.5%", "wastage": "3%", "labour_kg": "₹850/kg", "order": 1},
            {"metal_type": "silver", "item_name": "Silver Chain", "category": "Chain", "subcategory": "Italian", "purity": "92.5%", "wastage": "2.5%", "labour_kg": "₹750/kg", "order": 2},
            {"metal_type": "silver", "item_name": "Silver Kada (Bangle)", "category": "Kada", "subcategory": "Heavy", "purity": "92.5%", "wastage": "2%", "labour_kg": "₹600/kg", "order": 3},
            {"metal_type": "silver", "item_name": "Silver Articles (Pooja)", "category": "Articles", "subcategory": "Pooja Set", "purity": "92.5%", "wastage": "3%", "labour_kg": "₹900/kg", "order": 4},
            {"metal_type": "silver", "item_name": "Silver Coin", "category": "Coins", "subcategory": "Gifting", "purity": "99.9%", "wastage": "0%", "labour_kg": "₹200/kg", "order": 5},
            {"metal_type": "silver", "item_name": "Silver Toe Ring", "category": "Toe Ring", "subcategory": "Traditional", "purity": "92.5%", "wastage": "2%", "labour_kg": "₹1200/kg", "order": 6},
            {"metal_type": "gold", "item_name": "Gold Necklace Set", "category": "Necklace", "subcategory": "Bridal", "purity": "22K (91.6%)", "wastage": "5%", "labour_kg": "₹3500/10g", "order": 1},
            {"metal_type": "gold", "item_name": "Gold Bangles", "category": "Bangles", "subcategory": "Meenakari", "purity": "22K (91.6%)", "wastage": "4%", "labour_kg": "₹2800/10g", "order": 2},
            {"metal_type": "gold", "item_name": "Gold Earrings", "category": "Earrings", "subcategory": "Jhumka", "purity": "18K (75%)", "wastage": "6%", "labour_kg": "₹4000/10g", "order": 3},
            {"metal_type": "diamond", "item_name": "Diamond Solitaire Ring", "category": "Ring", "subcategory": "Solitaire", "purity": "VS1-VS2", "wastage": "N/A", "labour_kg": "Per piece", "order": 1},
            {"metal_type": "diamond", "item_name": "Diamond Tennis Bracelet", "category": "Bracelet", "subcategory": "Tennis", "purity": "SI1-SI2", "wastage": "N/A", "labour_kg": "Per piece", "order": 2},
        ]
        for sl in slabs:
            sl["id"] = str(uuid.uuid4())
            sl["created_at"] = datetime.now(timezone.utc).isoformat()
            sl["updated_at"] = datetime.now(timezone.utc).isoformat()
        await db.rate_slabs.insert_many(slabs)

    # Create indexes for new collections
    await db.about_content.create_index([("section", 1)], unique=True)
    await db.rate_slabs.create_index([("metal_type", 1), ("order", 1)])
    await db.schemes.create_index([("order", 1)])
    await db.brands.create_index([("order", 1)])
    await db.showroom_floors.create_index([("order", 1)])
    await db.exhibitions.create_index([("is_upcoming", -1), ("created_at", -1)])
    await db.banners.create_index([("order", 1)])
    await db.pdf_jobs.create_index([("upload_id", 1)], unique=True)

# ===================== APP SETUP =====================

app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=CORS_ORIGINS or ["*"],
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
    try:
        await seed_new_features()
        logger.info("New features seeded")
    except Exception as e:
        logger.warning(f"New features seed: {e}")
    # Cart cleanup: remove rows with quantity <= 0 or orphaned products
    try:
        bad_qty = await db.cart.delete_many({"quantity": {"$lte": 0}})
        if bad_qty.deleted_count > 0:
            logger.info(f"Cart cleanup: removed {bad_qty.deleted_count} rows with invalid quantity")
    except Exception as e:
        logger.warning(f"Cart cleanup: {e}")

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
