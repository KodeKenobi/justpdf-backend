#!/bin/bash
# Get port from environment variable or default to 5000
PORT=${PORT:-5000}

echo "Starting Flask backend on port $PORT"
echo "Python version: $(python --version)"
echo "FFmpeg version: $(ffmpeg -version | head -1)"

# Start gunicorn with the port
exec gunicorn --bind 0.0.0.0:$PORT --timeout 180 --workers 1 --max-requests 1000 --max-requests-jitter 50 app:app
