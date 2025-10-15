#!/usr/bin/env python3
"""Test script to verify backend functionality locally"""

from app import app

def test_health_endpoint():
    """Test the health endpoint"""
    print("🔍 Testing health endpoint...")
    with app.test_client() as client:
        response = client.get('/health')
        print(f"   Status: {response.status_code}")
        if response.status_code == 200:
            data = response.get_json()
            print(f"   Response: {data}")
            return True
        else:
            print(f"   Error: {response.get_data(as_text=True)}")
            return False

def test_ffmpeg_endpoint():
    """Test the FFmpeg endpoint"""
    print("🔍 Testing FFmpeg endpoint...")
    with app.test_client() as client:
        response = client.get('/test-ffmpeg')
        print(f"   Status: {response.status_code}")
        if response.status_code == 200:
            data = response.get_json()
            print(f"   Response: {data}")
            return True
        else:
            print(f"   Error: {response.get_data(as_text=True)}")
            return False

def test_convert_video_endpoint():
    """Test the convert-video endpoint (without file)"""
    print("🔍 Testing convert-video endpoint...")
    with app.test_client() as client:
        response = client.post('/convert-video')
        print(f"   Status: {response.status_code}")
        if response.status_code == 400:  # Expected - no file provided
            data = response.get_json()
            print(f"   Response: {data}")
            return True
        else:
            print(f"   Unexpected response: {response.get_data(as_text=True)}")
            return False

def main():
    """Run all tests"""
    print("🚀 Testing backend locally...")
    print("=" * 50)
    
    tests = [
        test_health_endpoint,
        test_ffmpeg_endpoint,
        test_convert_video_endpoint
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        try:
            if test():
                passed += 1
                print("   ✅ PASSED")
            else:
                print("   ❌ FAILED")
        except Exception as e:
            print(f"   ❌ ERROR: {e}")
        print()
    
    print("=" * 50)
    print(f"📊 Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! Backend is working locally.")
        return True
    else:
        print("⚠️  Some tests failed. Backend needs fixes.")
        return False

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
