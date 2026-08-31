"""
Iteration 3 backend tests: banners CRUD, live-rates removal, try-on removal,
AI chat still works, admin rates, product ids ordering, metal_type filter,
cart/orders, and auth/cart/wishlist/requests regressions.
"""
import io
import os
import time
import uuid
import pytest
import requests
from pathlib import Path
from dotenv import load_dotenv
from PIL import Image

frontend_env = Path(__file__).parent.parent.parent / "frontend" / ".env"
if frontend_env.exists():
    load_dotenv(frontend_env)

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    raise RuntimeError("EXPO_PUBLIC_BACKEND_URL not set")


# ---------- Fixtures ----------
@pytest.fixture(scope="module")
def api_client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


def _login(phone: str) -> str:
    # Send OTP first (required by backend flow)
    requests.post(f"{BASE_URL}/api/auth/send-otp", json={"phone": phone}, timeout=15)
    r = requests.post(
        f"{BASE_URL}/api/auth/verify-otp",
        json={"phone": phone, "otp": "1234"},
        timeout=15,
    )
    if r.status_code != 200:
        pytest.skip(f"Login failed for {phone}: {r.status_code} {r.text}")
    return r.json()["token"]


@pytest.fixture(scope="module")
def admin_token():
    return _login("9999999999")


@pytest.fixture(scope="module")
def customer_token():
    return _login("8888888888")


def _hdr(tok: str):
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


# ---------- Banners: public GET ----------
class TestBannersPublic:
    def test_public_banners_returns_active_sorted(self):
        r = requests.get(f"{BASE_URL}/api/banners", timeout=10)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "banners" in data
        banners = data["banners"]
        assert isinstance(banners, list)
        assert len(banners) >= 2, f"Expected at least 2 seeded banners, got {len(banners)}"
        orders = [b.get("order", 0) for b in banners]
        assert orders == sorted(orders), f"Banners must be sorted by order: {orders}"
        for b in banners:
            assert b.get("is_active") is True
        print(f"✓ /api/banners returned {len(banners)} active banners sorted")

    def test_public_banners_no_admin_required(self):
        # explicitly no auth header
        r = requests.get(f"{BASE_URL}/api/banners", timeout=10)
        assert r.status_code == 200


# ---------- Banners: admin CRUD ----------
class TestBannersAdminCRUD:
    def test_all_banners_admin_only(self, admin_token, customer_token):
        r_admin = requests.get(f"{BASE_URL}/api/banners/all", headers=_hdr(admin_token))
        assert r_admin.status_code == 200
        assert "banners" in r_admin.json()

        r_cust = requests.get(f"{BASE_URL}/api/banners/all", headers=_hdr(customer_token))
        assert r_cust.status_code == 403

        r_anon = requests.get(f"{BASE_URL}/api/banners/all")
        assert r_anon.status_code == 401

    def test_create_banner_missing_title_422(self, admin_token):
        r = requests.post(
            f"{BASE_URL}/api/banners",
            headers=_hdr(admin_token),
            json={"title": "   "},
        )
        assert r.status_code == 422, f"Expected 422 for empty title, got {r.status_code}"

    def test_create_banner_customer_forbidden(self, customer_token):
        r = requests.post(
            f"{BASE_URL}/api/banners",
            headers=_hdr(customer_token),
            json={"title": "TEST Banner Should Fail"},
        )
        assert r.status_code == 403

    def test_full_crud_and_toggle_active(self, admin_token):
        # Create
        payload = {
            "title": f"TEST_BANNER_{uuid.uuid4().hex[:6]}",
            "subtitle": "test subtitle",
            "order": 999,
            "is_active": True,
            "cta_type": "feed",
        }
        r_create = requests.post(f"{BASE_URL}/api/banners", headers=_hdr(admin_token), json=payload)
        assert r_create.status_code == 200, r_create.text
        banner = r_create.json()
        banner_id = banner["id"]
        assert banner["title"] == payload["title"]

        try:
            # GET all - should include our banner
            r_all = requests.get(f"{BASE_URL}/api/banners/all", headers=_hdr(admin_token))
            all_banners = r_all.json()["banners"]
            assert any(b["id"] == banner_id for b in all_banners), "Created banner missing in /banners/all"

            # Toggle inactive via PUT
            r_upd = requests.put(
                f"{BASE_URL}/api/banners/{banner_id}",
                headers=_hdr(admin_token),
                json={"is_active": False},
            )
            assert r_upd.status_code == 200
            assert r_upd.json()["is_active"] is False

            # Public GET should NOT include inactive banner
            r_pub = requests.get(f"{BASE_URL}/api/banners")
            pub_ids = [b["id"] for b in r_pub.json()["banners"]]
            assert banner_id not in pub_ids, "Inactive banner leaked to public endpoint"

            # Reactivate
            requests.put(
                f"{BASE_URL}/api/banners/{banner_id}",
                headers=_hdr(admin_token),
                json={"is_active": True},
            )
        finally:
            r_del = requests.delete(f"{BASE_URL}/api/banners/{banner_id}", headers=_hdr(admin_token))
            assert r_del.status_code == 200

            # Verify deleted
            r_check = requests.get(f"{BASE_URL}/api/banners/all", headers=_hdr(admin_token))
            assert not any(b["id"] == banner_id for b in r_check.json()["banners"])

    def test_date_window_filter_excludes_past_end_date(self, admin_token):
        payload = {
            "title": f"TEST_PAST_{uuid.uuid4().hex[:6]}",
            "is_active": True,
            "order": 998,
            "start_date": "2020-01-01",
            "end_date": "2020-12-31",  # in the past
        }
        r = requests.post(f"{BASE_URL}/api/banners", headers=_hdr(admin_token), json=payload)
        assert r.status_code == 200, r.text
        bid = r.json()["id"]
        try:
            # Public GET should NOT include it
            r_pub = requests.get(f"{BASE_URL}/api/banners")
            pub_ids = [b["id"] for b in r_pub.json()["banners"]]
            assert bid not in pub_ids, "Past-date banner leaked to public endpoint"

            # But /banners/all should include it
            r_all = requests.get(f"{BASE_URL}/api/banners/all", headers=_hdr(admin_token))
            all_ids = [b["id"] for b in r_all.json()["banners"]]
            assert bid in all_ids
        finally:
            requests.delete(f"{BASE_URL}/api/banners/{bid}", headers=_hdr(admin_token))


# ---------- Banners: image upload ----------
class TestBannerUpload:
    def _make_jpeg(self, size=(200, 100)) -> bytes:
        buf = io.BytesIO()
        Image.new("RGB", size, (200, 150, 50)).save(buf, format="JPEG")
        return buf.getvalue()

    def test_upload_valid_jpeg(self, admin_token):
        files = {"file": ("test.jpg", self._make_jpeg(), "image/jpeg")}
        headers = {"Authorization": f"Bearer {admin_token}"}
        r = requests.post(f"{BASE_URL}/api/banners/upload", headers=headers, files=files, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "image_url" in data
        assert data["image_url"].startswith("/api/files/"), f"URL should be relative /api/files/: {data['image_url']}"

    def test_upload_non_image_rejected(self, admin_token):
        headers = {"Authorization": f"Bearer {admin_token}"}
        files = {"file": ("bad.txt", b"this is not an image file, just plain text bytes here to pass min size threshold check.", "text/plain")}
        r = requests.post(f"{BASE_URL}/api/banners/upload", headers=headers, files=files, timeout=15)
        assert r.status_code == 400, f"Expected 400 for non-image, got {r.status_code}: {r.text}"

    def test_upload_requires_admin(self, customer_token):
        headers = {"Authorization": f"Bearer {customer_token}"}
        files = {"file": ("test.jpg", self._make_jpeg(), "image/jpeg")}
        r = requests.post(f"{BASE_URL}/api/banners/upload", headers=headers, files=files, timeout=15)
        assert r.status_code == 403


# ---------- Removed endpoints ----------
class TestRemovedEndpoints:
    def test_live_rates_removed(self):
        r = requests.get(f"{BASE_URL}/api/live-rates")
        assert r.status_code == 404, f"Expected 404 for /api/live-rates, got {r.status_code}"

    def test_live_rates_config_removed_get(self):
        r = requests.get(f"{BASE_URL}/api/live-rates/config")
        assert r.status_code in (404, 405), f"Expected 404/405, got {r.status_code}"

    def test_live_rates_config_removed_post(self):
        r = requests.post(f"{BASE_URL}/api/live-rates/config", json={})
        assert r.status_code in (404, 405, 401), f"Expected 404/405/401, got {r.status_code}"

    def test_ai_try_on_removed(self, customer_token):
        r = requests.post(
            f"{BASE_URL}/api/ai/try-on",
            headers=_hdr(customer_token),
            json={"product_id": "x"},
        )
        assert r.status_code in (404, 405), f"Expected 404/405, got {r.status_code}"

    def test_virtual_try_on_removed(self):
        r = requests.get(f"{BASE_URL}/api/virtual-try-on")
        assert r.status_code in (404, 405), f"Expected 404/405, got {r.status_code}"


# ---------- Kept: AI chat, admin rates ----------
class TestAIChatKept:
    def test_ai_chat_still_works(self, customer_token):
        r = requests.post(
            f"{BASE_URL}/api/ai/chat",
            headers=_hdr(customer_token),
            json={"message": "What is the difference between 925 and 999 silver?", "session_id": f"test-{uuid.uuid4().hex[:8]}"},
            timeout=90,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert "response" in data and len(data["response"]) > 5


class TestAdminRates:
    def test_rates_latest_still_works(self):
        r = requests.get(f"{BASE_URL}/api/rates/latest")
        assert r.status_code == 200
        d = r.json()
        assert "silver_rate" in d and "gold_rate" in d

    def test_rates_post_admin(self, admin_token):
        r = requests.post(
            f"{BASE_URL}/api/rates",
            headers=_hdr(admin_token),
            json={"silver_rate": 96.5, "gold_rate": 7450.0},
        )
        assert r.status_code in (200, 201), r.text


# ---------- Products: ordered IDs + metal filter ----------
class TestProductsIdsOrder:
    def test_ids_returns_requested_order(self):
        r0 = requests.get(f"{BASE_URL}/api/products?limit=10")
        assert r0.status_code == 200
        items = r0.json().get("products", [])
        assert len(items) >= 3, "Need at least 3 products to test ordering"
        ids = [items[0]["id"], items[1]["id"], items[2]["id"]]
        # Request in reverse
        reversed_ids = list(reversed(ids))
        r = requests.get(f"{BASE_URL}/api/products", params={"ids": ",".join(reversed_ids)})
        assert r.status_code == 200
        got_ids = [p["id"] for p in r.json()["products"]]
        assert got_ids == reversed_ids, f"Expected order {reversed_ids}, got {got_ids}"

    def test_metal_type_silver(self):
        r = requests.get(f"{BASE_URL}/api/products?metal_type=silver&limit=20")
        assert r.status_code == 200
        prods = r.json()["products"]
        assert len(prods) > 0
        assert all(p["metal_type"] == "silver" for p in prods)

    def test_metal_type_gold(self):
        r = requests.get(f"{BASE_URL}/api/products?metal_type=gold&limit=20")
        assert r.status_code == 200
        prods = r.json()["products"]
        if prods:
            assert all(p["metal_type"] == "gold" for p in prods)


# ---------- Cart orders (my orders) ----------
class TestCartOrders:
    def test_get_cart_orders(self, customer_token):
        r = requests.get(f"{BASE_URL}/api/cart/orders", headers=_hdr(customer_token))
        assert r.status_code == 200, r.text
        data = r.json()
        # Should return an orders list (possibly empty)
        assert isinstance(data, dict) or isinstance(data, list)


# ---------- Regressions: auth, cart, wishlist, requests, rate-list ----------
class TestRegression:
    def test_send_otp(self):
        r = requests.post(f"{BASE_URL}/api/auth/send-otp", json={"phone": "8888888888"})
        assert r.status_code == 200

    def test_verify_otp(self):
        r = requests.post(f"{BASE_URL}/api/auth/verify-otp", json={"phone": "8888888888", "otp": "1234"})
        assert r.status_code == 200

    def test_cart_add_list_count_submit(self, customer_token):
        # Get a product
        p = requests.get(f"{BASE_URL}/api/products?limit=1").json()["products"]
        assert p, "No products for cart test"
        pid = p[0]["id"]

        # Add
        r_add = requests.post(
            f"{BASE_URL}/api/cart/add",
            headers=_hdr(customer_token),
            json={"product_id": pid, "quantity": 1, "notes": "TEST"},
        )
        assert r_add.status_code in (200, 201), r_add.text

        # List
        r_list = requests.get(f"{BASE_URL}/api/cart", headers=_hdr(customer_token))
        assert r_list.status_code == 200

        # Count
        r_count = requests.get(f"{BASE_URL}/api/cart/count", headers=_hdr(customer_token))
        assert r_count.status_code == 200
        assert "count" in r_count.json()

        # Submit
        r_sub = requests.post(f"{BASE_URL}/api/cart/submit", headers=_hdr(customer_token), json={})
        assert r_sub.status_code in (200, 201), r_sub.text

    def test_wishlist_toggle_and_list(self, customer_token):
        p = requests.get(f"{BASE_URL}/api/products?limit=1").json()["products"]
        assert p
        pid = p[0]["id"]

        r_toggle = requests.post(
            f"{BASE_URL}/api/wishlist/toggle",
            headers=_hdr(customer_token),
            params={"product_id": pid},
        )
        assert r_toggle.status_code == 200, r_toggle.text

        r_list = requests.get(f"{BASE_URL}/api/wishlist", headers=_hdr(customer_token))
        assert r_list.status_code == 200

    def test_requests_create_and_my(self, customer_token):
        r = requests.post(
            f"{BASE_URL}/api/requests",
            headers=_hdr(customer_token),
            json={"request_type": "call", "category": "payal", "notes": "TEST regression"},
        )
        assert r.status_code == 200, r.text

        r_my = requests.get(f"{BASE_URL}/api/requests/my", headers=_hdr(customer_token))
        assert r_my.status_code == 200

    def test_rate_list_endpoint(self):
        r = requests.get(f"{BASE_URL}/api/rate-list")
        assert r.status_code == 200
