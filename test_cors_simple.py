#!/usr/bin/env python3
"""
Simple CORS test to verify the fix works
"""
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)

# CORS configuration similar to the main app
CORS(app, origins=[
    "https://web-production-ef253.up.railway.app",
    "https://trevnoctilla.com",
    "https://www.trevnoctilla.com",
    "http://localhost:3000",
    "http://localhost:8080"
], supports_credentials=True)

# Add CORS headers manually for additional debugging
@app.after_request
def after_request(response):
    # Get the origin from the request
    origin = request.headers.get('Origin')
    
    # Check if origin is in our allowed list
    allowed_origins = [
        "https://web-production-ef253.up.railway.app",
        "https://trevnoctilla.com", 
        "https://www.trevnoctilla.com",
        "http://localhost:3000",
        "http://localhost:8080"
    ]
    
    if origin in allowed_origins:
        response.headers.add('Access-Control-Allow-Origin', origin)
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
        response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
        response.headers.add('Access-Control-Allow-Credentials', 'true')
    
    return response

@app.route("/health", methods=["GET"])
def health_check():
    return jsonify({"status": "healthy", "message": "CORS test backend is running"}), 200

@app.route("/convert-video", methods=["POST", "OPTIONS"])
def convert_video():
    if request.method == "OPTIONS":
        return "", 200
    
    return jsonify({"status": "success", "message": "CORS test successful"}), 200

if __name__ == "__main__":
    print(" Starting CORS test server...")
    app.run(debug=True, host='0.0.0.0', port=5001)
