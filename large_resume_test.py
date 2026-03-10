#!/usr/bin/env python3
"""
Large File Resume Upload Testing
Creates larger PDF files to properly test chunked upload resume functionality.
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

class LargeFileResumeTest:
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
            print(f"✅ Authenticated as admin")
            return True
            
        except Exception as e:
            print(f"❌ Authentication failed: {str(e)}")
            return False
    
    def create_test_batch(self) -> bool:
        """Create a test batch for uploads"""
        try:
            response = self.session.post(f"{BASE_URL}/batches", json={
                "name": "Large File Resume Test",
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
    
    def create_very_large_pdf(self, target_size_mb: float = 15.0) -> bytes:
        """Create a PDF large enough to require multiple 5MB chunks"""
        try:
            target_size = int(target_size_mb * 1024 * 1024)  # Convert MB to bytes
            doc = fitz.open()
            
            # Create pages with lots of content until we reach target size
            page_num = 1
            current_size = 0
            
            while current_size < target_size:
                page = doc.new_page(width=595, height=842)  # A4
                
                # Create a lot of text content to increase file size
                large_text = ""
                for i in range(200):  # 200 paragraphs per page
                    large_text += f"""Page {page_num}, Paragraph {i+1}: This is comprehensive test content for PDF chunked upload functionality. 
The system must handle large files correctly with proper chunking and resume capabilities. Lorem ipsum dolor sit amet, 
consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, 
quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat. Duis aute irure dolor in reprehenderit 
in voluptate velit esse cillum dolore eu fugiat nulla pariatur. Excepteur sint occaecat cupidatat non proident, sunt in 
culpa qui officia deserunt mollit anim id est laborum. Sed ut perspiciatis unde omnis iste natus error sit voluptatem.

"""
                
                # Insert text with formatting
                rect = fitz.Rect(50, 50, 545, 792)
                page.insert_textbox(rect, large_text, fontsize=8, fontname="helv")
                
                # Add some graphics to increase file size
                for j in range(20):
                    y_pos = 100 + (j * 30)
                    page.draw_rect(fitz.Rect(50, y_pos, 545, y_pos + 20), 
                                 color=(j*0.05, 0.2, 0.8), fill=True)
                
                # Check current size
                temp_bytes = doc.tobytes()
                current_size = len(temp_bytes)
                page_num += 1
                
                print(f"   Created page {page_num-1}, current size: {current_size/1024/1024:.2f} MB")
                
                # Safety break to avoid infinite loop
                if page_num > 50:
                    break
            
            pdf_bytes = doc.tobytes()
            doc.close()
            
            print(f"✅ Created large PDF: {page_num-1} pages, {len(pdf_bytes)} bytes ({len(pdf_bytes)/(1024*1024):.2f} MB)")
            return pdf_bytes
            
        except Exception as e:
            print(f"❌ Large PDF creation failed: {str(e)}")
            return b""
    
    def test_actual_resume_functionality(self) -> bool:
        """Test the exact resume scenario from the review request"""
        print("\n📋 ACTUAL RESUME FUNCTIONALITY TEST")
        
        try:
            # Create a large PDF that will definitely need multiple chunks
            pdf_data = self.create_very_large_pdf(15.0)  # 15MB target
            if not pdf_data:
                return False
            
            chunk_size = 5242880  # 5MB
            total_chunks = (len(pdf_data) + chunk_size - 1) // chunk_size
            print(f"ℹ️  PDF: {len(pdf_data)} bytes, chunks needed: {total_chunks}")
            
            if total_chunks < 3:
                print("❌ Still not large enough for proper chunk testing")
                return False
            
            # Step 1: Initialize upload session
            init_response = self.session.post(f"{BASE_URL}/pdf-upload/init", json={
                "batch_id": self.batch_id,
                "filename": "large_resume_test.pdf",
                "file_size": len(pdf_data),
                "total_chunks": total_chunks
            })
            
            if init_response.status_code != 200:
                print(f"❌ Init failed: {init_response.status_code}")
                return False
            
            init_data = init_response.json()
            upload_id = init_data["upload_id"]
            print(f"✅ Initialized upload: {upload_id} ({total_chunks} chunks)")
            
            # Step 2: Upload only chunk 0 and chunk 1 (skip chunk 2 as per review request)
            uploaded_chunks = [0, 1]
            for chunk_index in uploaded_chunks:
                start_byte = chunk_index * chunk_size
                end_byte = min(start_byte + chunk_size, len(pdf_data))
                chunk_data = pdf_data[start_byte:end_byte]
                
                files = {'file': ('chunk', io.BytesIO(chunk_data), 'application/octet-stream')}
                response = self.session.post(
                    f"{BASE_URL}/pdf-upload/{upload_id}/chunk?chunk_index={chunk_index}",
                    files=files
                )
                
                if response.status_code != 200:
                    print(f"❌ Chunk {chunk_index} upload failed: {response.status_code}")
                    return False
                
                print(f"✅ Uploaded chunk {chunk_index}")
            
            # Step 3: Call GET /api/pdf-upload/{upload_id}/status and verify resume info
            status_response = self.session.get(f"{BASE_URL}/pdf-upload/{upload_id}/status")
            if status_response.status_code != 200:
                print(f"❌ Status check failed: {status_response.status_code}")
                return False
            
            status = status_response.json()
            print(f"📊 Status Response:")
            print(f"   - upload_status: {status.get('upload_status')}")
            print(f"   - chunks_received: {status.get('chunks_received')}")
            print(f"   - total_chunks: {status.get('total_chunks')}")
            print(f"   - received_chunk_indices: {status.get('received_chunk_indices')}")
            
            # Verify exact requirements from review request
            success = True
            
            if status.get('upload_status') != 'uploading':
                print(f"❌ Expected upload_status 'uploading', got '{status.get('upload_status')}'")
                success = False
            
            if status.get('chunks_received') != 2:
                print(f"❌ Expected chunks_received 2, got {status.get('chunks_received')}")
                success = False
            
            if status.get('received_chunk_indices') != [0, 1]:
                print(f"❌ Expected received_chunk_indices [0, 1], got {status.get('received_chunk_indices')}")
                success = False
            
            if success:
                print("✅ RESUME FUNCTIONALITY VERIFIED: All requirements met!")
                print("   ✓ upload_status is 'uploading'")
                print("   ✓ chunks_received is 2") 
                print("   ✓ received_chunk_indices contains [0, 1]")
            
            # Clean up by uploading remaining chunks and completing
            for chunk_index in range(2, total_chunks):
                start_byte = chunk_index * chunk_size
                end_byte = min(start_byte + chunk_size, len(pdf_data))
                chunk_data = pdf_data[start_byte:end_byte]
                
                files = {'file': ('chunk', io.BytesIO(chunk_data), 'application/octet-stream')}
                self.session.post(f"{BASE_URL}/pdf-upload/{upload_id}/chunk?chunk_index={chunk_index}", files=files)
            
            # Complete the upload
            self.session.post(f"{BASE_URL}/pdf-upload/{upload_id}/complete")
            
            return success
            
        except Exception as e:
            print(f"❌ Resume functionality test failed: {str(e)}")
            return False
    
    def test_simulated_resume_with_smaller_file(self) -> bool:
        """Test resume simulation even with smaller files by manually setting chunk count"""
        print("\n📋 SIMULATED RESUME TEST (Forced Multiple Chunks)")
        
        try:
            # Create a smaller PDF but force multiple chunks by setting total_chunks manually
            pdf_data = self.create_very_large_pdf(1.0)  # 1MB file
            if not pdf_data:
                return False
            
            # Force at least 3 chunks regardless of file size
            forced_total_chunks = 5
            simulated_chunk_size = len(pdf_data) // forced_total_chunks + 1
            
            print(f"ℹ️  Simulated test: {len(pdf_data)} bytes, forced {forced_total_chunks} chunks")
            
            # Step 1: Initialize with forced chunk count
            init_response = self.session.post(f"{BASE_URL}/pdf-upload/init", json={
                "batch_id": self.batch_id,
                "filename": "simulated_resume_test.pdf",
                "file_size": len(pdf_data),
                "total_chunks": forced_total_chunks
            })
            
            if init_response.status_code != 200:
                print(f"❌ Init failed: {init_response.status_code}")
                return False
            
            init_data = init_response.json()
            upload_id = init_data["upload_id"]
            actual_chunk_size = init_data["chunk_size"]  # Server determines chunk size
            
            print(f"✅ Initialized: {upload_id}, server chunk_size: {actual_chunk_size}")
            
            # Step 2: Upload only chunks 0 and 1
            for chunk_index in [0, 1]:
                if chunk_index == 0:
                    # First chunk
                    chunk_data = pdf_data[:min(actual_chunk_size, len(pdf_data))]
                else:
                    # Second chunk (remaining data or empty if file is too small)
                    start = actual_chunk_size
                    if start < len(pdf_data):
                        chunk_data = pdf_data[start:start + actual_chunk_size]
                    else:
                        chunk_data = b"dummy"  # Minimal dummy data for chunk 1
                
                files = {'file': ('chunk', io.BytesIO(chunk_data), 'application/octet-stream')}
                response = self.session.post(
                    f"{BASE_URL}/pdf-upload/{upload_id}/chunk?chunk_index={chunk_index}",
                    files=files
                )
                
                if response.status_code != 200:
                    print(f"❌ Chunk {chunk_index} upload failed: {response.status_code}")
                    return False
                
                print(f"✅ Uploaded chunk {chunk_index}")
            
            # Step 3: Check status
            status_response = self.session.get(f"{BASE_URL}/pdf-upload/{upload_id}/status")
            status = status_response.json()
            
            print(f"📊 Simulated Resume Status:")
            print(f"   - upload_status: {status.get('upload_status')}")
            print(f"   - chunks_received: {status.get('chunks_received')}")
            print(f"   - received_chunk_indices: {status.get('received_chunk_indices')}")
            
            # Verify resume support works
            success = (
                status.get('upload_status') == 'uploading' and
                status.get('chunks_received') == 2 and
                status.get('received_chunk_indices') == [0, 1]
            )
            
            if success:
                print("✅ SIMULATED RESUME TEST PASSED!")
            else:
                print("❌ Simulated resume test failed")
            
            return success
            
        except Exception as e:
            print(f"❌ Simulated resume test failed: {str(e)}")
            return False
    
    def cleanup(self) -> bool:
        """Clean up test batch"""
        if self.batch_id:
            try:
                response = self.session.delete(f"{BASE_URL}/batches/{self.batch_id}")
                return response.status_code == 200
            except:
                return False
        return True
    
    def run_tests(self) -> Dict[str, Any]:
        """Run all resume upload tests"""
        print("🚀 LARGE FILE RESUME UPLOAD TESTING")
        print("=" * 60)
        
        if not self.authenticate() or not self.create_test_batch():
            return {"success": False, "error": "Setup failed"}
        
        # Run tests
        test_results = {
            "actual_resume_functionality": self.test_actual_resume_functionality(),
            "simulated_resume_test": self.test_simulated_resume_with_smaller_file(),
        }
        
        self.cleanup()
        
        # Summary
        passed = sum(1 for result in test_results.values() if result)
        total = len(test_results)
        success = all(test_results.values())
        
        print(f"\n📊 RESUME TEST SUMMARY")
        print("=" * 60)
        print(f"Tests Passed: {passed}/{total}")
        
        for test_name, result in test_results.items():
            status = "✅ PASS" if result else "❌ FAIL"
            print(f"{test_name.replace('_', ' ').title()}: {status}")
        
        if success:
            print(f"\n🎉 RESUME UPLOAD FUNCTIONALITY VERIFIED!")
        else:
            print(f"\n❌ Some resume tests failed.")
        
        return {"success": success, "passed": passed, "total": total, "results": test_results}

if __name__ == "__main__":
    tester = LargeFileResumeTest()
    results = tester.run_tests()
    
    if not results["success"]:
        exit(1)