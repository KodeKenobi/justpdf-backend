#!/bin/bash
set -e  # Exit on error

# Get port from environment variable or default to 5000
PORT=${PORT:-5000}

echo "=== STARTING FLASK BACKEND ==="
echo "Port: $PORT"
echo "Python version: $(python --version)"
echo "FFmpeg version: $(ffmpeg -version | head -1 2>/dev/null || echo 'FFmpeg not found')"
echo "Current directory: $(pwd)"
echo "Files in current directory: $(ls -la)"

# Add current directory to Python path
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
echo "PYTHONPATH: $PYTHONPATH"

# Test if we can import the app
echo "Testing Python import..."
python -c "
import sys
import traceback
try:
    import app
    print('✅ App import successful')
except Exception as e:
    print(f'❌ Failed to import app: {e}')
    traceback.print_exc()
    sys.exit(1)
" || {
    echo "ERROR: Failed to import app"
    exit 1
}

# Test health endpoint before starting gunicorn (non-blocking)
echo "Testing health endpoint..."
python -c "
import sys
try:
    from app import app as flask_app
    with flask_app.test_client() as client:
        response = client.get('/health')
        print(f'Health test status: {response.status_code}')
        if response.status_code == 200:
            print('✅ Health endpoint working!')
        else:
            print(f'⚠️ Health endpoint returned: {response.get_data(as_text=True)}')
except Exception as e:
    print(f'⚠️ Health endpoint test failed: {e}')
    import traceback
    traceback.print_exc()
" || {
    echo "WARNING: Health endpoint test failed, but continuing..."
}

# Start gunicorn with the port
echo "Starting Gunicorn on 0.0.0.0:$PORT..."
echo "Gunicorn command: gunicorn --bind 0.0.0.0:$PORT --timeout 180 --workers 1 --max-requests 1000 --max-requests-jitter 50 app:app"
exec gunicorn --bind 0.0.0.0:$PORT --timeout 180 --workers 1 --max-requests 1000 --max-requests-jitter 50 --access-logfile - --error-logfile - --log-level info app:app
