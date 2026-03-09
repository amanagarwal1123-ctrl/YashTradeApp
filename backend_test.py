#!/usr/bin/env python3
"""
Backend API Test Script for Yash Trade App
Testing specific endpoints as per review request
"""

import requests
import json
import sys
from datetime import datetime

# Configuration
BASE_URL = "https://jeweler-network-dev.preview.emergentagent.com/api"
CUSTOMER_PHONE = "8888888888"
ADMIN_PHONE = "9999999999" 
OTP = "1234"

class TestRunner:
    def __init__(self):
        self.admin_token = None
        self.customer_token = None
        self.test_results = []
        
    def log(self, message):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")
        
    def authenticate(self):
        """Get admin and customer tokens"""
        # Admin auth
        try:
            # Send OTP
            response = requests.post(f"{BASE_URL}/auth/send-otp", 
                                   json={"phone": ADMIN_PHONE}, timeout=10)
            if response.status_code == 200:
                self.log(f"✅ Admin OTP sent successfully")
            
            # Verify OTP
            response = requests.post(f"{BASE_URL}/auth/verify-otp", 
                                   json={"phone": ADMIN_PHONE, "otp": OTP}, timeout=10)
            if response.status_code == 200:
                data = response.json()
                self.admin_token = data.get("token")
                self.log(f"✅ Admin authenticated: {data.get('user', {}).get('role', 'unknown')}")
            else:
                self.log(f"❌ Admin auth failed: {response.status_code}")
                
        except Exception as e:
            self.log(f"❌ Admin auth error: {str(e)}")
            
        # Customer auth
        try:
            # Send OTP
            response = requests.post(f"{BASE_URL}/auth/send-otp", 
                                   json={"phone": CUSTOMER_PHONE}, timeout=10)
            if response.status_code == 200:
                self.log(f"✅ Customer OTP sent successfully")
            
            # Verify OTP
            response = requests.post(f"{BASE_URL}/auth/verify-otp", 
                                   json={"phone": CUSTOMER_PHONE, "otp": OTP}, timeout=10)
            if response.status_code == 200:
                data = response.json()
                self.customer_token = data.get("token")
                self.log(f"✅ Customer authenticated: {data.get('user', {}).get('role', 'unknown')}")
            else:
                self.log(f"❌ Customer auth failed: {response.status_code}")
                
        except Exception as e:
            self.log(f"❌ Customer auth error: {str(e)}")
    
    def test_endpoint(self, method, endpoint, expected_status=200, headers=None, json_data=None, description=""):
        """Generic endpoint test function"""
        try:
            url = f"{BASE_URL}{endpoint}"
            
            if method == "GET":
                response = requests.get(url, headers=headers, timeout=10)
            elif method == "POST":
                response = requests.post(url, headers=headers, json=json_data, timeout=10)
            elif method == "DELETE":
                response = requests.delete(url, headers=headers, timeout=10)
            else:
                self.log(f"❌ Unsupported method: {method}")
                return False
                
            success = response.status_code == expected_status
            status_icon = "✅" if success else "❌"
            
            if success and response.content:
                try:
                    data = response.json()
                    if isinstance(data, dict):
                        keys = list(data.keys())[:3]  # Show first 3 keys
                        self.log(f"{status_icon} {method} {endpoint} - {description}")
                        self.log(f"    Response keys: {keys}...")
                    elif isinstance(data, list):
                        self.log(f"{status_icon} {method} {endpoint} - {description}")
                        self.log(f"    Response: {len(data)} items")
                    else:
                        self.log(f"{status_icon} {method} {endpoint} - {description}")
                except:
                    self.log(f"{status_icon} {method} {endpoint} - {description}")
            else:
                self.log(f"{status_icon} {method} {endpoint} - {description} (Status: {response.status_code})")
                
            self.test_results.append({
                'endpoint': endpoint,
                'method': method,
                'status': response.status_code,
                'success': success,
                'description': description
            })
            
            return success, response
            
        except Exception as e:
            self.log(f"❌ {method} {endpoint} - ERROR: {str(e)}")
            self.test_results.append({
                'endpoint': endpoint,
                'method': method,
                'status': 'ERROR',
                'success': False,
                'description': f"{description} - {str(e)}"
            })
            return False, None

    def run_tests(self):
        """Run all endpoint tests"""
        self.log("🚀 Starting Yash Trade API Tests")
        self.log("="*60)
        
        # Authenticate first
        self.authenticate()
        admin_headers = {"Authorization": f"Bearer {self.admin_token}"} if self.admin_token else None
        customer_headers = {"Authorization": f"Bearer {self.customer_token}"} if self.customer_token else None
        
        # Test 1: About API
        self.log("\n📋 Testing About Content API")
        success, resp = self.test_endpoint("GET", "/about?lang=en", 200, None, None, "About English content")
        if success and resp:
            data = resp.json()
            sections = data.get("sections", [])
            if len(sections) >= 6:
                required_sections = ["brand_intro", "why_buy", "new_shop_benefits", "b2b_benefits", "location_chandni_chowk", "location_karol_bagh"]
                found_sections = [s.get("section") for s in sections]
                missing = [r for r in required_sections if r not in found_sections]
                if not missing:
                    self.log("    ✅ All 6 required sections found")
                else:
                    self.log(f"    ❌ Missing sections: {missing}")
            else:
                self.log(f"    ❌ Expected 6+ sections, found {len(sections)}")
                
        self.test_endpoint("GET", "/about?lang=hi", 200, None, None, "About Hindi content")
        
        # Test 2: Products API
        self.log("\n📦 Testing Products API")
        success, resp = self.test_endpoint("GET", "/products?limit=50", 200, None, None, "Products endless feed")
        if success and resp:
            data = resp.json()
            products = data.get("products", [])
            self.log(f"    Products found: {len(products)}")
        
        # Test 3: Live Rates API
        self.log("\n💰 Testing Live Rates API")
        success, resp = self.test_endpoint("GET", "/live-rates", 200, None, None, "Live rates data")
        if success and resp:
            data = resp.json()
            rates = ["silver_dollar", "silver_mcx", "gold_dollar"]
            valid_rates = []
            for rate in rates:
                value = data.get(rate, 0)
                if isinstance(value, (int, float)) and value > 0:
                    valid_rates.append(f"{rate}:{value}")
            if len(valid_rates) >= 3:
                self.log(f"    ✅ Valid rates: {valid_rates}")
            else:
                self.log(f"    ❌ Invalid rates found: {data}")
        
        # Test 4: Rate List API
        self.log("\n📊 Testing Rate List API")
        success, resp = self.test_endpoint("GET", "/rate-list", 200, None, None, "Rate list - all slabs")
        if success and resp:
            data = resp.json()
            slabs = data if isinstance(data, list) else data.get("slabs", [])
            self.log(f"    Total slabs: {len(slabs)}")
            
        success, resp = self.test_endpoint("GET", "/rate-list?metal_type=silver", 200, None, None, "Rate list - silver filter")
        if success and resp:
            data = resp.json()
            slabs = data if isinstance(data, list) else data.get("slabs", [])
            self.log(f"    Silver slabs: {len(slabs)}")
        
        # Test 5: Schemes API
        self.log("\n🎯 Testing Schemes API")
        self.test_endpoint("GET", "/schemes", 200, None, None, "Schemes array")
        
        # Test 6: Brands API  
        self.log("\n🏷️ Testing Brands API")
        self.test_endpoint("GET", "/brands", 200, None, None, "Brands array")
        
        # Test 7: Showroom API
        self.log("\n🏢 Testing Showroom API")
        success, resp = self.test_endpoint("GET", "/showroom", 200, None, None, "Showroom floors")
        if success and resp:
            data = resp.json()
            floors = data.get("floors", []) if isinstance(data, dict) else data
            self.log(f"    Floors found: {len(floors)}")
        
        # Test 8: Exhibitions API
        self.log("\n🎪 Testing Exhibitions API")
        success, resp = self.test_endpoint("GET", "/exhibitions", 200, None, None, "Exhibitions data")
        if success and resp:
            data = resp.json()
            upcoming = data.get("upcoming", [])
            past = data.get("past", [])
            self.log(f"    Upcoming: {len(upcoming)}, Past: {len(past)}")
        
        # Test 9: Live Rates Config (Admin)
        self.log("\n⚙️ Testing Admin Live Rates Config")
        if admin_headers:
            success, resp = self.test_endpoint("GET", "/live-rates/config", 200, admin_headers, None, "Premium config (admin)")
            if success and resp:
                data = resp.json()
                config_keys = list(data.keys())
                self.log(f"    Config keys: {config_keys}")
        else:
            self.log("    ❌ No admin token - skipping admin tests")
        
        # Test 10-15: Admin CRUD Operations
        if admin_headers:
            self.log("\n🔧 Testing Admin CRUD Operations")
            
            # Create test scheme
            scheme_data = {
                "title": "Test Scheme", 
                "poster_url": "https://example.com/test.jpg",
                "description": "Test scheme description"
            }
            success, resp = self.test_endpoint("POST", "/schemes", 200, admin_headers, scheme_data, "Create test scheme")
            created_scheme_id = None
            if success and resp:
                data = resp.json()
                created_scheme_id = data.get("id")
                self.log(f"    Created scheme ID: {created_scheme_id}")
            
            # Create test brand
            brand_data = {
                "name": "Test Brand",
                "logo_url": "https://example.com/logo.jpg",
                "description": "Test brand description"
            }
            success, resp = self.test_endpoint("POST", "/brands", 200, admin_headers, brand_data, "Create test brand")
            created_brand_id = None
            if success and resp:
                data = resp.json()
                created_brand_id = data.get("id")
                self.log(f"    Created brand ID: {created_brand_id}")
            
            # Create test showroom floor
            showroom_data = {
                "floor_name": "Ground Floor",
                "products_available": "Silver Payal",
                "description": "Test floor description"
            }
            success, resp = self.test_endpoint("POST", "/showroom", 200, admin_headers, showroom_data, "Create test showroom floor")
            created_floor_id = None
            if success and resp:
                data = resp.json()
                created_floor_id = data.get("id")
                self.log(f"    Created floor ID: {created_floor_id}")
            
            # Create test exhibition
            exhibition_data = {
                "title": "Delhi Jewellery Expo",
                "is_upcoming": True,
                "date": "March 2026",
                "location": "Delhi"
            }
            success, resp = self.test_endpoint("POST", "/exhibitions", 200, admin_headers, exhibition_data, "Create test exhibition")
            created_exhibition_id = None
            if success and resp:
                data = resp.json()
                created_exhibition_id = data.get("id")
                self.log(f"    Created exhibition ID: {created_exhibition_id}")
            
            # Cleanup - Delete test items
            self.log("\n🧹 Cleaning up test data")
            if created_scheme_id:
                self.test_endpoint("DELETE", f"/schemes/{created_scheme_id}", 200, admin_headers, None, "Delete test scheme")
            if created_brand_id:
                self.test_endpoint("DELETE", f"/brands/{created_brand_id}", 200, admin_headers, None, "Delete test brand")
            if created_floor_id:
                self.test_endpoint("DELETE", f"/showroom/{created_floor_id}", 200, admin_headers, None, "Delete test floor")
            if created_exhibition_id:
                self.test_endpoint("DELETE", f"/exhibitions/{created_exhibition_id}", 200, admin_headers, None, "Delete test exhibition")
        
        # Summary
        self.log("\n" + "="*60)
        self.log("📊 TEST SUMMARY")
        total_tests = len(self.test_results)
        passed_tests = len([t for t in self.test_results if t['success']])
        failed_tests = total_tests - passed_tests
        
        self.log(f"Total Tests: {total_tests}")
        self.log(f"✅ Passed: {passed_tests}")
        self.log(f"❌ Failed: {failed_tests}")
        self.log(f"Success Rate: {(passed_tests/total_tests)*100:.1f}%")
        
        if failed_tests > 0:
            self.log("\n❌ FAILED TESTS:")
            for test in self.test_results:
                if not test['success']:
                    self.log(f"  - {test['method']} {test['endpoint']}: {test['description']}")
        
        return failed_tests == 0

if __name__ == "__main__":
    runner = TestRunner()
    success = runner.run_tests()
    sys.exit(0 if success else 1)