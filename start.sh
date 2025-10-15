#!/bin/bash
# Get port from environment variable or default to 5000
PORT=${PORT:-5000}

echo "Starting Flask backend on port $PORT"
echo "Python version: $(python --version)"
echo "FFmpeg version: $(ffmpeg -version | head -1)"
echo "Current directory: $(pwd)"
echo "Files in current directory: $(ls -la)"
echo "Checking if app.py exists: $(ls -la app.py)"

# Test if we can import the app
echo "Testing Python import..."
python -c "import app; print('App import successful')"

# Start gunicorn with the port
echo "Starting Gunicorn..."
exec gunicorn --bind 0.0.0.0:$PORT --timeout 180 --workers 1 --max-requests 1000 --max-requests-jitter 50 app:app
