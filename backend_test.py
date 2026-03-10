#!/usr/bin/env python3
"""
Comprehensive Backend Testing for Yash Trade Jewellery App - Virtual Try-On Feature
Testing all backend APIs at https://yash-tryon-test.preview.emergentagent.com
"""

import requests
import base64
import io
import json
from PIL import Image, ImageDraw

# Configuration
API_URL = "https://yash-tryon-test.preview.emergentagent.com"
ADMIN_PHONE = "9999999999"
CUSTOMER_PHONE = "8888888888"
TEST_OTP = "1234"

class VirtualTryOnTester:
    def __init__(self):
        self.session = requests.Session()
        self.admin_token = None
        self.customer_token = None
        self.test_results = []

    def log_test(self, test_name, status, message=""):
        """Log test results"""
        result = f"{'✅' if status else '❌'} {test_name}: {message}"
        print(result)
        self.test_results.append({"test": test_name, "passed": status, "message": message})

    def create_test_image(self, width=400, height=500, image_type="person"):
        """Create a test image for try-on testing"""
        if image_type == "person":
            # Create a simple person-like image with skin tone and clothing
            img = Image.new('RGB', (width, height), (200, 180, 160))  # Skin tone background
            draw = ImageDraw.Draw(img)
            
            # Draw head (face area)
            draw.ellipse([150, 50, 250, 170], fill=(230, 200, 170))  # Face
            
            # Draw neck
            draw.rectangle([180, 170, 220, 220], fill=(230, 200, 170))  # Neck
            
            # Draw body with clothing
            draw.rectangle([130, 220, 270, 400], fill=(100, 120, 140))  # Body/shirt
            
        else:  # non-person image
            img = Image.new('RGB', (width, height), (255, 0, 0))  # Red image
            draw = ImageDraw.Draw(img)
            draw.text((10, 10), "TEST IMAGE", fill=(255, 255, 255))

        # Convert to base64
        buf = io.BytesIO()
        img.save(buf, 'JPEG', quality=80)
        return base64.b64encode(buf.getvalue()).decode()

    def authenticate_user(self, phone, is_admin=False):
        """Authenticate and get JWT token"""
        try:
            # Send OTP (optional step)
            otp_response = self.session.post(f"{API_URL}/api/auth/send-otp", json={"phone": phone})
            
            # Verify OTP
            verify_response = self.session.post(f"{API_URL}/api/auth/verify-otp", json={
                "phone": phone,
                "otp": TEST_OTP
            })
            
            if verify_response.status_code == 200:
                data = verify_response.json()
                token = data.get("token")
                role = data.get("user", {}).get("role", "customer")
                self.log_test(f"Authentication ({'Admin' if is_admin else 'Customer'})", True, f"Phone: {phone}, Role: {role}")
                return token
            else:
                self.log_test(f"Authentication ({'Admin' if is_admin else 'Customer'})", False, f"HTTP {verify_response.status_code}")
                return None
        except Exception as e:
            self.log_test(f"Authentication ({'Admin' if is_admin else 'Customer'})", False, str(e))
            return None

    def test_virtual_tryon_web_page(self):
        """Test 1: Virtual Try-On Web Page (GET /api/virtual-try-on)"""
        print("\n=== TEST 1: Virtual Try-On Web Page ===")
        
        try:
            response = self.session.get(f"{API_URL}/api/virtual-try-on")
            
            if response.status_code == 200:
                content = response.text
                # Check for key elements in the HTML
                required_elements = [
                    "Virtual Try-On",
                    "login",
                    "product",
                    "photo",
                    "generate",
                    "API_BASE"
                ]
                
                missing_elements = []
                for element in required_elements:
                    if element.lower() not in content.lower():
                        missing_elements.append(element)
                
                if not missing_elements:
                    self.log_test("Virtual Try-On Web Page Load", True, "HTML page loaded with all required elements")
                    
                    # Check if it's a proper HTML page
                    if content.strip().startswith('<!DOCTYPE html>') or content.strip().startswith('<html'):
                        self.log_test("Virtual Try-On HTML Structure", True, "Valid HTML document structure")
                    else:
                        self.log_test("Virtual Try-On HTML Structure", False, "Not a valid HTML document")
                        
                else:
                    self.log_test("Virtual Try-On Web Page Load", False, f"Missing elements: {missing_elements}")
            else:
                self.log_test("Virtual Try-On Web Page Load", False, f"HTTP {response.status_code}")
                
        except Exception as e:
            self.log_test("Virtual Try-On Web Page Load", False, str(e))

    def test_ai_tryon_backend_api(self):
        """Test 2: AI Try-On Backend API (POST /api/ai/try-on)"""
        print("\n=== TEST 2: AI Try-On Backend API ===")
        
        if not self.customer_token:
            self.log_test("AI Try-On API", False, "No customer token available")
            return
            
        try:
            # First get a product ID
            products_response = self.session.get(f"{API_URL}/api/products?limit=1")
            if products_response.status_code != 200:
                self.log_test("AI Try-On API - Get Product", False, f"Products API failed: {products_response.status_code}")
                return
                
            products_data = products_response.json()
            if not products_data.get("products"):
                self.log_test("AI Try-On API - Get Product", False, "No products available")
                return
                
            product_id = products_data["products"][0]["id"]
            self.log_test("AI Try-On API - Get Product", True, f"Product ID: {product_id}")
            
            # Create test user image
            test_image_b64 = self.create_test_image(400, 500, "person")
            
            # Test AI Try-On API call
            tryon_payload = {
                "product_id": product_id,
                "user_photo_base64": test_image_b64,
                "body_area": "neck",
                "scale": 0.45,
                "offset_x": 0.5,
                "offset_y": 0.25
            }
            
            headers = {"Authorization": f"Bearer {self.customer_token}"}
            response = self.session.post(f"{API_URL}/api/ai/try-on", json=tryon_payload, headers=headers)
            
            if response.status_code == 200:
                data = response.json()
                
                # Check required response fields
                required_fields = ["image_url", "image_base64", "method"]
                missing_fields = []
                
                for field in required_fields:
                    if field not in data:
                        missing_fields.append(field)
                
                if not missing_fields:
                    # Verify method is exact_composite
                    if data.get("method") == "exact_composite":
                        self.log_test("AI Try-On API Response", True, f"All fields present, method: {data['method']}")
                        
                        # Test if returned image URL is accessible
                        self.test_generated_image_url(data["image_url"])
                        
                    else:
                        self.log_test("AI Try-On API Response", False, f"Expected method 'exact_composite', got '{data.get('method')}'")
                else:
                    self.log_test("AI Try-On API Response", False, f"Missing fields: {missing_fields}")
            else:
                error_msg = f"HTTP {response.status_code}"
                try:
                    error_data = response.json()
                    error_msg += f": {error_data.get('detail', 'Unknown error')}"
                except:
                    pass
                self.log_test("AI Try-On API Response", False, error_msg)
                
        except Exception as e:
            self.log_test("AI Try-On API", False, str(e))

    def test_different_body_areas(self):
        """Test 3: Test different body areas"""
        print("\n=== TEST 3: Different Body Areas ===")
        
        if not self.customer_token:
            self.log_test("Body Areas Test", False, "No customer token available")
            return
            
        try:
            # Get a product ID
            products_response = self.session.get(f"{API_URL}/api/products?limit=1")
            if products_response.status_code != 200:
                self.log_test("Body Areas Test - Get Product", False, "Products API failed")
                return
                
            products_data = products_response.json()
            product_id = products_data["products"][0]["id"]
            
            # Test different body areas
            body_areas = ["neck", "ear", "wrist", "ankle", "finger", "auto"]
            test_image_b64 = self.create_test_image(400, 500, "person")
            headers = {"Authorization": f"Bearer {self.customer_token}"}
            
            for area in body_areas:
                try:
                    payload = {
                        "product_id": product_id,
                        "user_photo_base64": test_image_b64,
                        "body_area": area,
                        "scale": 0.4,
                        "offset_x": 0.5,
                        "offset_y": 0.3
                    }
                    
                    response = self.session.post(f"{API_URL}/api/ai/try-on", json=payload, headers=headers)
                    
                    if response.status_code == 200:
                        data = response.json()
                        detected_area = data.get("body_area", area)
                        self.log_test(f"Body Area - {area}", True, f"Detected area: {detected_area}")
                    else:
                        self.log_test(f"Body Area - {area}", False, f"HTTP {response.status_code}")
                        
                except Exception as e:
                    self.log_test(f"Body Area - {area}", False, str(e))
                    
        except Exception as e:
            self.log_test("Body Areas Test", False, str(e))

    def test_error_handling(self):
        """Test 4: Error handling"""
        print("\n=== TEST 4: Error Handling ===")
        
        # Test 4a: Without auth token (should 401)
        try:
            payload = {
                "product_id": "test-product-id",
                "user_photo_base64": "invalid-base64",
                "body_area": "neck"
            }
            
            response = self.session.post(f"{API_URL}/api/ai/try-on", json=payload)
            
            if response.status_code == 401:
                self.log_test("Error Handling - No Auth", True, "Correctly returned 401 Unauthorized")
            else:
                self.log_test("Error Handling - No Auth", False, f"Expected 401, got {response.status_code}")
                
        except Exception as e:
            self.log_test("Error Handling - No Auth", False, str(e))
        
        if not self.customer_token:
            self.log_test("Error Handling - Invalid Product", False, "No customer token for further tests")
            return
            
        headers = {"Authorization": f"Bearer {self.customer_token}"}
        
        # Test 4b: Invalid product_id (should 404)
        try:
            payload = {
                "product_id": "invalid-product-id-12345",
                "user_photo_base64": self.create_test_image(400, 500, "person"),
                "body_area": "neck"
            }
            
            response = self.session.post(f"{API_URL}/api/ai/try-on", json=payload, headers=headers)
            
            if response.status_code == 404:
                self.log_test("Error Handling - Invalid Product", True, "Correctly returned 404 Not Found")
            else:
                self.log_test("Error Handling - Invalid Product", False, f"Expected 404, got {response.status_code}")
                
        except Exception as e:
            self.log_test("Error Handling - Invalid Product", False, str(e))
        
        # Test 4c: Missing/empty user_photo_base64
        try:
            # Get valid product ID
            products_response = self.session.get(f"{API_URL}/api/products?limit=1")
            product_id = products_response.json()["products"][0]["id"]
            
            payload = {
                "product_id": product_id,
                "user_photo_base64": "",  # Empty image
                "body_area": "neck"
            }
            
            response = self.session.post(f"{API_URL}/api/ai/try-on", json=payload, headers=headers)
            
            if response.status_code >= 400:
                self.log_test("Error Handling - Empty Image", True, f"Correctly returned error {response.status_code}")
            else:
                self.log_test("Error Handling - Empty Image", False, f"Should have returned error, got {response.status_code}")
                
        except Exception as e:
            self.log_test("Error Handling - Empty Image", False, str(e))

    def test_generated_image_url(self, image_url):
        """Test 5: Generated image URL works"""
        print(f"\n=== TEST 5: Generated Image URL Access ===")
        
        try:
            # Construct full URL if relative
            if image_url.startswith('/'):
                full_url = f"{API_URL}{image_url}"
            else:
                full_url = image_url
                
            response = self.session.get(full_url)
            
            if response.status_code == 200:
                content_type = response.headers.get('Content-Type', '')
                if 'image' in content_type.lower():
                    self.log_test("Generated Image URL Access", True, f"Image accessible, Content-Type: {content_type}")
                else:
                    self.log_test("Generated Image URL Access", False, f"Not an image, Content-Type: {content_type}")
            else:
                self.log_test("Generated Image URL Access", False, f"HTTP {response.status_code}")
                
        except Exception as e:
            self.log_test("Generated Image URL Access", False, str(e))

    def test_existing_endpoints_regression(self):
        """Test 6: Regression - Existing endpoints"""
        print("\n=== TEST 6: Existing Endpoints Regression ===")
        
        # Test products endpoint
        try:
            response = self.session.get(f"{API_URL}/api/products?limit=5")
            
            if response.status_code == 200:
                data = response.json()
                if data.get("products") and len(data["products"]) > 0:
                    self.log_test("Regression - Products API", True, f"Retrieved {len(data['products'])} products")
                else:
                    self.log_test("Regression - Products API", False, "No products returned")
            else:
                self.log_test("Regression - Products API", False, f"HTTP {response.status_code}")
                
        except Exception as e:
            self.log_test("Regression - Products API", False, str(e))
        
        # Test live rates endpoint
        try:
            response = self.session.get(f"{API_URL}/api/live-rates")
            
            if response.status_code == 200:
                data = response.json()
                required_fields = ["silver_dollar", "gold_dollar", "silver_mcx", "gold_mcx", "silver_physical", "gold_physical"]
                
                missing_fields = []
                for field in required_fields:
                    if field not in data:
                        missing_fields.append(field)
                
                if not missing_fields:
                    silver_dollar = data.get("silver_dollar", 0)
                    if silver_dollar > 0:
                        self.log_test("Regression - Live Rates API", True, f"All rate fields present, silver_dollar: ${silver_dollar}")
                    else:
                        self.log_test("Regression - Live Rates API", False, f"Invalid silver_dollar rate: {silver_dollar}")
                else:
                    self.log_test("Regression - Live Rates API", False, f"Missing fields: {missing_fields}")
            else:
                self.log_test("Regression - Live Rates API", False, f"HTTP {response.status_code}")
                
        except Exception as e:
            self.log_test("Regression - Live Rates API", False, str(e))
        
        # Test auth/me endpoint with customer token
        if self.customer_token:
            try:
                headers = {"Authorization": f"Bearer {self.customer_token}"}
                response = self.session.get(f"{API_URL}/api/auth/me", headers=headers)
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get("phone") == CUSTOMER_PHONE:
                        self.log_test("Regression - Auth Me API", True, f"User details correct: {data.get('phone')}")
                    else:
                        self.log_test("Regression - Auth Me API", False, f"Wrong user data: {data}")
                else:
                    self.log_test("Regression - Auth Me API", False, f"HTTP {response.status_code}")
                    
            except Exception as e:
                self.log_test("Regression - Auth Me API", False, str(e))

    def run_all_tests(self):
        """Run comprehensive Virtual Try-On feature testing"""
        print("=" * 80)
        print("🎭 YASH TRADE VIRTUAL TRY-ON COMPREHENSIVE BACKEND TESTING")
        print(f"🌐 API URL: {API_URL}")
        print("=" * 80)
        
        # Authenticate users
        print("\n🔐 AUTHENTICATION")
        self.admin_token = self.authenticate_user(ADMIN_PHONE, is_admin=True)
        self.customer_token = self.authenticate_user(CUSTOMER_PHONE, is_admin=False)
        
        # Run all test suites
        self.test_virtual_tryon_web_page()
        self.test_ai_tryon_backend_api()
        self.test_different_body_areas()
        self.test_error_handling()
        self.test_existing_endpoints_regression()
        
        # Summary
        print("\n" + "=" * 80)
        print("📊 TEST SUMMARY")
        print("=" * 80)
        
        passed_tests = [t for t in self.test_results if t["passed"]]
        failed_tests = [t for t in self.test_results if not t["passed"]]
        
        print(f"✅ PASSED: {len(passed_tests)}/{len(self.test_results)} tests")
        print(f"❌ FAILED: {len(failed_tests)}/{len(self.test_results)} tests")
        
        if failed_tests:
            print("\n🔥 FAILED TESTS:")
            for test in failed_tests:
                print(f"   ❌ {test['test']}: {test['message']}")
        
        if passed_tests:
            print(f"\n✨ SUCCESS RATE: {(len(passed_tests)/len(self.test_results)*100):.1f}%")
        
        print("\n" + "=" * 80)
        
        return len(failed_tests) == 0


if __name__ == "__main__":
    tester = VirtualTryOnTester()
    success = tester.run_all_tests()
    exit(0 if success else 1)