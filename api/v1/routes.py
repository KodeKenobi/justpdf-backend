from flask import Blueprint, request, jsonify, send_file, g
from werkzeug.utils import secure_filename
import os
import uuid
import time
from datetime import datetime
import subprocess
import threading

from api_auth import require_api_key, require_rate_limit, log_api_usage

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
    from database import db
    from models import Job
    
    job_id = str(uuid.uuid4())
    job = Job(
        job_id=job_id,
        api_key_id=g.current_api_key.id,
        user_id=g.current_user.id,
        endpoint=endpoint,
        input_file_path=input_file_path
    )
    db.session.add(job)
    db.session.commit()
    return job

def update_job_status(job_id, status, output_file_path=None, error_message=None, processing_time=None):
    """Update job status"""
    from database import db
    from models import Job
    
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
        
        db.session.commit()

@api_v1.route('/convert/video', methods=['POST'])
@require_api_key
@require_rate_limit
def convert_video():
    """Convert video file to different format"""
    start_time = time.time()
    request_timestamp = datetime.now().isoformat()
    
    # COMPREHENSIVE BACKEND LOGGING - REQUEST RECEIVED
    print("🚀 [BACKEND CONVERSION START] =================================")
    print(f"⏰ [TIMESTAMP] {request_timestamp}")
    print(f"⏰ [TIMING] Request received at: {start_time}")
    print(f"🔑 [AUTH] API Key ID: {g.current_api_key.id if hasattr(g, 'current_api_key') else 'Unknown'}")
    print(f"👤 [USER] User ID: {g.current_user.id if hasattr(g, 'current_user') else 'Unknown'}")
    print("🚀 [BACKEND CONVERSION START] =================================")
    
    try:
        # Check if file is provided
        if 'file' not in request.files:
            print("❌ [ERROR] No file provided in request")
            log_api_usage('/api/v1/convert/video', 'POST', 400, error_message='No file provided')
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        if file.filename == '':
            print("❌ [ERROR] No file selected")
            log_api_usage('/api/v1/convert/video', 'POST', 400, error_message='No file selected')
            return jsonify({'error': 'No file selected'}), 400
        
        # Get parameters
        output_format = request.form.get('format', 'mp4')
        quality = int(request.form.get('quality', 80))
        compression = request.form.get('compression', 'medium')
        async_mode = request.form.get('async', 'false').lower() == 'true'
        
        # COMPREHENSIVE BACKEND LOGGING - REQUEST PARAMETERS
        print("📋 [BACKEND REQUEST PARAMS] ===============================")
        print(f"📁 [FILE] Filename: {file.filename}")
        print(f"📁 [FILE] Content Type: {file.content_type}")
        print(f"🎯 [OUTPUT] Format: {output_format}")
        print(f"🎯 [OUTPUT] Quality: {quality}")
        print(f"🎯 [OUTPUT] Compression: {compression}")
        print(f"🔄 [MODE] Async: {async_mode}")
        print("📋 [BACKEND REQUEST PARAMS] ===============================")
        
        # Secure filename
        filename = secure_filename(file.filename)
        unique_filename = f"{uuid.uuid4().hex[:8]}_{filename}"
        input_path = os.path.join(UPLOAD_FOLDER, unique_filename)
        
        # Save uploaded file
        file_save_time = time.time()
        file.save(input_path)
        file_size = os.path.getsize(input_path)
        file_save_duration = time.time() - file_save_time
        
        # COMPREHENSIVE BACKEND LOGGING - FILE SAVED
        print("💾 [BACKEND FILE SAVED] =====================================")
        print(f"⏰ [TIMESTAMP] {datetime.now().isoformat()}")
        print(f"⏰ [TIMING] File save duration: {file_save_duration:.3f}s")
        print(f"📁 [FILE] Saved as: {unique_filename}")
        print(f"📁 [FILE] Input path: {input_path}")
        print(f"📁 [FILE] File size: {file_size} bytes ({file_size / 1024 / 1024:.2f} MB)")
        print("💾 [BACKEND FILE SAVED] =====================================")
        
        # Create job record
        job = create_job('/api/v1/convert/video', input_path)
        print(f"📝 [JOB] Created job ID: {job.job_id}")
        
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
                    
                    # COMPREHENSIVE BACKEND LOGGING - FFMPEG START
                    ffmpeg_start_time = time.time()
                    ffmpeg_start_timestamp = datetime.now().isoformat()
                    print("🎬 [BACKEND FFMPEG START] ==================================")
                    print(f"⏰ [TIMESTAMP] {ffmpeg_start_timestamp}")
                    print(f"⏰ [TIMING] FFmpeg started at: {ffmpeg_start_time}")
                    print(f"🎬 [FFMPEG] Command: {' '.join(cmd)}")
                    print(f"🎬 [FFMPEG] Input: {input_path}")
                    print(f"🎬 [FFMPEG] Output: {output_path}")
                    print(f"🎬 [FFMPEG] CRF: {crf}, Preset: {preset}")
                    print("🎬 [BACKEND FFMPEG START] ==================================")
                    
                    result = subprocess.run(cmd, capture_output=True, text=True)
                    
                    # COMPREHENSIVE BACKEND LOGGING - FFMPEG COMPLETE
                    ffmpeg_end_time = time.time()
                    ffmpeg_duration = ffmpeg_end_time - ffmpeg_start_time
                    ffmpeg_end_timestamp = datetime.now().isoformat()
                    print("🏁 [BACKEND FFMPEG COMPLETE] ==============================")
                    print(f"⏰ [TIMESTAMP] {ffmpeg_end_timestamp}")
                    print(f"⏰ [TIMING] FFmpeg duration: {ffmpeg_duration:.3f}s")
                    print(f"⏰ [TIMING] FFmpeg duration: {ffmpeg_duration:.1f} seconds")
                    print(f"🎬 [FFMPEG] Return code: {result.returncode}")
                    print(f"🎬 [FFMPEG] Success: {result.returncode == 0}")
                    if result.stderr:
                        print(f"🎬 [FFMPEG] Error output: {result.stderr[:200]}...")
                    print("🏁 [BACKEND FFMPEG COMPLETE] ==============================")
                    
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
            
            # COMPREHENSIVE BACKEND LOGGING - RESPONSE SENT
            response_time = time.time()
            response_timestamp = datetime.now().isoformat()
            print("📤 [BACKEND RESPONSE SENT] ================================")
            print(f"⏰ [TIMESTAMP] {response_timestamp}")
            print(f"⏰ [TIMING] Total request processing time: {processing_time:.3f}s")
            print(f"📤 [RESPONSE] Status: 202 (Processing)")
            print(f"📤 [RESPONSE] Job ID: {job.job_id}")
            print(f"📤 [RESPONSE] Unique filename: {unique_filename}")
            print(f"📤 [RESPONSE] File size: {file_size} bytes")
            print("📤 [BACKEND RESPONSE SENT] ================================")
            
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
        from models import Job
        
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
        from models import Job
        
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
