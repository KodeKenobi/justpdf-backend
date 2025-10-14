#!/usr/bin/env python3
"""
Test script for video conversion backend
"""

import requests
import os

def test_video_conversion():
    """Test video conversion endpoint"""
    
    # Test health endpoint first
    print("Testing health endpoint...")
    try:
        response = requests.get("http://localhost:5000/health")
        print(f"Health check: {response.status_code}")
        print(f"Response: {response.json()}")
    except Exception as e:
        print(f"Health check failed: {e}")
        return
    
    # Check if we have any video files to test with
    video_files = []
    # Check current directory
    for file in os.listdir('.'):
        if file.endswith(('.mp4', '.avi', '.mov', '.mkv', '.webm')):
            video_files.append(file)
    
    # Check uploads directory
    if os.path.exists('uploads'):
        for file in os.listdir('uploads'):
            if file.endswith(('.mp4', '.avi', '.mov', '.mkv', '.webm')):
                video_files.append(os.path.join('uploads', file))
    
    if not video_files:
        print("No video files found for testing")
        print("Please add a video file to test conversion")
        return
    
    print(f"Found video files: {video_files}")
    
    # Test with the first video file
    test_file = video_files[0]
    print(f"Testing with: {test_file}")
    
    # Test MP3 extraction
    print("\nTesting MP3 extraction...")
    try:
        with open(test_file, 'rb') as f:
            files = {'file': f}
            data = {
                'outputFormat': 'mp3',
                'quality': '80',
                'compression': 'medium'
            }
            
            response = requests.post("http://localhost:5000/convert-video", files=files, data=data)
            print(f"MP3 conversion status: {response.status_code}")
            print(f"Response: {response.json()}")
            
            if response.status_code == 200:
                result = response.json()
                if result.get('status') == 'success':
                    print(f"✅ MP3 conversion successful!")
                    print(f"Download URL: http://localhost:5000{result['download_url']}")
                else:
                    print(f"❌ MP3 conversion failed: {result.get('message')}")
            
    except Exception as e:
        print(f"MP3 conversion test failed: {e}")
    
    # Test video conversion
    print("\nTesting video conversion to MP4...")
    try:
        with open(test_file, 'rb') as f:
            files = {'file': f}
            data = {
                'outputFormat': 'mp4',
                'quality': '80',
                'compression': 'medium'
            }
            
            response = requests.post("http://localhost:5000/convert-video", files=files, data=data)
            print(f"Video conversion status: {response.status_code}")
            print(f"Response: {response.json()}")
            
            if response.status_code == 200:
                result = response.json()
                if result.get('status') == 'success':
                    print(f"✅ Video conversion successful!")
                    print(f"Download URL: http://localhost:5000{result['download_url']}")
                else:
                    print(f"❌ Video conversion failed: {result.get('message')}")
            
    except Exception as e:
        print(f"Video conversion test failed: {e}")

if __name__ == "__main__":
    test_video_conversion()
