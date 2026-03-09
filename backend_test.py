#!/usr/bin/env python3
"""
Backend Testing for Chunked PDF Upload System (1GB support)
Comprehensive test suite for the new PDF import functionality
"""

import asyncio
import requests
import json
import tempfile
import io
from pathlib import Path
import time
import os

# Get backend URL from frontend env
BACKEND_URL = "https://gem-bulk-import.preview.emergentagent.com/api"

# Test data
ADMIN_PHONE = "9999999999"
OTP = "1234"

class TestResult:
    def __init__(self):
        self.tests = []
        
    def add_test(self, name, status, details=""):
        self.tests.append({
            "test": name,
            "status": status,
            "details": details
        })
        print(f"{'✅' if status == 'PASS' else '❌'} {name}: {details}")
    
    def summary(self):
        passed = sum(1 for t in self.tests if t["status"] == "PASS")
        failed = sum(1 for t in self.tests if t["status"] == "FAIL")
        print(f"\n=== TEST SUMMARY ===")
        print(f"Total: {len(self.tests)}, Passed: {passed}, Failed: {failed}")
        return passed, failed

class PDFChunkedUploadTester:
    def __init__(self):
        self.session = requests.Session()
        self.session.timeout = 60
        self.auth_token = None
        self.result = TestResult()
        
    def authenticate(self):
        """Authenticate as admin user"""
        # Send OTP
        resp = self.session.post(f"{BACKEND_URL}/auth/send-otp", 
                               json={"phone": ADMIN_PHONE})
        if resp.status_code != 200:
            self.result.add_test("Admin OTP Send", "FAIL", f"Status {resp.status_code}")
            return False
            
        # Verify OTP
        resp = self.session.post(f"{BACKEND_URL}/auth/verify-otp",
                               json={"phone": ADMIN_PHONE, "otp": OTP})
        if resp.status_code != 200:
            self.result.add_test("Admin OTP Verify", "FAIL", f"Status {resp.status_code}")
            return False
            
        data = resp.json()
        self.auth_token = data["token"]
        self.session.headers.update({"Authorization": f"Bearer {self.auth_token}"})
        self.result.add_test("Admin Authentication", "PASS", f"Role: {data['user'].get('role')}")
        return True
    
    def create_test_batch(self):
        """Create a test batch for PDF upload"""
        resp = self.session.post(f"{BACKEND_URL}/batches", json={
            "name": "PDF Chunked Upload Test",
            "metal_type": "silver",
            "category": "test"
        })
        if resp.status_code != 200:
            self.result.add_test("Create Test Batch", "FAIL", f"Status {resp.status_code}")
            return None
            
        batch = resp.json()
        self.batch_id = batch["id"]
        self.result.add_test("Create Test Batch", "PASS", f"Batch ID: {batch['id']}")
        return batch["id"]
    
    def create_test_pdf(self, num_pages=5):
        """Create a test PDF with PyMuPDF"""
        try:
            import fitz  # PyMuPDF
            doc = fitz.open()  # Create empty PDF
            
            for i in range(num_pages):
                page = doc.new_page()
                text = f"Test PDF Page {i+1}\nThis is a test page for chunked upload testing.\nPage content: {i+1} of {num_pages}"
                page.insert_text((100, 100), text, fontsize=12)
                
                # Add some more content to make page larger
                for j in range(10):
                    page.insert_text((100, 200 + j*20), f"Line {j+1}: Sample content for testing PDF import functionality", fontsize=10)
            
            # Save to temporary file
            temp_file = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
            doc.save(temp_file.name)
            doc.close()
            
            file_size = os.path.getsize(temp_file.name)
            self.result.add_test("Create Test PDF", "PASS", f"{num_pages} pages, {file_size} bytes")
            return temp_file.name, file_size
            
        except Exception as e:
            self.result.add_test("Create Test PDF", "FAIL", f"Error: {str(e)}")
            return None, 0
    
    def test_validation_errors(self):
        """Test various validation scenarios"""
        
        # Test 1: File size > 1000MB
        resp = self.session.post(f"{BACKEND_URL}/pdf-upload/init", json={
            "batch_id": self.batch_id,
            "filename": "huge.pdf",
            "file_size": 1100000000,  # 1.1GB
            "total_chunks": 220
        })
        if resp.status_code == 413:
            self.result.add_test("Reject >1GB File", "PASS", "413 status returned")
        else:
            self.result.add_test("Reject >1GB File", "FAIL", f"Status {resp.status_code}")
        
        # Test 2: Non-PDF file
        resp = self.session.post(f"{BACKEND_URL}/pdf-upload/init", json={
            "batch_id": self.batch_id,
            "filename": "image.jpg",
            "file_size": 1000000,
            "total_chunks": 1
        })
        if resp.status_code == 400 and "PDF" in resp.text:
            self.result.add_test("Reject Non-PDF File", "PASS", "400 status with PDF error")
        else:
            self.result.add_test("Reject Non-PDF File", "FAIL", f"Status {resp.status_code}")
        
        # Test 3: Empty file
        resp = self.session.post(f"{BACKEND_URL}/pdf-upload/init", json={
            "batch_id": self.batch_id,
            "filename": "empty.pdf", 
            "file_size": 10,
            "total_chunks": 1
        })
        if resp.status_code == 400:
            self.result.add_test("Reject Empty File", "PASS", "400 status returned")
        else:
            self.result.add_test("Reject Empty File", "FAIL", f"Status {resp.status_code}")
        
        # Test 4: Invalid batch ID
        resp = self.session.post(f"{BACKEND_URL}/pdf-upload/init", json={
            "batch_id": "invalid-batch-id",
            "filename": "test.pdf",
            "file_size": 1000000,
            "total_chunks": 1
        })
        if resp.status_code == 404:
            self.result.add_test("Invalid Batch ID", "PASS", "404 status returned")
        else:
            self.result.add_test("Invalid Batch ID", "FAIL", f"Status {resp.status_code}")
    
    def test_chunked_upload_flow(self):
        """Test the complete chunked upload flow"""
        
        # Create test PDF
        pdf_path, file_size = self.create_test_pdf(5)
        if not pdf_path:
            return False
        
        # Calculate chunks (5MB per chunk)
        chunk_size = 5 * 1024 * 1024  # 5MB
        total_chunks = (file_size + chunk_size - 1) // chunk_size
        
        try:
            # Step 1: Initialize upload
            resp = self.session.post(f"{BACKEND_URL}/pdf-upload/init", json={
                "batch_id": self.batch_id,
                "filename": "test_5pages.pdf",
                "file_size": file_size,
                "total_chunks": total_chunks
            })
            
            if resp.status_code != 200:
                self.result.add_test("PDF Upload Init", "FAIL", f"Status {resp.status_code}")
                return False
            
            init_data = resp.json()
            upload_id = init_data["upload_id"]
            self.result.add_test("PDF Upload Init", "PASS", f"Upload ID: {upload_id}, Chunk size: {init_data['chunk_size']}")
            
            # Step 2: Upload chunks
            with open(pdf_path, 'rb') as f:
                for chunk_index in range(total_chunks):
                    chunk_data = f.read(chunk_size)
                    if not chunk_data:
                        break
                    
                    # Upload chunk
                    files = {'file': ('chunk.bin', chunk_data, 'application/octet-stream')}
                    resp = self.session.post(f"{BACKEND_URL}/pdf-upload/{upload_id}/chunk?chunk_index={chunk_index}", 
                                           files=files)
                    
                    if resp.status_code != 200:
                        self.result.add_test(f"Upload Chunk {chunk_index}", "FAIL", f"Status {resp.status_code}")
                        return False
                    
                    chunk_resp = resp.json()
                    print(f"  Chunk {chunk_index}: {chunk_resp['received']}/{chunk_resp['total']}")
            
            self.result.add_test("Upload All Chunks", "PASS", f"{total_chunks} chunks uploaded")
            
            # Step 3: Complete upload
            resp = self.session.post(f"{BACKEND_URL}/pdf-upload/{upload_id}/complete")
            if resp.status_code != 200:
                self.result.add_test("Complete Upload", "FAIL", f"Status {resp.status_code}")
                return False
            
            complete_data = resp.json()
            self.result.add_test("Complete Upload", "PASS", f"Status: {complete_data['status']}, Size: {complete_data['assembled_size_mb']}MB")
            
            # Step 4: Poll for completion
            max_polls = 30  # 30 seconds max
            for i in range(max_polls):
                resp = self.session.get(f"{BACKEND_URL}/pdf-upload/{upload_id}/status")
                if resp.status_code != 200:
                    self.result.add_test("Status Polling", "FAIL", f"Status {resp.status_code}")
                    return False
                
                status_data = resp.json()
                upload_status = status_data["upload_status"]
                
                print(f"  Poll {i+1}: {upload_status}, Pages: {status_data['pages_processed']}/{status_data['total_pages']}, Imported: {status_data['imported']}")
                
                if upload_status == "done":
                    self.result.add_test("PDF Processing Complete", "PASS", 
                                       f"Pages: {status_data['total_pages']}, Imported: {status_data['imported']}, Failed: {status_data['failed']}")
                    
                    # Verify expected results
                    if status_data['total_pages'] == 5 and status_data['imported'] == 5 and status_data['failed'] == 0:
                        self.result.add_test("PDF Import Results", "PASS", "All 5 pages imported successfully")
                    else:
                        self.result.add_test("PDF Import Results", "FAIL", f"Expected 5/5/0, got {status_data['total_pages']}/{status_data['imported']}/{status_data['failed']}")
                    break
                    
                elif upload_status == "error":
                    self.result.add_test("PDF Processing Complete", "FAIL", f"Error: {status_data.get('error', 'Unknown error')}")
                    return False
                
                time.sleep(1)
            else:
                self.result.add_test("PDF Processing Complete", "FAIL", "Timeout waiting for completion")
                return False
            
            # Step 5: Verify products created
            resp = self.session.get(f"{BACKEND_URL}/batches/{self.batch_id}/images")
            if resp.status_code != 200:
                self.result.add_test("Verify Products", "FAIL", f"Status {resp.status_code}")
                return False
            
            products_data = resp.json()
            products = products_data["images"]
            pdf_products = [p for p in products if p.get("source_type") == "pdf_import"]
            
            if len(pdf_products) == 5:
                # Check that all pages have correct source_page
                page_numbers = sorted([p.get("source_page", 0) for p in pdf_products])
                expected_pages = [1, 2, 3, 4, 5]
                if page_numbers == expected_pages:
                    self.result.add_test("Verify Products", "PASS", f"5 products with correct page numbers: {page_numbers}")
                else:
                    self.result.add_test("Verify Products", "FAIL", f"Wrong page numbers: {page_numbers}")
            else:
                self.result.add_test("Verify Products", "FAIL", f"Expected 5 PDF products, got {len(pdf_products)}")
            
            return True
            
        finally:
            # Cleanup temp file
            if os.path.exists(pdf_path):
                os.unlink(pdf_path)
    
    def test_missing_chunks_validation(self):
        """Test that completing upload with missing chunks fails"""
        pdf_path, file_size = self.create_test_pdf(2)
        if not pdf_path:
            return False
        
        try:
            # Initialize upload for 2 chunks but only upload 1
            total_chunks = 2
            resp = self.session.post(f"{BACKEND_URL}/pdf-upload/init", json={
                "batch_id": self.batch_id,
                "filename": "incomplete.pdf",
                "file_size": file_size,
                "total_chunks": total_chunks
            })
            
            if resp.status_code != 200:
                self.result.add_test("Init Incomplete Upload", "FAIL", f"Status {resp.status_code}")
                return False
            
            upload_id = resp.json()["upload_id"]
            
            # Upload only first chunk
            with open(pdf_path, 'rb') as f:
                chunk_data = f.read(file_size // 2)
                files = {'file': ('chunk.bin', chunk_data, 'application/octet-stream')}
                resp = self.session.post(f"{BACKEND_URL}/pdf-upload/{upload_id}/chunk?chunk_index=0", 
                                       files=files)
            
            if resp.status_code != 200:
                self.result.add_test("Upload Partial Chunks", "FAIL", f"Status {resp.status_code}")
                return False
            
            # Try to complete with missing chunks
            resp = self.session.post(f"{BACKEND_URL}/pdf-upload/{upload_id}/complete")
            if resp.status_code == 400 and "Missing chunks" in resp.text:
                self.result.add_test("Missing Chunks Validation", "PASS", "400 status with missing chunks error")
            else:
                self.result.add_test("Missing Chunks Validation", "FAIL", f"Status {resp.status_code}")
            
            return True
            
        finally:
            if os.path.exists(pdf_path):
                os.unlink(pdf_path)
    
    def test_legacy_compatibility(self):
        """Test that legacy PDF import endpoint still works"""
        pdf_path, file_size = self.create_test_pdf(3)
        if not pdf_path:
            return False
        
        try:
            with open(pdf_path, 'rb') as f:
                files = {'file': ('legacy_test.pdf', f, 'application/pdf')}
                resp = self.session.post(f"{BACKEND_URL}/batches/{self.batch_id}/import-pdf", files=files)
            
            if resp.status_code != 200:
                self.result.add_test("Legacy PDF Import", "FAIL", f"Status {resp.status_code}")
                return False
            
            data = resp.json()
            if data.get("total_pages") == 3 and data.get("imported") == 3 and data.get("failed") == 0:
                self.result.add_test("Legacy PDF Import", "PASS", f"3 pages imported successfully")
            else:
                self.result.add_test("Legacy PDF Import", "FAIL", f"Expected 3/3/0, got {data.get('total_pages')}/{data.get('imported')}/{data.get('failed')}")
            
            return True
            
        finally:
            if os.path.exists(pdf_path):
                os.unlink(pdf_path)
    
    def test_normal_image_upload(self):
        """Test that normal image upload still works"""
        try:
            # Create a simple test image
            from PIL import Image
            img = Image.new('RGB', (800, 600), color='red')
            img_buffer = io.BytesIO()
            img.save(img_buffer, format='JPEG')
            img_data = img_buffer.getvalue()
            
            files = {'files': ('test_image.jpg', img_data, 'image/jpeg')}
            resp = self.session.post(f"{BACKEND_URL}/batches/{self.batch_id}/upload", files=files)
            
            if resp.status_code != 200:
                self.result.add_test("Normal Image Upload", "FAIL", f"Status {resp.status_code}")
                return False
            
            data = resp.json()
            if data.get("uploaded", 0) > 0:
                self.result.add_test("Normal Image Upload", "PASS", f"Image uploaded successfully")
            else:
                self.result.add_test("Normal Image Upload", "FAIL", f"No images uploaded")
            
            return True
            
        except Exception as e:
            self.result.add_test("Normal Image Upload", "FAIL", f"Error: {str(e)}")
            return False
    
    def cleanup(self):
        """Clean up test batch"""
        if hasattr(self, 'batch_id'):
            resp = self.session.delete(f"{BACKEND_URL}/batches/{self.batch_id}")
            if resp.status_code == 200:
                self.result.add_test("Cleanup Test Batch", "PASS", f"Batch {self.batch_id} deleted")
            else:
                self.result.add_test("Cleanup Test Batch", "FAIL", f"Status {resp.status_code}")
    
    def run_all_tests(self):
        """Run complete test suite"""
        print("=== CHUNKED PDF UPLOAD TESTING ===")
        print(f"Backend URL: {BACKEND_URL}")
        
        # Authentication
        if not self.authenticate():
            return
        
        # Create test batch
        if not self.create_test_batch():
            return
        
        try:
            # Run all tests
            self.test_validation_errors()
            self.test_chunked_upload_flow() 
            self.test_missing_chunks_validation()
            self.test_legacy_compatibility()
            self.test_normal_image_upload()
            
        finally:
            # Always cleanup
            self.cleanup()
        
        # Print summary
        passed, failed = self.result.summary()
        
        if failed == 0:
            print("\n🎉 ALL TESTS PASSED! Chunked PDF upload system is working correctly.")
        else:
            print(f"\n⚠️  {failed} test(s) failed. Check the details above.")
        
        return failed == 0

def main():
    """Main test runner"""
    tester = PDFChunkedUploadTester()
    success = tester.run_all_tests()
    return success

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)