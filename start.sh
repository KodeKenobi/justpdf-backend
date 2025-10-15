#!/bin/bash
# Get port from environment variable or default to 5000
PORT=${PORT:-5000}

echo "=== STARTING FLASK BACKEND ==="
echo "Port: $PORT"
echo "Python version: $(python --version)"
echo "FFmpeg version: $(ffmpeg -version | head -1)"
echo "Current directory: $(pwd)"
echo "Files in current directory: $(ls -la)"
echo "Checking if app.py exists: $(ls -la app.py)"

# Test if we can import the app
echo "Testing Python import..."
python -c "import app; print('App import successful')"

# Test health endpoint before starting gunicorn
echo "Testing health endpoint..."
python -c "
from app import app as flask_app
with flask_app.test_client() as client:
    response = client.get('/health')
    print(f'Health test status: {response.status_code}')
    if response.status_code == 200:
        print('Health endpoint working!')
    else:
        print(f'Health endpoint failed: {response.get_data(as_text=True)}')
"

# Start gunicorn with the port
echo "Starting Gunicorn on 0.0.0.0:$PORT..."
exec gunicorn --bind 0.0.0.0:$PORT --timeout 180 --workers 1 --max-requests 1000 --max-requests-jitter 50 app:app
