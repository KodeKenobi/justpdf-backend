#!/usr/bin/env python
"""Test script to check the /convert endpoint with mobile parameter"""
import os
import sys
import requests
import json

# Test the endpoint
BASE_URL = "http://localhost:5000"

print(" Testing /convert endpoint with mobile parameter...\n")

# First, check if we have a test PDF file
upload_folder = "uploads"
if os.path.exists(upload_folder):
    pdf_files = [f for f in os.listdir(upload_folder) if f.endswith('.pdf')]
    if pdf_files:
        test_filename = pdf_files[0]
        print(f" Found test PDF: {test_filename}")
        
        # Test the endpoint
        url = f"{BASE_URL}/convert/{test_filename}?mobile=true&v=1234567890"
        print(f" Testing URL: {url}\n")
        
        try:
            response = requests.get(url, timeout=10)
            print(f"[INFO] Response status: {response.status_code}")
            print(f"[INFO] Response headers: {dict(response.headers)}")
            
            if response.status_code == 200:
                print(f"[OK] Success! Response length: {len(response.text)} bytes")
                print(f" Response preview (first 500 chars):\n{response.text[:500]}...")
            else:
                print(f"[ERROR] Error response!")
                print(f" Response text (first 1000 chars):\n{response.text[:1000]}")
                
                # Try to parse as JSON
                try:
                    error_data = response.json()
                    print(f"[LIST] Error JSON: {json.dumps(error_data, indent=2)}")
                except:
                    print("[WARN]  Response is not JSON")
                    
        except requests.exceptions.ConnectionError:
            print("[ERROR] Cannot connect to backend. Is it running on http://localhost:5000?")
        except requests.exceptions.Timeout:
            print("[ERROR] Request timed out")
        except Exception as e:
            print(f"[ERROR] Error: {str(e)}")
            import traceback
            print(f"Traceback:\n{traceback.format_exc()}")
    else:
        print("[WARN]  No PDF files found in uploads folder")
        print("[INFO] Upload a PDF first, then run this test")
else:
    print(f"[WARN]  Upload folder '{upload_folder}' does not exist")

print("\n[OK] Test complete!")

