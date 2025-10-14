#!/usr/bin/env python3
"""
Simple Video Converter Backend using Flask and FFmpeg
Handles video conversion and MP3 audio extraction
"""

import os
import subprocess
import uuid
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import tempfile
import shutil

app = Flask(__name__)
CORS(app)

# Configuration
UPLOAD_FOLDER = 'converted_videos'
ALLOWED_EXTENSIONS = {'mp4', 'avi', 'mov', 'mkv', 'webm', 'flv', 'wmv', 'm4v', '3gp', 'ogv'}

# Create upload folder if it doesn't exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_file_size(filepath):
    """Get file size in bytes"""
    return os.path.getsize(filepath)

def convert_video(input_path, output_path, output_format, quality=80, compression='medium'):
    """Convert video using FFmpeg"""
    try:
        print(f"DEBUG: Starting conversion from {input_path} to {output_path}")
        print(f"DEBUG: Output format: {output_format}, Quality: {quality}, Compression: {compression}")
        
        # Quality settings based on compression level
        quality_settings = {
            'low': '18',
            'medium': '23',
            'high': '28'
        }
        
        crf = quality_settings.get(compression, '23')
        
        if output_format == 'mp3':
            # Extract audio to MP3
            cmd = [
                'ffmpeg', '-i', input_path,
                '-vn',  # No video
                '-acodec', 'mp3',
                '-ab', '192k',  # Audio bitrate
                '-ar', '44100',  # Sample rate
                '-y',  # Overwrite output file
                output_path
            ]
        else:
            # Convert video
            cmd = [
                'ffmpeg', '-i', input_path,
                '-c:v', 'libx264',  # Video codec
                '-crf', crf,  # Quality
                '-preset', 'medium',  # Encoding speed
                '-c:a', 'aac',  # Audio codec
                '-b:a', '128k',  # Audio bitrate
                '-y',  # Overwrite output file
                output_path
            ]
        
        print(f"DEBUG: Running FFmpeg command: {' '.join(cmd)}")
        
        # Run FFmpeg command
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        print(f"DEBUG: FFmpeg return code: {result.returncode}")
        print(f"DEBUG: FFmpeg stdout: {result.stdout}")
        print(f"DEBUG: FFmpeg stderr: {result.stderr}")
        
        if result.returncode != 0:
            raise Exception(f"FFmpeg error: {result.stderr}")
        
        # Check if output file was created and has content
        if not os.path.exists(output_path):
            raise Exception("Output file was not created")
        
        output_size = os.path.getsize(output_path)
        print(f"DEBUG: Output file size: {output_size} bytes")
        
        if output_size == 0:
            raise Exception("Output file is empty")
        
        return True
        
    except Exception as e:
        print(f"Conversion error: {str(e)}")
        return False

@app.route('/convert-video', methods=['POST'])
def convert_video_endpoint():
    """Convert video to different format or extract audio"""
    try:
        # Check if file is provided
        if 'file' not in request.files:
            return jsonify({"status": "error", "message": "No file provided"}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({"status": "error", "message": "No file selected"}), 400
        
        # Check file type
        if not allowed_file(file.filename):
            return jsonify({"status": "error", "message": "Invalid file type"}), 400
        
        # Get parameters
        output_format = request.form.get('outputFormat', 'mp4')
        quality = int(request.form.get('quality', 80))
        compression = request.form.get('compression', 'medium')
        
        print(f"DEBUG: Received request - Format: {output_format}, Quality: {quality}, Compression: {compression}")
        
        # Generate unique filenames
        unique_id = str(uuid.uuid4())[:8]
        original_filename = file.filename
        base_name = os.path.splitext(original_filename)[0]
        
        # Input file path
        input_filename = f"{unique_id}_{original_filename}"
        input_path = os.path.join(UPLOAD_FOLDER, input_filename)
        
        # Output file path
        if output_format == 'mp3':
            output_filename = f"{unique_id}_{base_name}_converted.mp3"
        else:
            output_filename = f"{unique_id}_{base_name}_converted.{output_format}"
        
        output_path = os.path.join(UPLOAD_FOLDER, output_filename)
        
        print(f"DEBUG: Input path: {input_path}")
        print(f"DEBUG: Output path: {output_path}")
        
        # Save uploaded file
        file.save(input_path)
        print(f"DEBUG: File saved successfully")
        
        # Get original file size
        original_size = get_file_size(input_path)
        print(f"DEBUG: Original file size: {original_size} bytes")
        
        # Convert video
        print(f"DEBUG: Starting conversion...")
        success = convert_video(input_path, output_path, output_format, quality, compression)
        print(f"DEBUG: Conversion result: {success}")
        
        if not success:
            # Clean up input file
            if os.path.exists(input_path):
                os.remove(input_path)
            return jsonify({"status": "error", "message": "Conversion failed"}), 500
        
        # Get converted file size
        converted_size = get_file_size(output_path)
        
        # Clean up input file
        if os.path.exists(input_path):
            os.remove(input_path)
        
        # Return success response
        return jsonify({
            "status": "success",
            "message": f"Conversion completed successfully",
            "original_filename": original_filename,
            "converted_filename": output_filename,
            "original_size": original_size,
            "converted_size": converted_size,
            "download_url": f"/download_converted/{output_filename}",
            "output_format": output_format
        })
        
    except Exception as e:
        print(f"Error in convert_video_endpoint: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/download_converted/<filename>')
def download_converted(filename):
    """Download converted file"""
    try:
        file_path = os.path.join(UPLOAD_FOLDER, filename)
        if not os.path.exists(file_path):
            return jsonify({"error": "File not found"}), 404
        
        return send_file(file_path, as_attachment=True, download_name=filename)
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/health')
def health_check():
    """Health check endpoint"""
    return jsonify({"status": "healthy", "message": "Video converter backend is running"})

if __name__ == '__main__':
    print("Starting Video Converter Backend...")
    print("Make sure FFmpeg is installed and available in PATH")
    app.run(host='0.0.0.0', port=5000, debug=True)
