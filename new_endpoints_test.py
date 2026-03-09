#!/usr/bin/env python3
"""
New API Endpoints Testing for Yash Trade App
Testing all the new endpoints mentioned in the review request.
"""

import requests
import json
import sys

# Configuration
BASE_URL = "https://jeweler-network-dev.preview.emergentagent.com/api"
print(f"Testing new backend API endpoints at: {BASE_URL}")

class NewEndpointsTestRunner:
    def __init__(self):
        self.session = requests.Session()
        self.admin_token = None
        self.customer_token = None
        self.test_ids = {}  # Store created item IDs for cleanup
        
    def setup_auth(self):
        """Set up authentication for different user types"""
        print("\n=== Authentication Setup ===")
        
        # Customer login (8888888888, OTP: 1234)
        try:
            response = self.session.post(f"{BASE_URL}/auth/send-otp", json={"phone": "8888888888"})
            if response.status_code == 200:
                response = self.session.post(f"{BASE_URL}/auth/verify-otp", 
                                           json={"phone": "8888888888", "otp": "1234"})
                if response.status_code == 200:
                    self.customer_token = response.json()["token"]
                    user = response.json()["user"]
                    print(f"✅ Customer login successful: {user.get('name', 'Customer')} (role: {user.get('role')})")
                else:
                    print(f"❌ Customer OTP verification failed: {response.status_code} - {response.text}")
                    return False
            else:
                print(f"❌ Customer OTP send failed: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            print(f"❌ Customer auth error: {e}")
            return False
        
        # Admin login (9999999999, OTP: 1234)
        try:
            response = self.session.post(f"{BASE_URL}/auth/send-otp", json={"phone": "9999999999"})
            if response.status_code == 200:
                response = self.session.post(f"{BASE_URL}/auth/verify-otp", 
                                           json={"phone": "9999999999", "otp": "1234"})
                if response.status_code == 200:
                    self.admin_token = response.json()["token"]
                    user = response.json()["user"]
                    print(f"✅ Admin login successful: {user.get('name', 'Admin')} (role: {user.get('role')})")
                else:
                    print(f"❌ Admin OTP verification failed: {response.status_code} - {response.text}")
                    return False
            else:
                print(f"❌ Admin OTP send failed: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            print(f"❌ Admin auth error: {e}")
            return False
            
        return self.admin_token and self.customer_token

    def test_about_content_endpoints(self):
        """Test About Content endpoints"""
        print("\n=== Testing About Content Endpoints ===")
        
        # 1. GET /api/about?lang=en - should return 6 sections
        try:
            response = self.session.get(f"{BASE_URL}/about?lang=en")
            if response.status_code == 200:
                data = response.json()
                sections = data.get("sections", [])
                if len(sections) >= 6:
                    print(f"✅ About content (English) retrieved: {len(sections)} sections")
                    # Check if we have proper structure - sections should have 'content' and raw should have 'content_en'
                    if (sections and "content" in sections[0] and 
                        "raw" in data and data["raw"] and "content_en" in data["raw"][0]):
                        print("✅ English content structure validated")
                    else:
                        print("❌ English content structure invalid")
                        return False
                else:
                    print(f"❌ Expected 6+ sections, got {len(sections)}")
                    return False
            else:
                print(f"❌ About content (English) failed: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ About content (English) error: {e}")
            return False
        
        # 2. GET /api/about?lang=hi - should return Hindi content
        try:
            response = self.session.get(f"{BASE_URL}/about?lang=hi")
            if response.status_code == 200:
                data = response.json()
                sections = data.get("sections", [])
                if sections:
                    print(f"✅ About content (Hindi) retrieved: {len(sections)} sections")
                    # Check if we have Hindi content
                    has_hindi = any("content_hi" in section and section.get("content_hi") for section in sections)
                    if has_hindi:
                        print("✅ Hindi content found")
                    else:
                        print("⚠️ No Hindi content found (may be expected)")
                else:
                    print("❌ No sections found for Hindi")
                    return False
            else:
                print(f"❌ About content (Hindi) failed: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ About content (Hindi) error: {e}")
            return False
            
        return True

    def test_live_rates_endpoints(self):
        """Test Live Rates endpoints"""
        print("\n=== Testing Live Rates Endpoints ===")
        
        # 1. GET /api/live-rates - should return real values > 0
        try:
            response = self.session.get(f"{BASE_URL}/live-rates")
            if response.status_code == 200:
                data = response.json()
                
                # Check for expected fields with real values
                expected_fields = [
                    "silver_dollar", "gold_dollar", "silver_mcx", 
                    "gold_mcx", "silver_physical", "gold_physical"
                ]
                
                valid_rates = 0
                for field in expected_fields:
                    if field in data:
                        rate_value = data[field]
                        if isinstance(rate_value, (int, float)) and rate_value > 0:
                            valid_rates += 1
                            print(f"   {field}: {rate_value}")
                        else:
                            print(f"   {field}: {rate_value} (invalid or zero)")
                
                if valid_rates == len(expected_fields):
                    print(f"✅ Live rates retrieved: All {valid_rates} rates have valid values > 0")
                else:
                    print(f"❌ Live rates incomplete: {valid_rates}/{len(expected_fields)} valid rates")
                    return False
            else:
                print(f"❌ Live rates failed: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ Live rates error: {e}")
            return False
            
        return True

    def test_rate_list_endpoints(self):
        """Test Rate List endpoints"""
        print("\n=== Testing Rate List Endpoints ===")
        
        # 1. GET /api/rate-list - should return 10 slabs (silver, gold, diamond)
        try:
            response = self.session.get(f"{BASE_URL}/rate-list")
            if response.status_code == 200:
                data = response.json()
                slabs = data.get("slabs", [])
                if len(slabs) >= 10:
                    print(f"✅ Rate list retrieved: {len(slabs)} slabs")
                    
                    # Check for different metal types
                    metal_types = set(slab.get("metal_type", "") for slab in slabs)
                    expected_metals = {"silver", "gold", "diamond"}
                    found_metals = expected_metals.intersection(metal_types)
                    
                    if len(found_metals) >= 2:  # At least 2 metal types
                        print(f"✅ Multiple metal types found: {found_metals}")
                    else:
                        print(f"⚠️ Limited metal types: {metal_types}")
                else:
                    print(f"❌ Expected 10+ slabs, got {len(slabs)}")
                    return False
            else:
                print(f"❌ Rate list failed: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ Rate list error: {e}")
            return False
        
        # 2. GET /api/rate-list?metal_type=silver - should filter by metal type
        try:
            response = self.session.get(f"{BASE_URL}/rate-list?metal_type=silver")
            if response.status_code == 200:
                data = response.json()
                slabs = data.get("slabs", [])
                
                # Verify all slabs are silver
                all_silver = all(slab.get("metal_type") == "silver" for slab in slabs)
                if all_silver and len(slabs) > 0:
                    print(f"✅ Silver rate list filtering: {len(slabs)} silver slabs")
                elif len(slabs) == 0:
                    print("⚠️ No silver slabs found (may be expected)")
                else:
                    print("❌ Metal type filtering not working correctly")
                    return False
            else:
                print(f"❌ Silver rate list filter failed: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ Silver rate list filter error: {e}")
            return False
            
        return True

    def test_schemes_endpoints(self):
        """Test Schemes endpoints"""
        print("\n=== Testing Schemes Endpoints ===")
        
        # 1. GET /api/schemes - should return schemes array
        try:
            response = self.session.get(f"{BASE_URL}/schemes")
            if response.status_code == 200:
                data = response.json()
                schemes = data.get("schemes", [])
                print(f"✅ Schemes retrieved: {len(schemes)} schemes")
            else:
                print(f"❌ Schemes list failed: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ Schemes list error: {e}")
            return False
        
        # 2. POST /api/schemes (admin auth) - should create a scheme
        if not self.admin_token:
            print("❌ Admin token required for scheme creation")
            return False
            
        try:
            headers = {"Authorization": f"Bearer {self.admin_token}"}
            scheme_data = {
                "title": "Test Gold Scheme API",
                "title_hi": "टेस्ट गोल्ड स्कीम",
                "description": "Test scheme created via API testing",
                "description_hi": "एपीआई परीक्षण के द्वारा बनाई गई टेस्ट स्कीम",
                "poster_url": "https://example.com/poster.jpg",
                "is_active": True,
                "order": 1
            }
            
            response = self.session.post(f"{BASE_URL}/schemes", json=scheme_data, headers=headers)
            if response.status_code == 200:
                created_scheme = response.json()
                self.test_ids["scheme_id"] = created_scheme.get("id")
                print(f"✅ Scheme created successfully: {created_scheme.get('title')}")
                
                # Validate response structure
                required_fields = ["id", "title", "description", "is_active"]
                missing = [f for f in required_fields if f not in created_scheme]
                if not missing:
                    print("✅ Scheme creation response structure validated")
                else:
                    print(f"❌ Scheme response missing fields: {missing}")
                    return False
            else:
                print(f"❌ Scheme creation failed: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            print(f"❌ Scheme creation error: {e}")
            return False
            
        return True

    def test_brands_endpoints(self):
        """Test Brands endpoints"""
        print("\n=== Testing Brands Endpoints ===")
        
        # 1. GET /api/brands - should return brands array
        try:
            response = self.session.get(f"{BASE_URL}/brands")
            if response.status_code == 200:
                data = response.json()
                brands = data.get("brands", [])
                print(f"✅ Brands retrieved: {len(brands)} brands")
            else:
                print(f"❌ Brands list failed: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ Brands list error: {e}")
            return False
        
        # 2. POST /api/brands (admin auth) - should create a brand
        if not self.admin_token:
            print("❌ Admin token required for brand creation")
            return False
            
        try:
            headers = {"Authorization": f"Bearer {self.admin_token}"}
            brand_data = {
                "name": "Test Brand API",
                "logo_url": "https://example.com/logo.jpg",
                "description": "Test brand created via API testing",
                "order": 1,
                "is_active": True
            }
            
            response = self.session.post(f"{BASE_URL}/brands", json=brand_data, headers=headers)
            if response.status_code == 200:
                created_brand = response.json()
                self.test_ids["brand_id"] = created_brand.get("id")
                print(f"✅ Brand created successfully: {created_brand.get('name')}")
                
                # Validate response structure
                required_fields = ["id", "name", "is_active"]
                missing = [f for f in required_fields if f not in created_brand]
                if not missing:
                    print("✅ Brand creation response structure validated")
                else:
                    print(f"❌ Brand response missing fields: {missing}")
                    return False
            else:
                print(f"❌ Brand creation failed: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            print(f"❌ Brand creation error: {e}")
            return False
            
        return True

    def test_showroom_endpoints(self):
        """Test Showroom endpoints"""
        print("\n=== Testing Showroom Endpoints ===")
        
        # 1. GET /api/showroom - should return floors array
        try:
            response = self.session.get(f"{BASE_URL}/showroom")
            if response.status_code == 200:
                data = response.json()
                floors = data.get("floors", [])
                print(f"✅ Showroom floors retrieved: {len(floors)} floors")
            else:
                print(f"❌ Showroom floors list failed: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ Showroom floors list error: {e}")
            return False
        
        # 2. POST /api/showroom (admin auth) - should create a floor
        if not self.admin_token:
            print("❌ Admin token required for showroom floor creation")
            return False
            
        try:
            headers = {"Authorization": f"Bearer {self.admin_token}"}
            floor_data = {
                "floor_name": "Test Floor API",
                "floor_name_hi": "टेस्ट फ्लोर",
                "description": "Test floor created via API testing",
                "description_hi": "एपीआई परीक्षण के द्वारा बनाया गया टेस्ट फ्लोर",
                "products_available": "Silver jewelry, Gold ornaments",
                "products_available_hi": "चांदी के गहने, सोने के आभूषण",
                "photos": ["https://example.com/floor1.jpg"],
                "order": 1
            }
            
            response = self.session.post(f"{BASE_URL}/showroom", json=floor_data, headers=headers)
            if response.status_code == 200:
                created_floor = response.json()
                self.test_ids["floor_id"] = created_floor.get("id")
                print(f"✅ Showroom floor created successfully: {created_floor.get('floor_name')}")
                
                # Validate response structure
                required_fields = ["id", "floor_name", "order"]
                missing = [f for f in required_fields if f not in created_floor]
                if not missing:
                    print("✅ Showroom floor creation response structure validated")
                else:
                    print(f"❌ Showroom floor response missing fields: {missing}")
                    return False
            else:
                print(f"❌ Showroom floor creation failed: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            print(f"❌ Showroom floor creation error: {e}")
            return False
            
        return True

    def test_exhibitions_endpoints(self):
        """Test Exhibitions endpoints"""
        print("\n=== Testing Exhibitions Endpoints ===")
        
        # 1. GET /api/exhibitions - should return {upcoming: [], past: []}
        try:
            response = self.session.get(f"{BASE_URL}/exhibitions")
            if response.status_code == 200:
                data = response.json()
                
                # Check for proper structure
                if "upcoming" in data and "past" in data:
                    upcoming = data.get("upcoming", [])
                    past = data.get("past", [])
                    print(f"✅ Exhibitions retrieved: {len(upcoming)} upcoming, {len(past)} past")
                else:
                    print(f"❌ Exhibitions response structure invalid: {data.keys()}")
                    return False
            else:
                print(f"❌ Exhibitions list failed: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ Exhibitions list error: {e}")
            return False
        
        # 2. POST /api/exhibitions (admin auth) - should create an exhibition
        if not self.admin_token:
            print("❌ Admin token required for exhibition creation")
            return False
            
        try:
            headers = {"Authorization": f"Bearer {self.admin_token}"}
            exhibition_data = {
                "title": "Test Exhibition API",
                "title_hi": "टेस्ट प्रदर्शनी",
                "description": "Test exhibition created via API testing",
                "description_hi": "एपीआई परीक्षण के द्वारा बनाई गई टेस्ट प्रदर्शनी",
                "poster_url": "https://example.com/exhibition-poster.jpg",
                "photos": ["https://example.com/exhibition1.jpg"],
                "date": "2024-06-15",
                "location": "Mumbai Convention Center",
                "is_upcoming": True,
                "is_active": True
            }
            
            response = self.session.post(f"{BASE_URL}/exhibitions", json=exhibition_data, headers=headers)
            if response.status_code == 200:
                created_exhibition = response.json()
                self.test_ids["exhibition_id"] = created_exhibition.get("id")
                print(f"✅ Exhibition created successfully: {created_exhibition.get('title')}")
                
                # Validate response structure
                required_fields = ["id", "title", "date", "location", "is_upcoming"]
                missing = [f for f in required_fields if f not in created_exhibition]
                if not missing:
                    print("✅ Exhibition creation response structure validated")
                else:
                    print(f"❌ Exhibition response missing fields: {missing}")
                    return False
            else:
                print(f"❌ Exhibition creation failed: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            print(f"❌ Exhibition creation error: {e}")
            return False
            
        return True

    def test_live_rate_config_endpoints(self):
        """Test Live Rate Config endpoints (admin only)"""
        print("\n=== Testing Live Rate Config Endpoints ===")
        
        if not self.admin_token:
            print("❌ Admin token required for live rate config testing")
            return False
            
        headers = {"Authorization": f"Bearer {self.admin_token}"}
        
        # 1. GET /api/live-rates/config (admin auth) - should return premium config
        try:
            response = self.session.get(f"{BASE_URL}/live-rates/config", headers=headers)
            if response.status_code == 200:
                config = response.json()
                print(f"✅ Live rate config retrieved: {len(config)} config items")
                
                # Check for expected config fields
                expected_fields = ["silver_premium", "gold_premium", "auto_fetch_enabled"]
                found_fields = [f for f in expected_fields if f in config]
                if len(found_fields) >= 2:
                    print(f"✅ Config structure validated: {found_fields}")
                else:
                    print(f"⚠️ Limited config fields: {list(config.keys())}")
            else:
                print(f"❌ Live rate config retrieval failed: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ Live rate config retrieval error: {e}")
            return False
        
        # 2. POST /api/live-rates/config (admin auth) - should update config
        try:
            config_data = {
                "silver_premium": 2.50,
                "gold_premium": 100.00,
                "auto_fetch_enabled": True,
                "fetch_interval_seconds": 120
            }
            
            response = self.session.post(f"{BASE_URL}/live-rates/config", json=config_data, headers=headers)
            if response.status_code == 200:
                updated_config = response.json()
                print(f"✅ Live rate config updated successfully")
                
                # Verify the update
                if (updated_config.get("silver_premium") == 2.50 and 
                    updated_config.get("gold_premium") == 100.00):
                    print("✅ Config update values verified")
                else:
                    print(f"❌ Config values not updated correctly: {updated_config}")
                    return False
            else:
                print(f"❌ Live rate config update failed: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            print(f"❌ Live rate config update error: {e}")
            return False
            
        return True

    def test_existing_endpoints_regression(self):
        """Test existing endpoints still work"""
        print("\n=== Testing Existing Endpoints (Regression) ===")
        
        # 1. GET /api/products
        try:
            response = self.session.get(f"{BASE_URL}/products")
            if response.status_code == 200:
                data = response.json()
                products = data.get("products", [])
                print(f"✅ Products endpoint working: {len(products)} products")
            else:
                print(f"❌ Products endpoint failed: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ Products endpoint error: {e}")
            return False
        
        # 2. GET /api/rates/latest
        try:
            response = self.session.get(f"{BASE_URL}/rates/latest")
            if response.status_code == 200:
                rates = response.json()
                if "silver_physical_rate" in rates and "gold_physical_rate" in rates:
                    print(f"✅ Rates endpoint working: Silver ₹{rates.get('silver_physical_rate')}, Gold ₹{rates.get('gold_physical_rate')}")
                else:
                    print("❌ Rates endpoint missing expected fields")
                    return False
            else:
                print(f"❌ Rates endpoint failed: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ Rates endpoint error: {e}")
            return False
        
        # 3. GET /api/cart/count (with auth)
        if self.customer_token:
            try:
                headers = {"Authorization": f"Bearer {self.customer_token}"}
                response = self.session.get(f"{BASE_URL}/cart/count", headers=headers)
                if response.status_code == 200:
                    data = response.json()
                    count = data.get("count", 0)
                    print(f"✅ Cart count endpoint working: {count} items")
                else:
                    print(f"❌ Cart count endpoint failed: {response.status_code}")
                    return False
            except Exception as e:
                print(f"❌ Cart count endpoint error: {e}")
                return False
        else:
            print("⚠️ Customer token not available for cart count test")
            
        return True

    def cleanup_test_data(self):
        """Clean up test data created during testing"""
        print("\n=== Cleanup Test Data ===")
        
        if not self.admin_token:
            print("⚠️ No admin token for cleanup")
            return
            
        headers = {"Authorization": f"Bearer {self.admin_token}"}
        
        # Clean up created items
        cleanup_endpoints = {
            "scheme_id": "schemes",
            "brand_id": "brands", 
            "floor_id": "showroom",
            "exhibition_id": "exhibitions"
        }
        
        for key, endpoint in cleanup_endpoints.items():
            if key in self.test_ids:
                try:
                    item_id = self.test_ids[key]
                    response = self.session.delete(f"{BASE_URL}/{endpoint}/{item_id}", headers=headers)
                    if response.status_code == 200:
                        print(f"✅ Cleaned up test {key}")
                    else:
                        print(f"⚠️ Could not cleanup {key}: {response.status_code}")
                except Exception as e:
                    print(f"⚠️ Cleanup error for {key}: {e}")

    def run_all_tests(self):
        """Run all new endpoint tests"""
        print("🧪 Starting New API Endpoints Tests for Yash Trade App")
        print("=" * 60)
        
        # Setup
        if not self.setup_auth():
            print("💥 Authentication setup failed - cannot continue")
            return False
        
        test_results = []
        
        # Test all new endpoints
        test_results.append(("About Content Endpoints", self.test_about_content_endpoints()))
        test_results.append(("Live Rates Endpoints", self.test_live_rates_endpoints()))
        test_results.append(("Rate List Endpoints", self.test_rate_list_endpoints()))
        test_results.append(("Schemes Endpoints", self.test_schemes_endpoints()))
        test_results.append(("Brands Endpoints", self.test_brands_endpoints()))
        test_results.append(("Showroom Endpoints", self.test_showroom_endpoints()))
        test_results.append(("Exhibitions Endpoints", self.test_exhibitions_endpoints()))
        test_results.append(("Live Rate Config Endpoints", self.test_live_rate_config_endpoints()))
        
        # Regression tests
        test_results.append(("Existing Endpoints Regression", self.test_existing_endpoints_regression()))
        
        # Cleanup
        self.cleanup_test_data()
        
        # Summary
        print("\n" + "=" * 60)
        print("🏁 NEW ENDPOINTS TEST SUMMARY")
        print("=" * 60)
        
        passed = 0
        failed = 0
        
        for test_name, result in test_results:
            status = "✅ PASSED" if result else "❌ FAILED"
            print(f"{test_name}: {status}")
            
            if result:
                passed += 1
            else:
                failed += 1
        
        print(f"\nTotal: {passed + failed} tests")
        print(f"Passed: {passed}")
        print(f"Failed: {failed}")
        
        if failed == 0:
            print("\n🎉 ALL NEW ENDPOINT TESTS PASSED! The new API endpoints are working correctly.")
        else:
            print(f"\n⚠️ {failed} test(s) failed. Please check the issues above.")
            
        return failed == 0

if __name__ == "__main__":
    runner = NewEndpointsTestRunner()
    success = runner.run_all_tests()
    
    if not success:
        sys.exit(1)