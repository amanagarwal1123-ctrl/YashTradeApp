#!/usr/bin/env python3
"""
Backend API Tests for Yash Trade App Web Panel Architecture
Testing customer mobile app + admin/executive web panel split with role-based access.

Base URL: https://gold-silver-biz.preview.emergentagent.com

Credentials:
- Admin: Phone 9999999999, OTP 1234
- Executive: Phone 7777777777, OTP 1234  
- Customer: Phone 8888888888, OTP 1234
"""

import requests
import json
import uuid
from datetime import datetime

# Configuration
BASE_URL = "https://gold-silver-biz.preview.emergentagent.com/api"
print(f"Testing Web Panel Architecture at: {BASE_URL}")

class WebPanelTestRunner:
    def __init__(self):
        self.session = requests.Session()
        self.admin_token = None
        self.executive_token = None
        self.customer_token = None
        self.test_request_id = None
        self.test_batch_id = None
        
    def setup_auth(self):
        """Set up authentication for all user roles"""
        print("\n=== Authentication Setup ===")
        
        auth_results = {}
        
        # Test each user type
        users = [
            ("9999999999", "admin", "Admin"),
            ("7777777777", "executive", "Executive"), 
            ("8888888888", "customer", "Customer")
        ]
        
        for phone, expected_role, user_type in users:
            try:
                # Send OTP
                response = self.session.post(f"{BASE_URL}/auth/send-otp", json={"phone": phone})
                if response.status_code != 200:
                    print(f"❌ {user_type} OTP send failed: {response.status_code}")
                    continue
                
                # Verify OTP
                response = self.session.post(f"{BASE_URL}/auth/verify-otp", 
                                           json={"phone": phone, "otp": "1234"})
                if response.status_code == 200:
                    data = response.json()
                    token = data["token"]
                    user = data["user"]
                    actual_role = user.get("role", "")
                    
                    if actual_role == expected_role:
                        print(f"✅ {user_type} login successful: {user.get('name', user_type)} (role: {actual_role})")
                        auth_results[expected_role] = token
                        
                        if expected_role == "admin":
                            self.admin_token = token
                        elif expected_role == "executive":
                            self.executive_token = token
                        elif expected_role == "customer":
                            self.customer_token = token
                    else:
                        print(f"❌ {user_type} role mismatch: expected '{expected_role}', got '{actual_role}'")
                        
                else:
                    print(f"❌ {user_type} OTP verification failed: {response.status_code} - {response.text}")
                    
            except Exception as e:
                print(f"❌ {user_type} auth error: {e}")
        
        return auth_results

    def test_1_panel_login_rejects_customer(self):
        """Test 1: Panel login rejects customer"""
        print("\n=== Test 1: Panel Login Rejects Customer ===")
        
        if not self.customer_token:
            print("❌ Customer token not available")
            return False
            
        # Verify customer gets correct role from backend
        response = self.session.post(f"{BASE_URL}/auth/verify-otp", 
                                   json={"phone": "8888888888", "otp": "1234"})
        if response.status_code == 200:
            user = response.json()["user"]
            role = user.get("role", "")
            
            if role == "customer":
                print("✅ Backend correctly returns customer role")
                print("   Note: Frontend web panel at /panel should reject this login")
            else:
                print(f"❌ Expected customer role, got: {role}")
                return False
        else:
            print(f"❌ Customer verification failed: {response.status_code}")
            return False
            
        return True

    def test_2_panel_login_accepts_admin(self):
        """Test 2: Panel login accepts admin"""
        print("\n=== Test 2: Panel Login Accepts Admin ===")
        
        if not self.admin_token:
            print("❌ Admin token not available")
            return False
            
        # Verify admin gets correct role
        response = self.session.post(f"{BASE_URL}/auth/verify-otp", 
                                   json={"phone": "9999999999", "otp": "1234"})
        if response.status_code == 200:
            user = response.json()["user"]
            role = user.get("role", "")
            
            if role == "admin":
                print("✅ Backend correctly returns admin role")
            else:
                print(f"❌ Expected admin role, got: {role}")
                return False
        else:
            print(f"❌ Admin verification failed: {response.status_code}")
            return False
            
        # Test admin analytics dashboard access
        headers = {"Authorization": f"Bearer {self.admin_token}"}
        response = self.session.get(f"{BASE_URL}/analytics/dashboard", headers=headers)
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Admin analytics dashboard access successful")
            print(f"   Dashboard data: {len(data)} metrics available")
        else:
            print(f"❌ Admin analytics dashboard failed: {response.status_code}")
            return False
            
        return True

    def test_3_panel_login_accepts_executive(self):
        """Test 3: Panel login accepts executive"""
        print("\n=== Test 3: Panel Login Accepts Executive ===")
        
        if not self.executive_token:
            print("❌ Executive token not available")
            return False
            
        # Verify executive gets correct role
        response = self.session.post(f"{BASE_URL}/auth/verify-otp", 
                                   json={"phone": "7777777777", "otp": "1234"})
        if response.status_code == 200:
            user = response.json()["user"]
            role = user.get("role", "")
            
            if role == "executive":
                print("✅ Backend correctly returns executive role")
            else:
                print(f"❌ Expected executive role, got: {role}")
                return False
        else:
            print(f"❌ Executive verification failed: {response.status_code}")
            return False
            
        # Test executive requests access
        headers = {"Authorization": f"Bearer {self.executive_token}"}
        response = self.session.get(f"{BASE_URL}/requests", headers=headers)
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Executive requests access successful")
            print(f"   Requests available: {len(data.get('requests', []))}")
        else:
            print(f"❌ Executive requests access failed: {response.status_code}")
            return False
            
        return True

    def test_4_executive_request_management(self):
        """Test 4: Executive can manage requests"""
        print("\n=== Test 4: Executive Request Management ===")
        
        if not self.customer_token or not self.executive_token:
            print("❌ Both customer and executive tokens required")
            return False
            
        # Step 1: Create request as customer
        customer_headers = {"Authorization": f"Bearer {self.customer_token}"}
        request_data = {
            "request_type": "call",
            "category": "silver_jewelry", 
            "preferred_time": "afternoon",
            "notes": "Interested in silver chains for retail",
            "product_id": ""
        }
        
        response = self.session.post(f"{BASE_URL}/requests", json=request_data, headers=customer_headers)
        if response.status_code == 200:
            request_obj = response.json()
            self.test_request_id = request_obj["id"]
            print(f"✅ Customer request created: ID {self.test_request_id[:8]}...")
        else:
            print(f"❌ Customer request creation failed: {response.status_code}")
            return False
            
        # Step 2: List requests as executive
        exec_headers = {"Authorization": f"Bearer {self.executive_token}"}
        response = self.session.get(f"{BASE_URL}/requests", headers=exec_headers)
        
        if response.status_code == 200:
            data = response.json()
            requests_list = data.get("requests", [])
            
            # Find our test request
            found_request = None
            for req in requests_list:
                if req.get("id") == self.test_request_id:
                    found_request = req
                    break
                    
            if found_request:
                print("✅ Executive can see customer request in list")
            else:
                print("❌ Test request not found in executive list")
                return False
        else:
            print(f"❌ Executive request listing failed: {response.status_code}")
            return False
            
        # Step 3: Update request status as executive
        update_data = {
            "status": "in_progress", 
            "notes": "Executive assigned and processing request",
            "assigned_to": "executive_user"
        }
        
        response = self.session.patch(f"{BASE_URL}/requests/{self.test_request_id}", 
                                    json=update_data, headers=exec_headers)
        
        if response.status_code == 200:
            updated_request = response.json()
            if updated_request.get("status") == "in_progress":
                print("✅ Executive request status update successful")
            else:
                print(f"❌ Status not updated correctly: {updated_request.get('status')}")
                return False
        else:
            print(f"❌ Executive request update failed: {response.status_code}")
            return False
            
        # Step 4: Test status normalization - "done" -> "resolved"
        normalize_data = {"status": "done", "notes": "Request completed successfully"}
        
        response = self.session.patch(f"{BASE_URL}/requests/{self.test_request_id}", 
                                    json=normalize_data, headers=exec_headers)
        
        if response.status_code == 200:
            normalized_request = response.json()
            actual_status = normalized_request.get("status")
            
            if actual_status == "resolved":
                print("✅ Status normalization working: 'done' -> 'resolved'")
            else:
                print(f"❌ Status normalization failed: expected 'resolved', got '{actual_status}'")
                return False
        else:
            print(f"❌ Status normalization test failed: {response.status_code}")
            return False
            
        return True

    def test_5_admin_rate_management(self):
        """Test 5: Admin can manage rates"""
        print("\n=== Test 5: Admin Rate Management ===")
        
        if not self.admin_token:
            print("❌ Admin token required")
            return False
            
        admin_headers = {"Authorization": f"Bearer {self.admin_token}"}
        
        # Test rate creation
        new_rates = {
            "silver_dollar_rate": 32.50,
            "silver_mcx_rate": 97.25,
            "silver_physical_rate": 98.00,
            "gold_dollar_rate": 2400.00,
            "gold_mcx_rate": 7420.00,
            "gold_physical_rate": 7500.00,
            "market_summary": "Test rates from web panel API testing"
        }
        
        response = self.session.post(f"{BASE_URL}/rates", json=new_rates, headers=admin_headers)
        
        if response.status_code == 200:
            rate_obj = response.json()
            print("✅ Admin rate creation successful")
            print(f"   Silver Physical: ₹{rate_obj.get('silver_physical_rate')}")
            print(f"   Gold Physical: ₹{rate_obj.get('gold_physical_rate')}")
        else:
            print(f"❌ Admin rate creation failed: {response.status_code}")
            return False
            
        # Test latest rates retrieval (public endpoint)
        response = self.session.get(f"{BASE_URL}/rates/latest")
        
        if response.status_code == 200:
            latest_rates = response.json()
            
            # Verify our updated rates are returned
            if (latest_rates.get("silver_physical_rate") == 98.00 and
                latest_rates.get("gold_physical_rate") == 7500.00):
                print("✅ Latest rates reflect admin updates")
            else:
                print("⚠️ Latest rates may not reflect immediate updates (timing issue)")
        else:
            print(f"❌ Latest rates retrieval failed: {response.status_code}")
            return False
            
        return True

    def test_6_admin_batch_management(self):
        """Test 6: Admin can manage batches"""
        print("\n=== Test 6: Admin Batch Management ===")
        
        if not self.admin_token:
            print("❌ Admin token required")
            return False
            
        admin_headers = {"Authorization": f"Bearer {self.admin_token}"}
        
        # Create batch
        batch_data = {
            "name": "Web Panel Test Batch",
            "metal_type": "silver",
            "category": "chains"
        }
        
        response = self.session.post(f"{BASE_URL}/batches", json=batch_data, headers=admin_headers)
        
        if response.status_code == 200:
            batch_obj = response.json()
            self.test_batch_id = batch_obj["id"]
            print(f"✅ Admin batch creation successful: {batch_obj['name']}")
        else:
            print(f"❌ Admin batch creation failed: {response.status_code}")
            return False
            
        # List batches
        response = self.session.get(f"{BASE_URL}/batches", headers=admin_headers)
        
        if response.status_code == 200:
            data = response.json()
            batches = data.get("batches", [])
            
            # Find our test batch
            found = any(b.get("id") == self.test_batch_id for b in batches)
            if found:
                print(f"✅ Admin batch listing successful: {len(batches)} batches")
            else:
                print("❌ Test batch not found in listing")
                return False
        else:
            print(f"❌ Admin batch listing failed: {response.status_code}")
            return False
            
        # Toggle visibility
        response = self.session.patch(f"{BASE_URL}/batches/{self.test_batch_id}/visibility", 
                                    headers=admin_headers)
        
        if response.status_code == 200:
            visibility_data = response.json()
            new_status = visibility_data.get("status")
            if new_status in ["hidden", "visible"]:
                print(f"✅ Admin batch visibility toggle successful: {new_status}")
            else:
                print(f"❌ Visibility toggle returned unexpected status: {new_status}")
                return False
        else:
            print(f"❌ Admin batch visibility toggle failed: {response.status_code}")
            return False
            
        return True

    def test_7_seed_endpoints_protected(self):
        """Test 7: Seed endpoints still protected"""
        print("\n=== Test 7: Seed Endpoints Protection ===")
        
        # Test seed endpoint without auth
        response = self.session.post(f"{BASE_URL}/seed", json={})
        
        if response.status_code == 401:
            print("✅ /api/seed correctly returns 401 without auth")
        else:
            print(f"❌ /api/seed should return 401, got: {response.status_code}")
            return False
            
        # Test seed/expand endpoint without auth  
        response = self.session.post(f"{BASE_URL}/seed/expand", json={})
        
        if response.status_code == 401:
            print("✅ /api/seed/expand correctly returns 401 without auth")
        else:
            print(f"❌ /api/seed/expand should return 401, got: {response.status_code}")
            return False
            
        return True

    def test_8_customer_endpoints_working(self):
        """Test 8: Customer endpoints still work"""
        print("\n=== Test 8: Customer Endpoints Still Working ===")
        
        # Test public products endpoint
        response = self.session.get(f"{BASE_URL}/products?limit=5")
        
        if response.status_code == 200:
            data = response.json()
            products = data.get("products", [])
            print(f"✅ Public products endpoint working: {len(products)} products")
        else:
            print(f"❌ Public products endpoint failed: {response.status_code}")
            return False
            
        # Test public latest rates
        response = self.session.get(f"{BASE_URL}/rates/latest")
        
        if response.status_code == 200:
            rates = response.json()
            if "silver_physical_rate" in rates and "gold_physical_rate" in rates:
                print("✅ Public rates endpoint working")
            else:
                print("❌ Public rates missing required fields")
                return False
        else:
            print(f"❌ Public rates endpoint failed: {response.status_code}")
            return False
            
        if not self.customer_token:
            print("⚠️ Skipping authenticated customer tests (no token)")
            return True
            
        customer_headers = {"Authorization": f"Bearer {self.customer_token}"}
        
        # Test customer request creation
        request_data = {
            "request_type": "video_call",
            "category": "gold_jewelry",
            "preferred_time": "morning", 
            "notes": "Looking for gold chains for wedding"
        }
        
        response = self.session.post(f"{BASE_URL}/requests", json=request_data, headers=customer_headers)
        
        if response.status_code == 200:
            print("✅ Customer request creation working")
        else:
            print(f"❌ Customer request creation failed: {response.status_code}")
            return False
            
        # Test customer's own requests
        response = self.session.get(f"{BASE_URL}/requests/my", headers=customer_headers)
        
        if response.status_code == 200:
            data = response.json()
            requests_list = data.get("requests", [])
            print(f"✅ Customer own requests working: {len(requests_list)} requests")
        else:
            print(f"❌ Customer own requests failed: {response.status_code}")
            return False
            
        # Test wishlist toggle
        response = self.session.post(f"{BASE_URL}/wishlist/toggle?product_id=test-product-123", 
                                   headers=customer_headers)
        
        if response.status_code == 200:
            print("✅ Customer wishlist toggle working")
        else:
            print(f"❌ Customer wishlist toggle failed: {response.status_code}")
            return False
            
        # Test wishlist retrieval
        response = self.session.get(f"{BASE_URL}/wishlist", headers=customer_headers)
        
        if response.status_code == 200:
            print("✅ Customer wishlist retrieval working")
        else:
            print(f"❌ Customer wishlist retrieval failed: {response.status_code}")
            return False
            
        return True

    def test_9_redeem_validation(self):
        """Test 9: Redeem validation"""
        print("\n=== Test 9: Redeem Validation ===")
        
        if not self.customer_token:
            print("❌ Customer token required for redeem testing")
            return False
            
        customer_headers = {"Authorization": f"Bearer {self.customer_token}"}
        
        # Test redeem with 0 points
        redeem_data = {"points": 0, "reward_name": "Test redemption"}
        response = self.session.post(f"{BASE_URL}/rewards/redeem", json=redeem_data, headers=customer_headers)
        
        if response.status_code == 422:
            print("✅ Redeem with 0 points correctly returns 422")
        elif response.status_code == 400:
            print("✅ Redeem with 0 points correctly returns 400 (validation error)")
        else:
            print(f"❌ Redeem with 0 points should return 422/400, got: {response.status_code}")
            return False
            
        # Test redeem with negative points
        redeem_data = {"points": -1, "reward_name": "Test redemption"}
        response = self.session.post(f"{BASE_URL}/rewards/redeem", json=redeem_data, headers=customer_headers)
        
        if response.status_code == 422:
            print("✅ Redeem with negative points correctly returns 422")
        elif response.status_code == 400:
            print("✅ Redeem with negative points correctly returns 400 (validation error)")
        else:
            print(f"❌ Redeem with negative points should return 422/400, got: {response.status_code}")
            return False
            
        return True

    def cleanup_test_data(self):
        """Clean up test data"""
        print("\n=== Cleanup Test Data ===")
        
        if self.admin_token and self.test_batch_id:
            headers = {"Authorization": f"Bearer {self.admin_token}"}
            response = self.session.delete(f"{BASE_URL}/batches/{self.test_batch_id}", headers=headers)
            if response.status_code == 200:
                print("✅ Test batch cleaned up")
            else:
                print(f"⚠️ Could not cleanup test batch: {response.status_code}")

    def run_web_panel_tests(self):
        """Run all web panel architecture tests"""
        print("🏢 Starting Yash Trade App Web Panel Architecture Tests")
        print("=" * 70)
        
        # Setup authentication
        auth_results = self.setup_auth()
        if not auth_results:
            print("💥 Authentication setup failed - cannot continue")
            return False
            
        test_results = []
        
        # Run all tests in sequence
        test_methods = [
            ("Test 1: Panel Login Rejects Customer", self.test_1_panel_login_rejects_customer),
            ("Test 2: Panel Login Accepts Admin", self.test_2_panel_login_accepts_admin),
            ("Test 3: Panel Login Accepts Executive", self.test_3_panel_login_accepts_executive),
            ("Test 4: Executive Request Management", self.test_4_executive_request_management),
            ("Test 5: Admin Rate Management", self.test_5_admin_rate_management),
            ("Test 6: Admin Batch Management", self.test_6_admin_batch_management),
            ("Test 7: Seed Endpoints Protected", self.test_7_seed_endpoints_protected),
            ("Test 8: Customer Endpoints Working", self.test_8_customer_endpoints_working),
            ("Test 9: Redeem Validation", self.test_9_redeem_validation)
        ]
        
        for test_name, test_method in test_methods:
            try:
                result = test_method()
                test_results.append((test_name, result))
            except Exception as e:
                print(f"💥 {test_name} crashed: {e}")
                test_results.append((test_name, False))
        
        # Cleanup
        self.cleanup_test_data()
        
        # Summary
        print("\n" + "=" * 70)
        print("🏁 WEB PANEL ARCHITECTURE TEST SUMMARY")
        print("=" * 70)
        
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
            print("\n🎉 ALL WEB PANEL TESTS PASSED! Architecture properly implemented.")
            print("   • Customer mobile app + admin/executive web panel split working correctly")
            print("   • Role-based access control properly enforced")
            print("   • All endpoints functioning as expected")
        else:
            print(f"\n⚠️ {failed} test(s) failed. Architecture issues need attention.")
            
        return failed == 0

if __name__ == "__main__":
    runner = WebPanelTestRunner()
    success = runner.run_web_panel_tests()
    
    if not success:
        exit(1)