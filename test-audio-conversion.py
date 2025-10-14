#!/usr/bin/env python3
"""
Test script for audio conversion backend
"""

import requests
import os

def test_audio_conversion():
    """Test audio conversion endpoint"""
    
    # Test health endpoint first
    print("Testing health endpoint...")
    try:
        response = requests.get("http://localhost:5000/health")
        print(f"Health check: {response.status_code}")
        print(f"Response: {response.json()}")
    except Exception as e:
        print(f"Health check failed: {e}")
        return
    
    # Check if we have any audio files to test with
    audio_files = []
    # Check current directory
    for file in os.listdir('.'):
        if file.endswith(('.mp3', '.wav', '.flac', '.aac', '.ogg', '.m4a', '.wma', '.aiff', '.au')):
            audio_files.append(file)
    
    # Check uploads directory
    if os.path.exists('uploads'):
        for file in os.listdir('uploads'):
            if file.endswith(('.mp3', '.wav', '.flac', '.aac', '.ogg', '.m4a', '.wma', '.aiff', '.au')):
                audio_files.append(os.path.join('uploads', file))
    
    if not audio_files:
        print("No audio files found for testing")
        print("Please add an audio file to test conversion")
        return
    
    print(f"Found audio files: {audio_files}")
    
    # Test with the first audio file
    test_file = audio_files[0]
    print(f"Testing with: {test_file}")
    
    # Test MP3 conversion
    print("\nTesting MP3 conversion...")
    try:
        with open(test_file, 'rb') as f:
            files = {'file': f}
            data = {
                'outputFormat': 'mp3',
                'bitrate': '192',
                'sampleRate': '44100',
                'channels': 'stereo',
                'quality': '80'
            }
            
            response = requests.post("http://localhost:5000/convert-audio", files=files, data=data)
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
    
    # Test FLAC conversion
    print("\nTesting FLAC conversion...")
    try:
        with open(test_file, 'rb') as f:
            files = {'file': f}
            data = {
                'outputFormat': 'flac',
                'bitrate': '0',  # FLAC is lossless
                'sampleRate': '44100',
                'channels': 'stereo',
                'quality': '100'
            }
            
            response = requests.post("http://localhost:5000/convert-audio", files=files, data=data)
            print(f"FLAC conversion status: {response.status_code}")
            print(f"Response: {response.json()}")
            
            if response.status_code == 200:
                result = response.json()
                if result.get('status') == 'success':
                    print(f"✅ FLAC conversion successful!")
                    print(f"Download URL: http://localhost:5000{result['download_url']}")
                else:
                    print(f"❌ FLAC conversion failed: {result.get('message')}")
            
    except Exception as e:
        print(f"FLAC conversion test failed: {e}")

if __name__ == "__main__":
    test_audio_conversion()
