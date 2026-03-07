from fastapi import FastAPI, APIRouter, Depends, HTTPException, Query, Header
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import uuid
from datetime import datetime, timezone
import jwt
import asyncio

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
    stock_status: str = "in_stock"
    tags: List[str] = []
    is_pinned: bool = False
    is_new_arrival: bool = True
    is_trending: bool = False
    visibility: str = "all"
    post_type: str = "product"

class RateUpdate(BaseModel):
    silver_rate: float
    gold_rate: float
    silver_movement: str = "stable"
    gold_movement: str = "stable"
    market_summary: str = ""

class RequestCreate(BaseModel):
    request_type: str  # call, video_call, ask_price, hold_item, ask_similar, quick_reorder
    category: str = ""
    preferred_time: str = ""
    notes: str = ""
    product_id: str = ""

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
    points: int
    reward_name: str = ""

class AIChatRequest(BaseModel):
    message: str
    session_id: str = ""

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
    token = create_token(user["id"], user.get("role", "customer"))
    return {"token": token, "user": {**user, "is_new": is_new}}

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
    search: str = Query(""), post_type: str = Query("")
):
    query = {}
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
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    await db.products.insert_one(product)
    return {k: v for k, v in product.items() if k != "_id"}

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

# ===================== RATE ENDPOINTS =====================

@api_router.get("/rates/latest")
async def get_latest_rates():
    rate = await db.rates.find_one({}, {"_id": 0}, sort=[("created_at", -1)])
    if not rate:
        return {"silver_rate": 0, "gold_rate": 0, "silver_movement": "stable", "gold_movement": "stable", "market_summary": "No data"}
    return rate

@api_router.post("/rates")
async def update_rates(req: RateUpdate, user=Depends(get_admin_user)):
    rate_data = {
        "id": str(uuid.uuid4()),
        **req.dict(),
        "updated_by": user["id"],
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.rates.insert_one(rate_data)
    return {k: v for k, v in rate_data.items() if k != "_id"}

@api_router.get("/rates/history")
async def rate_history(days: int = Query(7, ge=1, le=90)):
    rates = await db.rates.find({}, {"_id": 0}).sort("created_at", -1).limit(days * 3).to_list(days * 3)
    return {"rates": rates}

# ===================== REQUEST ENDPOINTS =====================

@api_router.post("/requests")
async def create_request(req: RequestCreate, user=Depends(get_current_user)):
    request_data = {
        "id": str(uuid.uuid4()),
        **req.dict(),
        "user_id": user["id"],
        "user_phone": user.get("phone", ""),
        "user_name": user.get("name", ""),
        "status": "pending",
        "assigned_to": "",
        "admin_notes": "",
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.requests.insert_one(request_data)
    return {k: v for k, v in request_data.items() if k != "_id"}

@api_router.get("/requests/my")
async def my_requests(user=Depends(get_current_user)):
    reqs = await db.requests.find({"user_id": user["id"]}, {"_id": 0}).sort("created_at", -1).limit(50).to_list(50)
    return {"requests": reqs}

@api_router.get("/requests")
async def list_requests(status: str = Query(""), user=Depends(get_admin_user)):
    query = {}
    if status:
        query["status"] = status
    reqs = await db.requests.find(query, {"_id": 0}).sort("created_at", -1).limit(200).to_list(200)
    return {"requests": reqs}

@api_router.patch("/requests/{request_id}")
async def update_request(request_id: str, req: RequestStatusUpdate, user=Depends(get_admin_user)):
    updates = {"status": req.status}
    if req.assigned_to:
        updates["assigned_to"] = req.assigned_to
    if req.notes:
        updates["admin_notes"] = req.notes
    await db.requests.update_one({"id": request_id}, {"$set": updates})
    return await db.requests.find_one({"id": request_id}, {"_id": 0})

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
async def credit_points(req: RewardCreditRequest, user=Depends(get_admin_user)):
    await db.users.update_one({"id": req.user_id}, {"$inc": {"reward_points": req.points}})
    txn = {
        "id": str(uuid.uuid4()), "user_id": req.user_id, "points": req.points,
        "type": "credit", "reason": req.reason or "Admin credit",
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.reward_transactions.insert_one(txn)
    return {"message": f"Credited {req.points} points"}

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
        )
        # Load chat history
        history = await db.ai_chat_history.find(
            {"session_id": session_id}, {"_id": 0}
        ).sort("created_at", -1).limit(10).to_list(10)
        history.reverse()

        chat = LlmChat(
            api_key=EMERGENT_KEY,
            session_id=session_id,
            system_message=system_msg
        ).with_model("anthropic", "claude-sonnet-4-5-20250929")

        # Replay history for context
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
    total_products = await db.products.count_documents({})
    total_requests = await db.requests.count_documents({})
    pending_requests = await db.requests.count_documents({"status": "pending"})
    total_points = 0
    async for u in db.users.find({"role": "customer"}, {"reward_points": 1, "_id": 0}):
        total_points += u.get("reward_points", 0)
    recent_requests = await db.requests.find({}, {"_id": 0}).sort("created_at", -1).limit(10).to_list(10)
    return {
        "total_users": total_users, "total_products": total_products,
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

@api_router.post("/seed")
async def seed_data():
    existing = await db.products.count_documents({})
    if existing > 0:
        return {"message": "Data already seeded", "products": existing}

    # Admin user
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

    # Demo customer
    await db.users.update_one({"phone": "8888888888"}, {"$setOnInsert": {
        "id": str(uuid.uuid4()), "phone": "8888888888", "name": "Rajesh Kumar",
        "city": "Jaipur", "customer_code": "AA8888", "customer_type": "retailer",
        "role": "customer", "category_interests": ["payal", "chain", "articles"],
        "is_eligible_rewards": True, "assigned_salesperson": "", "status": "active",
        "reward_points": 250, "is_new": False, "created_at": datetime.now(timezone.utc).isoformat(),
        "last_login": datetime.now(timezone.utc).isoformat()
    }}, upsert=True)

    # Products
    products = [
        {"title": "Designer Silver Payal", "description": "Handcrafted silver anklets with intricate jali work. Perfect for bridal and festive wear.", "metal_type": "silver", "category": "payal", "subcategory": "bridal", "images": ["https://images.unsplash.com/photo-1611652022419-a9419f74343d?w=600"], "approx_weight": "45-55 grams", "stock_status": "in_stock", "tags": ["bridal", "festive", "bestseller"], "is_trending": True, "is_new_arrival": True},
        {"title": "Pure Silver Chain Collection", "description": "Premium Italian-style silver chains in various thicknesses. High polish finish.", "metal_type": "silver", "category": "chain", "subcategory": "italian", "images": ["https://images.unsplash.com/photo-1679973296611-82470327c513?w=600"], "approx_weight": "20-80 grams", "stock_status": "in_stock", "tags": ["chain", "daily_wear", "men"], "is_trending": True},
        {"title": "Silver Articles - Pooja Thali Set", "description": "Complete silver pooja thali with kalash, diya, and bell. 925 hallmarked.", "metal_type": "silver", "category": "articles", "subcategory": "pooja", "images": ["https://images.unsplash.com/photo-1589128784765-a69d61ed9c39?w=600"], "approx_weight": "150-200 grams", "stock_status": "in_stock", "tags": ["pooja", "gifting", "articles", "hallmarked"]},
        {"title": "Gold Temple Necklace Set", "description": "Traditional temple design gold necklace with matching earrings. 22K gold.", "metal_type": "gold", "category": "necklace", "subcategory": "temple", "images": ["https://images.unsplash.com/photo-1599643478518-a784e5dc4c8f?w=600"], "approx_weight": "35-45 grams", "stock_status": "in_stock", "tags": ["bridal", "temple", "traditional"], "is_pinned": True},
        {"title": "Diamond Solitaire Ring", "description": "Elegant solitaire diamond ring in 18K white gold setting. VVS clarity.", "metal_type": "diamond", "category": "ring", "subcategory": "solitaire", "images": ["https://images.unsplash.com/photo-1606623546924-a4f3ae5ea3e8?w=600"], "approx_weight": "4.5 grams", "stock_status": "limited", "tags": ["diamond", "engagement", "premium"]},
        {"title": "Silver Toe Rings Set", "description": "Traditional silver toe rings with oxidized finish. Set of 6 pairs.", "metal_type": "silver", "category": "toe_rings", "subcategory": "traditional", "images": ["https://images.unsplash.com/photo-1605100804763-247f67b3557e?w=600"], "approx_weight": "8-12 grams", "stock_status": "in_stock", "tags": ["toe_rings", "daily_wear", "women"]},
        {"title": "Gold Bangles - Rajasthani Design", "description": "Beautiful Rajasthani meenakari gold bangles. 22K hallmarked gold.", "metal_type": "gold", "category": "bangles", "subcategory": "meenakari", "images": ["https://images.unsplash.com/photo-1611591437281-460bfbe1220a?w=600"], "approx_weight": "25-35 grams per pair", "stock_status": "in_stock", "tags": ["bangles", "rajasthani", "festive"]},
        {"title": "Silver Baby Gifting Set", "description": "Complete baby gift set in pure silver - spoon, bowl, glass, and rattle.", "metal_type": "silver", "category": "gifting", "subcategory": "baby", "images": ["https://images.unsplash.com/photo-1515562141589-67f0d97dc11b?w=600"], "approx_weight": "80-100 grams", "stock_status": "in_stock", "tags": ["gifting", "baby", "premium"]},
        {"title": "Mens Silver Bracelet - Heavy", "description": "Bold heavy silver bracelet for men. Curb link design with high polish.", "metal_type": "silver", "category": "bracelet", "subcategory": "mens", "images": ["https://images.unsplash.com/photo-1693213085231-fc580d8916de?w=600"], "approx_weight": "60-80 grams", "stock_status": "in_stock", "tags": ["mens", "bracelet", "heavy", "daily_wear"]},
        {"title": "Silver Coin - Lakshmi Ji", "description": "Pure 999 silver coin with Lakshmi Ji embossing. Available in 10g, 20g, 50g, 100g.", "metal_type": "silver", "category": "coins", "subcategory": "religious", "images": ["https://images.unsplash.com/photo-1589128784765-a69d61ed9c39?w=600"], "approx_weight": "10-100 grams", "stock_status": "in_stock", "tags": ["coins", "gifting", "diwali", "investment"], "is_trending": True},
        {"title": "Designer Kundan Choker", "description": "Exquisite kundan choker set with pearl drops and matching maang tikka.", "metal_type": "gold", "category": "necklace", "subcategory": "kundan", "images": ["https://images.unsplash.com/photo-1599643478518-a784e5dc4c8f?w=600"], "approx_weight": "55-65 grams", "stock_status": "limited", "tags": ["bridal", "kundan", "premium"]},
        {"title": "Silver Kadaa - Sikh Design", "description": "Traditional Sikh style silver kadaa in heavy gauge. High polish.", "metal_type": "silver", "category": "kadaa", "subcategory": "sikh", "images": ["https://images.unsplash.com/photo-1611652022419-a9419f74343d?w=600"], "approx_weight": "40-60 grams", "stock_status": "in_stock", "tags": ["kadaa", "mens", "traditional"]},
        {"title": "Diamond Pendant - Heart", "description": "Beautiful heart-shaped diamond pendant in 18K rose gold with chain.", "metal_type": "diamond", "category": "pendant", "subcategory": "heart", "images": ["https://images.unsplash.com/photo-1515562141589-67f0d97dc11b?w=600"], "approx_weight": "3.2 grams", "stock_status": "in_stock", "tags": ["diamond", "pendant", "valentine", "gifting"]},
        {"title": "Silver Dinner Set - 51 Pcs", "description": "Complete 51 piece silver dinner set. Premium quality for gifting and personal use.", "metal_type": "silver", "category": "articles", "subcategory": "dinner_set", "images": ["https://images.unsplash.com/photo-1679973296611-82470327c513?w=600"], "approx_weight": "2500-3000 grams", "stock_status": "in_stock", "tags": ["articles", "dinner_set", "premium", "gifting"]},
        {"title": "Kids Silver Bracelet - Cartoon", "description": "Fun cartoon character silver bracelet for kids. Lightweight and comfortable.", "metal_type": "silver", "category": "kids", "subcategory": "bracelet", "images": ["https://images.unsplash.com/photo-1605100804763-247f67b3557e?w=600"], "approx_weight": "8-12 grams", "stock_status": "in_stock", "tags": ["kids", "bracelet", "fun", "daily_wear"]},
    ]
    for p in products:
        p["id"] = str(uuid.uuid4())
        p["post_type"] = "product"
        p["views"] = 0
        p["is_pinned"] = p.get("is_pinned", False)
        p["is_new_arrival"] = p.get("is_new_arrival", True)
        p["is_trending"] = p.get("is_trending", False)
        p["visibility"] = "all"
        p["video_url"] = ""
        p["created_at"] = datetime.now(timezone.utc).isoformat()
        p["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.products.insert_many(products)

    # Rates
    await db.rates.insert_one({
        "id": str(uuid.uuid4()), "silver_rate": 96.50, "gold_rate": 7450.00,
        "silver_movement": "up", "gold_movement": "stable",
        "market_summary": "Silver up 1.2% today. Gold holding steady near all-time highs.",
        "created_at": datetime.now(timezone.utc).isoformat()
    })

    # Knowledge articles
    knowledge_items = [
        {"title": "Why Does Silver Turn Black?", "content": "Silver turns black due to a chemical reaction with sulphur compounds in the air. This is called tarnishing or oxidation. It is completely natural and does NOT mean the silver is impure.\n\nKey points to share with customers:\n- Tarnishing is a sign of REAL silver\n- It happens faster in humid weather\n- Perfumes, lotions, and sweat speed it up\n- It can be easily cleaned at home\n- 925 silver tarnishes slower than pure silver", "category": "silver_care", "card_type": "article", "tags": ["care", "education", "customer_facing"]},
        {"title": "How to Clean Silver at Home", "content": "Simple home cleaning methods:\n\n1. Baking Soda Paste: Mix baking soda with water, apply gently, rinse\n2. Toothpaste Method: Use plain white toothpaste, rub gently, wash\n3. Aluminium Foil Method: Boil water with baking soda and aluminium foil, dip silver\n4. Lemon + Salt: Rub with lemon and salt for quick shine\n\nTips:\n- Always dry completely after cleaning\n- Use soft cloth, never rough materials\n- Store in airtight bags when not wearing", "category": "silver_care", "card_type": "article", "tags": ["cleaning", "tips", "customer_facing"]},
        {"title": "Benefits of Wearing Silver", "content": "Silver has been valued for centuries. Share these benefits with customers:\n\n1. Antimicrobial properties - kills bacteria naturally\n2. Regulates body temperature\n3. Believed to improve blood circulation\n4. Hypoallergenic - safe for sensitive skin\n5. Affordable luxury compared to gold\n6. Versatile for daily wear and occasions\n7. Silver turns dark if toxins are near (traditional belief)\n8. Investment value - silver prices rising steadily", "category": "benefits", "card_type": "article", "tags": ["benefits", "selling_point", "customer_facing"]},
        {"title": "Silver Storage Best Practices", "content": "Proper storage prevents 80% of tarnishing:\n\n- Store in anti-tarnish cloth or bag\n- Keep in airtight ziplock bags\n- Add silica gel packets to storage\n- Separate pieces to avoid scratching\n- Keep away from bathroom humidity\n- Remove before swimming or bathing\n- Apply perfume BEFORE wearing jewellery", "category": "silver_care", "card_type": "article", "tags": ["storage", "care", "customer_facing"]},
        {"title": "Silver Gifting Ideas", "content": "Silver makes the perfect gift for every occasion:\n\nWedding: Dinner sets, pooja thali, photo frames\nBaby: Spoon set, bowl, glass, rattle\nDiwali: Lakshmi coins, diyas, puja items\nBirthday: Personalized jewelry, cufflinks\nAnniversary: Photo frames, wine glasses\nHousewarming: Flower vase, decorative items\nCorporate: Pens, card holders, desk items\n\nSilver gifts feel premium and last forever.", "category": "gifting", "card_type": "article", "tags": ["gifting", "ideas", "selling_point"]},
    ]
    for k in knowledge_items:
        k["id"] = str(uuid.uuid4())
        k["image_url"] = ""
        k["created_at"] = datetime.now(timezone.utc).isoformat()
    await db.knowledge.insert_many(knowledge_items)

    # Stories
    stories = [
        {"title": "New Silver Collection", "image_url": "https://images.unsplash.com/photo-1679973296611-82470327c513?w=400", "category": "new_arrivals", "link_type": "category", "link_id": "chain"},
        {"title": "Today's Silver Rate", "image_url": "https://images.unsplash.com/photo-1589128784765-a69d61ed9c39?w=400", "category": "rates", "link_type": "rates", "link_id": ""},
        {"title": "Trending: Payal", "image_url": "https://images.unsplash.com/photo-1611652022419-a9419f74343d?w=400", "category": "trending", "link_type": "category", "link_id": "payal"},
        {"title": "Video Selection", "image_url": "https://images.unsplash.com/photo-1606623546924-a4f3ae5ea3e8?w=400", "category": "video_call", "link_type": "request", "link_id": "video_call"},
        {"title": "Festival Offers", "image_url": "https://images.unsplash.com/photo-1599643478518-a784e5dc4c8f?w=400", "category": "offers", "link_type": "feed", "link_id": ""},
    ]
    for s in stories:
        s["id"] = str(uuid.uuid4())
        s["is_active"] = True
        s["created_at"] = datetime.now(timezone.utc).isoformat()
    await db.stories.insert_many(stories)

    # Reward config
    await db.reward_config.update_one({}, {"$set": {
        "points_per_1000": 10, "welcome_bonus": 100, "first_purchase_bonus": 50,
        "first_video_bonus": 25, "eligible_types": ["retailer", "mixed"]
    }}, upsert=True)

    # Indexes
    await db.products.create_index([("created_at", -1)])
    await db.products.create_index([("category", 1)])
    await db.products.create_index([("metal_type", 1)])
    await db.rates.create_index([("created_at", -1)])
    await db.requests.create_index([("user_id", 1)])
    await db.requests.create_index([("status", 1)])
    await db.users.create_index([("phone", 1)], unique=True)

    return {"message": "Seed data created successfully", "products": len(products)}

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
        await seed_data()
        logger.info("Seed data initialized")
    except Exception as e:
        logger.info(f"Seed check: {e}")

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
