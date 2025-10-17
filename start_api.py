#!/usr/bin/env python3
"""
Startup script for the JustPDF API
"""

import os
import sys
import subprocess
from pathlib import Path

def check_dependencies():
    """Check if required dependencies are installed"""
    required_packages = [
        'flask',
        'flask-sqlalchemy',
        'flask-migrate',
        'flask-jwt-extended',
        'redis',
        'celery',
        'bcrypt',
        'psutil'
    ]
    
    missing_packages = []
    for package in required_packages:
        try:
            __import__(package.replace('-', '_'))
        except ImportError:
            missing_packages.append(package)
    
    if missing_packages:
        print("Missing required packages:")
        for package in missing_packages:
            print(f"  - {package}")
        print("\nInstall them with: pip install " + " ".join(missing_packages))
        return False
    
    return True

def check_redis():
    """Check if Redis is running"""
    try:
        import redis
        r = redis.from_url('redis://localhost:6379/0')
        r.ping()
        print("✓ Redis is running")
        return True
    except Exception as e:
        print(f"✗ Redis is not running: {e}")
        print("Start Redis with: redis-server")
        return False

def check_ffmpeg():
    """Check if FFmpeg is installed"""
    try:
        result = subprocess.run(['ffmpeg', '-version'], 
                              capture_output=True, text=True)
        if result.returncode == 0:
            print("✓ FFmpeg is installed")
            return True
    except FileNotFoundError:
        pass
    
    print("✗ FFmpeg is not installed")
    print("Install FFmpeg from: https://ffmpeg.org/download.html")
    return False

def setup_database():
    """Initialize database tables"""
    try:
        from app import app
        from database import init_db
        
        with app.app_context():
            init_db(app)
            print("✓ Database initialized")
        return True
    except Exception as e:
        print(f"✗ Database setup failed: {e}")
        return False

def start_celery():
    """Start Celery worker"""
    try:
        print("Starting Celery worker...")
        subprocess.Popen([
            sys.executable, '-m', 'celery', 
            '-A', 'celery_app', 'worker', 
            '--loglevel=info'
        ])
        print("✓ Celery worker started")
        return True
    except Exception as e:
        print(f"✗ Failed to start Celery: {e}")
        return False

def start_flask():
    """Start Flask application"""
    try:
        print("Starting Flask application...")
        from app import app
        app.run(debug=True, host='0.0.0.0', port=5000)
    except Exception as e:
        print(f"✗ Failed to start Flask: {e}")
        return False

def main():
    """Main startup function"""
    print("JustPDF API Startup")
    print("=" * 50)
    
    # Check dependencies
    if not check_dependencies():
        sys.exit(1)
    
    # Check external services
    if not check_redis():
        print("\nNote: Redis is required for rate limiting and async processing")
        print("You can still run the API without Redis, but some features will be limited")
    
    if not check_ffmpeg():
        print("\nNote: FFmpeg is required for video/audio conversion")
        print("The API will start but conversion features will not work")
    
    # Setup database
    if not setup_database():
        sys.exit(1)
    
    # Start Celery (optional)
    if check_redis():
        start_celery()
    
    # Start Flask
    print("\nStarting API server...")
    print("API will be available at: http://localhost:5000")
    print("Admin dashboard: http://localhost:3000/admin")
    print("Client dashboard: http://localhost:3000/dashboard")
    print("API documentation: http://localhost:3000/api/docs")
    print("\nPress Ctrl+C to stop the server")
    
    start_flask()

if __name__ == "__main__":
    main()
