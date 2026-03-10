#!/usr/bin/env python3
"""
Comprehensive Chunked PDF Upload Test
Testing all review request requirements with proper validation.
"""

import requests
import fitz  # PyMuPDF
import os
import io
import time
import json
from typing import Dict, List, Any

# Configuration
BASE_URL = "https://yash-tryon-test.preview.emergentagent.com/api"
ADMIN_PHONE = "9999999999"
ADMIN_OTP = "1234"

class ComprehensiveChunkedUploadTest:
    def __init__(self):
        self.session = requests.Session()
        self.auth_token = None
        self.batch_id = None
        
    def authenticate(self) -> bool:
        """Authenticate as admin user"""
        try:
            response = self.session.post(f"{BASE_URL}/auth/send-otp", json={"phone": ADMIN_PHONE})
            if response.status_code != 200:
                return False
            
            response = self.session.post(f"{BASE_URL}/auth/verify-otp", json={"phone": ADMIN_PHONE, "otp": ADMIN_OTP})
            if response.status_code != 200:
                return False
            
            data = response.json()
            self.auth_token = data.get("token")
            self.session.headers.update({"Authorization": f"Bearer {self.auth_token}"})
            print(f"✅ Authenticated as admin (9999999999)")
            return True
            
        except Exception as e:
            print(f"❌ Authentication failed: {str(e)}")
            return False
    
    def create_test_batch(self) -> bool:
        """Create a test batch for uploads"""
        try:
            response = self.session.post(f"{BASE_URL}/batches", json={
                "name": "Chunked Upload Review Test",
                "metal_type": "silver",
                "category": "test"
            })
            if response.status_code != 200:
                return False
            
            data = response.json()
            self.batch_id = data.get("id")
            print(f"✅ Created test batch: {self.batch_id}")
            return True
            
        except Exception as e:
            print(f"❌ Batch creation failed: {str(e)}")
            return False
    
    def create_test_pdf(self, pages: int) -> bytes:
        """Create a test PDF with specified pages"""
        try:
            doc = fitz.open()
            for i in range(pages):
                page = doc.new_page()
                text = f"Test Page {i + 1} of {pages}\n\nThis is test content for chunked upload validation.\nPage created for testing PDF import functionality."
                rect = fitz.Rect(72, 72, 500, 700)
                page.insert_textbox(rect, text, fontsize=12, fontname="helv")
            
            pdf_bytes = doc.tobytes()
            doc.close()
            print(f"✅ Created {pages}-page PDF: {len(pdf_bytes)} bytes")
            return pdf_bytes
            
        except Exception as e:
            print(f"❌ PDF creation failed: {str(e)}")
            return b""
    
    def test_1_resume_upload_support(self) -> bool:
        """Test 1: Resume Upload Support - Init with 3 chunks, upload 0 and 1, verify status"""
        print("\n📋 TEST 1: Resume Upload Support")
        print("Testing server-side chunk tracking for resume functionality")
        
        try:
            # Create PDF and force 3+ chunks by setting total_chunks parameter
            pdf_data = self.create_test_pdf(5)
            if not pdf_data:
                return False
            
            # Force 3 chunks regardless of actual file size for testing
            forced_total_chunks = 3
            
            # Step 1: Initialize upload session with 3 chunks
            init_response = self.session.post(f"{BASE_URL}/pdf-upload/init", json={
                "batch_id": self.batch_id,
                "filename": "resume_test.pdf",
                "file_size": len(pdf_data),
                "total_chunks": forced_total_chunks
            })
            
            if init_response.status_code != 200:
                print(f"❌ Init upload failed: {init_response.status_code}")
                return False
            
            init_data = init_response.json()
            upload_id = init_data["upload_id"]
            chunk_size = init_data["chunk_size"]
            print(f"✅ Upload initialized: {upload_id} (3 chunks)")
            
            # Step 2: Upload only chunk 0 and chunk 1 (skip chunk 2)
            for chunk_index in [0, 1]:
                # Create appropriate chunk data
                if chunk_index == 0:
                    chunk_data = pdf_data[:min(chunk_size, len(pdf_data))]
                else:
                    # For chunk 1, use remaining data or create dummy data
                    start = min(chunk_size, len(pdf_data))
                    if start < len(pdf_data):
                        chunk_data = pdf_data[start:]
                    else:
                        chunk_data = b"dummy_chunk_data_for_testing"
                
                files = {'file': ('chunk', io.BytesIO(chunk_data), 'application/octet-stream')}
                upload_response = self.session.post(
                    f"{BASE_URL}/pdf-upload/{upload_id}/chunk?chunk_index={chunk_index}",
                    files=files
                )
                
                if upload_response.status_code != 200:
                    print(f"❌ Chunk {chunk_index} upload failed: {upload_response.status_code}")
                    return False
                
                print(f"✅ Uploaded chunk {chunk_index}")
            
            # Step 3: Call GET /api/pdf-upload/{upload_id}/status and verify
            status_response = self.session.get(f"{BASE_URL}/pdf-upload/{upload_id}/status")
            if status_response.status_code != 200:
                print(f"❌ Status check failed: {status_response.status_code}")
                return False
            
            status_data = status_response.json()
            print(f"📊 Status Response:")
            
            # Verify exact requirements from review request
            success = True
            requirements_met = []
            
            # Requirement: upload_status is "uploading"
            if status_data.get("upload_status") == "uploading":
                requirements_met.append("✅ upload_status is 'uploading'")
            else:
                requirements_met.append(f"❌ upload_status is '{status_data.get('upload_status')}', expected 'uploading'")
                success = False
            
            # Requirement: chunks_received is 2
            if status_data.get("chunks_received") == 2:
                requirements_met.append("✅ chunks_received is 2")
            else:
                requirements_met.append(f"❌ chunks_received is {status_data.get('chunks_received')}, expected 2")
                success = False
            
            # Requirement: received_chunk_indices contains [0, 1]
            if status_data.get("received_chunk_indices") == [0, 1]:
                requirements_met.append("✅ received_chunk_indices contains [0, 1]")
            else:
                requirements_met.append(f"❌ received_chunk_indices is {status_data.get('received_chunk_indices')}, expected [0, 1]")
                success = False
            
            for req in requirements_met:
                print(f"   {req}")
            
            if success:
                print("🎉 TEST 1 PASSED: Resume upload support verified!")
                print("   Server-side chunk tracking working correctly")
            
            return success
            
        except Exception as e:
            print(f"❌ Test 1 failed: {str(e)}")
            return False
    
    def test_2_full_end_to_end_with_resume(self) -> bool:
        """Test 2: Full End-to-End with Resume"""
        print("\n📋 TEST 2: Full End-to-End with Resume")
        print("Complete chunked upload workflow with resume capabilities")
        
        try:
            # Create a 5-page test PDF
            pdf_data = self.create_test_pdf(5)
            if not pdf_data:
                return False
            
            total_chunks = max(1, (len(pdf_data) + 5242879) // 5242880)  # Ensure at least 1 chunk
            
            # Step 1: Create a batch
            print("✅ Using existing batch for end-to-end test")
            
            # Step 2: Initialize chunked upload
            init_response = self.session.post(f"{BASE_URL}/pdf-upload/init", json={
                "batch_id": self.batch_id,
                "filename": "end_to_end_test.pdf", 
                "file_size": len(pdf_data),
                "total_chunks": total_chunks
            })
            
            if init_response.status_code != 200:
                print(f"❌ Init upload failed: {init_response.status_code}")
                return False
            
            init_data = init_response.json()
            upload_id = init_data["upload_id"]
            chunk_size = init_data["chunk_size"]
            print(f"✅ Init chunked upload: {upload_id}")
            
            # Step 3: Upload chunk 0
            chunk_data = pdf_data[:min(chunk_size, len(pdf_data))]
            files = {'file': ('chunk', io.BytesIO(chunk_data), 'application/octet-stream')}
            upload_response = self.session.post(
                f"{BASE_URL}/pdf-upload/{upload_id}/chunk?chunk_index=0",
                files=files
            )
            
            if upload_response.status_code != 200:
                print(f"❌ Chunk 0 upload failed: {upload_response.status_code}")
                return False
            
            print("✅ Upload chunk 0")
            
            # Step 4: Check status (should show chunks_received=1, received_chunk_indices=[0])
            status_response = self.session.get(f"{BASE_URL}/pdf-upload/{upload_id}/status")
            status_data = status_response.json()
            
            if status_data.get("chunks_received") != 1 or status_data.get("received_chunk_indices") != [0]:
                print(f"❌ Unexpected status after chunk 0")
                return False
            
            print("✅ Check status: chunks_received=1, received_chunk_indices=[0]")
            
            # Step 5: Upload remaining chunks (if any)
            for chunk_index in range(1, total_chunks):
                start_byte = chunk_index * chunk_size
                end_byte = min(start_byte + chunk_size, len(pdf_data))
                if start_byte >= len(pdf_data):
                    chunk_data = b"padding_data"  # Dummy data for extra chunks
                else:
                    chunk_data = pdf_data[start_byte:end_byte]
                
                files = {'file': ('chunk', io.BytesIO(chunk_data), 'application/octet-stream')}
                self.session.post(f"{BASE_URL}/pdf-upload/{upload_id}/chunk?chunk_index={chunk_index}", files=files)
            
            print(f"✅ Upload remaining chunks")
            
            # Step 6: Call complete
            complete_response = self.session.post(f"{BASE_URL}/pdf-upload/{upload_id}/complete")
            if complete_response.status_code != 200:
                print(f"❌ Complete upload failed: {complete_response.status_code}")
                return False
            
            print("✅ Call complete")
            
            # Step 7: Poll status until done
            max_polls = 20
            final_status = None
            for poll in range(max_polls):
                time.sleep(1)
                status_response = self.session.get(f"{BASE_URL}/pdf-upload/{upload_id}/status")
                status_data = status_response.json()
                
                status = status_data["upload_status"]
                print(f"   Poll {poll + 1}: {status} (imported: {status_data.get('imported', 0)})")
                
                if status == "done":
                    final_status = status_data
                    break
                elif status == "error":
                    print(f"❌ Processing failed: {status_data.get('error', 'Unknown error')}")
                    return False
            
            if not final_status:
                print(f"❌ Processing timeout after {max_polls} seconds")
                return False
            
            # Step 8: Verify: imported=5, total_pages=5
            if final_status.get("imported") == 5 and final_status.get("total_pages") == 5:
                print("✅ Poll status until done")
                print("✅ Verify: imported=5, total_pages=5")
                print("🎉 TEST 2 PASSED: Full end-to-end with resume completed!")
                return True
            else:
                print(f"❌ Verification failed: imported={final_status.get('imported')}, total_pages={final_status.get('total_pages')}")
                return False
            
        except Exception as e:
            print(f"❌ Test 2 failed: {str(e)}")
            return False
    
    def test_3_validation_tests(self) -> bool:
        """Test 3: Validation Tests"""
        print("\n📋 TEST 3: Validation Tests") 
        print("Testing file size, type, and batch validation")
        
        results = []
        
        # Test 3.1: Reject >1000MB
        try:
            response = self.session.post(f"{BASE_URL}/pdf-upload/init", json={
                "batch_id": self.batch_id,
                "filename": "large.pdf",
                "file_size": 1100000000,  # 1100MB
                "total_chunks": 220
            })
            
            if response.status_code == 413:
                print("✅ Reject >1000MB: Init with file_size=1100000000 → got 413")
                results.append(True)
            else:
                print(f"❌ Expected 413 for >1000MB, got {response.status_code}")
                results.append(False)
        except Exception as e:
            print(f"❌ Large file test failed: {str(e)}")
            results.append(False)
        
        # Test 3.2: Reject non-PDF
        try:
            response = self.session.post(f"{BASE_URL}/pdf-upload/init", json={
                "batch_id": self.batch_id,
                "filename": "test.jpg",
                "file_size": 1000000,
                "total_chunks": 1
            })
            
            if response.status_code == 400:
                print("✅ Reject non-PDF: Init with filename='test.jpg' → got 400")
                results.append(True)
            else:
                print(f"❌ Expected 400 for non-PDF, got {response.status_code}")
                results.append(False)
        except Exception as e:
            print(f"❌ Non-PDF test failed: {str(e)}")
            results.append(False)
        
        # Test 3.3: Invalid batch
        try:
            response = self.session.post(f"{BASE_URL}/pdf-upload/init", json={
                "batch_id": "nonexistent",
                "filename": "test.pdf",
                "file_size": 1000000,
                "total_chunks": 1
            })
            
            if response.status_code == 404:
                print("✅ Invalid batch: Init with batch_id='nonexistent' → got 404")
                results.append(True)
            else:
                print(f"❌ Expected 404 for invalid batch, got {response.status_code}")
                results.append(False)
        except Exception as e:
            print(f"❌ Invalid batch test failed: {str(e)}")
            results.append(False)
        
        # Test 3.4: Missing chunks
        try:
            pdf_data = self.create_test_pdf(2)
            init_response = self.session.post(f"{BASE_URL}/pdf-upload/init", json={
                "batch_id": self.batch_id,
                "filename": "missing_test.pdf",
                "file_size": len(pdf_data),
                "total_chunks": 3  # Force 3 chunks but only upload 1
            })
            
            if init_response.status_code == 200:
                upload_id = init_response.json()["upload_id"]
                chunk_size = init_response.json()["chunk_size"]
                
                # Upload only chunk 0
                chunk_data = pdf_data[:min(chunk_size, len(pdf_data))]
                files = {'file': ('chunk', io.BytesIO(chunk_data), 'application/octet-stream')}
                self.session.post(f"{BASE_URL}/pdf-upload/{upload_id}/chunk?chunk_index=0", files=files)
                
                # Try to complete with missing chunks
                complete_response = self.session.post(f"{BASE_URL}/pdf-upload/{upload_id}/complete")
                
                if complete_response.status_code == 400:
                    print("✅ Missing chunks: complete before all chunks → got 400")
                    results.append(True)
                else:
                    print(f"❌ Expected 400 for missing chunks, got {complete_response.status_code}")
                    results.append(False)
            else:
                print("❌ Failed to init missing chunks test")
                results.append(False)
        except Exception as e:
            print(f"❌ Missing chunks test failed: {str(e)}")
            results.append(False)
        
        success = all(results)
        if success:
            print("🎉 TEST 3 PASSED: All validation tests working correctly!")
        
        return success
    
    def test_4_legacy_endpoint(self) -> bool:
        """Test 4: Legacy Endpoint"""
        print("\n📋 TEST 4: Legacy Endpoint")
        print("POST /api/batches/{batch_id}/import-pdf still works with direct upload")
        
        try:
            pdf_data = self.create_test_pdf(3)
            
            files = {'file': ('legacy_test.pdf', io.BytesIO(pdf_data), 'application/pdf')}
            response = self.session.post(f"{BASE_URL}/batches/{self.batch_id}/import-pdf", files=files)
            
            if response.status_code == 200:
                data = response.json()
                if data.get("total_pages") == 3 and data.get("imported") == 3:
                    print("✅ Legacy endpoint works with direct upload")
                    print("🎉 TEST 4 PASSED: Legacy compatibility maintained!")
                    return True
                else:
                    print(f"❌ Legacy endpoint returned unexpected results: {data}")
                    return False
            else:
                print(f"❌ Legacy endpoint failed: {response.status_code}")
                return False
                
        except Exception as e:
            print(f"❌ Test 4 failed: {str(e)}")
            return False
    
    def test_5_regression(self) -> bool:
        """Test 5: Regression"""
        print("\n📋 TEST 5: Regression")
        print("Verify core functionality still works")
        
        results = []
        
        # Test 5.1: Auth still works
        try:
            response = self.session.get(f"{BASE_URL}/auth/me")
            if response.status_code == 200 and response.json().get("role") == "admin":
                print("✅ Auth still works")
                results.append(True)
            else:
                print("❌ Auth regression detected")
                results.append(False)
        except Exception as e:
            print(f"❌ Auth test failed: {str(e)}")
            results.append(False)
        
        # Test 5.2: Products endpoint works
        try:
            response = self.session.get(f"{BASE_URL}/products")
            if response.status_code == 200:
                data = response.json()
                if "products" in data and isinstance(data["products"], list):
                    print("✅ Products endpoint works")
                    results.append(True)
                else:
                    print("❌ Products endpoint format changed")
                    results.append(False)
            else:
                print(f"❌ Products endpoint failed: {response.status_code}")
                results.append(False)
        except Exception as e:
            print(f"❌ Products test failed: {str(e)}")
            results.append(False)
        
        # Test 5.3: Live rates
        try:
            response = self.session.get(f"{BASE_URL}/live-rates")
            if response.status_code == 200:
                data = response.json()
                if "silver_dollar" in data and data["silver_dollar"] > 0:
                    print(f"✅ Live rates: silver_dollar=${data['silver_dollar']}")
                    results.append(True)
                else:
                    print("❌ Live rates format issue")
                    results.append(False)
            else:
                print(f"❌ Live rates failed: {response.status_code}")
                results.append(False)
        except Exception as e:
            print(f"❌ Live rates test failed: {str(e)}")
            results.append(False)
        
        success = all(results)
        if success:
            print("🎉 TEST 5 PASSED: No regression detected!")
        
        return success
    
    def cleanup(self) -> bool:
        """Clean up test batch"""
        if self.batch_id:
            try:
                response = self.session.delete(f"{BASE_URL}/batches/{self.batch_id}")
                if response.status_code == 200:
                    print(f"✅ Cleaned up test batch: {self.batch_id}")
                    return True
            except Exception as e:
                print(f"⚠️  Cleanup failed: {str(e)}")
        return False
    
    def run_all_tests(self) -> Dict[str, Any]:
        """Run all comprehensive tests"""
        print("🚀 COMPREHENSIVE CHUNKED PDF UPLOAD TESTING")
        print("Testing improved chunked upload system per review request")
        print("=" * 80)
        
        # Setup
        if not self.authenticate() or not self.create_test_batch():
            return {"success": False, "error": "Setup failed"}
        
        # Run all tests
        test_results = {
            "1_resume_upload_support": self.test_1_resume_upload_support(),
            "2_full_end_to_end_with_resume": self.test_2_full_end_to_end_with_resume(),
            "3_validation_tests": self.test_3_validation_tests(),
            "4_legacy_endpoint": self.test_4_legacy_endpoint(),
            "5_regression": self.test_5_regression()
        }
        
        # Cleanup
        cleanup_success = self.cleanup()
        
        # Summary
        passed = sum(1 for result in test_results.values() if result)
        total = len(test_results)
        success = all(test_results.values())
        
        print(f"\n📊 COMPREHENSIVE TEST SUMMARY")
        print("=" * 80)
        print(f"Tests Passed: {passed}/{total}")
        
        for test_name, result in test_results.items():
            status = "✅ PASS" if result else "❌ FAIL"
            test_display = test_name.replace('_', ' ').replace('1 ', '1. ').replace('2 ', '2. ').replace('3 ', '3. ').replace('4 ', '4. ').replace('5 ', '5. ').title()
            print(f"{test_display}: {status}")
        
        if success:
            print(f"\n🎉 ALL TESTS PASSED! Chunked upload improvements working correctly!")
            print("✅ Resume upload support with server-side chunk tracking")
            print("✅ Full end-to-end workflow with polling and verification")  
            print("✅ Proper validation (file size, type, batch, missing chunks)")
            print("✅ Legacy endpoint backward compatibility maintained")
            print("✅ No regression in existing functionality")
        else:
            print(f"\n❌ Some tests failed. See details above.")
        
        return {
            "success": success,
            "passed": passed,
            "total": total,
            "results": test_results,
            "cleanup": cleanup_success
        }

if __name__ == "__main__":
    tester = ComprehensiveChunkedUploadTest()
    results = tester.run_all_tests()
    
    if not results["success"]:
        exit(1)