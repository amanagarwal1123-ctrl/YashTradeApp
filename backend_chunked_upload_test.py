#!/usr/bin/env python3
"""
Chunked PDF Upload Improvements Testing
Testing resume upload support, validation, and regression tests for the improved chunked upload system.
"""

import requests
import fitz  # PyMuPDF
import os
import io
import time
import json
from typing import Dict, List, Any

# Configuration
BASE_URL = "https://gem-bulk-import.preview.emergentagent.com/api"
ADMIN_PHONE = "9999999999"
ADMIN_OTP = "1234"

class ChunkedUploadTester:
    def __init__(self):
        self.session = requests.Session()
        self.auth_token = None
        self.batch_id = None
        
    def authenticate(self) -> bool:
        """Authenticate as admin user"""
        try:
            # Send OTP
            response = self.session.post(f"{BASE_URL}/auth/send-otp", 
                                       json={"phone": ADMIN_PHONE})
            if response.status_code != 200:
                print(f"❌ Failed to send OTP: {response.status_code}")
                return False
            
            # Verify OTP
            response = self.session.post(f"{BASE_URL}/auth/verify-otp", 
                                       json={"phone": ADMIN_PHONE, "otp": ADMIN_OTP})
            if response.status_code != 200:
                print(f"❌ Failed to verify OTP: {response.status_code}")
                return False
            
            data = response.json()
            self.auth_token = data.get("token")
            self.session.headers.update({"Authorization": f"Bearer {self.auth_token}"})
            print(f"✅ Authenticated as admin (phone: {ADMIN_PHONE})")
            return True
            
        except Exception as e:
            print(f"❌ Authentication failed: {str(e)}")
            return False
    
    def create_test_batch(self) -> bool:
        """Create a test batch for uploads"""
        try:
            response = self.session.post(f"{BASE_URL}/batches", 
                                       json={
                                           "name": "Chunked Upload Test Batch",
                                           "metal_type": "silver",
                                           "category": "test"
                                       })
            if response.status_code != 200:
                print(f"❌ Failed to create batch: {response.status_code} - {response.text}")
                return False
            
            data = response.json()
            self.batch_id = data.get("id")
            print(f"✅ Created test batch: {self.batch_id}")
            return True
            
        except Exception as e:
            print(f"❌ Batch creation failed: {str(e)}")
            return False
    
    def create_test_pdf(self, pages: int) -> bytes:
        """Create a test PDF with specified number of pages using PyMuPDF"""
        try:
            doc = fitz.open()  # Create new PDF document
            
            for i in range(pages):
                page = doc.new_page()  # A4 page
                text = f"Test Page {i + 1} of {pages}\nThis is a test PDF for chunked upload testing.\nPage content for chunk upload validation."
                
                # Add text to the page
                rect = fitz.Rect(72, 72, 500, 700)  # Text area
                page.insert_textbox(rect, text, fontsize=12, fontname="helv")
            
            # Save to bytes
            pdf_bytes = doc.tobytes()
            doc.close()
            
            print(f"✅ Created test PDF: {pages} pages, {len(pdf_bytes)} bytes")
            return pdf_bytes
            
        except Exception as e:
            print(f"❌ PDF creation failed: {str(e)}")
            return b""
    
    def calculate_chunks(self, file_size: int, chunk_size: int = 5242880) -> int:
        """Calculate number of chunks needed (5MB default chunk size)"""
        return (file_size + chunk_size - 1) // chunk_size
    
    def test_resume_upload_support(self) -> bool:
        """Test 1: Resume Upload Support - Init upload with 3 chunks, upload only 0 and 1, check status"""
        print("\n📋 TEST 1: Resume Upload Support")
        
        try:
            # Create a 5-page PDF for this test
            pdf_data = self.create_test_pdf(5)
            if not pdf_data:
                return False
            
            total_chunks = self.calculate_chunks(len(pdf_data))
            
            # Step 1: Initialize upload
            init_response = self.session.post(f"{BASE_URL}/pdf-upload/init", json={
                "batch_id": self.batch_id,
                "filename": "resume_test.pdf",
                "file_size": len(pdf_data),
                "total_chunks": total_chunks
            })
            
            if init_response.status_code != 200:
                print(f"❌ Init upload failed: {init_response.status_code} - {init_response.text}")
                return False
            
            init_data = init_response.json()
            upload_id = init_data["upload_id"]
            chunk_size = init_data["chunk_size"]
            print(f"✅ Upload initialized: {upload_id}, chunk_size: {chunk_size}")
            
            # Step 2: Upload only chunks 0 and 1 (if we have at least 3 chunks)
            if total_chunks < 3:
                print("ℹ️  PDF too small for resume test (need at least 3 chunks), uploading all chunks")
                chunks_to_upload = list(range(total_chunks))
            else:
                chunks_to_upload = [0, 1]  # Skip chunk 2 to test resume
            
            for chunk_index in chunks_to_upload:
                start_byte = chunk_index * chunk_size
                end_byte = min(start_byte + chunk_size, len(pdf_data))
                chunk_data = pdf_data[start_byte:end_byte]
                
                files = {'file': ('chunk', io.BytesIO(chunk_data), 'application/octet-stream')}
                upload_response = self.session.post(
                    f"{BASE_URL}/pdf-upload/{upload_id}/chunk?chunk_index={chunk_index}",
                    files=files
                )
                
                if upload_response.status_code != 200:
                    print(f"❌ Chunk {chunk_index} upload failed: {upload_response.status_code}")
                    return False
                
                print(f"✅ Uploaded chunk {chunk_index}")
            
            # Step 3: Check status to verify resume tracking
            status_response = self.session.get(f"{BASE_URL}/pdf-upload/{upload_id}/status")
            if status_response.status_code != 200:
                print(f"❌ Status check failed: {status_response.status_code}")
                return False
            
            status_data = status_response.json()
            
            # Verify resume support fields
            expected_chunks = len(chunks_to_upload)
            if status_data["upload_status"] != "uploading":
                print(f"❌ Expected 'uploading' status, got: {status_data['upload_status']}")
                return False
            
            if status_data["chunks_received"] != expected_chunks:
                print(f"❌ Expected {expected_chunks} chunks received, got: {status_data['chunks_received']}")
                return False
            
            if "received_chunk_indices" not in status_data:
                print("❌ Missing 'received_chunk_indices' field for resume support")
                return False
            
            received_indices = status_data["received_chunk_indices"]
            if received_indices != chunks_to_upload:
                print(f"❌ Expected received indices {chunks_to_upload}, got: {received_indices}")
                return False
            
            print(f"✅ Resume support verified:")
            print(f"   - upload_status: {status_data['upload_status']}")
            print(f"   - chunks_received: {status_data['chunks_received']}")
            print(f"   - received_chunk_indices: {received_indices}")
            
            # Clean up - upload remaining chunks to complete (if any)
            if total_chunks > len(chunks_to_upload):
                remaining_chunks = [i for i in range(total_chunks) if i not in chunks_to_upload]
                for chunk_index in remaining_chunks:
                    start_byte = chunk_index * chunk_size
                    end_byte = min(start_byte + chunk_size, len(pdf_data))
                    chunk_data = pdf_data[start_byte:end_byte]
                    
                    files = {'file': ('chunk', io.BytesIO(chunk_data), 'application/octet-stream')}
                    self.session.post(f"{BASE_URL}/pdf-upload/{upload_id}/chunk?chunk_index={chunk_index}", files=files)
                
                # Complete upload for cleanup
                self.session.post(f"{BASE_URL}/pdf-upload/{upload_id}/complete")
            
            return True
            
        except Exception as e:
            print(f"❌ Resume upload test failed: {str(e)}")
            return False
    
    def test_full_end_to_end_with_resume(self) -> bool:
        """Test 2: Full End-to-End with Resume - Complete chunked upload workflow"""
        print("\n📋 TEST 2: Full End-to-End with Resume")
        
        try:
            # Create a 5-page PDF
            pdf_data = self.create_test_pdf(5)
            if not pdf_data:
                return False
            
            total_chunks = self.calculate_chunks(len(pdf_data))
            
            # Step 1: Initialize upload
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
            print(f"✅ Upload initialized: {upload_id}")
            
            # Step 2: Upload chunk 0
            chunk_data = pdf_data[:chunk_size]
            files = {'file': ('chunk', io.BytesIO(chunk_data), 'application/octet-stream')}
            upload_response = self.session.post(
                f"{BASE_URL}/pdf-upload/{upload_id}/chunk?chunk_index=0",
                files=files
            )
            
            if upload_response.status_code != 200:
                print(f"❌ Chunk 0 upload failed: {upload_response.status_code}")
                return False
            
            print("✅ Uploaded chunk 0")
            
            # Step 3: Check status (should show chunks_received=1, received_chunk_indices=[0])
            status_response = self.session.get(f"{BASE_URL}/pdf-upload/{upload_id}/status")
            status_data = status_response.json()
            
            if status_data["chunks_received"] != 1 or status_data["received_chunk_indices"] != [0]:
                print(f"❌ Unexpected status after chunk 0: {status_data}")
                return False
            
            print("✅ Status verified after chunk 0: chunks_received=1, received_chunk_indices=[0]")
            
            # Step 4: Upload remaining chunks
            for chunk_index in range(1, total_chunks):
                start_byte = chunk_index * chunk_size
                end_byte = min(start_byte + chunk_size, len(pdf_data))
                chunk_data = pdf_data[start_byte:end_byte]
                
                files = {'file': ('chunk', io.BytesIO(chunk_data), 'application/octet-stream')}
                upload_response = self.session.post(
                    f"{BASE_URL}/pdf-upload/{upload_id}/chunk?chunk_index={chunk_index}",
                    files=files
                )
                
                if upload_response.status_code != 200:
                    print(f"❌ Chunk {chunk_index} upload failed")
                    return False
            
            print(f"✅ Uploaded all {total_chunks} chunks")
            
            # Step 5: Complete upload
            complete_response = self.session.post(f"{BASE_URL}/pdf-upload/{upload_id}/complete")
            if complete_response.status_code != 200:
                print(f"❌ Complete upload failed: {complete_response.status_code}")
                return False
            
            print("✅ Upload completed, starting processing")
            
            # Step 6: Poll status until done
            max_polls = 30
            for poll in range(max_polls):
                time.sleep(1)
                status_response = self.session.get(f"{BASE_URL}/pdf-upload/{upload_id}/status")
                status_data = status_response.json()
                
                status = status_data["upload_status"]
                print(f"   Poll {poll + 1}: {status} (imported: {status_data.get('imported', 0)}, total_pages: {status_data.get('total_pages', 0)})")
                
                if status == "done":
                    break
                elif status == "error":
                    print(f"❌ Processing failed: {status_data.get('error', 'Unknown error')}")
                    return False
            
            if status_data["upload_status"] != "done":
                print(f"❌ Processing did not complete in {max_polls} seconds")
                return False
            
            # Step 7: Verify results
            if status_data["imported"] != 5 or status_data["total_pages"] != 5:
                print(f"❌ Expected 5 imported pages, got: imported={status_data['imported']}, total_pages={status_data['total_pages']}")
                return False
            
            print("✅ End-to-end upload completed successfully!")
            print(f"   - Total pages: {status_data['total_pages']}")
            print(f"   - Imported: {status_data['imported']}")
            
            return True
            
        except Exception as e:
            print(f"❌ End-to-end test failed: {str(e)}")
            return False
    
    def test_validation_tests(self) -> bool:
        """Test 3: Validation Tests - File size, type, and batch validation"""
        print("\n📋 TEST 3: Validation Tests")
        
        results = []
        
        # Test 3.1: Reject >1000MB file
        try:
            large_file_size = 1100 * 1024 * 1024  # 1100MB
            init_response = self.session.post(f"{BASE_URL}/pdf-upload/init", json={
                "batch_id": self.batch_id,
                "filename": "large_test.pdf",
                "file_size": large_file_size,
                "total_chunks": 220  # Approximate chunks for 1100MB
            })
            
            if init_response.status_code == 413:
                print("✅ 3.1: Large file (>1000MB) correctly rejected with 413")
                results.append(True)
            else:
                print(f"❌ 3.1: Expected 413 for large file, got {init_response.status_code}")
                results.append(False)
                
        except Exception as e:
            print(f"❌ 3.1: Large file test failed: {str(e)}")
            results.append(False)
        
        # Test 3.2: Reject non-PDF file
        try:
            init_response = self.session.post(f"{BASE_URL}/pdf-upload/init", json={
                "batch_id": self.batch_id,
                "filename": "test.jpg",
                "file_size": 1024 * 1024,  # 1MB
                "total_chunks": 1
            })
            
            if init_response.status_code == 400:
                print("✅ 3.2: Non-PDF file correctly rejected with 400")
                results.append(True)
            else:
                print(f"❌ 3.2: Expected 400 for non-PDF, got {init_response.status_code}")
                results.append(False)
                
        except Exception as e:
            print(f"❌ 3.2: Non-PDF test failed: {str(e)}")
            results.append(False)
        
        # Test 3.3: Invalid batch ID
        try:
            init_response = self.session.post(f"{BASE_URL}/pdf-upload/init", json={
                "batch_id": "nonexistent-batch-id",
                "filename": "test.pdf",
                "file_size": 1024 * 1024,  # 1MB
                "total_chunks": 1
            })
            
            if init_response.status_code == 404:
                print("✅ 3.3: Invalid batch ID correctly rejected with 404")
                results.append(True)
            else:
                print(f"❌ 3.3: Expected 404 for invalid batch, got {init_response.status_code}")
                results.append(False)
                
        except Exception as e:
            print(f"❌ 3.3: Invalid batch test failed: {str(e)}")
            results.append(False)
        
        # Test 3.4: Missing chunks validation
        try:
            # Create small PDF
            pdf_data = self.create_test_pdf(2)
            total_chunks = max(2, self.calculate_chunks(len(pdf_data)))  # Ensure at least 2 chunks for test
            
            # Initialize upload
            init_response = self.session.post(f"{BASE_URL}/pdf-upload/init", json={
                "batch_id": self.batch_id,
                "filename": "missing_chunks_test.pdf",
                "file_size": len(pdf_data),
                "total_chunks": total_chunks
            })
            
            if init_response.status_code != 200:
                print(f"❌ 3.4: Failed to init missing chunks test")
                results.append(False)
            else:
                init_data = init_response.json()
                upload_id = init_data["upload_id"]
                
                # Upload only first chunk (leave others missing)
                chunk_size = init_data["chunk_size"]
                chunk_data = pdf_data[:chunk_size]
                files = {'file': ('chunk', io.BytesIO(chunk_data), 'application/octet-stream')}
                self.session.post(f"{BASE_URL}/pdf-upload/{upload_id}/chunk?chunk_index=0", files=files)
                
                # Try to complete with missing chunks
                complete_response = self.session.post(f"{BASE_URL}/pdf-upload/{upload_id}/complete")
                
                if complete_response.status_code == 400:
                    print("✅ 3.4: Missing chunks correctly rejected with 400")
                    results.append(True)
                else:
                    print(f"❌ 3.4: Expected 400 for missing chunks, got {complete_response.status_code}")
                    results.append(False)
                
        except Exception as e:
            print(f"❌ 3.4: Missing chunks test failed: {str(e)}")
            results.append(False)
        
        return all(results)
    
    def test_legacy_endpoint(self) -> bool:
        """Test 4: Legacy Endpoint - Verify backward compatibility"""
        print("\n📋 TEST 4: Legacy Endpoint Compatibility")
        
        try:
            # Create small PDF for legacy test
            pdf_data = self.create_test_pdf(2)
            
            # Test legacy upload endpoint
            files = {'file': ('legacy_test.pdf', io.BytesIO(pdf_data), 'application/pdf')}
            upload_response = self.session.post(
                f"{BASE_URL}/batches/{self.batch_id}/import-pdf",
                files=files
            )
            
            if upload_response.status_code != 200:
                print(f"❌ Legacy endpoint failed: {upload_response.status_code} - {upload_response.text}")
                return False
            
            upload_data = upload_response.json()
            
            if upload_data.get("imported", 0) != 2:
                print(f"❌ Legacy upload: Expected 2 pages imported, got {upload_data.get('imported', 0)}")
                return False
            
            print("✅ Legacy endpoint working correctly")
            print(f"   - Total pages: {upload_data.get('total_pages', 0)}")
            print(f"   - Imported: {upload_data.get('imported', 0)}")
            
            return True
            
        except Exception as e:
            print(f"❌ Legacy endpoint test failed: {str(e)}")
            return False
    
    def test_regression(self) -> bool:
        """Test 5: Regression - Verify core functionality still works"""
        print("\n📋 TEST 5: Regression Testing")
        
        results = []
        
        # Test 5.1: Auth still works (already authenticated)
        try:
            me_response = self.session.get(f"{BASE_URL}/auth/me")
            if me_response.status_code == 200:
                user_data = me_response.json()
                if user_data.get("role") == "admin":
                    print("✅ 5.1: Authentication still working")
                    results.append(True)
                else:
                    print(f"❌ 5.1: Auth working but wrong role: {user_data.get('role')}")
                    results.append(False)
            else:
                print(f"❌ 5.1: Auth check failed: {me_response.status_code}")
                results.append(False)
                
        except Exception as e:
            print(f"❌ 5.1: Auth regression test failed: {str(e)}")
            results.append(False)
        
        # Test 5.2: Products endpoint works
        try:
            products_response = self.session.get(f"{BASE_URL}/products")
            if products_response.status_code == 200:
                products_data = products_response.json()
                if isinstance(products_data, list):
                    print(f"✅ 5.2: Products endpoint working ({len(products_data)} products)")
                    results.append(True)
                else:
                    print(f"❌ 5.2: Products returned unexpected format")
                    results.append(False)
            else:
                print(f"❌ 5.2: Products endpoint failed: {products_response.status_code}")
                results.append(False)
                
        except Exception as e:
            print(f"❌ 5.2: Products regression test failed: {str(e)}")
            results.append(False)
        
        # Test 5.3: Live rates endpoint
        try:
            rates_response = self.session.get(f"{BASE_URL}/live-rates")
            if rates_response.status_code == 200:
                rates_data = rates_response.json()
                if "silver_dollar" in rates_data and rates_data["silver_dollar"] > 0:
                    print(f"✅ 5.3: Live rates working (silver_dollar: ${rates_data['silver_dollar']})")
                    results.append(True)
                else:
                    print(f"❌ 5.3: Live rates missing silver_dollar or zero value")
                    results.append(False)
            else:
                print(f"❌ 5.3: Live rates failed: {rates_response.status_code}")
                results.append(False)
                
        except Exception as e:
            print(f"❌ 5.3: Live rates regression test failed: {str(e)}")
            results.append(False)
        
        return all(results)
    
    def cleanup(self) -> bool:
        """Clean up test batch"""
        if self.batch_id:
            try:
                response = self.session.delete(f"{BASE_URL}/batches/{self.batch_id}")
                if response.status_code == 200:
                    print(f"✅ Cleaned up test batch: {self.batch_id}")
                    return True
                else:
                    print(f"⚠️  Failed to cleanup batch: {response.status_code}")
                    return False
            except Exception as e:
                print(f"⚠️  Cleanup failed: {str(e)}")
                return False
        return True
    
    def run_all_tests(self) -> Dict[str, Any]:
        """Run all chunked upload improvement tests"""
        print("🚀 CHUNKED PDF UPLOAD IMPROVEMENTS TESTING")
        print("=" * 60)
        
        # Authenticate
        if not self.authenticate():
            return {"success": False, "error": "Authentication failed"}
        
        # Create test batch
        if not self.create_test_batch():
            return {"success": False, "error": "Batch creation failed"}
        
        # Run all tests
        test_results = {
            "1_resume_upload_support": self.test_resume_upload_support(),
            "2_full_end_to_end_with_resume": self.test_full_end_to_end_with_resume(),
            "3_validation_tests": self.test_validation_tests(),
            "4_legacy_endpoint": self.test_legacy_endpoint(),
            "5_regression": self.test_regression()
        }
        
        # Cleanup
        cleanup_success = self.cleanup()
        
        # Summary
        passed = sum(1 for result in test_results.values() if result)
        total = len(test_results)
        
        print(f"\n📊 TEST SUMMARY")
        print("=" * 60)
        print(f"Tests Passed: {passed}/{total}")
        
        for test_name, result in test_results.items():
            status = "✅ PASS" if result else "❌ FAIL"
            print(f"{test_name.replace('_', ' ').title()}: {status}")
        
        success = all(test_results.values())
        
        if success:
            print(f"\n🎉 ALL TESTS PASSED! Chunked upload improvements are working correctly.")
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
    tester = ChunkedUploadTester()
    results = tester.run_all_tests()
    
    if not results["success"]:
        exit(1)