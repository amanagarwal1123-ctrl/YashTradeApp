"""Backend API tests for the 12-fix patch set."""
import pytest
import httpx
import os

API_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "").rstrip("/") or "https://yash-tryon-test.preview.emergentagent.com"
BASE = f"{API_URL}/api"

def get_token(phone: str) -> str:
    r = httpx.post(f"{BASE}/auth/verify-otp", json={"phone": phone, "otp": "1234"})
    assert r.status_code == 200
    return r.json()["token"]

@pytest.fixture(scope="module")
def admin_token():
    return get_token("9999999999")

@pytest.fixture(scope="module")
def user_token():
    return get_token("8888888888")

@pytest.fixture(scope="module")
def exec_token():
    return get_token("7777777777")

# ---- Fix 1: Redeem non-positive points ----

def test_redeem_zero_points_rejected(user_token):
    r = httpx.post(f"{BASE}/rewards/redeem", json={"points": 0}, headers={"Authorization": f"Bearer {user_token}"})
    assert r.status_code == 422  # Pydantic validation

def test_redeem_negative_points_rejected(user_token):
    r = httpx.post(f"{BASE}/rewards/redeem", json={"points": -10}, headers={"Authorization": f"Bearer {user_token}"})
    assert r.status_code == 422

# ---- Fix 2: Seed endpoints protected ----

def test_seed_requires_auth():
    r = httpx.post(f"{BASE}/seed")
    assert r.status_code == 401

def test_seed_expand_requires_auth():
    r = httpx.post(f"{BASE}/seed/expand")
    assert r.status_code == 401

# ---- Fix 3: PATCH unknown request -> 404 ----

def test_patch_unknown_request_404(admin_token):
    r = httpx.patch(f"{BASE}/requests/nonexistent-id-xyz", json={"status": "resolved"}, headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 404
    assert "not found" in r.json()["detail"].lower()

# ---- Fix 4: Status normalization ----

def test_status_done_normalizes_to_resolved(admin_token, user_token):
    # Create a request
    r = httpx.post(f"{BASE}/requests", json={"request_type": "call"}, headers={"Authorization": f"Bearer {user_token}"})
    req_id = r.json()["id"]
    # Patch with legacy "done"
    r2 = httpx.patch(f"{BASE}/requests/{req_id}", json={"status": "done"}, headers={"Authorization": f"Bearer {admin_token}"})
    assert r2.status_code == 200
    assert r2.json()["status"] == "resolved"

def test_status_assigned_normalizes_to_in_progress(admin_token, user_token):
    r = httpx.post(f"{BASE}/requests", json={"request_type": "video_call"}, headers={"Authorization": f"Bearer {user_token}"})
    req_id = r.json()["id"]
    r2 = httpx.patch(f"{BASE}/requests/{req_id}", json={"status": "assigned"}, headers={"Authorization": f"Bearer {admin_token}"})
    assert r2.status_code == 200
    assert r2.json()["status"] == "in_progress"

# ---- Fix 12: Executive seeded ----

def test_executive_user_exists(exec_token):
    r = httpx.get(f"{BASE}/auth/me", headers={"Authorization": f"Bearer {exec_token}"})
    assert r.status_code == 200
    assert r.json()["role"] == "executive"

# ---- Regression: core endpoints still work ----

def test_products_endpoint():
    r = httpx.get(f"{BASE}/products?limit=3")
    assert r.status_code == 200
    assert "products" in r.json()

def test_rates_endpoint():
    r = httpx.get(f"{BASE}/rates/latest")
    assert r.status_code == 200
    d = r.json()
    assert "silver_dollar_rate" in d
    assert "gold_mcx_rate" in d

def test_wishlist_toggle(user_token):
    # Get a product ID
    r = httpx.get(f"{BASE}/products?limit=1")
    pid = r.json()["products"][0]["id"]
    # Toggle on
    r2 = httpx.post(f"{BASE}/wishlist/toggle?product_id={pid}", headers={"Authorization": f"Bearer {user_token}"})
    assert r2.status_code == 200
    # Toggle off
    r3 = httpx.post(f"{BASE}/wishlist/toggle?product_id={pid}", headers={"Authorization": f"Bearer {user_token}"})
    assert r3.status_code == 200

def test_my_requests(user_token):
    r = httpx.get(f"{BASE}/requests/my", headers={"Authorization": f"Bearer {user_token}"})
    assert r.status_code == 200
    assert "requests" in r.json()

def test_wishlist_list(user_token):
    r = httpx.get(f"{BASE}/wishlist", headers={"Authorization": f"Bearer {user_token}"})
    assert r.status_code == 200
    assert "products" in r.json()
