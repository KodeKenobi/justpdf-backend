from celery import current_task
from celery_app import celery_app
import subprocess
import os
import time
from datetime import datetime
from models import Job, db
from database import db as database

@celery_app.task(bind=True)
def convert_video_async(self, job_id, input_path, output_format, quality, compression):
    """Convert video file asynchronously"""
    try:
        # Update job status to processing
        job = Job.query.filter_by(job_id=job_id).first()
        if job:
            job.status = 'processing'
            job.started_at = datetime.utcnow()
            database.session.commit()

        # Generate output path
        output_filename = f"{os.path.splitext(os.path.basename(input_path))[0]}_converted.{output_format}"
        output_path = os.path.join("converted_videos", output_filename)
        
        # Ensure output directory exists
        os.makedirs("converted_videos", exist_ok=True)

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

        # Run FFmpeg
        start_time = time.time()
        result = subprocess.run(cmd, capture_output=True, text=True)
        processing_time = time.time() - start_time

        # Update job status
        if result.returncode == 0:
            job.status = 'completed'
            job.output_file_path = output_path
            job.processing_time = processing_time
            job.completed_at = datetime.utcnow()
        else:
            job.status = 'failed'
            job.error_message = result.stderr
            job.completed_at = datetime.utcnow()

        database.session.commit()

        # Clean up input file
        if os.path.exists(input_path):
            os.remove(input_path)

        return {
            'status': job.status,
            'output_path': job.output_file_path,
            'processing_time': processing_time,
            'error': job.error_message
        }

    except Exception as e:
        # Update job status to failed
        job = Job.query.filter_by(job_id=job_id).first()
        if job:
            job.status = 'failed'
            job.error_message = str(e)
            job.completed_at = datetime.utcnow()
            database.session.commit()

        # Clean up input file
        if os.path.exists(input_path):
            os.remove(input_path)

        raise self.retry(exc=e, countdown=60, max_retries=3)

@celery_app.task(bind=True)
def convert_audio_async(self, job_id, input_path, output_format, bitrate):
    """Convert audio file asynchronously"""
    try:
        # Update job status to processing
        job = Job.query.filter_by(job_id=job_id).first()
        if job:
            job.status = 'processing'
            job.started_at = datetime.utcnow()
            database.session.commit()

        # Generate output path
        output_filename = f"{os.path.splitext(os.path.basename(input_path))[0]}_converted.{output_format}"
        output_path = os.path.join("converted_audio", output_filename)
        
        # Ensure output directory exists
        os.makedirs("converted_audio", exist_ok=True)

        # FFmpeg command for audio conversion
        cmd = [
            'ffmpeg', '-i', input_path,
            '-b:a', f'{bitrate}k',
            '-y', output_path
        ]

        # Run FFmpeg
        start_time = time.time()
        result = subprocess.run(cmd, capture_output=True, text=True)
        processing_time = time.time() - start_time

        # Update job status
        if result.returncode == 0:
            job.status = 'completed'
            job.output_file_path = output_path
            job.processing_time = processing_time
            job.completed_at = datetime.utcnow()
        else:
            job.status = 'failed'
            job.error_message = result.stderr
            job.completed_at = datetime.utcnow()

        database.session.commit()

        # Clean up input file
        if os.path.exists(input_path):
            os.remove(input_path)

        return {
            'status': job.status,
            'output_path': job.output_file_path,
            'processing_time': processing_time,
            'error': job.error_message
        }

    except Exception as e:
        # Update job status to failed
        job = Job.query.filter_by(job_id=job_id).first()
        if job:
            job.status = 'failed'
            job.error_message = str(e)
            job.completed_at = datetime.utcnow()
            database.session.commit()

        # Clean up input file
        if os.path.exists(input_path):
            os.remove(input_path)

        raise self.retry(exc=e, countdown=60, max_retries=3)

@celery_app.task(bind=True)
def convert_image_async(self, job_id, input_path, output_format, quality, width, height):
    """Convert image file asynchronously"""
    try:
        # Update job status to processing
        job = Job.query.filter_by(job_id=job_id).first()
        if job:
            job.status = 'processing'
            job.started_at = datetime.utcnow()
            database.session.commit()

        # Generate output path
        output_filename = f"{os.path.splitext(os.path.basename(input_path))[0]}_converted.{output_format}"
        output_path = os.path.join("converted_images", output_filename)
        
        # Ensure output directory exists
        os.makedirs("converted_images", exist_ok=True)

        # ImageMagick command for image conversion
        cmd = ['convert', input_path]
        
        # Add resize if specified
        if width and height:
            cmd.extend(['-resize', f'{width}x{height}'])
        
        # Add quality for JPEG
        if output_format.lower() in ['jpg', 'jpeg']:
            cmd.extend(['-quality', str(quality)])
        
        cmd.append(output_path)

        # Run ImageMagick
        start_time = time.time()
        result = subprocess.run(cmd, capture_output=True, text=True)
        processing_time = time.time() - start_time

        # Update job status
        if result.returncode == 0:
            job.status = 'completed'
            job.output_file_path = output_path
            job.processing_time = processing_time
            job.completed_at = datetime.utcnow()
        else:
            job.status = 'failed'
            job.error_message = result.stderr
            job.completed_at = datetime.utcnow()

        database.session.commit()

        # Clean up input file
        if os.path.exists(input_path):
            os.remove(input_path)

        return {
            'status': job.status,
            'output_path': job.output_file_path,
            'processing_time': processing_time,
            'error': job.error_message
        }

    except Exception as e:
        # Update job status to failed
        job = Job.query.filter_by(job_id=job_id).first()
        if job:
            job.status = 'failed'
            job.error_message = str(e)
            job.completed_at = datetime.utcnow()
            database.session.commit()

        # Clean up input file
        if os.path.exists(input_path):
            os.remove(input_path)

        raise self.retry(exc=e, countdown=60, max_retries=3)

@celery_app.task(bind=True)
def process_pdf_async(self, job_id, input_path, operation, **kwargs):
    """Process PDF file asynchronously"""
    try:
        # Update job status to processing
        job = Job.query.filter_by(job_id=job_id).first()
        if job:
            job.status = 'processing'
            job.started_at = datetime.utcnow()
            database.session.commit()

        # Generate output path based on operation
        base_name = os.path.splitext(os.path.basename(input_path))[0]
        
        if operation == 'extract_text':
            output_path = os.path.join("saved_html", f"{base_name}_extracted.txt")
        elif operation == 'extract_images':
            output_path = os.path.join("converted_images", f"{base_name}_images")
        elif operation == 'compress':
            output_path = os.path.join("edited", f"{base_name}_compressed.pdf")
        else:
            output_path = os.path.join("edited", f"{base_name}_processed.pdf")

        # Ensure output directory exists
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        # Process PDF based on operation
        start_time = time.time()
        
        if operation == 'extract_text':
            # Extract text using PyMuPDF
            import fitz
            doc = fitz.open(input_path)
            text = ""
            for page in doc:
                text += page.get_text()
            doc.close()
            
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(text)
                
        elif operation == 'extract_images':
            # Extract images using PyMuPDF
            import fitz
            doc = fitz.open(input_path)
            os.makedirs(output_path, exist_ok=True)
            
            for page_num in range(len(doc)):
                page = doc[page_num]
                image_list = page.get_images()
                
                for img_index, img in enumerate(image_list):
                    xref = img[0]
                    pix = fitz.Pixmap(doc, xref)
                    if pix.n - pix.alpha < 4:  # GRAY or RGB
                        pix.save(f"{output_path}/page_{page_num}_img_{img_index}.png")
                    pix = None
            
            doc.close()
            
        elif operation == 'compress':
            # Compress PDF using Ghostscript
            cmd = [
                'gs', '-sDEVICE=pdfwrite', '-dCompatibilityLevel=1.4',
                '-dPDFSETTINGS=/ebook', '-dNOPAUSE', '-dQUIET', '-dBATCH',
                f'-sOutputFile={output_path}', input_path
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                raise Exception(f"Ghostscript error: {result.stderr}")
        
        processing_time = time.time() - start_time

        # Update job status
        job.status = 'completed'
        job.output_file_path = output_path
        job.processing_time = processing_time
        job.completed_at = datetime.utcnow()
        database.session.commit()

        # Clean up input file
        if os.path.exists(input_path):
            os.remove(input_path)

        return {
            'status': job.status,
            'output_path': job.output_file_path,
            'processing_time': processing_time,
            'error': job.error_message
        }

    except Exception as e:
        # Update job status to failed
        job = Job.query.filter_by(job_id=job_id).first()
        if job:
            job.status = 'failed'
            job.error_message = str(e)
            job.completed_at = datetime.utcnow()
            database.session.commit()

        # Clean up input file
        if os.path.exists(input_path):
            os.remove(input_path)

        raise self.retry(exc=e, countdown=60, max_retries=3)

@celery_app.task
def cleanup_old_files():
    """Clean up old files from conversion directories"""
    import glob
    from datetime import datetime, timedelta
    
    # Clean up files older than 24 hours
    cutoff_time = datetime.now() - timedelta(hours=24)
    
    directories = ['converted_videos', 'converted_audio', 'converted_images', 'edited', 'saved_html']
    
    for directory in directories:
        if os.path.exists(directory):
            for file_path in glob.glob(os.path.join(directory, '*')):
                if os.path.isfile(file_path):
                    file_time = datetime.fromtimestamp(os.path.getctime(file_path))
                    if file_time < cutoff_time:
                        try:
                            os.remove(file_path)
                            print(f"Cleaned up old file: {file_path}")
                        except Exception as e:
                            print(f"Error cleaning up {file_path}: {e}")

# Schedule cleanup task to run every hour
from celery.schedules import crontab

celery_app.conf.beat_schedule = {
    'cleanup-old-files': {
        'task': 'trevnoctilla_backend.tasks.cleanup_old_files',
        'schedule': crontab(minute=0),  # Run every hour
    },
}
