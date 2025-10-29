from flask import Blueprint, request, jsonify, send_file, g
from werkzeug.utils import secure_filename
import os
import uuid
import time
from datetime import datetime
import subprocess
import threading
import base64

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
        
        # Get parameters - can come from form or JSON
        if request.is_json:
            data = request.get_json()
            output_format = data.get('output_format') or data.get('format', 'mp4')
            quality = int(data.get('quality', 80))
            compression = data.get('compression', 'medium')
            async_mode = data.get('async', 'false').lower() == 'true'
        else:
            output_format = request.form.get('output_format') or request.form.get('format', 'mp4')
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
                    # Read file and encode as base64
                    with open(output_path, 'rb') as f:
                        file_content = f.read()
                        file_base64 = base64.b64encode(file_content).decode('utf-8')
                    
                    # Clean up
                    try:
                        if os.path.exists(output_path):
                            os.remove(output_path)
                    except:
                        pass
                    
                    processing_time = time.time() - start_time
                    update_job_status(job.job_id, 'completed', None, processing_time=processing_time)
                    log_api_usage('/api/v1/convert/video', 'POST', 200, file_size, processing_time)
                    
                    return jsonify({
                        'job_id': job.job_id,
                        'status': 'completed',
                        'message': 'Video converted successfully',
                        'file_base64': file_base64,
                        'format': output_format,
                        'file_size': len(file_content),
                        'mime_type': f'video/{output_format}',
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
        
        # Get parameters - can come from form or JSON
        if request.is_json:
            data = request.get_json()
            output_format = data.get('output_format') or data.get('format', 'mp3')
            bitrate = data.get('bitrate', '192')
        else:
            output_format = request.form.get('output_format') or request.form.get('format', 'mp3')
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
                # Read file and encode as base64
                with open(output_path, 'rb') as f:
                    file_content = f.read()
                    file_base64 = base64.b64encode(file_content).decode('utf-8')
                
                # Clean up
                try:
                    if os.path.exists(output_path):
                        os.remove(output_path)
                except:
                    pass
                
                processing_time = time.time() - start_time
                update_job_status(job.job_id, 'completed', None, processing_time=processing_time)
                log_api_usage('/api/v1/convert/audio', 'POST', 200, file_size, processing_time)
                
                return jsonify({
                    'job_id': job.job_id,
                    'status': 'completed',
                    'message': 'Audio converted successfully',
                    'file_base64': file_base64,
                    'format': output_format,
                    'file_size': len(file_content),
                    'mime_type': f'audio/{output_format}',
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

@api_v1.route('/convert/pdf-extract-text', methods=['POST'])
@require_api_key
@require_rate_limit
def pdf_extract_text():
    """Extract text from PDF file"""
    start_time = time.time()
    
    try:
        if 'file' not in request.files:
            log_api_usage('/api/v1/convert/pdf-extract-text', 'POST', 400, error_message='No file provided')
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        if file.filename == '':
            log_api_usage('/api/v1/convert/pdf-extract-text', 'POST', 400, error_message='No file selected')
            return jsonify({'error': 'No file selected'}), 400
        
        # Get parameters - can come from form or JSON
        if request.is_json:
            data = request.get_json()
            output_format = data.get('output_format', 'txt')
        else:
            output_format = request.form.get('output_format', 'txt')
        
        # Secure filename
        filename = secure_filename(file.filename)
        unique_filename = f"{uuid.uuid4().hex[:8]}_{filename}"
        input_path = os.path.join(UPLOAD_FOLDER, unique_filename)
        
        # Save uploaded file
        file.save(input_path)
        
        # Create job record
        job = create_job('/api/v1/convert/pdf-extract-text', input_path)
        
        try:
            import fitz  # PyMuPDF
            doc = fitz.open(input_path)
            text_content = ""
            
            for page in doc:
                text_content += page.get_text()
            
            doc.close()
            
            # Clean up input file
            try:
                if os.path.exists(input_path):
                    os.remove(input_path)
            except:
                pass  # Don't fail if cleanup fails
            
            processing_time = time.time() - start_time
            update_job_status(job.job_id, 'completed', None, processing_time=processing_time)
            log_api_usage('/api/v1/convert/pdf-extract-text', 'POST', 200, processing_time=processing_time)
            
            # Return text content directly in response
            return jsonify({
                'job_id': job.job_id,
                'status': 'completed',
                'message': 'Text extracted successfully',
                'text': text_content,
                'text_length': len(text_content),
                'processing_time': processing_time
            }), 200
            
        except Exception as e:
            processing_time = time.time() - start_time
            update_job_status(job.job_id, 'failed', error_message=str(e), processing_time=processing_time)
            log_api_usage('/api/v1/convert/pdf-extract-text', 'POST', 500, processing_time=processing_time, error_message=str(e))
            return jsonify({
                'job_id': job.job_id,
                'status': 'failed',
                'error': str(e)
            }), 500
    
    except Exception as e:
        processing_time = time.time() - start_time
        log_api_usage('/api/v1/convert/pdf-extract-text', 'POST', 500, error_message=str(e))
        return jsonify({'error': str(e)}), 500

@api_v1.route('/convert/qr-generate', methods=['POST'])
@require_api_key
@require_rate_limit
def qr_generate():
    """Generate QR code from text or URL"""
    start_time = time.time()
    
    try:
        # Get parameters - can come from form or JSON
        if request.is_json:
            data = request.get_json()
            text = data.get('text', '')
            size = data.get('size', 'medium')
            format_type = data.get('format', 'png')
        else:
            text = request.form.get('text', '')
            size = request.form.get('size', 'medium')
            format_type = request.form.get('format', 'png')
        
        if not text:
            log_api_usage('/api/v1/convert/qr-generate', 'POST', 400, error_message='No text provided')
            return jsonify({'error': 'Text parameter is required'}), 400
        
        # Create job record
        job = create_job('/api/v1/convert/qr-generate')
        
        try:
            import qrcode
            from io import BytesIO
            import base64
            
            # Size mapping
            size_map = {'small': 4, 'medium': 10, 'large': 20}
            box_size = size_map.get(size, 10)
            
            # Create QR code
            qr = qrcode.QRCode(version=1, box_size=box_size, border=4)
            qr.add_data(text)
            qr.make(fit=True)
            
            # Create image
            img = qr.make_image(fill_color="black", back_color="white")
            
            # Convert to base64 instead of saving file
            buffer = BytesIO()
            img.save(buffer, format=format_type.upper() if format_type.upper() != 'JPG' else 'PNG')
            buffer.seek(0)
            image_base64 = base64.b64encode(buffer.read()).decode('utf-8')
            
            processing_time = time.time() - start_time
            update_job_status(job.job_id, 'completed', None, processing_time=processing_time)
            log_api_usage('/api/v1/convert/qr-generate', 'POST', 200, processing_time=processing_time)
            
            return jsonify({
                'job_id': job.job_id,
                'status': 'completed',
                'message': 'QR code generated successfully',
                'image_base64': image_base64,
                'format': format_type,
                'mime_type': f'image/{format_type.lower() if format_type.lower() != "jpg" else "png"}',
                'processing_time': processing_time
            }), 200
            
        except ImportError:
            processing_time = time.time() - start_time
            update_job_status(job.job_id, 'failed', error_message='qrcode library not installed')
            log_api_usage('/api/v1/convert/qr-generate', 'POST', 500, processing_time=processing_time, error_message='qrcode library not installed')
            return jsonify({
                'job_id': job.job_id,
                'status': 'failed',
                'error': 'QR code generation requires qrcode library'
            }), 500
        except Exception as e:
            processing_time = time.time() - start_time
            update_job_status(job.job_id, 'failed', error_message=str(e), processing_time=processing_time)
            log_api_usage('/api/v1/convert/qr-generate', 'POST', 500, processing_time=processing_time, error_message=str(e))
            return jsonify({
                'job_id': job.job_id,
                'status': 'failed',
                'error': str(e)
            }), 500
    
    except Exception as e:
        processing_time = time.time() - start_time
        log_api_usage('/api/v1/convert/qr-generate', 'POST', 500, error_message=str(e))
        return jsonify({'error': str(e)}), 500

@api_v1.route('/convert/image', methods=['POST'])
@require_api_key
@require_rate_limit
def convert_image():
    """Convert image file to different format"""
    start_time = time.time()
    
    try:
        if 'file' not in request.files:
            log_api_usage('/api/v1/convert/image', 'POST', 400, error_message='No file provided')
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        if file.filename == '':
            log_api_usage('/api/v1/convert/image', 'POST', 400, error_message='No file selected')
            return jsonify({'error': 'No file selected'}), 400
        
        # Get parameters - can come from form or JSON
        if request.is_json:
            data = request.get_json()
            output_format = data.get('output_format', 'png')
            quality = int(data.get('quality', 90))
        else:
            output_format = request.form.get('output_format', 'png')
            quality = int(request.form.get('quality', 90))
        
        # Secure filename
        filename = secure_filename(file.filename)
        unique_filename = f"{uuid.uuid4().hex[:8]}_{filename}"
        input_path = os.path.join(UPLOAD_FOLDER, unique_filename)
        
        # Save uploaded file
        file.save(input_path)
        file_size = os.path.getsize(input_path)
        
        # Create job record
        job = create_job('/api/v1/convert/image', input_path)
        
        try:
            from PIL import Image
            
            # Open image
            img = Image.open(input_path)
            
            # Convert to base64 instead of saving file
            from io import BytesIO
            buffer = BytesIO()
            if output_format.lower() in ['jpg', 'jpeg']:
                img = img.convert('RGB')
                img.save(buffer, format='JPEG', quality=quality)
            else:
                img.save(buffer, format=output_format.upper())
            buffer.seek(0)
            image_base64 = base64.b64encode(buffer.read()).decode('utf-8')
            
            processing_time = time.time() - start_time
            update_job_status(job.job_id, 'completed', None, processing_time=processing_time)
            log_api_usage('/api/v1/convert/image', 'POST', 200, file_size, processing_time)
            
            return jsonify({
                'job_id': job.job_id,
                'status': 'completed',
                'message': 'Image converted successfully',
                'image_base64': image_base64,
                'format': output_format,
                'file_size': len(image_base64) * 3 // 4,  # Approximate from base64
                'mime_type': f'image/{output_format.lower() if output_format.lower() != "jpg" else "jpeg"}',
                'processing_time': processing_time
            }), 200
            
        except ImportError:
            processing_time = time.time() - start_time
            update_job_status(job.job_id, 'failed', error_message='PIL/Pillow library not installed')
            log_api_usage('/api/v1/convert/image', 'POST', 500, file_size, processing_time, 'PIL/Pillow library not installed')
            return jsonify({
                'job_id': job.job_id,
                'status': 'failed',
                'error': 'Image conversion requires PIL/Pillow library'
            }), 500
        except Exception as e:
            processing_time = time.time() - start_time
            update_job_status(job.job_id, 'failed', error_message=str(e), processing_time=processing_time)
            log_api_usage('/api/v1/convert/image', 'POST', 500, file_size, processing_time, str(e))
            return jsonify({
                'job_id': job.job_id,
                'status': 'failed',
                'error': str(e)
            }), 500
    
    except Exception as e:
        processing_time = time.time() - start_time
        log_api_usage('/api/v1/convert/image', 'POST', 500, error_message=str(e))
        return jsonify({'error': str(e)}), 500

@api_v1.route('/convert/pdf-merge', methods=['POST'])
@require_api_key
@require_rate_limit
def pdf_merge():
    """Merge multiple PDF files into one"""
    start_time = time.time()
    
    try:
        # Check for files
        if 'files' not in request.files:
            log_api_usage('/api/v1/convert/pdf-merge', 'POST', 400, error_message='No files provided')
            return jsonify({'error': 'No files provided'}), 400
        
        files = request.files.getlist('files')
        if not files or all(f.filename == '' for f in files):
            log_api_usage('/api/v1/convert/pdf-merge', 'POST', 400, error_message='No files selected')
            return jsonify({'error': 'No files selected'}), 400
        
        # Get output filename
        output_filename = request.form.get('output_filename', 'merged.pdf')
        
        # Save all uploaded files
        input_paths = []
        for file in files:
            if file.filename:
                filename = secure_filename(file.filename)
                unique_filename = f"{uuid.uuid4().hex[:8]}_{filename}"
                input_path = os.path.join(UPLOAD_FOLDER, unique_filename)
                file.save(input_path)
                input_paths.append(input_path)
        
        if not input_paths:
            return jsonify({'error': 'No valid files to merge'}), 400
        
        # Create job record
        job = create_job('/api/v1/convert/pdf-merge', ','.join(input_paths))
        
        try:
            import fitz  # PyMuPDF
            
            # Create new PDF
            merged_doc = fitz.open()
            
            # Merge all PDFs
            for input_path in input_paths:
                doc = fitz.open(input_path)
                merged_doc.insert_pdf(doc)
                doc.close()
            
            # Save to buffer and encode as base64
            from io import BytesIO
            buffer = BytesIO()
            merged_doc.save(buffer)
            buffer.seek(0)
            pdf_base64 = base64.b64encode(buffer.read()).decode('utf-8')
            merged_doc.close()
            
            # Clean up input files
            for input_path in input_paths:
                if os.path.exists(input_path):
                    os.remove(input_path)
            
            processing_time = time.time() - start_time
            update_job_status(job.job_id, 'completed', None, processing_time=processing_time)
            log_api_usage('/api/v1/convert/pdf-merge', 'POST', 200, processing_time=processing_time)
            
            return jsonify({
                'job_id': job.job_id,
                'status': 'completed',
                'message': 'PDFs merged successfully',
                'pdf_base64': pdf_base64,
                'file_size': len(pdf_base64) * 3 // 4,  # Approximate from base64
                'mime_type': 'application/pdf',
                'processing_time': processing_time
            }), 200
            
        except Exception as e:
            processing_time = time.time() - start_time
            update_job_status(job.job_id, 'failed', error_message=str(e), processing_time=processing_time)
            log_api_usage('/api/v1/convert/pdf-merge', 'POST', 500, processing_time=processing_time, error_message=str(e))
            return jsonify({
                'job_id': job.job_id,
                'status': 'failed',
                'error': str(e)
            }), 500
    
    except Exception as e:
        processing_time = time.time() - start_time
        log_api_usage('/api/v1/convert/pdf-merge', 'POST', 500, error_message=str(e))
        return jsonify({'error': str(e)}), 500

@api_v1.route('/convert/pdf-split', methods=['POST'])
@require_api_key
@require_rate_limit
def pdf_split():
    """Split PDF into multiple pages"""
    start_time = time.time()
    
    try:
        if 'file' not in request.files:
            log_api_usage('/api/v1/convert/pdf-split', 'POST', 400, error_message='No file provided')
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        if file.filename == '':
            log_api_usage('/api/v1/convert/pdf-split', 'POST', 400, error_message='No file selected')
            return jsonify({'error': 'No file selected'}), 400
        
        # Get parameters
        split_type = request.form.get('split_type', 'every_page')
        page_range = request.form.get('page_range', '')
        
        # Secure filename
        filename = secure_filename(file.filename)
        unique_filename = f"{uuid.uuid4().hex[:8]}_{filename}"
        input_path = os.path.join(UPLOAD_FOLDER, unique_filename)
        
        # Save uploaded file
        file.save(input_path)
        file_size = os.path.getsize(input_path)
        
        # Create job record
        job = create_job('/api/v1/convert/pdf-split', input_path)
        
        try:
            import fitz  # PyMuPDF
            
            doc = fitz.open(input_path)
            total_pages = len(doc)
            
            # Determine which pages to extract
            pages_to_extract = []
            if split_type == 'every_page':
                pages_to_extract = [i for i in range(total_pages)]
            elif split_type == 'by_range' and page_range:
                # Parse ranges like "1-5,10-15"
                for part in page_range.split(','):
                    if '-' in part:
                        start, end = map(int, part.split('-'))
                        pages_to_extract.extend(range(start - 1, end))  # Convert to 0-indexed
                    else:
                        pages_to_extract.append(int(part) - 1)
            else:
                pages_to_extract = [0]  # Default to first page
            
            # Create output PDF with selected pages
            output_doc = fitz.open()
            for page_num in pages_to_extract:
                if 0 <= page_num < total_pages:
                    output_doc.insert_pdf(doc, from_page=page_num, to_page=page_num)
            
            # Save to buffer and encode as base64
            from io import BytesIO
            buffer = BytesIO()
            output_doc.save(buffer)
            buffer.seek(0)
            pdf_base64 = base64.b64encode(buffer.read()).decode('utf-8')
            
            doc.close()
            output_doc.close()
            
            # Clean up input file
            if os.path.exists(input_path):
                os.remove(input_path)
            
            processing_time = time.time() - start_time
            update_job_status(job.job_id, 'completed', None, processing_time=processing_time)
            log_api_usage('/api/v1/convert/pdf-split', 'POST', 200, file_size, processing_time)
            
            return jsonify({
                'job_id': job.job_id,
                'status': 'completed',
                'message': 'PDF split successfully',
                'pdf_base64': pdf_base64,
                'file_size': len(pdf_base64) * 3 // 4,  # Approximate from base64
                'mime_type': 'application/pdf',
                'processing_time': processing_time
            }), 200
            
        except Exception as e:
            processing_time = time.time() - start_time
            update_job_status(job.job_id, 'failed', error_message=str(e), processing_time=processing_time)
            log_api_usage('/api/v1/convert/pdf-split', 'POST', 500, file_size, processing_time, str(e))
            return jsonify({
                'job_id': job.job_id,
                'status': 'failed',
                'error': str(e)
            }), 500
    
    except Exception as e:
        processing_time = time.time() - start_time
        log_api_usage('/api/v1/convert/pdf-split', 'POST', 500, error_message=str(e))
        return jsonify({'error': str(e)}), 500

@api_v1.route('/convert/pdf-watermark', methods=['POST'])
@require_api_key
@require_rate_limit
def pdf_watermark():
    """Add watermark to PDF"""
    start_time = time.time()
    
    try:
        if 'file' not in request.files:
            log_api_usage('/api/v1/convert/pdf-watermark', 'POST', 400, error_message='No file provided')
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        if file.filename == '':
            log_api_usage('/api/v1/convert/pdf-watermark', 'POST', 400, error_message='No file selected')
            return jsonify({'error': 'No file selected'}), 400
        
        # Get parameters
        watermark_text = request.form.get('watermark_text', '')
        position = request.form.get('position', 'center')
        
        if not watermark_text:
            log_api_usage('/api/v1/convert/pdf-watermark', 'POST', 400, error_message='No watermark text provided')
            return jsonify({'error': 'Watermark text is required'}), 400
        
        # Secure filename
        filename = secure_filename(file.filename)
        unique_filename = f"{uuid.uuid4().hex[:8]}_{filename}"
        input_path = os.path.join(UPLOAD_FOLDER, unique_filename)
        
        # Save uploaded file
        file.save(input_path)
        file_size = os.path.getsize(input_path)
        
        # Create job record
        job = create_job('/api/v1/convert/pdf-watermark', input_path)
        
        try:
            import fitz  # PyMuPDF
            
            doc = fitz.open(input_path)
            
            # Position mapping
            pos_map = {
                'center': (0.5, 0.5),
                'top-left': (0.1, 0.1),
                'top-right': (0.9, 0.1),
                'bottom-left': (0.1, 0.9),
                'bottom-right': (0.9, 0.9)
            }
            x_pos, y_pos = pos_map.get(position, (0.5, 0.5))
            
            # Add watermark to each page
            for page_num in range(len(doc)):
                page = doc[page_num]
                rect = page.rect
                
                # Calculate position
                x = rect.width * x_pos
                y = rect.height * y_pos
                
                # Insert text watermark
                text_rect = fitz.Rect(x - 50, y - 10, x + 50, y + 10)
                page.insert_textbox(
                    text_rect,
                    watermark_text,
                    fontsize=20,
                    color=(0.5, 0.5, 0.5),  # Gray color
                    align=1  # Center alignment
                )
            
            # Save watermarked PDF
            output_filename = f"{uuid.uuid4().hex[:8]}_watermarked.pdf"
            output_path = os.path.join(UPLOAD_FOLDER, output_filename)
            doc.save(output_path)
            doc.close()
            
            # Clean up input file
            if os.path.exists(input_path):
                os.remove(input_path)
            
            processing_time = time.time() - start_time
            update_job_status(job.job_id, 'completed', output_path, processing_time=processing_time)
            log_api_usage('/api/v1/convert/pdf-watermark', 'POST', 200, file_size, processing_time)
            
            return jsonify({
                'job_id': job.job_id,
                'status': 'completed',
                'message': 'Watermark added successfully',
                'download_url': f'/api/v1/jobs/{job.job_id}/download',
                'processing_time': processing_time
            }), 200
            
        except Exception as e:
            processing_time = time.time() - start_time
            update_job_status(job.job_id, 'failed', error_message=str(e), processing_time=processing_time)
            log_api_usage('/api/v1/convert/pdf-watermark', 'POST', 500, file_size, processing_time, str(e))
            return jsonify({
                'job_id': job.job_id,
                'status': 'failed',
                'error': str(e)
            }), 500
    
    except Exception as e:
        processing_time = time.time() - start_time
        log_api_usage('/api/v1/convert/pdf-watermark', 'POST', 500, error_message=str(e))
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
