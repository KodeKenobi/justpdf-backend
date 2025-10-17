#!/usr/bin/env python3
"""
Test script to verify CORS configuration
"""
import requests
import json

def test_cors_headers():
    """Test CORS headers for the video conversion endpoint"""
    
    # Test URLs
    base_url = "https://justpdf-backend-production.up.railway.app"
    local_url = "http://localhost:5000"
    
    # Test origins
    test_origins = [
        "https://www.trevnoctilla.com",
        "https://trevnoctilla.com", 
        "http://localhost:3000",
        "https://web-production-ef253.up.railway.app"
    ]
    
    print("🧪 Testing CORS Configuration")
    print("=" * 50)
    
    # Test production backend
    print(f"\n🌐 Testing Production Backend: {base_url}")
    try:
        # Test OPTIONS request (preflight)
        for origin in test_origins:
            print(f"\n📍 Testing origin: {origin}")
            try:
                response = requests.options(
                    f"{base_url}/convert-video",
                    headers={
                        'Origin': origin,
                        'Access-Control-Request-Method': 'POST',
                        'Access-Control-Request-Headers': 'Content-Type'
                    },
                    timeout=10
                )
                
                print(f"   Status: {response.status_code}")
                cors_headers = {k: v for k, v in response.headers.items() if 'access-control' in k.lower()}
                
                if cors_headers:
                    print("   CORS Headers:")
                    for header, value in cors_headers.items():
                        print(f"     {header}: {value}")
                else:
                    print("   ❌ No CORS headers found")
                    
            except requests.exceptions.RequestException as e:
                print(f"   ❌ Error: {e}")
                
    except Exception as e:
        print(f"❌ Production backend test failed: {e}")
    
    # Test local backend
    print(f"\n🏠 Testing Local Backend: {local_url}")
    try:
        # Test OPTIONS request (preflight)
        for origin in test_origins:
            print(f"\n📍 Testing origin: {origin}")
            try:
                response = requests.options(
                    f"{local_url}/convert-video",
                    headers={
                        'Origin': origin,
                        'Access-Control-Request-Method': 'POST',
                        'Access-Control-Request-Headers': 'Content-Type'
                    },
                    timeout=5
                )
                
                print(f"   Status: {response.status_code}")
                cors_headers = {k: v for k, v in response.headers.items() if 'access-control' in k.lower()}
                
                if cors_headers:
                    print("   CORS Headers:")
                    for header, value in cors_headers.items():
                        print(f"     {header}: {value}")
                else:
                    print("   ❌ No CORS headers found")
                    
            except requests.exceptions.RequestException as e:
                print(f"   ❌ Error: {e}")
                
    except Exception as e:
        print(f"❌ Local backend test failed: {e}")

if __name__ == "__main__":
    test_cors_headers()
