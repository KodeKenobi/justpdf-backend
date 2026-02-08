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
# Maximum concurrent workers to avoid OOM or CPU saturation
MAX_CONCURRENT_WORKERS = 8

def _kill_process_tree(proc):
    """Safely terminate a process and all its children across platforms."""
    if not proc: return
    try:
        if sys.platform == 'win32':
            # On Windows, taskkill /F /T kills the process and all its children
            subprocess.run(['taskkill', '/F', '/T', '/PID', str(proc.pid)], 
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            # On Linux/macOS, we use process groups
            import signal
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except:
        # Fallback to simple terminate if group kill fails
        try: proc.kill()
        except: pass

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
    # Info
    if level == 'info':
        if 'opening' in msg_lower or 'navigation' in msg_lower:
            return "Opening website..."
        if 'strategy 1' in msg_lower or 'homepage' in msg_lower:
            return "Checking homepage for a form..."
        if 'strategy 2' in msg_lower or 'contact link' in msg_lower:
            return "Looking for contact or about page..."
        if 'strategy 3' in msg_lower or 'frame' in msg_lower:
            return "Checking embedded forms..."
        if 'strategy 4' in msg_lower or 'heuristic' in msg_lower:
            return "Scanning page for form fields..."
        if 'form filling' in msg_lower or 'starting' in msg_lower:
            return "Filling out the form..."
        if 'field filled' in msg_lower or 'field filled' in action_lower:
            return "Field completed."
        if 'country' in msg_lower and ('selected' in msg_lower or 'filled' in msg_lower):
            return "Country selected."
        if 'checkbox' in msg_lower:
            return "Option selected."
        if 'contact page' in msg_lower and ('scroll' in msg_lower or 'wait' in msg_lower):
            return "Loading contact page..."
        if 'testing link' in msg_lower:
            return "Checking a link..."
        if 'discovery' in msg_lower:
            return "Searching for contact options..."
        if 'sending email' in msg_lower:
            return "Sending email..."
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
        return "Processing..."
    # Fallback: shorten technical message (remove file paths, long URLs)
    if message and len(message) > 80:
        short = re.sub(r'https?://\S+', '[link]', message)
        short = short[:77] + '...' if len(short) > 80 else short
        return short
    return message or "Processing..."

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
    Process a campaign with "Lightning Fast" parallelism.
    Uses ThreadPoolExecutor and multiple subprocesses for maximum speed.
    """
    from concurrent.futures import ThreadPoolExecutor
    import threading
    
    # Get flask app for DB updates early so it's available to everything
    from flask import current_app
    try:
        flask_app = current_app._get_current_object()
    except:
        from app import app as flask_app

    # DIAGNOSTIC: Log function entry
    print(f"[Parallel] ENTRY: campaign_id={campaign_id}, python={sys.executable}")
    
    # Shared state for watchdog and progress tracking
    state = {
        'last_activity_at': time.time(),
        'active_procs': {}, # pid -> proc
        'stop_watchdog': False,
        'interrupted': False, # New: Prevent new tasks from starting
        'processed_count': 0,
        'total_companies': 0,
        'lock': threading.Lock()
    }
    
    # Watchdog to monitor all active processes
    def watchdog():
        print(f"[Parallel] [WATCHDOG] Started for campaign {campaign_id}")
        last_db_check = 0
        while not state['stop_watchdog']:
            time.sleep(5) # Faster checks (was 30)
            now = time.time()
            offline_sec = now - state['last_activity_at']
            
            # 1. Heartbeat check
            if int(now) % 60 < 10:
                print(f"[Parallel] [WATCHDOG] Heartbeat. Last activity {offline_sec:.0f}s ago. Active: {len(state['active_procs'])}")
            
            # 2. IMMEDIATE STOP CHECK
            # Check DB status every 5 seconds to see if user clicked Stop
            if now - last_db_check > 5:
                last_db_check = now
                try:
                    with flask_app.app_context():
                        from models import Campaign
                        from database import db
                        db.session.rollback()
                        camp = Campaign.query.get(campaign_id)
                        if camp and camp.status in ['stopping', 'cancelled']:
                            print(f"[Parallel] [WATCHDOG] STOP REQUESTED (status={camp.status}). Killing active workers...")
                            state['interrupted'] = True
                            with state['lock']:
                                for pid, proc in list(state['active_procs'].items()):
                                    print(f"[Parallel] [WATCHDOG] Killing PID {pid}")
                                    _kill_process_tree(proc)
                                state['active_procs'].clear()
                        db.session.remove()
                except Exception as e:
                    print(f"[Parallel] [WATCHDOG] Stop check error: {e}")

            # 3. Kill stuck processes (Individual timeout)
            if offline_sec > (PER_COMPANY_TIMEOUT_SEC + WORKER_WAIT_TIMEOUT_SEC + 60):
                print(f"[Parallel] [WATCHDOG] [STALL] Global inactivity! Killing all active workers...")
                with state['lock']:
                    for pid, proc in list(state['active_procs'].items()):
                        _kill_process_tree(proc)
                    state['active_procs'].clear()
            
            # 3. Update campaign heartbeat and report progress in DB
            if int(now) % 60 < 35:
                try:
                    with flask_app.app_context():
                        from models import Campaign, Company
                        from database import db
                        db.session.rollback()
                        camp = Campaign.query.get(campaign_id)
                        if camp:
                            camp.last_heartbeat_at = datetime.utcnow()
                            
                            # Optimized stats update: Single query instead of 4
                            stats = db.session.query(
                                Company.status, 
                                func.count(Company.id)
                            ).filter(Company.campaign_id == campaign_id).group_by(Company.status).all()
                            
                            counts = {s: c for s, c in stats}
                            processed = sum(c for s, c in counts.items() if s not in ['pending', 'processing'])
                            success = counts.get('completed', 0) + counts.get('contact_info_found', 0)
                            failed = counts.get('failed', 0)
                            captcha = counts.get('captcha', 0)
                            
                            camp.processed_count = processed
                            camp.success_count = success
                            camp.failed_count = failed
                            camp.captcha_count = captcha
                            db.session.commit()
                            db.session.remove() # Release connection while waiting for next heartbeat
                            
                            total = camp.total_companies or 0
                            pct = (processed / total * 100) if total > 0 else 0
                            print(f"\n[PROGRESS] Campaign {campaign_id}: {processed}/{total} ({pct:.1f}%) | Success: {success} | Failed: {failed} | Captcha: {captcha}")
                except Exception as e:
                    print(f"[Parallel] Watchdog DB error: {e}")
                    try: db.session.remove()
                    except: pass

    watchdog_thread = threading.Thread(target=watchdog, daemon=True)
    watchdog_thread.start()
    
    from websocket_manager import ws_manager
    from utils.supabase_storage import upload_screenshot

    try:
        # 1. Startup: Cleanup and count
        db.session.rollback()
        db.session.expire_all()
        
        campaign = Campaign.query.get(campaign_id)
        if not campaign:
            return {'error': f'Campaign {campaign_id} not found'}

        # Reset stuck processing
        stuck = Company.query.filter_by(campaign_id=campaign_id, status='processing').update({'status': 'pending'})
        campaign.status = 'processing'
        campaign.started_at = datetime.utcnow()
        db.session.commit()

        limit = int(processing_limit) if processing_limit is not None else None
        if company_ids:
            q = Company.query.filter(Company.id.in_(company_ids), Company.campaign_id == campaign_id).order_by(Company.id)
        else:
            q = Company.query.filter_by(campaign_id=campaign_id, status='pending').order_by(Company.id)
        
        companies = q.limit(limit).all() if limit else q.all()
        if not companies:
            campaign.status = 'completed'
            db.session.commit()
            return {'message': 'No companies to process'}

        state['total_companies'] = len(companies)
        message_template_str = campaign.message_template
        # (Template parsing omitted for brevity in diff, keep original logic)
        subject_str = 'Partnership Inquiry'
        sender_data = {}
        try:
            if isinstance(campaign.message_template, str) and (campaign.message_template.strip().startswith('{') or campaign.message_template.strip().startswith('[')):
                parsed = json.loads(campaign.message_template)
                if isinstance(parsed, dict):
                    sender_data = parsed
                    message_template_str = parsed.get('message', campaign.message_template)
                    subject_str = parsed.get('subject', 'Partnership Inquiry')
        except: pass

        ws_manager.broadcast_event(campaign_id, {
            'type': 'campaign_start',
            'data': {'campaign_id': campaign_id, 'total_companies': len(companies)}
        })

        # 2. Worker Execution in ThreadPool
        # ---------------------------------------------------------------------
        semaphore = threading.Semaphore(MAX_CONCURRENT_WORKERS)
        
        def process_one_company(comp_id, comp_name):
            with semaphore:
                try:
                    # Check global interrupt flag before starting new work
                    if state['interrupted']:
                        return

                    with flask_app.app_context():
                        from models import Company, Campaign
                        from database import db
                        
                        # A. Refresh state
                        db.session.remove()
                        db.session.rollback()
                        company = Company.query.get(comp_id)
                        if not company: return
                        
                        camp = Campaign.query.get(campaign_id)
                        if not camp or camp.status in ['stopping', 'cancelled']:
                            return

                        # B. Mark processing
                        company.status = 'processing'
                        # Capture data into serializable dict BEFORE we commit and potentially lose the session
                        company_data_dict = company.to_dict()
                        db.session.commit()
                        db.session.remove() # AGGRESSIVE: Release connection back to pool while worker is busy (~90s)
                        
                        with state['lock']: state['last_activity_at'] = time.time()
                        
                        ws_manager.broadcast_event(campaign_id, {
                            'type': 'company_processing',
                            'data': {'company_id': comp_id, 'company_name': comp_name}
                        })

                        # C. Run Worker Subprocess
                        input_fd, input_path = tempfile.mkstemp(suffix='.json', prefix='worker_in_')
                        output_fd, output_path = tempfile.mkstemp(suffix='.json', prefix='worker_out_')
                        result = None
                        try:
                            os.close(input_fd)
                            os.close(output_fd)
                            worker_input = {
                                'campaign_id': campaign_id,
                                'company_id': comp_id,
                                'company_data': company_data_dict,
                                'message_template': message_template_str,
                                'subject': subject_str,
                                'sender_data': sender_data,
                                'timeout_sec': PER_COMPANY_TIMEOUT_SEC,
                                'skip_submit': skip_submit
                            }
                            with open(input_path, 'w', encoding='utf-8') as f:
                                json.dump(worker_input, f)
                            
                            python_exe = sys.executable or 'py'
                            worker_script = os.path.join(os.path.dirname(__file__), 'process_single_company.py')
                            cmd = [python_exe, worker_script, '--input', input_path, '--output', output_path]
                            
                            kwargs = {
                                'stdout': subprocess.PIPE, 'stderr': subprocess.STDOUT,
                                'cwd': os.path.dirname(__file__), 'bufsize': -1
                            }
                            if sys.platform != 'win32': kwargs['preexec_fn'] = os.setsid
                            
                            proc = subprocess.Popen(cmd, **kwargs)
                            with state['lock']: state['active_procs'][proc.pid] = proc

                            # Log streaming
                            def stream_logs(pipe, cid, cname):
                                for line in iter(pipe.readline, b''):
                                    line_str = line.decode('utf-8', errors='ignore').strip()
                                    if not line_str: continue
                                    match = re.match(r'\[(\w+)\] (.*?): (.*)', line_str)
                                    if match:
                                        level, action, message = match.groups()
                                        with state['lock']: state['last_activity_at'] = time.time()
                                        user_msg = _user_friendly_message(level, action, message)
                                        ws_manager.broadcast_event(campaign_id, {
                                            'type': 'activity',
                                            'data': {
                                                'company_id': cid, 'company_name': cname,
                                                'level': level, 'action': action, 'message': message,
                                                'user_message': user_msg, 'timestamp': datetime.utcnow().isoformat()
                                            }
                                        })
                            
                            log_thread = threading.Thread(target=stream_logs, args=(proc.stdout, comp_id, comp_name), daemon=True)
                            log_thread.start()

                            try:
                                proc.wait(timeout=PER_COMPANY_TIMEOUT_SEC + WORKER_WAIT_TIMEOUT_SEC)
                                with state['lock']: state['last_activity_at'] = time.time()
                                if os.path.exists(output_path):
                                    with open(output_path, 'r', encoding='utf-8') as f:
                                        result = json.load(f)
                            except subprocess.TimeoutExpired:
                                _kill_process_tree(proc)
                                result = {'success': False, 'error': 'Processing timed out', 'method': 'timeout'}
                            finally:
                                with state['lock']: state['active_procs'].pop(proc.pid, None)

                        except Exception as e:
                            result = {'success': False, 'error': str(e), 'method': 'error'}
                        finally:
                            for p in [input_path, output_path]:
                                if os.path.exists(p):
                                    try: os.remove(p)
                                    except: pass

                        # D. Update Result - RE-FETCH first to avoid DetachedInstanceError
                        # The commit earlier (line 273) expired these objects, and the long-running 
                        # subprocess might have timed out the session or seen other thread-local issues.
                        db.session.rollback() # Clear any stale cache/objects for this thread
                        company = Company.query.get(comp_id)
                        camp = Campaign.query.get(campaign_id)
                        
                        if not company or not camp:
                            print(f"[Parallel] CRITICAL: Company {comp_id} or Campaign {campaign_id} not found in DB after worker.")
                            return

                        if result:
                            if result.get('success'):
                                method = result.get('method', '')
                                company.status = 'contact_info_found' if (method == 'contact_info_found' or method.startswith('email')) else 'completed'
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
                                try:
                                    import base64
                                    s_bytes = base64.b64decode(result.get('screenshot_bytes'))
                                    sb_url = upload_screenshot(s_bytes, campaign_id, comp_id)
                                    if sb_url: company.screenshot_url = sb_url
                                except: pass

                        company.processed_at = datetime.utcnow()
                        db.session.commit()
                        
                        with state['lock']:
                            state['processed_count'] += 1
                            processed = state['processed_count']
                        
                        progress_pct = round((processed / state['total_companies']) * 100, 1)
                        
                        # Signal completion via WebSocket for real-time UI updates
                        ws_manager.broadcast_event(campaign_id, {
                            'type': 'company_completed',
                            'data': {
                                'company_id': comp_id, 'status': company.status,
                                'screenshot_url': getattr(company, 'screenshot_url', None),
                                'progress': progress_pct, 'processed_count': processed,
                                'total_companies': state['total_companies']
                            }
                        })
                        
                        db.session.remove() # Aggressive cleanup

                except Exception as e:
                    print(f"[Parallel] Error in company task {comp_id}: {e}")
                    import traceback
                    traceback.print_exc()
                    try: db.session.remove()
                    except: pass

        # Execute in ThreadPool
        with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_WORKERS) as executor:
            for c in companies:
                executor.submit(process_one_company, c.id, getattr(c, 'company_name', ''))

        # 3. Finalization
        # ---------------------------------------------------------------------
        db.session.remove()
        db.session.rollback()
        campaign = Campaign.query.get(campaign_id)
        if campaign and campaign.status not in ['stopping', 'cancelled']:
            campaign.status = 'completed'
            campaign.completed_at = datetime.utcnow()
            db.session.commit()
            ws_manager.broadcast_event(campaign_id, {'type': 'campaign_complete', 'data': {'campaign_id': campaign_id}})
        db.session.remove()

        return {'status': 'success', 'processed': state['processed_count']}

    except Exception as e:
        print(f"Parallel Task Error: {e}")
        import traceback
        traceback.print_exc()
        return {'error': str(e)}
    finally:
        state['stop_watchdog'] = True
        if 'campaign_id' in locals() and campaign_id:
            try:
                db.session.rollback()
                Company.query.filter_by(campaign_id=campaign_id, status='processing').update({'status': 'pending'})
                db.session.commit()
                db.session.remove()
            except: pass
