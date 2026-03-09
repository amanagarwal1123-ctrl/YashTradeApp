#!/usr/bin/env python3
"""
Backend PDF Import Test Script for Yash Trade App
Testing PDF import functionality as per review request
"""

import requests
import json
import sys
import tempfile
import os
from datetime import datetime
import fitz  # PyMuPDF

# Configuration
BASE_URL = "https://gem-bulk-import.preview.emergentagent.com/api"
ADMIN_PHONE = "9999999999"
OTP = "1234"

class PDFImportTester:
    def __init__(self):
        self.admin_token = None
        self.test_batch_id = None
        
    def log(self, message):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")
        
    def authenticate_admin(self):
        """Get admin token"""
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
                role = data.get('user', {}).get('role', 'unknown')
                self.log(f"✅ Admin authenticated: {role}")
                return True
            else:
                self.log(f"❌ Admin auth failed: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            self.log(f"❌ Admin auth error: {str(e)}")
            return False
    
    def create_test_batch(self):
        """Create a batch for PDF testing"""
        try:
            headers = {"Authorization": f"Bearer {self.admin_token}"}
            batch_data = {
                "name": "PDF Import Test",
                "metal_type": "silver"
            }
            
            response = requests.post(f"{BASE_URL}/batches", 
                                   headers=headers, json=batch_data, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                self.test_batch_id = data.get("id")
                self.log(f"✅ Created test batch: {self.test_batch_id}")
                return True
            else:
                self.log(f"❌ Batch creation failed: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            self.log(f"❌ Batch creation error: {str(e)}")
            return False
    
    def create_test_pdf(self):
        """Create a 3-page test PDF using fitz library"""
        try:
            doc = fitz.open()
            for i in range(3):
                page = doc.new_page(width=595, height=842)
                tw = fitz.TextWriter(page.rect)
                tw.append((100, 400), f'Product {i+1}', fontsize=48)
                tw.write_text(page)
                page.draw_rect(fitz.Rect(100, 100, 495, 350), color=(0.8, 0.7, 0.2), fill=(0.9, 0.8, 0.3))
            
            doc.save('/tmp/test_import.pdf')
            doc.close()
            self.log(f"✅ Created test PDF: /tmp/test_import.pdf")
            return True
            
        except Exception as e:
            self.log(f"❌ PDF creation error: {str(e)}")
            return False
    
    def test_pdf_validation_with_invalid_file(self):
        """Test PDF validation with non-PDF file"""
        try:
            headers = {"Authorization": f"Bearer {self.admin_token}"}
            
            # Create a fake text file with enough content to pass size check
            fake_content = "This is not a PDF file. " * 20  # Make it larger than 100 bytes
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
                f.write(fake_content)
                fake_file_path = f.name
            
            try:
                with open(fake_file_path, 'rb') as f:
                    files = {'file': ('fake.pdf', f, 'application/pdf')}
                    response = requests.post(
                        f"{BASE_URL}/batches/{self.test_batch_id}/import-pdf",
                        headers=headers, files=files, timeout=30
                    )
                
                if response.status_code == 400 and ("Not a valid PDF file" in response.text or "File too small" in response.text):
                    self.log(f"✅ PDF validation working - correctly rejected non-PDF file")
                    return True
                else:
                    self.log(f"❌ PDF validation failed: {response.status_code} - {response.text}")
                    return False
            finally:
                os.unlink(fake_file_path)
                
        except Exception as e:
            self.log(f"❌ PDF validation test error: {str(e)}")
            return False
    
    def test_pdf_import(self):
        """Import the test PDF and verify response"""
        try:
            headers = {"Authorization": f"Bearer {self.admin_token}"}
            
            with open('/tmp/test_import.pdf', 'rb') as f:
                files = {'file': ('test_import.pdf', f, 'application/pdf')}
                response = requests.post(
                    f"{BASE_URL}/batches/{self.test_batch_id}/import-pdf",
                    headers=headers, files=files, timeout=60
                )
            
            if response.status_code == 200:
                data = response.json()
                total_pages = data.get("total_pages", 0)
                imported = data.get("imported", 0)
                failed = data.get("failed", 0)
                results = data.get("results", [])
                
                self.log(f"✅ PDF import successful")
                self.log(f"    Total pages: {total_pages}")
                self.log(f"    Imported: {imported}")
                self.log(f"    Failed: {failed}")
                self.log(f"    Results count: {len(results)}")
                
                # Verify expected response
                if total_pages == 3 and imported == 3 and failed == 0 and len(results) == 3:
                    all_ok = all(r.get("status") == "ok" for r in results)
                    if all_ok:
                        self.log(f"✅ PDF import response matches expectations")
                        return True
                    else:
                        self.log(f"❌ Some results not 'ok': {results}")
                        return False
                else:
                    self.log(f"❌ Unexpected response values")
                    return False
            else:
                self.log(f"❌ PDF import failed: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            self.log(f"❌ PDF import error: {str(e)}")
            return False
    
    def verify_products_created(self):
        """Verify products were created with source_type pdf_import"""
        try:
            headers = {"Authorization": f"Bearer {self.admin_token}"}
            
            response = requests.get(f"{BASE_URL}/batches/{self.test_batch_id}/images", 
                                  headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                images = data.get("images", [])
                
                pdf_imports = [img for img in images if img.get("source_type") == "pdf_import"]
                
                self.log(f"✅ Retrieved batch images: {len(images)} total")
                self.log(f"    PDF imports: {len(pdf_imports)}")
                
                if len(pdf_imports) == 3:
                    self.log(f"✅ Correct number of PDF import products created")
                    
                    # Check if all have source_type pdf_import
                    for i, img in enumerate(pdf_imports):
                        source_page = img.get("source_page")
                        title = img.get("title", "")
                        self.log(f"    Product {i+1}: {title} (page {source_page})")
                    
                    return True
                else:
                    self.log(f"❌ Expected 3 PDF import products, found {len(pdf_imports)}")
                    return False
            else:
                self.log(f"❌ Failed to get batch images: {response.status_code}")
                return False
                
        except Exception as e:
            self.log(f"❌ Product verification error: {str(e)}")
            return False
    
    def test_normal_image_upload(self):
        """Test that normal image upload still works"""
        try:
            headers = {"Authorization": f"Bearer {self.admin_token}"}
            
            # Create a new batch for testing normal upload
            batch_data = {"name": "Image Upload Test", "metal_type": "gold"}
            response = requests.post(f"{BASE_URL}/batches", 
                                   headers=headers, json=batch_data, timeout=10)
            
            if response.status_code != 200:
                self.log(f"❌ Could not create test batch for image upload")
                return False
                
            test_batch_id = response.json().get("id")
            
            try:
                # Create a small test image (1x1 pixel PNG)
                test_image_data = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xdb\x00\x00\x00\x00IEND\xaeB`\x82'
                
                # Note: Upload endpoint expects 'files' (plural) parameter
                files = {'files': ('test_image.png', test_image_data, 'image/png')}
                response = requests.post(
                    f"{BASE_URL}/batches/{test_batch_id}/upload",
                    headers=headers, files=files, timeout=30
                )
                
                if response.status_code == 200:
                    data = response.json()
                    uploaded = data.get("uploaded", 0)
                    total_results = len(data.get("results", []))
                    self.log(f"✅ Normal image upload still works")
                    self.log(f"    Uploaded: {uploaded}, Total results: {total_results}")
                    return True
                else:
                    self.log(f"❌ Normal image upload failed: {response.status_code} - {response.text}")
                    return False
            finally:
                # Clean up the test batch
                requests.delete(f"{BASE_URL}/batches/{test_batch_id}", headers=headers, timeout=10)
                
        except Exception as e:
            self.log(f"❌ Normal image upload error: {str(e)}")
            return False
    
    def cleanup_test_batch(self):
        """Delete the test batch"""
        try:
            if not self.test_batch_id:
                return True
                
            headers = {"Authorization": f"Bearer {self.admin_token}"}
            response = requests.delete(f"{BASE_URL}/batches/{self.test_batch_id}", 
                                     headers=headers, timeout=10)
            
            if response.status_code == 200:
                self.log(f"✅ Test batch cleaned up: {self.test_batch_id}")
                return True
            else:
                self.log(f"❌ Batch cleanup failed: {response.status_code}")
                return False
                
        except Exception as e:
            self.log(f"❌ Batch cleanup error: {str(e)}")
            return False
    
    def run_pdf_import_tests(self):
        """Run complete PDF import test flow"""
        self.log("🚀 Starting PDF Import Tests for Yash Trade App")
        self.log("="*60)
        
        # Track test results
        results = []
        
        # Step 1: Authenticate
        self.log("\n🔐 Step 1: Admin Authentication")
        success = self.authenticate_admin()
        results.append(("Admin Authentication", success))
        if not success:
            self.log("❌ Cannot proceed without admin authentication")
            return False
        
        # Step 2: Create test batch
        self.log("\n📦 Step 2: Create Test Batch")
        success = self.create_test_batch()
        results.append(("Create Test Batch", success))
        if not success:
            return False
        
        # Step 3: Create test PDF
        self.log("\n📄 Step 3: Create Test PDF")
        success = self.create_test_pdf()
        results.append(("Create Test PDF", success))
        if not success:
            return False
        
        # Step 4: Test PDF validation
        self.log("\n🚫 Step 4: Test PDF Validation (Non-PDF File)")
        success = self.test_pdf_validation_with_invalid_file()
        results.append(("PDF Validation Test", success))
        
        # Step 5: Import test PDF
        self.log("\n📥 Step 5: Import Test PDF")
        success = self.test_pdf_import()
        results.append(("PDF Import", success))
        
        # Step 6: Verify products created
        self.log("\n✔️ Step 6: Verify Products Created")
        success = self.verify_products_created()
        results.append(("Verify Products Created", success))
        
        # Step 7: Test normal image upload still works
        self.log("\n🖼️ Step 7: Test Normal Image Upload")
        success = self.test_normal_image_upload()
        results.append(("Normal Image Upload Test", success))
        
        # Step 8: Cleanup
        self.log("\n🧹 Step 8: Cleanup Test Data")
        success = self.cleanup_test_batch()
        results.append(("Cleanup Test Batch", success))
        
        # Summary
        self.log("\n" + "="*60)
        self.log("📊 PDF IMPORT TEST SUMMARY")
        
        total_tests = len(results)
        passed_tests = len([r for r in results if r[1]])
        failed_tests = total_tests - passed_tests
        
        for test_name, success in results:
            status = "✅ PASS" if success else "❌ FAIL"
            self.log(f"  {status}: {test_name}")
        
        self.log(f"\nTotal Tests: {total_tests}")
        self.log(f"✅ Passed: {passed_tests}")
        self.log(f"❌ Failed: {failed_tests}")
        self.log(f"Success Rate: {(passed_tests/total_tests)*100:.1f}%")
        
        if failed_tests == 0:
            self.log("\n🎉 ALL PDF IMPORT TESTS PASSED!")
            return True
        else:
            self.log(f"\n❌ {failed_tests} TEST(S) FAILED")
            return False

if __name__ == "__main__":
    tester = PDFImportTester()
    success = tester.run_pdf_import_tests()
    sys.exit(0 if success else 1)