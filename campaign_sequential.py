"""
Standalone campaign sequential processor.
No Celery/Redis imports - safe to use when Redis is not running (e.g. Start button).
Uses a subprocess-based architecture for robustness: each company is processed in its own 
process that can be forcefully killed if it hangs, preventing the whole run from freezing.
"""
import os
import json
import re
import threading
import subprocess
import tempfile
import time
import sys
from datetime import datetime
from models import Campaign, Company, db

# Per-company timeout so one slow site doesn't hang the whole run
PER_COMPANY_TIMEOUT_SEC = 90
# Max time to wait for worker output/cleanup
WORKER_WAIT_TIMEOUT_SEC = 10

# Map technical log (action / message) to user-friendly English for the right-hand panel
def _user_friendly_message(level, action, message):
    action_lower = (action or '').lower()
    msg_lower = (message or '').lower()
    # Success
    if level == 'success':
        if 'form detected' in msg_lower or 'form found' in msg_lower:
            return "Form found on page."
        if 'form processed' in msg_lower or 'successfully filled' in msg_lower:
            return "Form filled and screenshot saved."
        if 'email sent' in msg_lower:
            return "Email sent successfully."
        if 'contact link' in msg_lower or 'contact page' in msg_lower:
            return "Contact page found."
        if 'frame' in msg_lower and 'found' in msg_lower:
            return "Form found in embedded section."
    # Info → friendly one-liners
    if level == 'info':
        if 'opening' in msg_lower or 'navigation' in msg_lower:
            return "Opening website…"
        if 'strategy 1' in msg_lower or 'homepage' in msg_lower:
            return "Checking homepage for a form…"
        if 'strategy 2' in msg_lower or 'contact link' in msg_lower:
            return "Looking for contact or about page…"
        if 'strategy 3' in msg_lower or 'frame' in msg_lower:
            return "Checking embedded forms…"
        if 'strategy 4' in msg_lower or 'heuristic' in msg_lower:
            return "Scanning page for form fields…"
        if 'form filling' in msg_lower or 'starting' in msg_lower:
            return "Filling out the form…"
        if 'field filled' in msg_lower or 'field filled' in action_lower:
            return "Field completed."
        if 'country' in msg_lower and ('selected' in msg_lower or 'filled' in msg_lower):
            return "Country selected."
        if 'checkbox' in msg_lower:
            return "Option selected."
        if 'contact page' in msg_lower and ('scroll' in msg_lower or 'wait' in msg_lower):
            return "Loading contact page…"
        if 'testing link' in msg_lower:
            return "Checking a link…"
        if 'discovery' in msg_lower:
            return "Searching for contact options…"
        if 'sending email' in msg_lower:
            return "Sending email…"
    # Warnings
    if level == 'warning':
        if 'captcha' in msg_lower:
            return "This form uses CAPTCHA; we can't submit it automatically."
        if 'no fields' in msg_lower or 'form empty' in msg_lower:
            return "No form fields could be filled."
        if 'field fill failed' in msg_lower:
            return "One field could not be filled."
    # Errors
    if level == 'error':
        if 'no contact found' in msg_lower:
            return "No contact form or email found on this site."
        if 'navigation' in msg_lower or 'failed' in msg_lower or 'timed out' in msg_lower:
            return "Could not load this page."
        if 'form fill error' in msg_lower or 'form processing' in msg_lower:
            return "Something went wrong while filling the form."
        if 'execution error' in action_lower:
            return "An error occurred; this lead was skipped."
    # Never expose technical jargon (Cursor, fetch, scroll, lazy-loading, etc.)
    msg_lower = (message or '').lower()
    if any(x in msg_lower for x in ('cursor', 'fetch', 'scroll', 'lazy', 'scrolling', 'fetch-first', 'into view')):
        return "Processing…"
    # Fallback: shorten technical message (remove file paths, long URLs)
    if message and len(message) > 80:
        short = re.sub(r'https?://\S+', '[link]', message)
        short = short[:77] + '…' if len(short) > 80 else short
        return short
    return message or "Processing…"


def _user_facing_error(err: str) -> str:
    """Short, clear error for UI (no stack traces or long URLs)."""
    if not err or not str(err).strip():
        return "Something went wrong. Try again or skip."
    s = str(err).strip()
    if len(s) > 200:
        s = s[:197] + "..."
    s = re.sub(r'https?://\S+', '[url]', s)
    lower = s.lower()
    if 'timeout' in lower or 'timed out' in lower:
        return "Request timed out. Try again or skip."
    if 'captcha' in lower:
        return "This form uses CAPTCHA; we can't submit it."
    if 'no contact' in lower or 'no discovery' in lower:
        return "No contact form or email found on this site."
    if 'only one field' in lower or 'not treated as contact' in lower:
        return "Only one field filled; skipped (likely newsletter/search)."
    if 'no fields were filled' in lower:
        return "Form could not be filled. Cookie or layout may be blocking."
    if 'navigation' in lower or 'failed or timed out' in lower:
        return "Page did not load in time."
    if 'form' in lower and 'error' in lower:
        return "Form error. Try again or skip."
    if 'invalid switch' in lower or 'event.wait' in lower:
        return "Processing error (browser context). You can retry this company."
    return s


def process_campaign_sequential(campaign_id, company_ids=None, processing_limit=None, skip_submit=False):
    """
    Process a campaign sequentially (one-by-one). Runs until all requested companies are done.
    Each company is processed in a separate subprocess for maximum reliability.
    """
    # DIAGNOSTIC: Log function entry
    print(f"[Sequential] ENTRY: campaign_id={campaign_id}, python={sys.executable}")
    
    from websocket_manager import ws_manager
    from utils.supabase_storage import upload_screenshot

    try:
        campaign = Campaign.query.get(campaign_id)
        if not campaign:
            return {'error': f'Campaign {campaign_id} not found'}

        # Clear stuck processing
        stuck = Company.query.filter_by(campaign_id=campaign_id, status='processing').count()
        if stuck:
            Company.query.filter_by(campaign_id=campaign_id, status='processing').update({'status': 'pending'})
            db.session.commit()
            print(f"[Sequential] Reset {stuck} stuck 'processing' companies to 'pending'")

        campaign.status = 'processing'
        campaign.started_at = datetime.utcnow()
        db.session.commit()

        limit = int(processing_limit) if processing_limit is not None else None
        if company_ids:
            q = Company.query.filter(Company.id.in_(company_ids), Company.campaign_id == campaign_id).order_by(Company.id)
            companies = q.limit(limit).all() if limit else q.all()
        else:
            q = Company.query.filter_by(campaign_id=campaign_id, status='pending').order_by(Company.id)
            companies = q.limit(limit).all() if limit else q.all()

        if not companies:
            campaign.status = 'completed'
            db.session.commit()
            return {'message': 'No companies to process'}

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
        except Exception:
            pass

        ws_manager.broadcast_event(campaign_id, {
            'type': 'campaign_start',
            'data': {
                'campaign_id': campaign_id,
                'total_companies': len(companies)
            }
        })

        for idx, company in enumerate(companies):
            _company_id = company.id
            _company_name = getattr(company, 'company_name', '') or ''
            
            try:
                # 1. Fresh state check
                db.session.rollback()
                db.session.refresh(campaign)
                if campaign.status in ['stopping', 'cancelled']:
                    Company.query.filter_by(campaign_id=campaign_id, status='processing').update({'status': 'pending'})
                    campaign.status = 'cancelled'
                    db.session.commit()
                    ws_manager.broadcast_event(campaign_id, {'type': 'campaign_stopped', 'data': {'message': 'Stopped by user'}})
                    break

                # 2. Mark as processing
                company.status = 'processing'
                db.session.commit()
                ws_manager.broadcast_event(campaign_id, {
                    'type': 'company_processing',
                    'data': {'company_id': _company_id, 'company_name': _company_name}
                })

                # 3. Subprocess setup
                input_fd, input_path = tempfile.mkstemp(suffix='.json', prefix='worker_in_')
                output_fd, output_path = tempfile.mkstemp(suffix='.json', prefix='worker_out_')
                
                result = None
                try:
                    os.close(input_fd)
                    os.close(output_fd)
                    
                    worker_input = {
                        'campaign_id': campaign_id,
                        'company_id': _company_id,
                        'company_data': company.to_dict(),
                        'message_template': message_template_str,
                        'subject': subject_str,
                        'sender_data': sender_data,
                        'timeout_sec': PER_COMPANY_TIMEOUT_SEC,
                        'skip_submit': skip_submit
                    }
                    
                    with open(input_path, 'w', encoding='utf-8') as f:
                        json.dump(worker_input, f)
                    
                    worker_script = os.path.join(os.path.dirname(__file__), 'process_single_company.py')
                    
                    # Auto-detect the Python command to work on both Windows (local) and Linux (Railway)
                    python_exe = sys.executable or 'py'
                    cmd = [python_exe, worker_script, '--input', input_path, '--output', output_path]
                    
                    print(f"[Sequential] Starting worker for company {_company_id}")
                    proc = subprocess.Popen(
                        cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        cwd=os.path.dirname(__file__)
                    )

                    # Helper to stream logs from stderr to WebSocket
                    def stream_logs(pipe, cid, cname):
                        for line in iter(pipe.readline, b''):
                            line_str = line.decode('utf-8', errors='ignore').strip()
                            if line_str:
                                # Parse [LEVEL] ACTION: MESSAGE
                                match = re.match(r'\[(\w+)\] (.*?): (.*)', line_str)
                                if match:
                                    level, action, message = match.groups()
                                    user_msg = _user_friendly_message(level, action, message)
                                    ws_manager.broadcast_event(campaign_id, {
                                        'type': 'activity',
                                        'data': {
                                            'company_id': cid,
                                            'company_name': cname,
                                            'level': level,
                                            'action': action,
                                            'message': message,
                                            'user_message': user_msg,
                                            'timestamp': datetime.utcnow().isoformat()
                                        }
                                    })
                                else:
                                    print(f"[Worker Output] {line_str}")

                    logger_thread = threading.Thread(target=stream_logs, args=(proc.stderr, _company_id, _company_name))
                    logger_thread.daemon = True
                    logger_thread.start()

                    # Wait for worker
                    try:
                        proc.wait(timeout=PER_COMPANY_TIMEOUT_SEC + WORKER_WAIT_TIMEOUT_SEC)
                        if os.path.exists(output_path):
                            with open(output_path, 'r', encoding='utf-8') as f:
                                result = json.load(f)
                    except subprocess.TimeoutExpired:
                        print(f"[Sequential] Worker TIMEOUT for company {_company_id} - killing")
                        proc.kill()
                        proc.wait()
                        result = {'success': False, 'error': 'Processing timed out', 'method': 'timeout'}

                except Exception as sub_err:
                    print(f"[Sequential] Subprocess error for company {_company_id}: {sub_err}")
                    result = {'success': False, 'error': str(sub_err), 'method': 'error'}
                finally:
                    # Cleanup temp files
                    for p in [input_path, output_path]:
                        if os.path.exists(p):
                            try: os.remove(p)
                            except: pass

                # 4. Process result
                if result:
                    if result.get('success'):
                        method = result.get('method', '')
                        if method == 'contact_info_found' or method.startswith('email'):
                            company.status = 'contact_info_found'
                        else:
                            company.status = 'completed'
                        company.contact_method = (method or '')[:20]
                        company.fields_filled = result.get('fields_filled', 0)
                        company.error_message = None
                    else:
                        error_msg = (result.get('error') or '').lower()
                        method = result.get('method') or ''
                        if method == 'timeout':
                            company.status = 'failed'
                            company.error_message = _user_facing_error('Processing timed out.')
                        elif 'captcha' in error_msg or method == 'form_with_captcha':
                            company.status = 'captcha'
                        elif method == 'no_contact_found':
                            company.status = 'no_contact_found'
                            company.error_message = 'No contact form found.'
                        else:
                            company.status = 'failed'
                            company.error_message = _user_facing_error(result.get('error'))
                        company.contact_method = (method or '')[:20]
                    
                    if result.get('screenshot_bytes'):
                        # Upload screenshot if provided
                        try:
                            import base64
                            # If it's a list or string, handle it (depends on how worker wrote it)
                            # process_single_company returns Dict which result of process_company
                            # which might contain bytes. But JSON doesn't support bytes.
                            # So worker should have base64 encoded it.
                            s_data = result.get('screenshot_bytes')
                            if isinstance(s_data, str):
                                s_bytes = base64.b64decode(s_data)
                                sb_url = upload_screenshot(s_bytes, campaign_id, _company_id)
                                if sb_url: company.screenshot_url = sb_url
                        except:
                            pass

                company.processed_at = datetime.utcnow()
                db.session.commit()
                
                # Update campaign stats
                campaign.processed_count = Company.query.filter(Company.campaign_id == campaign.id, Company.status != 'pending', Company.status != 'processing').count()
                campaign.success_count = Company.query.filter(Company.campaign_id == campaign.id, Company.status.in_(['completed', 'contact_info_found'])).count()
                campaign.failed_count = Company.query.filter_by(campaign_id=campaign.id, status='failed').count()
                campaign.captcha_count = Company.query.filter_by(campaign_id=campaign.id, status='captcha').count()
                db.session.commit()
                
                ws_manager.broadcast_event(campaign_id, {
                    'type': 'company_completed',
                    'data': {
                        'company_id': _company_id,
                        'status': company.status,
                        'screenshot_url': getattr(company, 'screenshot_url', None),
                        'progress': int((idx + 1) / len(companies) * 100)
                    }
                })

            except BaseException as e:
                print(f"[Sequential] Fatal iteration error for company {_company_id}: {e}")
                import traceback
                traceback.print_exc()
                try:
                    db.session.rollback()
                    c = Company.query.get(_company_id)
                    if c:
                        c.status = 'failed'
                        c.error_message = _user_facing_error(str(e))
                        db.session.commit()
                except: pass

        if campaign.status not in ['stopping', 'cancelled']:
            campaign.status = 'completed'
            campaign.completed_at = datetime.utcnow()
            db.session.commit()
            ws_manager.broadcast_event(campaign_id, {'type': 'campaign_complete', 'data': {'campaign_id': campaign_id}})

        return {'status': 'success', 'processed': len(companies)}

    except Exception as e:
        print(f"Sequential Task Error: {e}")
        import traceback
        traceback.print_exc()
        return {'error': str(e)}
    finally:
        # Cleanup any stuck processing
        if 'campaign_id' in locals() and campaign_id:
            try:
                db.session.rollback()
                Company.query.filter_by(campaign_id=campaign_id, status='processing').update({'status': 'pending'})
                db.session.commit()
            except: pass
