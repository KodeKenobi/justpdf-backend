#!/usr/bin/env python3
"""
Audio Converter Backend using Flask and FFmpeg
Handles audio conversion between all major formats with quality control
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
UPLOAD_FOLDER = 'converted_audio'
ALLOWED_EXTENSIONS = {'mp3', 'wav', 'flac', 'aac', 'ogg', 'm4a', 'wma', 'aiff', 'au', 'opus'}

# Create upload folder if it doesn't exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_file_size(filepath):
    """Get file size in bytes"""
    return os.path.getsize(filepath)

def convert_audio(input_path, output_path, output_format, bitrate=192, sample_rate=44100, channels="stereo", quality=80):
    """Convert audio using FFmpeg"""
    try:
        print(f"DEBUG: Starting audio conversion from {input_path} to {output_path}")
        print(f"DEBUG: Format: {output_format}, Bitrate: {bitrate}, Sample Rate: {sample_rate}, Channels: {channels}, Quality: {quality}")
        
        # Build FFmpeg command based on output format
        cmd = ['ffmpeg', '-i', input_path]
        
        # Audio codec selection
        if output_format == 'mp3':
            cmd.extend(['-acodec', 'libmp3lame'])
            if bitrate > 0:
                cmd.extend(['-ab', f'{bitrate}k'])
        elif output_format == 'aac':
            cmd.extend(['-acodec', 'aac'])
            if bitrate > 0:
                cmd.extend(['-ab', f'{bitrate}k'])
        elif output_format == 'flac':
            cmd.extend(['-acodec', 'flac'])
        elif output_format == 'ogg':
            cmd.extend(['-acodec', 'libvorbis'])
            if bitrate > 0:
                cmd.extend(['-ab', f'{bitrate}k'])
        elif output_format == 'opus':
            cmd.extend(['-acodec', 'libopus'])
            if bitrate > 0:
                cmd.extend(['-ab', f'{bitrate}k'])
        elif output_format == 'wav':
            cmd.extend(['-acodec', 'pcm_s16le'])
        elif output_format == 'aiff':
            cmd.extend(['-acodec', 'pcm_s16be'])
        elif output_format == 'm4a':
            cmd.extend(['-acodec', 'aac'])
            if bitrate > 0:
                cmd.extend(['-ab', f'{bitrate}k'])
        elif output_format == 'wma':
            cmd.extend(['-acodec', 'wmav2'])
            if bitrate > 0:
                cmd.extend(['-ab', f'{bitrate}k'])
        else:
            # Default to libmp3lame for unknown formats
            cmd.extend(['-acodec', 'libmp3lame'])
            if bitrate > 0:
                cmd.extend(['-ab', f'{bitrate}k'])
        
        # Sample rate
        cmd.extend(['-ar', str(sample_rate)])
        
        # Channel configuration
        if channels == 'mono':
            cmd.extend(['-ac', '1'])
        elif channels == 'stereo':
            cmd.extend(['-ac', '2'])
        elif channels == 'surround':
            cmd.extend(['-ac', '6'])  # 5.1 surround
        # For 'original', don't specify channels
        
        # Quality settings for lossy formats
        if output_format in ['mp3', 'aac', 'ogg', 'opus', 'm4a', 'wma']:
            if quality < 50:
                cmd.extend(['-q:a', '9'])  # Low quality
            elif quality < 70:
                cmd.extend(['-q:a', '6'])  # Medium quality
            elif quality < 90:
                cmd.extend(['-q:a', '3'])  # High quality
            else:
                cmd.extend(['-q:a', '0'])  # Maximum quality
        
        # Overwrite output file
        cmd.extend(['-y', output_path])
        
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

@app.route('/convert-audio', methods=['POST'])
def convert_audio_endpoint():
    """Convert audio to different format"""
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
        output_format = request.form.get('outputFormat', 'mp3')
        bitrate = int(request.form.get('bitrate', 192))
        sample_rate = int(request.form.get('sampleRate', 44100))
        channels = request.form.get('channels', 'stereo')
        quality = int(request.form.get('quality', 80))
        
        print(f"DEBUG: Received request - Format: {output_format}, Bitrate: {bitrate}, Sample Rate: {sample_rate}, Channels: {channels}, Quality: {quality}")
        
        # Generate unique filenames
        unique_id = str(uuid.uuid4())[:8]
        original_filename = file.filename
        base_name = os.path.splitext(original_filename)[0]
        
        # Input file path
        input_filename = f"{unique_id}_{original_filename}"
        input_path = os.path.join(UPLOAD_FOLDER, input_filename)
        
        # Output file path
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
        
        # Convert audio
        print(f"DEBUG: Starting conversion...")
        success = convert_audio(input_path, output_path, output_format, bitrate, sample_rate, channels, quality)
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
            "message": f"Audio conversion completed successfully",
            "original_filename": original_filename,
            "converted_filename": output_filename,
            "original_size": original_size,
            "converted_size": converted_size,
            "download_url": f"/download_converted_audio/{output_filename}",
            "output_format": output_format,
            "bitrate": bitrate,
            "sample_rate": sample_rate,
            "channels": channels,
            "quality": quality
        })
        
    except Exception as e:
        print(f"Error in convert_audio_endpoint: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/download_converted_audio/<filename>')
def download_converted_audio(filename):
    """Download converted audio file"""
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
    return jsonify({"status": "healthy", "message": "Audio converter backend is running"})

if __name__ == '__main__':
    print("Starting Audio Converter Backend...")
    print("Make sure FFmpeg is installed and available in PATH")
    app.run(host='0.0.0.0', port=5001, debug=True)
