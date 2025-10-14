#!/usr/bin/env python3
"""
Create a test audio file using FFmpeg
"""

import subprocess
import os

def create_test_audio():
    """Create a test audio file"""
    try:
        # Create a 10-second test audio file with a sine wave
        cmd = [
            'ffmpeg',
            '-f', 'lavfi',
            '-i', 'sine=frequency=440:duration=10',
            '-acodec', 'pcm_s16le',
            '-ar', '44100',
            '-ac', '2',
            '-y',
            'test-audio.wav'
        ]
        
        print("Creating test audio file...")
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            print("✅ Test audio file created successfully!")
            print("File: test-audio.wav")
            return True
        else:
            print(f"❌ Failed to create test audio: {result.stderr}")
            return False
            
    except Exception as e:
        print(f"Error creating test audio: {e}")
        return False

if __name__ == "__main__":
    create_test_audio()
