#!/usr/bin/env python3
"""
Enhanced Resume Upload Testing
Testing resume upload support specifically for the review request requirements.
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

class ResumeUploadTester:
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
                                           "name": "Resume Upload Test Batch",
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
    
    def create_large_test_pdf(self, pages: int = 10) -> bytes:
        """Create a larger test PDF to ensure multiple chunks"""
        try:
            doc = fitz.open()  # Create new PDF document
            
            for i in range(pages):
                page = doc.new_page(width=595, height=842)  # A4 page
                
                # Add more content per page to increase size
                text = f"""Test Page {i + 1} of {pages}
This is a comprehensive test PDF for chunked upload testing.
The PDF is designed to be large enough to require multiple chunks.

Content Section 1:
Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed do eiusmod tempor 
incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis 
nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat.

Content Section 2:
Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore 
eu fugiat nulla pariatur. Excepteur sint occaecat cupidatat non proident, sunt 
in culpa qui officia deserunt mollit anim id est laborum.

Content Section 3:
Sed ut perspiciatis unde omnis iste natus error sit voluptatem accusantium 
doloremque laudantium, totam rem aperiam, eaque ipsa quae ab illo inventore 
veritatis et quasi architecto beatae vitae dicta sunt explicabo.

Additional Technical Information:
- Page Number: {i + 1}
- Total Pages: {pages}
- Test Type: Resume Upload Validation
- Chunk Size: 5MB (5242880 bytes)
- Expected Chunks: Multiple for comprehensive testing

This content is repeated to increase the file size and ensure that we have 
enough data to create multiple chunks for proper resume functionality testing.
The chunked upload system should handle this PDF correctly and allow for
resume operations when chunks are missing or interrupted.
"""
                
                # Add text to the page with more formatting
                rect = fitz.Rect(50, 50, 545, 792)  # Full page text area
                page.insert_textbox(rect, text, fontsize=10, fontname="helv")
                
                # Add some shapes to increase file size
                page.draw_rect(fitz.Rect(50, 50, 545, 792), color=(0, 0, 0), width=2)
                page.draw_line(fitz.Point(50, 100), fitz.Point(545, 100), color=(0.5, 0.5, 0.5), width=1)
            
            # Save to bytes
            pdf_bytes = doc.tobytes()
            doc.close()
            
            print(f"✅ Created large test PDF: {pages} pages, {len(pdf_bytes)} bytes ({len(pdf_bytes)/(1024*1024):.2f} MB)")
            return pdf_bytes
            
        except Exception as e:
            print(f"❌ PDF creation failed: {str(e)}")
            return b""
    
    def calculate_chunks(self, file_size: int, chunk_size: int = 5242880) -> int:
        """Calculate number of chunks needed (5MB default chunk size)"""
        return (file_size + chunk_size - 1) // chunk_size
    
    def test_resume_upload_scenario_1(self) -> bool:
        """Test Scenario 1: Init with 3+ chunks, upload 0 and 1, verify status shows resume info"""
        print("\n📋 TEST SCENARIO 1: Resume Upload Support (3+ chunks)")
        
        try:
            # Create a larger PDF to ensure at least 3 chunks
            pdf_data = self.create_large_test_pdf(15)  # 15 pages should be large enough
            if not pdf_data:
                return False
            
            total_chunks = self.calculate_chunks(len(pdf_data))
            print(f"ℹ️  PDF size: {len(pdf_data)} bytes, calculated chunks: {total_chunks}")
            
            if total_chunks < 3:
                print("❌ PDF not large enough to create 3+ chunks. Need larger test file.")
                return False
            
            # Step 1: Initialize upload
            init_response = self.session.post(f"{BASE_URL}/pdf-upload/init", json={
                "batch_id": self.batch_id,
                "filename": "resume_scenario_1.pdf",
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
            
            # Step 2: Upload only chunks 0 and 1 (skip chunk 2)
            for chunk_index in [0, 1]:
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
            
            # Step 3: Check status to verify resume tracking matches requirements
            status_response = self.session.get(f"{BASE_URL}/pdf-upload/{upload_id}/status")
            if status_response.status_code != 200:
                print(f"❌ Status check failed: {status_response.status_code}")
                return False
            
            status_data = status_response.json()
            print(f"📊 Status Response: {json.dumps(status_data, indent=2)}")
            
            # Verify exact requirements from review request
            success = True
            
            # Requirement: upload_status is "uploading"
            if status_data["upload_status"] != "uploading":
                print(f"❌ Expected upload_status 'uploading', got: {status_data['upload_status']}")
                success = False
            else:
                print("✅ upload_status is 'uploading'")
            
            # Requirement: chunks_received is 2
            if status_data["chunks_received"] != 2:
                print(f"❌ Expected chunks_received 2, got: {status_data['chunks_received']}")
                success = False
            else:
                print("✅ chunks_received is 2")
            
            # Requirement: received_chunk_indices contains [0, 1]
            if "received_chunk_indices" not in status_data:
                print("❌ Missing 'received_chunk_indices' field")
                success = False
            elif status_data["received_chunk_indices"] != [0, 1]:
                print(f"❌ Expected received_chunk_indices [0, 1], got: {status_data['received_chunk_indices']}")
                success = False
            else:
                print("✅ received_chunk_indices contains [0, 1]")
            
            if success:
                print("✅ SCENARIO 1 PASSED: Resume upload support verified!")
            
            # Clean up this upload session (upload remaining chunks to complete)
            for chunk_index in range(2, total_chunks):
                start_byte = chunk_index * chunk_size
                end_byte = min(start_byte + chunk_size, len(pdf_data))
                chunk_data = pdf_data[start_byte:end_byte]
                
                files = {'file': ('chunk', io.BytesIO(chunk_data), 'application/octet-stream')}
                self.session.post(f"{BASE_URL}/pdf-upload/{upload_id}/chunk?chunk_index={chunk_index}", files=files)
            
            # Complete upload
            self.session.post(f"{BASE_URL}/pdf-upload/{upload_id}/complete")
            
            return success
            
        except Exception as e:
            print(f"❌ Scenario 1 test failed: {str(e)}")
            return False
    
    def test_full_end_to_end_with_large_pdf(self) -> bool:
        """Test Scenario 2: Full End-to-End with larger PDF and resume verification"""
        print("\n📋 TEST SCENARIO 2: Full End-to-End with Resume (Large PDF)")
        
        try:
            # Create a 5-page PDF (as required)
            pdf_data = self.create_large_test_pdf(5)
            if not pdf_data:
                return False
            
            total_chunks = self.calculate_chunks(len(pdf_data))
            print(f"ℹ️  PDF size: {len(pdf_data)} bytes, calculated chunks: {total_chunks}")
            
            # Step 1: Initialize upload
            init_response = self.session.post(f"{BASE_URL}/pdf-upload/init", json={
                "batch_id": self.batch_id,
                "filename": "end_to_end_large.pdf",
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
            chunk_data = pdf_data[:min(chunk_size, len(pdf_data))]
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
                print(f"❌ Unexpected status after chunk 0: received={status_data['chunks_received']}, indices={status_data['received_chunk_indices']}")
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
            final_status = None
            for poll in range(max_polls):
                time.sleep(1)
                status_response = self.session.get(f"{BASE_URL}/pdf-upload/{upload_id}/status")
                status_data = status_response.json()
                
                status = status_data["upload_status"]
                print(f"   Poll {poll + 1}: {status} (imported: {status_data.get('imported', 0)}, total_pages: {status_data.get('total_pages', 0)})")
                
                if status == "done":
                    final_status = status_data
                    break
                elif status == "error":
                    print(f"❌ Processing failed: {status_data.get('error', 'Unknown error')}")
                    return False
            
            if not final_status or final_status["upload_status"] != "done":
                print(f"❌ Processing did not complete in {max_polls} seconds")
                return False
            
            # Step 7: Verify results (imported=5, total_pages=5)
            if final_status["imported"] != 5 or final_status["total_pages"] != 5:
                print(f"❌ Expected 5 imported pages, got: imported={final_status['imported']}, total_pages={final_status['total_pages']}")
                return False
            
            print("✅ SCENARIO 2 PASSED: End-to-end upload with resume completed successfully!")
            print(f"   - Total pages: {final_status['total_pages']}")
            print(f"   - Imported: {final_status['imported']}")
            
            return True
            
        except Exception as e:
            print(f"❌ Scenario 2 test failed: {str(e)}")
            return False
    
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
    
    def run_resume_tests(self) -> Dict[str, Any]:
        """Run enhanced resume upload tests"""
        print("🚀 ENHANCED RESUME UPLOAD TESTING")
        print("=" * 60)
        
        # Authenticate
        if not self.authenticate():
            return {"success": False, "error": "Authentication failed"}
        
        # Create test batch
        if not self.create_test_batch():
            return {"success": False, "error": "Batch creation failed"}
        
        # Run enhanced resume tests
        test_results = {
            "scenario_1_resume_support": self.test_resume_upload_scenario_1(),
            "scenario_2_full_end_to_end": self.test_full_end_to_end_with_large_pdf(),
        }
        
        # Cleanup
        cleanup_success = self.cleanup()
        
        # Summary
        passed = sum(1 for result in test_results.values() if result)
        total = len(test_results)
        
        print(f"\n📊 ENHANCED TEST SUMMARY")
        print("=" * 60)
        print(f"Tests Passed: {passed}/{total}")
        
        for test_name, result in test_results.items():
            status = "✅ PASS" if result else "❌ FAIL"
            print(f"{test_name.replace('_', ' ').title()}: {status}")
        
        success = all(test_results.values())
        
        if success:
            print(f"\n🎉 ALL ENHANCED RESUME TESTS PASSED!")
            print("✅ Resume upload support is working correctly with server-side chunk tracking")
            print("✅ Full end-to-end workflow with resume capabilities functional")
            print("✅ Status endpoint provides proper resume information (chunks_received, received_chunk_indices)")
        else:
            print(f"\n❌ Some enhanced resume tests failed. See details above.")
        
        return {
            "success": success,
            "passed": passed,
            "total": total,
            "results": test_results,
            "cleanup": cleanup_success
        }

if __name__ == "__main__":
    tester = ResumeUploadTester()
    results = tester.run_resume_tests()
    
    if not results["success"]:
        exit(1)