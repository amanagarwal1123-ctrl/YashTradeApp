#!/usr/bin/env python3
"""
Backend API Test Script for Yash Trade App - Review Request Verification
Testing 9 specific feature changes as per review request
"""

import requests
import json
import sys
from datetime import datetime
import uuid

# Configuration
BASE_URL = "https://jeweler-network-dev.preview.emergentagent.com/api"
CUSTOMER_PHONE = "8888888888"
ADMIN_PHONE = "9999999999" 
OTP = "1234"

class ReviewTestRunner:
    def __init__(self):
        self.admin_token = None
        self.customer_token = None
        self.test_results = []
        self.created_test_items = []
        
    def log(self, message):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")
        
    def authenticate(self):
        """Get admin and customer tokens"""
        # Admin auth
        try:
            response = requests.post(f"{BASE_URL}/auth/send-otp", 
                                   json={"phone": ADMIN_PHONE}, timeout=10)
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
            response = requests.post(f"{BASE_URL}/auth/send-otp", 
                                   json={"phone": CUSTOMER_PHONE}, timeout=10)
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

    def test_silver_rate_list_item_wise(self):
        """Test 1: Silver Rate List is now item-wise (not slab-based)"""
        self.log("\n🥈 TEST 1: Silver Rate List - Item-wise Structure")
        try:
            response = requests.get(f"{BASE_URL}/rate-list?metal_type=silver", timeout=10)
            if response.status_code == 200:
                data = response.json()
                # The response has a 'slabs' key but contains item-wise data
                items = data.get("slabs", [])
                
                if len(items) >= 5:
                    self.log(f"✅ Found {len(items)} silver items")
                    
                    # Check first item structure for item-wise fields
                    if items:
                        first_item = items[0]
                        required_fields = ["item_name", "category", "subcategory", "purity", "wastage", "labour_kg"]
                        forbidden_fields = ["slab_name", "min_qty", "max_qty", "rate"]
                        
                        has_required = all(field in first_item for field in required_fields)
                        has_forbidden = any(field in first_item for field in forbidden_fields)
                        
                        if has_required and not has_forbidden:
                            self.log("✅ Item-wise structure verified - has required fields, no slab fields")
                            self.log(f"    Sample item: {first_item.get('item_name')} - {first_item.get('category')}")
                            return True
                        else:
                            missing = [f for f in required_fields if f not in first_item]
                            present = [f for f in forbidden_fields if f in first_item]
                            if missing:
                                self.log(f"❌ Missing required fields: {missing}")
                            if present:
                                self.log(f"❌ Still has slab-based fields: {present}")
                            return False
                    else:
                        self.log("❌ No items found in response")
                        return False
                else:
                    self.log(f"❌ Expected at least 5 silver items, found {len(items)}")
                    return False
            else:
                self.log(f"❌ API call failed: {response.status_code}")
                return False
                
        except Exception as e:
            self.log(f"❌ Test failed: {str(e)}")
            return False

    def test_office_addresses(self):
        """Test 2: Office addresses are correct"""
        self.log("\n🏢 TEST 2: Office Addresses Verification")
        try:
            response = requests.get(f"{BASE_URL}/about?lang=en", timeout=10)
            if response.status_code == 200:
                data = response.json()
                sections = data.get("sections", [])
                
                # Find location sections
                chandni_section = None
                karol_section = None
                
                for section in sections:
                    if section.get("section") == "location_chandni_chowk":
                        chandni_section = section
                    elif section.get("section") == "location_karol_bagh":
                        karol_section = section
                
                success = True
                
                # Check Chandni Chowk
                if chandni_section:
                    content = chandni_section.get("content", "")
                    required_chandni = ["Head Office", "1159/1114", "Kucha Mahajani"]
                    missing_chandni = [term for term in required_chandni if term not in content]
                    
                    if not missing_chandni:
                        self.log("✅ Chandni Chowk address verified")
                    else:
                        self.log(f"❌ Chandni Chowk missing: {missing_chandni}")
                        success = False
                else:
                    self.log("❌ Chandni Chowk section not found")
                    success = False
                
                # Check Karol Bagh
                if karol_section:
                    content = karol_section.get("content", "")
                    required_karol = ["Branch Office", "20/2799", "Beadon Pura"]
                    missing_karol = [term for term in required_karol if term not in content]
                    
                    if not missing_karol:
                        self.log("✅ Karol Bagh address verified")
                    else:
                        self.log(f"❌ Karol Bagh missing: {missing_karol}")
                        success = False
                else:
                    self.log("❌ Karol Bagh section not found")
                    success = False
                
                return success
            else:
                self.log(f"❌ API call failed: {response.status_code}")
                return False
                
        except Exception as e:
            self.log(f"❌ Test failed: {str(e)}")
            return False

    def test_admin_add_item_wise_rate(self):
        """Test 3: Admin can add item-wise rate list entries"""
        self.log("\n➕ TEST 3: Admin Add Item-wise Rate Entry")
        
        if not self.admin_token:
            self.log("❌ No admin token available")
            return False
            
        admin_headers = {"Authorization": f"Bearer {self.admin_token}"}
        
        try:
            # Create test rate entry
            test_entry = {
                "metal_type": "silver",
                "item_name": "Test Silver Ring",
                "category": "Ring", 
                "purity": "92.5%",
                "wastage": "2%",
                "labour_kg": "₹1000/kg"
            }
            
            response = requests.post(f"{BASE_URL}/rate-list", 
                                   headers=admin_headers, 
                                   json=test_entry, 
                                   timeout=10)
            
            if response.status_code in [200, 201]:
                data = response.json()
                created_id = data.get("id")
                self.log("✅ Item-wise rate entry created successfully")
                self.log(f"    Created: {test_entry['item_name']} - {test_entry['category']}")
                
                # Store for cleanup
                if created_id:
                    self.created_test_items.append(("rate-list", created_id))
                
                # Verify it was created with correct fields
                if all(field in data for field in test_entry.keys()):
                    self.log("✅ All fields preserved in created entry")
                    return True
                else:
                    self.log("❌ Some fields missing in created entry")
                    return False
            else:
                self.log(f"❌ Creation failed: {response.status_code}")
                try:
                    error_data = response.json()
                    self.log(f"    Error: {error_data}")
                except:
                    pass
                return False
                
        except Exception as e:
            self.log(f"❌ Test failed: {str(e)}")
            return False

    def test_admin_manage_brands_poster(self):
        """Test 4: Admin can manage brands (poster-style)"""
        self.log("\n🎨 TEST 4: Admin Manage Brands (Poster-style)")
        
        if not self.admin_token:
            self.log("❌ No admin token available")
            return False
            
        admin_headers = {"Authorization": f"Bearer {self.admin_token}"}
        
        try:
            # Create test brand poster
            test_brand = {
                "name": "Test Brand Poster",
                "logo_url": "https://example.com/brand-poster.jpg"
            }
            
            response = requests.post(f"{BASE_URL}/brands", 
                                   headers=admin_headers, 
                                   json=test_brand, 
                                   timeout=10)
            
            if response.status_code in [200, 201]:
                data = response.json()
                created_id = data.get("id")
                self.log("✅ Brand poster created successfully")
                self.log(f"    Created: {test_brand['name']}")
                
                # Store for cleanup
                if created_id:
                    self.created_test_items.append(("brands", created_id))
                
                return True
            else:
                self.log(f"❌ Brand creation failed: {response.status_code}")
                try:
                    error_data = response.json()
                    self.log(f"    Error: {error_data}")
                except:
                    pass
                return False
                
        except Exception as e:
            self.log(f"❌ Test failed: {str(e)}")
            return False

    def test_cart_submit(self):
        """Test 5: Cart submit works"""
        self.log("\n🛒 TEST 5: Cart Submit Functionality")
        
        if not self.customer_token:
            self.log("❌ No customer token available")
            return False
            
        customer_headers = {"Authorization": f"Bearer {self.customer_token}"}
        
        try:
            # First get a valid product_id
            response = requests.get(f"{BASE_URL}/products?limit=1", timeout=10)
            if response.status_code != 200:
                self.log("❌ Failed to get products for cart test")
                return False
                
            products_data = response.json()
            products = products_data.get("products", [])
            if not products:
                self.log("❌ No products available for cart test")
                return False
                
            product_id = products[0].get("id")
            if not product_id:
                self.log("❌ Product has no ID")
                return False
            
            # Add to cart
            cart_item = {"product_id": product_id}
            response = requests.post(f"{BASE_URL}/cart/add", 
                                   headers=customer_headers, 
                                   json=cart_item, 
                                   timeout=10)
            
            if response.status_code in [200, 201]:
                self.log("✅ Item added to cart")
                
                # Submit cart
                submit_data = {"notes": "Test cart submission"}
                response = requests.post(f"{BASE_URL}/cart/submit", 
                                       headers=customer_headers, 
                                       json=submit_data,
                                       timeout=10)
                
                if response.status_code in [200, 201]:
                    self.log("✅ Cart submitted successfully")
                    return True
                else:
                    self.log(f"❌ Cart submit failed: {response.status_code}")
                    try:
                        error_data = response.json()
                        self.log(f"    Error: {error_data}")
                    except:
                        pass
                    return False
            else:
                self.log(f"❌ Add to cart failed: {response.status_code}")
                return False
                
        except Exception as e:
            self.log(f"❌ Test failed: {str(e)}")
            return False

    def test_existing_endpoints(self):
        """Test 6: Existing endpoints still work"""
        self.log("\n🔄 TEST 6: Existing Endpoints Functionality")
        
        endpoints_to_test = [
            ("/products", "Products endpoint"),
            ("/live-rates", "Live rates endpoint"),
            ("/schemes", "Schemes endpoint"), 
            ("/showroom", "Showroom endpoint"),
            ("/exhibitions", "Exhibitions endpoint")
        ]
        
        all_passed = True
        
        for endpoint, description in endpoints_to_test:
            try:
                response = requests.get(f"{BASE_URL}{endpoint}", timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    
                    # Special validation for live-rates
                    if endpoint == "/live-rates":
                        silver_dollar = data.get("silver_dollar", 0)
                        if isinstance(silver_dollar, (int, float)) and silver_dollar > 0:
                            self.log(f"✅ {description} - silver_dollar: ${silver_dollar}")
                        else:
                            self.log(f"❌ {description} - invalid silver_dollar: {silver_dollar}")
                            all_passed = False
                    else:
                        self.log(f"✅ {description}")
                else:
                    self.log(f"❌ {description} - Status: {response.status_code}")
                    all_passed = False
                    
            except Exception as e:
                self.log(f"❌ {description} - Error: {str(e)}")
                all_passed = False
        
        return all_passed

    def cleanup_test_items(self):
        """Clean up created test items"""
        if not self.created_test_items:
            return
            
        self.log("\n🧹 Cleaning up test data")
        admin_headers = {"Authorization": f"Bearer {self.admin_token}"}
        
        for endpoint, item_id in self.created_test_items:
            try:
                response = requests.delete(f"{BASE_URL}/{endpoint}/{item_id}", 
                                         headers=admin_headers, 
                                         timeout=10)
                if response.status_code in [200, 204]:
                    self.log(f"✅ Deleted {endpoint}/{item_id}")
                else:
                    self.log(f"❌ Failed to delete {endpoint}/{item_id}: {response.status_code}")
            except Exception as e:
                self.log(f"❌ Delete error {endpoint}/{item_id}: {str(e)}")

    def run_review_tests(self):
        """Run all review-specific tests"""
        self.log("🎯 Starting Yash Trade App Review Request Tests")
        self.log("="*60)
        
        # Authenticate first
        self.authenticate()
        
        # Run all 6 test suites
        test_results = {}
        
        test_results["silver_rate_item_wise"] = self.test_silver_rate_list_item_wise()
        test_results["office_addresses"] = self.test_office_addresses()
        test_results["admin_add_rate"] = self.test_admin_add_item_wise_rate()
        test_results["admin_manage_brands"] = self.test_admin_manage_brands_poster()
        test_results["cart_submit"] = self.test_cart_submit()
        test_results["existing_endpoints"] = self.test_existing_endpoints()
        
        # Cleanup
        self.cleanup_test_items()
        
        # Summary
        self.log("\n" + "="*60)
        self.log("📊 REVIEW TEST SUMMARY")
        
        total_tests = len(test_results)
        passed_tests = sum(1 for result in test_results.values() if result)
        failed_tests = total_tests - passed_tests
        
        self.log(f"Total Test Suites: {total_tests}")
        self.log(f"✅ Passed: {passed_tests}")
        self.log(f"❌ Failed: {failed_tests}")
        self.log(f"Success Rate: {(passed_tests/total_tests)*100:.1f}%")
        
        # Detail failed tests
        if failed_tests > 0:
            self.log("\n❌ FAILED TEST SUITES:")
            for test_name, result in test_results.items():
                if not result:
                    self.log(f"  - {test_name}")
        
        return failed_tests == 0

if __name__ == "__main__":
    runner = ReviewTestRunner()
    success = runner.run_review_tests()
    sys.exit(0 if success else 1)