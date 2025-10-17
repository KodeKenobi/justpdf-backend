from flask import Blueprint, request, jsonify, send_file, g
from werkzeug.utils import secure_filename
import os
import uuid
import time
from datetime import datetime
import subprocess
import threading

from api_auth import require_api_key, require_rate_limit, log_api_usage
from database import db
from models import Job

# Create Blueprint
api_v1 = Blueprint('api_v1', __name__, url_prefix='/api/v1')

# Define folder constants
UPLOAD_FOLDER = "uploads"
VIDEO_FOLDER = "converted_videos"
AUDIO_FOLDER = "converted_audio"
IMAGE_FOLDER = "converted_images"

# Ensure directories exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(VIDEO_FOLDER, exist_ok=True)
os.makedirs(AUDIO_FOLDER, exist_ok=True)
os.makedirs(IMAGE_FOLDER, exist_ok=True)

def create_job(endpoint, input_file_path=None):
    """Create a new job record"""
    job_id = str(uuid.uuid4())
    job = Job(
        job_id=job_id,
        api_key_id=g.current_api_key.id,
        user_id=g.current_user.id,
        endpoint=endpoint,
        input_file_path=input_file_path
    )
    database.session.add(job)
    database.session.commit()
    return job

def update_job_status(job_id, status, output_file_path=None, error_message=None, processing_time=None):
    """Update job status"""
    job = Job.query.filter_by(job_id=job_id).first()
    if job:
        job.status = status
        if output_file_path:
            job.output_file_path = output_file_path
        if error_message:
            job.error_message = error_message
        if processing_time:
            job.processing_time = processing_time
        
        if status == 'processing':
            job.started_at = datetime.utcnow()
        elif status in ['completed', 'failed']:
            job.completed_at = datetime.utcnow()
        
        database.session.commit()

@api_v1.route('/convert/video', methods=['POST'])
@require_api_key
@require_rate_limit
def convert_video():
    """Convert video file to different format"""
    start_time = time.time()
    
    try:
        # Check if file is provided
        if 'file' not in request.files:
            log_api_usage('/api/v1/convert/video', 'POST', 400, error_message='No file provided')
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        if file.filename == '':
            log_api_usage('/api/v1/convert/video', 'POST', 400, error_message='No file selected')
            return jsonify({'error': 'No file selected'}), 400
        
        # Get parameters
        output_format = request.form.get('format', 'mp4')
        quality = int(request.form.get('quality', 80))
        compression = request.form.get('compression', 'medium')
        async_mode = request.form.get('async', 'false').lower() == 'true'
        
        # Secure filename
        filename = secure_filename(file.filename)
        unique_filename = f"{uuid.uuid4().hex[:8]}_{filename}"
        input_path = os.path.join(UPLOAD_FOLDER, unique_filename)
        
        # Save uploaded file
        file.save(input_path)
        file_size = os.path.getsize(input_path)
        
        # Create job record
        job = create_job('/api/v1/convert/video', input_path)
        
        if async_mode or file_size > 50 * 1024 * 1024:  # 50MB threshold for async
            # Process asynchronously
            update_job_status(job.job_id, 'processing')
            
            def process_video():
                try:
                    # Video conversion logic (simplified)
                    output_filename = f"{uuid.uuid4().hex[:8]}_converted.{output_format}"
                    output_path = os.path.join(VIDEO_FOLDER, output_filename)
                    
                    # FFmpeg command
                    quality_map = {95: 18, 85: 23, 75: 28, 60: 32, 40: 35}
                    preset_map = {'ultrafast': 'ultrafast', 'fast': 'fast', 'medium': 'medium', 'slow': 'slow', 'veryslow': 'veryslow'}
                    
                    crf = quality_map.get(quality, 28)
                    preset = preset_map.get(compression, 'medium')
                    
                    cmd = [
                        'ffmpeg', '-i', input_path,
                        '-c:v', 'libx264', '-crf', str(crf), '-preset', preset,
                        '-c:a', 'aac', '-b:a', '128k',
                        '-y', output_path
                    ]
                    
                    result = subprocess.run(cmd, capture_output=True, text=True)
                    
                    if result.returncode == 0:
                        update_job_status(job.job_id, 'completed', output_path)
                    else:
                        update_job_status(job.job_id, 'failed', error_message=result.stderr)
                    
                    # Clean up input file
                    if os.path.exists(input_path):
                        os.remove(input_path)
                        
                except Exception as e:
                    update_job_status(job.job_id, 'failed', error_message=str(e))
            
            # Start background thread
            thread = threading.Thread(target=process_video)
            thread.start()
            
            processing_time = time.time() - start_time
            log_api_usage('/api/v1/convert/video', 'POST', 202, file_size, processing_time)
            
            return jsonify({
                'job_id': job.job_id,
                'status': 'processing',
                'message': 'Video conversion started',
                'check_status_url': f'/api/v1/jobs/{job.job_id}/status'
            }), 202
        
        else:
            # Process synchronously
            try:
                output_filename = f"{uuid.uuid4().hex[:8]}_converted.{output_format}"
                output_path = os.path.join(VIDEO_FOLDER, output_filename)
                
                # FFmpeg command
                quality_map = {95: 18, 85: 23, 75: 28, 60: 32, 40: 35}
                preset_map = {'ultrafast': 'ultrafast', 'fast': 'fast', 'medium': 'medium', 'slow': 'slow', 'veryslow': 'veryslow'}
                
                crf = quality_map.get(quality, 28)
                preset = preset_map.get(compression, 'medium')
                
                cmd = [
                    'ffmpeg', '-i', input_path,
                    '-c:v', 'libx264', '-crf', str(crf), '-preset', preset,
                    '-c:a', 'aac', '-b:a', '128k',
                    '-y', output_path
                ]
                
                result = subprocess.run(cmd, capture_output=True, text=True)
                
                processing_time = time.time() - start_time
                
                if result.returncode == 0:
                    update_job_status(job.job_id, 'completed', output_path, processing_time=processing_time)
                    log_api_usage('/api/v1/convert/video', 'POST', 200, file_size, processing_time)
                    
                    return jsonify({
                        'job_id': job.job_id,
                        'status': 'completed',
                        'download_url': f'/api/v1/jobs/{job.job_id}/download',
                        'processing_time': processing_time
                    }), 200
                else:
                    update_job_status(job.job_id, 'failed', error_message=result.stderr)
                    log_api_usage('/api/v1/convert/video', 'POST', 500, file_size, processing_time, result.stderr)
                    
                    return jsonify({
                        'job_id': job.job_id,
                        'status': 'failed',
                        'error': result.stderr
                    }), 500
                    
            except Exception as e:
                processing_time = time.time() - start_time
                update_job_status(job.job_id, 'failed', error_message=str(e))
                log_api_usage('/api/v1/convert/video', 'POST', 500, file_size, processing_time, str(e))
                
                return jsonify({
                    'job_id': job.job_id,
                    'status': 'failed',
                    'error': str(e)
                }), 500
    
    except Exception as e:
        processing_time = time.time() - start_time
        log_api_usage('/api/v1/convert/video', 'POST', 500, error_message=str(e))
        return jsonify({'error': str(e)}), 500

@api_v1.route('/convert/audio', methods=['POST'])
@require_api_key
@require_rate_limit
def convert_audio():
    """Convert audio file to different format"""
    start_time = time.time()
    
    try:
        if 'file' not in request.files:
            log_api_usage('/api/v1/convert/audio', 'POST', 400, error_message='No file provided')
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        if file.filename == '':
            log_api_usage('/api/v1/convert/audio', 'POST', 400, error_message='No file selected')
            return jsonify({'error': 'No file selected'}), 400
        
        # Get parameters
        output_format = request.form.get('format', 'mp3')
        bitrate = request.form.get('bitrate', '192')
        
        # Secure filename
        filename = secure_filename(file.filename)
        unique_filename = f"{uuid.uuid4().hex[:8]}_{filename}"
        input_path = os.path.join(UPLOAD_FOLDER, unique_filename)
        
        # Save uploaded file
        file.save(input_path)
        file_size = os.path.getsize(input_path)
        
        # Create job record
        job = create_job('/api/v1/convert/audio', input_path)
        
        try:
            output_filename = f"{uuid.uuid4().hex[:8]}_converted.{output_format}"
            output_path = os.path.join(AUDIO_FOLDER, output_filename)
            
            # FFmpeg command for audio conversion
            cmd = [
                'ffmpeg', '-i', input_path,
                '-b:a', f'{bitrate}k',
                '-y', output_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            processing_time = time.time() - start_time
            
            if result.returncode == 0:
                update_job_status(job.job_id, 'completed', output_path, processing_time=processing_time)
                log_api_usage('/api/v1/convert/audio', 'POST', 200, file_size, processing_time)
                
                return jsonify({
                    'job_id': job.job_id,
                    'status': 'completed',
                    'download_url': f'/api/v1/jobs/{job.job_id}/download',
                    'processing_time': processing_time
                }), 200
            else:
                update_job_status(job.job_id, 'failed', error_message=result.stderr)
                log_api_usage('/api/v1/convert/audio', 'POST', 500, file_size, processing_time, result.stderr)
                
                return jsonify({
                    'job_id': job.job_id,
                    'status': 'failed',
                    'error': result.stderr
                }), 500
                
        except Exception as e:
            processing_time = time.time() - start_time
            update_job_status(job.job_id, 'failed', error_message=str(e))
            log_api_usage('/api/v1/convert/audio', 'POST', 500, file_size, processing_time, str(e))
            
            return jsonify({
                'job_id': job.job_id,
                'status': 'failed',
                'error': str(e)
            }), 500
    
    except Exception as e:
        processing_time = time.time() - start_time
        log_api_usage('/api/v1/convert/audio', 'POST', 500, error_message=str(e))
        return jsonify({'error': str(e)}), 500

@api_v1.route('/jobs/<job_id>/status', methods=['GET'])
@require_api_key
def get_job_status(job_id):
    """Get status of a job"""
    try:
        job = Job.query.filter_by(job_id=job_id, user_id=g.current_user.id).first()
        if not job:
            return jsonify({'error': 'Job not found'}), 404
        
        return jsonify(job.to_dict()), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@api_v1.route('/jobs/<job_id>/download', methods=['GET'])
@require_api_key
def download_job_result(job_id):
    """Download result of a completed job"""
    try:
        job = Job.query.filter_by(job_id=job_id, user_id=g.current_user.id).first()
        if not job:
            return jsonify({'error': 'Job not found'}), 404
        
        if job.status != 'completed':
            return jsonify({'error': 'Job not completed'}), 400
        
        if not job.output_file_path or not os.path.exists(job.output_file_path):
            return jsonify({'error': 'Output file not found'}), 404
        
        # Get filename for download
        filename = os.path.basename(job.output_file_path)
        
        return send_file(
            job.output_file_path,
            as_attachment=True,
            download_name=filename,
            mimetype='application/octet-stream'
        )
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@api_v1.route('/health', methods=['GET'])
def health_check():
    """API health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.utcnow().isoformat(),
        'version': '1.0.0'
    }), 200
