from celery import current_task
from celery_app import celery_app
from celery.schedules import crontab
import subprocess
import os
import time
from datetime import datetime
import json
from models import Campaign, Company, Job, db
database = db
from playwright.sync_api import sync_playwright

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

@celery_app.task(bind=True)
def process_campaign_sequential(self, campaign_id, company_ids=None):
    """
    Process a campaign sequentially (one-by-one)
    Ensures stability and real-time monitoring via WebSockets
    """
    from services.fast_campaign_processor import FastCampaignProcessor
    from websocket_manager import ws_manager
    from utils.supabase_storage import upload_screenshot
    
    try:
        campaign = Campaign.query.get(campaign_id)
        if not campaign:
            return {'error': f'Campaign {campaign_id} not found'}
        
        # Mark campaign as processing
        campaign.status = 'processing'
        campaign.started_at = datetime.utcnow()
        db.session.commit()
        
        # Get companies to process
        if company_ids:
            companies = Company.query.filter(
                Company.id.in_(company_ids),
                Company.campaign_id == campaign_id
            ).all()
        else:
            companies = Company.query.filter_by(
                campaign_id=campaign_id,
                status='pending'
            ).all()
        
        if not companies:
            campaign.status = 'completed'
            db.session.commit()
            return {'message': 'No companies to process'}
            
        # Parse message template
        message_template_str = campaign.message_template
        subject_str = 'Partnership Inquiry'
        sender_data = {}
        try:
            if isinstance(campaign.message_template, str) and (campaign.message_template.strip().startswith('{') or campaign.message_template.strip().startswith('[')):
                parsed = json.loads(campaign.message_template)
                if isinstance(parsed, dict):
                    sender_data = parsed
                    message_template_str = parsed.get('message', campaign.message_template)
                    subject_str = parsed.get('subject', 'Partnership Inquiry')
        except:
            pass

        # Broadcast start
        ws_manager.broadcast_event(campaign_id, {
            'type': 'campaign_start',
            'data': {
                'campaign_id': campaign_id,
                'total_companies': len(companies)
            }
        })
        
        with sync_playwright() as p:
            # Shared browser for all companies in this campaign
            browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-setuid-sandbox'])
            context = browser.new_context()
            
            for idx, company in enumerate(companies):
                # Check for cancellation
                db.session.refresh(campaign)
                if campaign.status in ['stopping', 'cancelled']:
                    ws_manager.broadcast_event(campaign_id, {
                        'type': 'campaign_stopped',
                        'data': {'message': 'Processing stopped by user'}
                    })
                    break
                
                # Update company status
                company.status = 'processing'
                db.session.commit()
                
                page = context.new_page()
                
                # Custom logger for this company that streams to WebSocket
                def live_logger(level, action, message):
                    print(f"[{level}] {action}: {message}")
                    ws_manager.broadcast_event(campaign_id, {
                        'type': 'activity',
                        'data': {
                            'company_id': company.id,
                            'company_name': company.company_name,
                            'level': level,
                            'action': action,
                            'message': message,
                            'timestamp': datetime.utcnow().isoformat()
                        }
                    })

                try:
                    processor = FastCampaignProcessor(
                        page=page,
                        company_data=company.to_dict(),
                        message_template=message_template_str,
                        campaign_id=campaign_id,
                        company_id=company.id,
                        logger=live_logger,
                        subject=subject_str,
                        sender_data=sender_data
                    )
                    
                    result = processor.process_company()
                    
                    # Update company based on result
                    if result.get('success'):
                        method = result.get('method', '')
                        if method.startswith('email'):
                            company.status = 'contact_info_found'
                        else:
                            company.status = 'completed'
                        company.contact_method = method
                        company.fields_filled = result.get('fields_filled', 0)
                        company.error_message = None
                    else:
                        error_msg = result.get('error', '').lower()
                        if 'captcha' in error_msg or result.get('method') == 'form_with_captcha':
                            company.status = 'captcha'
                        else:
                            company.status = 'failed'
                        company.error_message = result.get('error')
                        company.contact_method = result.get('method')
                    
                    # Handle screenshot
                    local_path = result.get('screenshot_url')
                    if local_path:
                        try:
                            # Assume project_root is parent of trevnoctilla-backend
                            project_root = os.path.dirname(os.path.abspath(__file__))
                            full_path = os.path.join(project_root, local_path)
                            if os.path.exists(full_path):
                                with open(full_path, 'rb') as f:
                                    sb_url = upload_screenshot(f.read(), campaign_id, company.id)
                                    if sb_url:
                                        company.screenshot_url = sb_url
                                        os.remove(full_path)
                                    else:
                                        company.screenshot_url = local_path
                        except Exception as e:
                            print(f"Screenshot error: {e}")
                            company.screenshot_url = local_path
                    
                    company.processed_at = datetime.utcnow()
                    db.session.commit()
                    
                    # Update campaign stats
                    campaign.processed_count = Company.query.filter_by(campaign_id=campaign.id).filter(Company.status != 'pending').count()
                    campaign.success_count = Company.query.filter_by(campaign_id=campaign.id, status='completed').count() + \
                                           Company.query.filter_by(campaign_id=campaign.id, status='contact_info_found').count()
                    campaign.failed_count = Company.query.filter_by(campaign_id=campaign.id, status='failed').count()
                    db.session.commit()
                    
                    # Broadcast completion for this company
                    ws_manager.broadcast_event(campaign_id, {
                        'type': 'company_completed',
                        'data': {
                            'company_id': company.id,
                            'status': company.status,
                            'screenshot_url': company.screenshot_url,
                            'progress': int((idx + 1) / len(companies) * 100)
                        }
                    })
                    
                except Exception as e:
                    live_logger('error', 'Execution Error', str(e))
                    company.status = 'failed'
                    company.error_message = str(e)
                    db.session.commit()
                finally:
                    page.close()
            
            browser.close()
            
        # Final campaign update
        campaign.status = 'completed'
        campaign.completed_at = datetime.utcnow()
        db.session.commit()
        
        ws_manager.broadcast_event(campaign_id, {
            'type': 'campaign_complete',
            'data': {'campaign_id': campaign_id}
        })
        
        return {'status': 'success', 'processed': len(companies)}
        
    except Exception as e:
        print(f"Sequential Task Error: {e}")
        import traceback
        traceback.print_exc()
        if 'campaign' in locals():
            campaign.status = 'failed'
            db.session.commit()
        return {'error': str(e)}

celery_app.conf.beat_schedule = {
    'cleanup-old-files': {
        'task': 'tasks.cleanup_old_files',
        'schedule': crontab(minute=0),  # Run every hour
    },
}
