#!/usr/bin/env python3
"""
Comprehensive Backend API Tests for Yash Trade App
Testing the jewelry business mobile app APIs with focus on NEW batch management and file upload features.
"""

import requests
import json
import io
import os
from pathlib import Path

# Configuration
BASE_URL = "https://jeweler-network-dev.preview.emergentagent.com/api"
print(f"Testing backend API at: {BASE_URL}")

class TestRunner:
    def __init__(self):
        self.session = requests.Session()
        self.admin_token = None
        self.executive_token = None
        self.customer_token = None
        self.test_batch_id = None
        self.test_image_id = None
        
    def setup_auth(self):
        """Set up authentication for different user types"""
        print("\n=== Authentication Setup ===")
        
        # Admin login
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
            
        # Executive login
        try:
            response = self.session.post(f"{BASE_URL}/auth/send-otp", json={"phone": "7777777777"})
            if response.status_code == 200:
                response = self.session.post(f"{BASE_URL}/auth/verify-otp", 
                                           json={"phone": "7777777777", "otp": "1234"})
                if response.status_code == 200:
                    self.executive_token = response.json()["token"]
                    user = response.json()["user"]
                    print(f"✅ Executive login successful: {user.get('name', 'Executive')} (role: {user.get('role')})")
                else:
                    print(f"❌ Executive OTP verification failed: {response.status_code}")
        except Exception as e:
            print(f"⚠️ Executive auth error (may not exist): {e}")
            
        # Customer login
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
                    print(f"❌ Customer OTP verification failed: {response.status_code}")
                    return False
        except Exception as e:
            print(f"❌ Customer auth error: {e}")
            return False
            
        return self.admin_token and self.customer_token

    def test_auth_endpoints(self):
        """Test authentication endpoints"""
        print("\n=== Testing Authentication Endpoints ===")
        
        # Test /auth/me with different tokens
        if self.admin_token:
            headers = {"Authorization": f"Bearer {self.admin_token}"}
            response = self.session.get(f"{BASE_URL}/auth/me", headers=headers)
            if response.status_code == 200:
                user = response.json()
                if user.get("role") == "admin":
                    print(f"✅ Admin /auth/me successful: {user.get('phone')} (role: {user.get('role')})")
                else:
                    print(f"❌ Admin role incorrect: expected 'admin', got '{user.get('role')}'")
                    return False
            else:
                print(f"❌ Admin /auth/me failed: {response.status_code}")
                return False
                
        if self.customer_token:
            headers = {"Authorization": f"Bearer {self.customer_token}"}
            response = self.session.get(f"{BASE_URL}/auth/me", headers=headers)
            if response.status_code == 200:
                user = response.json()
                print(f"✅ Customer /auth/me successful: {user.get('phone')} (role: {user.get('role')})")
            else:
                print(f"❌ Customer /auth/me failed: {response.status_code}")
                return False
                
        # Test invalid OTP
        response = self.session.post(f"{BASE_URL}/auth/verify-otp", 
                                   json={"phone": "9999999999", "otp": "0000"})
        if response.status_code == 400:
            print("✅ Invalid OTP correctly rejected")
        else:
            print(f"❌ Invalid OTP should be rejected, got: {response.status_code}")
            return False
            
        return True

    def test_batch_management(self):
        """Test NEW batch management features"""
        print("\n=== Testing Batch Management API (NEW CRITICAL FEATURE) ===")
        
        if not self.admin_token:
            print("❌ Admin token required for batch testing")
            return False
            
        headers = {"Authorization": f"Bearer {self.admin_token}"}
        
        # 1. POST /api/batches - Create batch
        batch_data = {
            "name": "Test Silver Batch",
            "metal_type": "silver", 
            "category": "payal"
        }
        
        response = self.session.post(f"{BASE_URL}/batches", json=batch_data, headers=headers)
        if response.status_code == 200:
            batch = response.json()
            self.test_batch_id = batch["id"]
            print(f"✅ Batch created successfully: {batch['name']} (ID: {batch['id'][:8]}...)")
            
            # Validate response fields
            expected_fields = ["id", "name", "metal_type", "category", "status", "image_count"]
            missing = [f for f in expected_fields if f not in batch]
            if missing:
                print(f"❌ Batch response missing fields: {missing}")
                return False
                
            if batch["status"] != "visible":
                print(f"❌ New batch should have status 'visible', got: {batch['status']}")
                return False
                
        else:
            print(f"❌ Batch creation failed: {response.status_code} - {response.text}")
            return False
        
        # 2. GET /api/batches - List batches
        response = self.session.get(f"{BASE_URL}/batches", headers=headers)
        if response.status_code == 200:
            data = response.json()
            if "batches" in data and len(data["batches"]) > 0:
                print(f"✅ Batch listing successful: {len(data['batches'])} batches found")
                # Verify our test batch is in the list
                found = any(b["id"] == self.test_batch_id for b in data["batches"])
                if found:
                    print("✅ Test batch found in batch list")
                else:
                    print("❌ Test batch not found in batch list")
                    return False
            else:
                print("❌ No batches found in listing")
                return False
        else:
            print(f"❌ Batch listing failed: {response.status_code}")
            return False
            
        # 3. GET /api/batches/{batch_id} - Get specific batch
        response = self.session.get(f"{BASE_URL}/batches/{self.test_batch_id}", headers=headers)
        if response.status_code == 200:
            batch = response.json()
            if batch["name"] == "Test Silver Batch":
                print(f"✅ Batch detail retrieval successful: {batch['name']}")
            else:
                print(f"❌ Batch name mismatch: expected 'Test Silver Batch', got '{batch['name']}'")
                return False
        else:
            print(f"❌ Batch detail failed: {response.status_code}")
            return False
            
        # 4. PUT /api/batches/{batch_id} - Update batch
        update_data = {
            "name": "Updated Test Batch",
            "metal_type": "gold"
        }
        response = self.session.put(f"{BASE_URL}/batches/{self.test_batch_id}", 
                                  json=update_data, headers=headers)
        if response.status_code == 200:
            batch = response.json()
            if batch["name"] == "Updated Test Batch" and batch["metal_type"] == "gold":
                print(f"✅ Batch update successful: {batch['name']} ({batch['metal_type']})")
            else:
                print(f"❌ Batch update failed: name={batch.get('name')}, metal={batch.get('metal_type')}")
                return False
        else:
            print(f"❌ Batch update failed: {response.status_code} - {response.text}")
            return False
            
        # 5. PATCH /api/batches/{batch_id}/visibility - Toggle visibility
        response = self.session.patch(f"{BASE_URL}/batches/{self.test_batch_id}/visibility", headers=headers)
        if response.status_code == 200:
            data = response.json()
            if data.get("status") == "hidden":
                print("✅ Batch visibility toggled to hidden")
            else:
                print(f"❌ Visibility toggle failed: expected 'hidden', got '{data.get('status')}'")
                return False
        else:
            print(f"❌ Visibility toggle failed: {response.status_code}")
            return False
            
        # Toggle back to visible
        response = self.session.patch(f"{BASE_URL}/batches/{self.test_batch_id}/visibility", headers=headers)
        if response.status_code == 200:
            data = response.json()
            if data.get("status") == "visible":
                print("✅ Batch visibility toggled back to visible")
            else:
                print(f"❌ Visibility toggle back failed: {data.get('status')}")
                return False
        else:
            print(f"❌ Visibility toggle back failed: {response.status_code}")
            return False
            
        return True

    def test_file_upload(self):
        """Test NEW file upload functionality"""
        print("\n=== Testing File Upload System (NEW CRITICAL FEATURE) ===")
        
        if not self.admin_token or not self.test_batch_id:
            print("❌ Admin token and test batch required for file upload testing")
            return False
            
        headers = {"Authorization": f"Bearer {self.admin_token}"}
        
        # Create a test image file
        try:
            from PIL import Image
            # Create a simple test image
            img = Image.new('RGB', (300, 200), color='red')
            img_bytes = io.BytesIO()
            img.save(img_bytes, format='JPEG', quality=85)
            img_bytes.seek(0)
            
            print("✅ Test image created (300x200 JPEG)")
        except ImportError:
            # Fallback: create a simple test file
            img_bytes = io.BytesIO()
            img_bytes.write(b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00\xff\xdb\x00C\x00')  # Minimal JPEG header
            img_bytes.seek(0)
            print("✅ Fallback test file created")
        
        # 1. POST /api/batches/{batch_id}/upload - Upload image file
        files = {"files": ("test_image.jpg", img_bytes, "image/jpeg")}
        
        # Remove Content-Type header for multipart upload
        upload_headers = {"Authorization": f"Bearer {self.admin_token}"}
        
        response = self.session.post(f"{BASE_URL}/batches/{self.test_batch_id}/upload", 
                                   files=files, headers=upload_headers)
        
        if response.status_code == 200:
            data = response.json()
            if data.get("uploaded", 0) > 0:
                print(f"✅ File upload successful: {data['uploaded']} file(s) uploaded")
                
                # Check response structure
                expected_fields = ["results", "uploaded", "failed", "batch_image_count"]
                missing = [f for f in expected_fields if f not in data]
                if missing:
                    print(f"❌ Upload response missing fields: {missing}")
                    return False
                    
                # Get the uploaded image ID from results
                if data["results"] and len(data["results"]) > 0:
                    result = data["results"][0]
                    if result.get("status") == "ok":
                        self.test_image_id = result.get("id")
                        print(f"✅ Image ID captured: {self.test_image_id}")
                    else:
                        print(f"❌ Upload result not OK: {result}")
                        return False
                        
            else:
                print(f"❌ No files uploaded: {data}")
                return False
        else:
            print(f"❌ File upload failed: {response.status_code} - {response.text}")
            return False
        
        # 2. GET /api/batches/{batch_id}/images - Verify uploaded image appears
        response = self.session.get(f"{BASE_URL}/batches/{self.test_batch_id}/images", headers=headers)
        if response.status_code == 200:
            data = response.json()
            if "images" in data and len(data["images"]) > 0:
                print(f"✅ Batch images retrieved: {len(data['images'])} images")
                
                # Find our uploaded image
                uploaded_image = None
                for img in data["images"]:
                    if img.get("id") == self.test_image_id:
                        uploaded_image = img
                        break
                        
                if uploaded_image:
                    # Verify image has required paths
                    if "storage_path" in uploaded_image and "thumbnail_path" in uploaded_image:
                        print("✅ Uploaded image has storage_path and thumbnail_path")
                        
                        # Test file serving
                        self.test_file_serving(uploaded_image)
                    else:
                        print(f"❌ Image missing paths: {uploaded_image}")
                        return False
                else:
                    print(f"❌ Uploaded image {self.test_image_id} not found in batch images")
                    return False
            else:
                print("❌ No images found in batch")
                return False
        else:
            print(f"❌ Batch images retrieval failed: {response.status_code}")
            return False
            
        return True

    def test_file_serving(self, image_data):
        """Test file serving endpoints"""
        print("\n--- Testing File Serving ---")
        
        storage_path = image_data.get("storage_path", "")
        thumbnail_path = image_data.get("thumbnail_path", "")
        
        if not storage_path or not thumbnail_path:
            print("❌ Missing file paths for serving test")
            return False
        
        # Test thumbnail serving
        response = self.session.get(f"{BASE_URL}/files/{thumbnail_path}")
        if response.status_code == 200:
            content_type = response.headers.get("Content-Type", "")
            if "image" in content_type.lower():
                print(f"✅ Thumbnail served successfully: {content_type}")
            else:
                print(f"❌ Thumbnail wrong content type: {content_type}")
                return False
        else:
            print(f"❌ Thumbnail serving failed: {response.status_code}")
            return False
            
        # Test original image serving
        response = self.session.get(f"{BASE_URL}/files/{storage_path}")
        if response.status_code == 200:
            content_type = response.headers.get("Content-Type", "")
            if "image" in content_type.lower():
                print(f"✅ Original image served successfully: {content_type}")
            else:
                print(f"❌ Original image wrong content type: {content_type}")
                return False
        else:
            print(f"❌ Original image serving failed: {response.status_code}")
            return False
            
        return True

    def test_batch_image_management(self):
        """Test batch image deletion"""
        print("\n=== Testing Batch Image Management ===")
        
        if not self.admin_token or not self.test_batch_id or not self.test_image_id:
            print("❌ Admin token, batch ID, and image ID required for image management testing")
            return False
            
        headers = {"Authorization": f"Bearer {self.admin_token}"}
        
        # POST /api/batches/{batch_id}/images/delete - Soft delete images
        delete_data = {"image_ids": [self.test_image_id]}
        
        response = self.session.post(f"{BASE_URL}/batches/{self.test_batch_id}/images/delete", 
                                   json=delete_data, headers=headers)
        
        if response.status_code == 200:
            data = response.json()
            if data.get("deleted", 0) > 0:
                print(f"✅ Image deletion successful: {data['deleted']} image(s) deleted")
            else:
                print(f"❌ No images deleted: {data}")
                return False
        else:
            print(f"❌ Image deletion failed: {response.status_code} - {response.text}")
            return False
            
        # Verify deleted images don't appear in batch images list
        response = self.session.get(f"{BASE_URL}/batches/{self.test_batch_id}/images", headers=headers)
        if response.status_code == 200:
            data = response.json()
            images = data.get("images", [])
            
            # Check if deleted image is still in list
            found_deleted = any(img.get("id") == self.test_image_id and not img.get("is_deleted") for img in images)
            if not found_deleted:
                print("✅ Deleted image not showing in batch images list")
            else:
                print("❌ Deleted image still appearing in batch images list")
                return False
        else:
            print(f"❌ Could not verify image deletion: {response.status_code}")
            return False
            
        return True

    def test_products_visibility_filtering(self):
        """Test product visibility filtering"""
        print("\n=== Testing Products with Visibility Filtering ===")
        
        # 1. GET /api/products - Should NOT include deleted/hidden products
        response = self.session.get(f"{BASE_URL}/products?limit=10")
        if response.status_code == 200:
            data = response.json()
            products = data.get("products", [])
            
            # Check that no products have visibility=hidden or is_deleted=true
            hidden_products = [p for p in products if p.get("visibility") == "hidden" or p.get("is_deleted")]
            if not hidden_products:
                print(f"✅ Product feed excludes hidden/deleted products ({len(products)} visible products)")
            else:
                print(f"❌ Product feed includes {len(hidden_products)} hidden/deleted products")
                return False
        else:
            print(f"❌ Product listing failed: {response.status_code}")
            return False
            
        # 2. Test batch visibility affects products
        if not self.admin_token or not self.test_batch_id:
            print("⚠️ Skipping batch visibility test (missing admin token or batch ID)")
            return True
            
        headers = {"Authorization": f"Bearer {self.admin_token}"}
        
        # Hide the batch
        response = self.session.patch(f"{BASE_URL}/batches/{self.test_batch_id}/visibility", headers=headers)
        if response.status_code == 200:
            # Check if products from this batch are now hidden
            response = self.session.get(f"{BASE_URL}/products?limit=50")
            if response.status_code == 200:
                products = response.json().get("products", [])
                batch_products = [p for p in products if p.get("batch_id") == self.test_batch_id]
                
                if not batch_products:
                    print("✅ Hidden batch products excluded from feed")
                else:
                    # Check if they're all marked as hidden
                    hidden = all(p.get("visibility") == "hidden" for p in batch_products)
                    if hidden:
                        print("✅ Batch products correctly hidden but still in results (expected)")
                    else:
                        print("❌ Batch products not properly hidden")
                        return False
            
            # Unhide the batch
            response = self.session.patch(f"{BASE_URL}/batches/{self.test_batch_id}/visibility", headers=headers)
            if response.status_code == 200:
                print("✅ Batch visibility toggling working correctly")
            else:
                print(f"❌ Could not unhide batch: {response.status_code}")
                return False
        else:
            print(f"❌ Could not hide batch for visibility test: {response.status_code}")
            return False
            
        return True

    def test_request_management(self):
        """Test request management enhancements"""
        print("\n=== Testing Request Management Enhancement ===")
        
        if not self.customer_token:
            print("❌ Customer token required for request testing")
            return False
            
        customer_headers = {"Authorization": f"Bearer {self.customer_token}"}
        
        # Create a test request first
        request_data = {
            "request_type": "call",
            "category": "payal",
            "preferred_time": "2:00 PM",
            "notes": "Test request for API testing"
        }
        
        response = self.session.post(f"{BASE_URL}/requests", json=request_data, headers=customer_headers)
        if response.status_code == 200:
            request_obj = response.json()
            request_id = request_obj["id"]
            print(f"✅ Test request created: {request_id[:8]}...")
        else:
            print(f"❌ Could not create test request: {response.status_code}")
            return False
        
        # Test admin/executive request updates
        if self.admin_token:
            admin_headers = {"Authorization": f"Bearer {self.admin_token}"}
            
            # PATCH /api/requests/{id} - Update with status and notes
            update_data = {
                "status": "contacted",
                "notes": "Called customer for payal inquiry - API test"
            }
            
            response = self.session.patch(f"{BASE_URL}/requests/{request_id}", 
                                        json=update_data, headers=admin_headers)
            if response.status_code == 200:
                updated_request = response.json()
                if (updated_request.get("status") == "contacted" and 
                    updated_request.get("admin_notes") == update_data["notes"]):
                    print("✅ Request status and notes update successful")
                else:
                    print(f"❌ Request update incomplete: {updated_request}")
                    return False
            else:
                print(f"❌ Request update failed: {response.status_code} - {response.text}")
                return False
            
            # GET /api/requests/{id}/history - Get request history with customer info
            response = self.session.get(f"{BASE_URL}/requests/{request_id}/history", headers=admin_headers)
            if response.status_code == 200:
                history_data = response.json()
                expected_fields = ["request", "customer", "past_requests"]
                missing = [f for f in expected_fields if f not in history_data]
                if not missing:
                    print(f"✅ Request history retrieved: customer info and {len(history_data.get('past_requests', []))} past requests")
                    
                    # Verify notes_history was created
                    request_detail = history_data.get("request", {})
                    notes_history = request_detail.get("notes_history", [])
                    if notes_history:
                        print(f"✅ Notes history created: {len(notes_history)} entries")
                    else:
                        print("⚠️ Notes history empty (may be expected)")
                        
                else:
                    print(f"❌ Request history missing fields: {missing}")
                    return False
            else:
                print(f"❌ Request history failed: {response.status_code}")
                return False
        else:
            print("⚠️ Skipping admin request operations (no admin token)")
            
        return True

    def test_rates_system(self):
        """Test rate system (regression)"""
        print("\n=== Testing Rate System (Regression) ===")
        
        # GET /api/rates/latest - 6-point rate system
        response = self.session.get(f"{BASE_URL}/rates/latest")
        if response.status_code == 200:
            rates = response.json()
            
            # Check for 6-point rate system
            expected_rate_fields = [
                "silver_dollar_rate", "silver_mcx_rate", "silver_physical_rate",
                "gold_dollar_rate", "gold_mcx_rate", "gold_physical_rate"
            ]
            
            missing = [f for f in expected_rate_fields if f not in rates]
            if not missing:
                print("✅ 6-point rate system working correctly")
                print(f"   Silver: Dollar ${rates['silver_dollar_rate']}, MCX ₹{rates['silver_mcx_rate']}, Physical ₹{rates['silver_physical_rate']}")
                print(f"   Gold: Dollar ${rates['gold_dollar_rate']}, MCX ₹{rates['gold_mcx_rate']}, Physical ₹{rates['gold_physical_rate']}")
            else:
                print(f"❌ Rate system missing fields: {missing}")
                return False
        else:
            print(f"❌ Rate retrieval failed: {response.status_code}")
            return False
            
        # Test admin rate updates
        if self.admin_token:
            headers = {"Authorization": f"Bearer {self.admin_token}"}
            
            rate_update = {
                "silver_physical_rate": 97.50,
                "gold_physical_rate": 7500.00,
                "market_summary": "API test rate update"
            }
            
            response = self.session.post(f"{BASE_URL}/rates", json=rate_update, headers=headers)
            if response.status_code == 200:
                print("✅ Admin rate update successful")
            else:
                print(f"❌ Admin rate update failed: {response.status_code}")
                return False
                
        # GET /api/rates/history
        response = self.session.get(f"{BASE_URL}/rates/history?days=7")
        if response.status_code == 200:
            history = response.json()
            if "rates" in history:
                print(f"✅ Rate history retrieved: {len(history['rates'])} entries")
            else:
                print("❌ Rate history missing rates field")
                return False
        else:
            print(f"❌ Rate history failed: {response.status_code}")
            return False
            
        return True

    def test_analytics_dashboard(self):
        """Test analytics dashboard enhancements"""
        print("\n=== Testing Analytics Dashboard Enhancement ===")
        
        if not self.admin_token:
            print("❌ Admin token required for analytics testing")
            return False
            
        headers = {"Authorization": f"Bearer {self.admin_token}"}
        
        # GET /api/analytics/dashboard - Should include total_batches and uploaded_images
        response = self.session.get(f"{BASE_URL}/analytics/dashboard", headers=headers)
        if response.status_code == 200:
            data = response.json()
            
            # Check for enhanced fields
            expected_fields = ["total_batches", "uploaded_images", "total_users", "total_products", "total_requests"]
            missing = [f for f in expected_fields if f not in data]
            
            if not missing:
                print(f"✅ Analytics dashboard enhanced correctly:")
                print(f"   Total Batches: {data['total_batches']}")
                print(f"   Uploaded Images: {data['uploaded_images']}")  
                print(f"   Total Products: {data['total_products']}")
                print(f"   Total Users: {data['total_users']}")
            else:
                print(f"❌ Analytics dashboard missing enhanced fields: {missing}")
                return False
        else:
            print(f"❌ Analytics dashboard failed: {response.status_code}")
            return False
            
        return True

    def test_bulk_upload_regression(self):
        """Test existing bulk upload still works"""
        print("\n=== Testing Bulk Upload Regression ===")
        
        if not self.admin_token:
            print("❌ Admin token required for bulk upload testing")
            return False
            
        headers = {"Authorization": f"Bearer {self.admin_token}"}
        
        # POST /api/products/bulk - URL-based bulk upload
        bulk_data = {
            "image_urls": [
                "https://images.unsplash.com/photo-1611652022419-a9419f74343d?w=600",
                "https://images.unsplash.com/photo-1679973296611-82470327c513?w=600"
            ],
            "metal_type": "silver",
            "category": "test_bulk",
            "batch_name": "API Test Bulk Upload",
            "visibility": "all"
        }
        
        response = self.session.post(f"{BASE_URL}/products/bulk", json=bulk_data, headers=headers)
        if response.status_code == 200:
            data = response.json()
            if data.get("count", 0) > 0:
                print(f"✅ Legacy bulk upload working: {data['count']} products created")
                print(f"   Batch ID: {data.get('batch_id', 'N/A')[:8]}...")
            else:
                print(f"❌ Bulk upload created no products: {data}")
                return False
        else:
            print(f"❌ Bulk upload failed: {response.status_code} - {response.text}")
            return False
            
        return True

    def test_pagination_and_filtering(self):
        """Test product pagination and filtering (regression)"""
        print("\n=== Testing Product Pagination & Filtering (Regression) ===")
        
        # Test pagination
        response = self.session.get(f"{BASE_URL}/products?page=1&limit=5")
        if response.status_code == 200:
            page1 = response.json()
            if "products" in page1 and "page" in page1:
                print(f"✅ Pagination working: Page {page1['page']}, {len(page1['products'])} products")
            else:
                print("❌ Pagination response structure invalid")
                return False
        else:
            print(f"❌ Pagination test failed: {response.status_code}")
            return False
            
        # Test category filter
        response = self.session.get(f"{BASE_URL}/products?category=payal")
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Category filter working: {len(data.get('products', []))} payal products")
        else:
            print(f"❌ Category filter failed: {response.status_code}")
            return False
            
        return True

    def cleanup_test_data(self):
        """Clean up test data"""
        print("\n=== Cleanup Test Data ===")
        
        if self.admin_token and self.test_batch_id:
            headers = {"Authorization": f"Bearer {self.admin_token}"}
            
            # Delete test batch (soft delete)
            response = self.session.delete(f"{BASE_URL}/batches/{self.test_batch_id}", headers=headers)
            if response.status_code == 200:
                print("✅ Test batch cleaned up")
            else:
                print(f"⚠️ Could not cleanup test batch: {response.status_code}")
                
    def run_all_tests(self):
        """Run all test suites"""
        print("🧪 Starting Yash Trade App Backend API Tests")
        print("=" * 60)
        
        # Setup
        if not self.setup_auth():
            print("💥 Authentication setup failed - cannot continue")
            return False
        
        test_results = []
        
        # Core authentication tests
        test_results.append(("Authentication Endpoints", self.test_auth_endpoints()))
        
        # NEW critical features
        test_results.append(("Batch Management API (NEW)", self.test_batch_management()))
        test_results.append(("File Upload System (NEW)", self.test_file_upload()))
        test_results.append(("Batch Image Management", self.test_batch_image_management()))
        
        # Product visibility and filtering
        test_results.append(("Products Visibility Filtering", self.test_products_visibility_filtering()))
        
        # Enhanced features
        test_results.append(("Request Management Enhancement", self.test_request_management()))
        
        # Regression tests
        test_results.append(("Rate System (Regression)", self.test_rates_system()))
        test_results.append(("Analytics Dashboard Enhancement", self.test_analytics_dashboard()))
        test_results.append(("Bulk Upload (Regression)", self.test_bulk_upload_regression()))
        test_results.append(("Pagination & Filtering (Regression)", self.test_pagination_and_filtering()))
        
        # Cleanup
        self.cleanup_test_data()
        
        # Summary
        print("\n" + "=" * 60)
        print("🏁 TEST SUMMARY")
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
            print("\n🎉 ALL TESTS PASSED! The Yash Trade App backend is working correctly.")
        else:
            print(f"\n⚠️ {failed} test(s) failed. Please check the issues above.")
            
        return failed == 0

if __name__ == "__main__":
    runner = TestRunner()
    success = runner.run_all_tests()
    
    if not success:
        exit(1)