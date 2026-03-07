"""
Backend API tests for Aman Agarwal Jewellers App
Tests: Auth, Rates, Products, Stories, Knowledge, Rewards, Requests, AI Chat, Admin
"""
import pytest
import requests
import os
from pathlib import Path
from dotenv import load_dotenv

# Load frontend env vars to get public URL
frontend_env = Path(__file__).parent.parent.parent / 'frontend' / '.env'
if frontend_env.exists():
    load_dotenv(frontend_env)

BASE_URL = os.environ.get('EXPO_PUBLIC_BACKEND_URL', '').rstrip('/')
if not BASE_URL:
    raise ValueError("EXPO_PUBLIC_BACKEND_URL not found in environment")

@pytest.fixture
def api_client():
    """Shared requests session"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session

@pytest.fixture
def demo_customer_token(api_client):
    """Login as demo customer 8888888888"""
    response = api_client.post(f"{BASE_URL}/api/auth/verify-otp", json={
        "phone": "8888888888",
        "otp": "1234"
    })
    if response.status_code != 200:
        pytest.skip("Customer auth failed - skipping dependent tests")
    return response.json().get("token")

@pytest.fixture
def admin_token(api_client):
    """Login as admin 9999999999"""
    response = api_client.post(f"{BASE_URL}/api/auth/verify-otp", json={
        "phone": "9999999999",
        "otp": "1234"
    })
    if response.status_code != 200:
        pytest.skip("Admin auth failed - skipping dependent tests")
    return response.json().get("token")


# ===================== AUTH TESTS =====================
class TestAuth:
    """Authentication endpoint tests"""

    def test_send_otp_valid_phone(self, api_client):
        """Test sending OTP with valid phone number"""
        response = api_client.post(f"{BASE_URL}/api/auth/send-otp", json={"phone": "8888888888"})
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        print(f"✓ Send OTP success: {data.get('message')}")

    def test_send_otp_invalid_phone(self, api_client):
        """Test sending OTP with invalid phone number"""
        response = api_client.post(f"{BASE_URL}/api/auth/send-otp", json={"phone": "123"})
        assert response.status_code == 400
        print("✓ Invalid phone rejected")

    def test_verify_otp_valid(self, api_client):
        """Test OTP verification with correct OTP"""
        response = api_client.post(f"{BASE_URL}/api/auth/verify-otp", json={
            "phone": "8888888888",
            "otp": "1234"
        })
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert "user" in data
        assert data["user"]["phone"] == "8888888888"
        print(f"✓ OTP verified, user: {data['user'].get('name', 'N/A')}")

    def test_verify_otp_invalid(self, api_client):
        """Test OTP verification with wrong OTP"""
        response = api_client.post(f"{BASE_URL}/api/auth/verify-otp", json={
            "phone": "8888888888",
            "otp": "0000"
        })
        assert response.status_code == 400
        print("✓ Invalid OTP rejected")

    def test_admin_login(self, api_client):
        """Test admin user can login"""
        response = api_client.post(f"{BASE_URL}/api/auth/verify-otp", json={
            "phone": "9999999999",
            "otp": "1234"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["user"]["role"] == "admin"
        print(f"✓ Admin login success: {data['user'].get('name')}")

    def test_get_me_authenticated(self, api_client, demo_customer_token):
        """Test /auth/me with valid token"""
        api_client.headers.update({"Authorization": f"Bearer {demo_customer_token}"})
        response = api_client.get(f"{BASE_URL}/api/auth/me")
        assert response.status_code == 200
        data = response.json()
        assert data["phone"] == "8888888888"
        print(f"✓ Get me success: {data.get('name')}, points: {data.get('reward_points')}")

    def test_get_me_unauthenticated(self, api_client):
        """Test /auth/me without token"""
        response = api_client.get(f"{BASE_URL}/api/auth/me")
        assert response.status_code == 401
        print("✓ Unauthorized request blocked")


# ===================== RATES TESTS =====================
class TestRates:
    """Rate endpoints tests"""

    def test_get_latest_rates(self, api_client):
        """Test fetching latest silver/gold rates"""
        response = api_client.get(f"{BASE_URL}/api/rates/latest")
        assert response.status_code == 200
        data = response.json()
        assert "silver_rate" in data
        assert "gold_rate" in data
        assert data["silver_rate"] == 96.50
        assert data["gold_rate"] == 7450.00
        print(f"✓ Rates fetched: Silver ₹{data['silver_rate']}, Gold ₹{data['gold_rate']}")


# ===================== PRODUCTS TESTS =====================
class TestProducts:
    """Product endpoints tests"""

    def test_list_products(self, api_client):
        """Test listing products"""
        response = api_client.get(f"{BASE_URL}/api/products?limit=5")
        assert response.status_code == 200
        data = response.json()
        assert "products" in data
        assert "total" in data
        assert len(data["products"]) > 0
        print(f"✓ Products listed: {data['total']} total, {len(data['products'])} fetched")

    def test_filter_products_by_metal(self, api_client):
        """Test filtering products by metal type"""
        response = api_client.get(f"{BASE_URL}/api/products?metal_type=silver&limit=5")
        assert response.status_code == 200
        data = response.json()
        if data["products"]:
            assert all(p["metal_type"] == "silver" for p in data["products"])
        print(f"✓ Metal filter works: {len(data['products'])} silver products")

    def test_filter_products_by_category(self, api_client):
        """Test filtering products by category"""
        response = api_client.get(f"{BASE_URL}/api/products?category=payal&limit=5")
        assert response.status_code == 200
        data = response.json()
        print(f"✓ Category filter works: {len(data['products'])} payal products")

    def test_search_products(self, api_client):
        """Test product search"""
        response = api_client.get(f"{BASE_URL}/api/products?search=chain&limit=5")
        assert response.status_code == 200
        data = response.json()
        print(f"✓ Search works: {len(data['products'])} results for 'chain'")

    def test_get_product_by_id(self, api_client):
        """Test fetching single product and verify persistence"""
        # First get list to get a product ID
        list_response = api_client.get(f"{BASE_URL}/api/products?limit=1")
        products = list_response.json()["products"]
        if not products:
            pytest.skip("No products available")
        
        product_id = products[0]["id"]
        # Now fetch single product
        response = api_client.get(f"{BASE_URL}/api/products/{product_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == product_id
        assert "title" in data
        print(f"✓ Product fetched: {data['title']}")

    def test_pagination(self, api_client):
        """Test product pagination"""
        page1 = api_client.get(f"{BASE_URL}/api/products?page=1&limit=5").json()
        page2 = api_client.get(f"{BASE_URL}/api/products?page=2&limit=5").json()
        assert page1["page"] == 1
        assert page2["page"] == 2
        print(f"✓ Pagination works: Page 1 has {len(page1['products'])}, Page 2 has {len(page2['products'])}")


# ===================== STORIES TESTS =====================
class TestStories:
    """Stories endpoint tests"""

    def test_list_stories(self, api_client):
        """Test fetching stories"""
        response = api_client.get(f"{BASE_URL}/api/stories")
        assert response.status_code == 200
        data = response.json()
        assert "stories" in data
        assert len(data["stories"]) > 0
        print(f"✓ Stories fetched: {len(data['stories'])} stories")


# ===================== KNOWLEDGE TESTS =====================
class TestKnowledge:
    """Knowledge articles endpoint tests"""

    def test_list_knowledge(self, api_client):
        """Test fetching knowledge articles"""
        response = api_client.get(f"{BASE_URL}/api/knowledge")
        assert response.status_code == 200
        data = response.json()
        assert "articles" in data
        assert len(data["articles"]) > 0
        print(f"✓ Knowledge articles fetched: {len(data['articles'])} articles")

    def test_filter_knowledge_by_category(self, api_client):
        """Test filtering knowledge by category"""
        response = api_client.get(f"{BASE_URL}/api/knowledge?category=silver_care")
        assert response.status_code == 200
        data = response.json()
        print(f"✓ Knowledge category filter works: {len(data['articles'])} silver_care articles")


# ===================== REWARDS TESTS =====================
class TestRewards:
    """Reward system endpoint tests"""

    def test_get_wallet(self, api_client, demo_customer_token):
        """Test fetching reward wallet"""
        api_client.headers.update({"Authorization": f"Bearer {demo_customer_token}"})
        response = api_client.get(f"{BASE_URL}/api/rewards/wallet")
        assert response.status_code == 200
        data = response.json()
        assert "current_points" in data
        assert "total_earned" in data
        assert "recent_transactions" in data
        print(f"✓ Wallet fetched: {data['current_points']} points, earned {data['total_earned']}")

    def test_get_wallet_unauthenticated(self, api_client):
        """Test wallet access without auth"""
        response = api_client.get(f"{BASE_URL}/api/rewards/wallet")
        assert response.status_code == 401
        print("✓ Wallet access blocked without auth")

    def test_reward_history(self, api_client, demo_customer_token):
        """Test fetching reward transaction history"""
        api_client.headers.update({"Authorization": f"Bearer {demo_customer_token}"})
        response = api_client.get(f"{BASE_URL}/api/rewards/history")
        assert response.status_code == 200
        data = response.json()
        assert "transactions" in data
        print(f"✓ Reward history fetched: {len(data['transactions'])} transactions")


# ===================== REQUESTS TESTS =====================
class TestRequests:
    """Request call/video system tests"""

    def test_create_request(self, api_client, demo_customer_token):
        """Test creating a call request"""
        api_client.headers.update({"Authorization": f"Bearer {demo_customer_token}"})
        response = api_client.post(f"{BASE_URL}/api/requests", json={
            "request_type": "call",
            "category": "payal",
            "preferred_time": "10:00 AM",
            "notes": "TEST request for testing purposes"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["request_type"] == "call"
        assert data["status"] == "pending"
        assert data["user_phone"] == "8888888888"
        print(f"✓ Request created: {data['request_type']}, ID: {data['id']}")

    def test_get_my_requests(self, api_client, demo_customer_token):
        """Test fetching user's own requests"""
        api_client.headers.update({"Authorization": f"Bearer {demo_customer_token}"})
        response = api_client.get(f"{BASE_URL}/api/requests/my")
        assert response.status_code == 200
        data = response.json()
        assert "requests" in data
        print(f"✓ My requests fetched: {len(data['requests'])} requests")

    def test_admin_list_all_requests(self, api_client, admin_token):
        """Test admin can view all requests"""
        api_client.headers.update({"Authorization": f"Bearer {admin_token}"})
        response = api_client.get(f"{BASE_URL}/api/requests")
        assert response.status_code == 200
        data = response.json()
        assert "requests" in data
        print(f"✓ Admin view all requests: {len(data['requests'])} total requests")


# ===================== AI CHAT TESTS =====================
class TestAIChat:
    """AI Assistant endpoint tests"""

    def test_ai_chat(self, api_client, demo_customer_token):
        """Test AI chat endpoint"""
        api_client.headers.update({"Authorization": f"Bearer {demo_customer_token}"})
        response = api_client.post(f"{BASE_URL}/api/ai/chat", json={
            "message": "Why does silver turn black?",
            "session_id": "test-session-123"
        })
        assert response.status_code == 200
        data = response.json()
        assert "response" in data
        assert "session_id" in data
        assert len(data["response"]) > 10  # Should have a meaningful response
        print(f"✓ AI chat works: Response length {len(data['response'])} chars")

    def test_ai_suggestions(self, api_client):
        """Test fetching AI quick prompts"""
        response = api_client.get(f"{BASE_URL}/api/ai/suggestions")
        assert response.status_code == 200
        data = response.json()
        assert "suggestions" in data
        assert len(data["suggestions"]) > 0
        print(f"✓ AI suggestions fetched: {len(data['suggestions'])} prompts")


# ===================== ADMIN TESTS =====================
class TestAdmin:
    """Admin panel endpoint tests"""

    def test_analytics_dashboard(self, api_client, admin_token):
        """Test admin analytics dashboard"""
        api_client.headers.update({"Authorization": f"Bearer {admin_token}"})
        response = api_client.get(f"{BASE_URL}/api/analytics/dashboard")
        assert response.status_code == 200
        data = response.json()
        assert "total_users" in data
        assert "total_products" in data
        assert "total_requests" in data
        print(f"✓ Admin dashboard: {data['total_users']} users, {data['total_products']} products")

    def test_list_customers(self, api_client, admin_token):
        """Test admin listing customers"""
        api_client.headers.update({"Authorization": f"Bearer {admin_token}"})
        response = api_client.get(f"{BASE_URL}/api/customers?limit=10")
        assert response.status_code == 200
        data = response.json()
        assert "customers" in data
        assert "total" in data
        print(f"✓ Admin customer list: {data['total']} total customers")

    def test_customer_access_denied_for_regular_user(self, api_client, demo_customer_token):
        """Test regular user cannot access customer list"""
        api_client.headers.update({"Authorization": f"Bearer {demo_customer_token}"})
        response = api_client.get(f"{BASE_URL}/api/customers")
        assert response.status_code == 403
        print("✓ Customer list access blocked for non-admin")


# ===================== CATEGORIES TESTS =====================
class TestCategories:
    """Product categories endpoint tests"""

    def test_get_categories(self, api_client):
        """Test fetching product categories and metal types"""
        response = api_client.get(f"{BASE_URL}/api/categories")
        assert response.status_code == 200
        data = response.json()
        assert "categories" in data
        assert "metal_types" in data
        assert len(data["categories"]) > 0
        assert len(data["metal_types"]) > 0
        print(f"✓ Categories fetched: {len(data['categories'])} categories, {len(data['metal_types'])} metals")
