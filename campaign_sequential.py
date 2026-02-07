"""
Standalone campaign sequential processor.
No Celery/Redis imports - safe to use when Redis is not running (e.g. Start button).
"""
import os
import json
import re
import threading
from datetime import datetime
from playwright.sync_api import sync_playwright
from models import Campaign, Company, db

# Per-company timeout so one slow site doesn't hang the whole run (e.g. 5th company)
PER_COMPANY_TIMEOUT_SEC = 90
# Max time to wait for page.close() so one stuck close doesn't freeze the entire run
PAGE_CLOSE_TIMEOUT_SEC = 8
# Recreate browser context every N companies to avoid Chromium memory bloat and "context gone bad" on long runs (2000+)
CONTEXT_REFRESH_INTERVAL = 50

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
    - company_ids: optional list of ids to process; if None, processes all pending.
    - processing_limit: optional max number to process (e.g. 2000); when None, no cap.
    """
    from websocket_manager import ws_manager
    from utils.supabase_storage import upload_screenshot

    try:
        campaign = Campaign.query.get(campaign_id)
        if not campaign:
            return {'error': f'Campaign {campaign_id} not found'}

        # Permanent fix: clear any stale "processing" from a previous crashed run so they can be retried
        stuck = Company.query.filter_by(campaign_id=campaign_id, status='processing').count()
        if stuck:
            Company.query.filter_by(campaign_id=campaign_id, status='processing').update({'status': 'pending'})
            db.session.commit()
            print(f"[Sequential] Reset {stuck} stuck 'processing' company/companies to 'pending' for campaign {campaign_id}")

        campaign.status = 'processing'
        campaign.started_at = datetime.utcnow()
        db.session.commit()

        limit = int(processing_limit) if processing_limit is not None else None
        if company_ids:
            q = Company.query.filter(
                Company.id.in_(company_ids),
                Company.campaign_id == campaign_id
            ).order_by(Company.id)
            companies = q.limit(limit).all() if limit else q.all()
        else:
            q = Company.query.filter_by(
                campaign_id=campaign_id,
                status='pending'
            ).order_by(Company.id)
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

        # Mark first company as processing immediately so UI/API show "Processing" before we touch FastCampaignProcessor
        first = companies[0]
        first.status = 'processing'
        db.session.commit()
        ws_manager.broadcast_event(campaign_id, {
            'type': 'company_processing',
            'data': {'company_id': first.id, 'company_name': getattr(first, 'company_name', '')}
        })

        # Import after first commit so if FastCampaignProcessor import fails, API still shows 1 processing and we can see the error in logs
        try:
            from services.fast_campaign_processor import FastCampaignProcessor
        except Exception as imp_err:
            print(f"[Sequential] Failed to import FastCampaignProcessor: {imp_err}")
            import traceback
            traceback.print_exc()
            first.status = 'failed'
            first.error_message = 'Backend failed to load processor. Check server logs.'
            db.session.commit()
            return {'error': str(imp_err)}

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-setuid-sandbox'])
            context = browser.new_context()

            for idx, company in enumerate(companies):
                page = None
                # Periodic context refresh: avoid Chromium memory bloat and "context gone bad" on long runs (2000+ companies)
                if idx > 0 and idx % CONTEXT_REFRESH_INTERVAL == 0:
                    try:
                        context.close()
                    except Exception as ctx_err:
                        print(f"[Sequential] Context close warning: {ctx_err}")
                    try:
                        context = browser.new_context()
                        print(f"[Sequential] Refreshed browser context after {idx} companies (continuing to next)")
                    except Exception as ctx_err:
                        print(f"[Sequential] New context failed: {ctx_err}; continuing with existing context")
                # Re-fetch company by id so we always have a fresh session reference (avoids expired/detached after previous commit)
                try:
                    _cid = company.id if hasattr(company, 'id') else None
                    if _cid is not None:
                        company = Company.query.filter_by(id=_cid, campaign_id=campaign_id).first()
                    if company is None:
                        print(f"[Sequential] Skipping missing company at index {idx}")
                        continue
                except Exception as refetch_err:
                    print(f"[Sequential] Refetch company at index {idx} failed: {refetch_err}; skipping")
                    continue

                try:
                    db.session.rollback()
                    db.session.refresh(campaign)
                    if campaign.status in ['stopping', 'cancelled']:
                        # Reset any company still "processing" so UI doesn't show it stuck
                        Company.query.filter_by(
                            campaign_id=campaign_id,
                            status='processing'
                        ).update({'status': 'pending'})
                        campaign.status = 'cancelled'
                        db.session.commit()
                        ws_manager.broadcast_event(campaign_id, {
                            'type': 'campaign_stopped',
                            'data': {'message': 'Processing stopped by user'}
                        })
                        break

                    # PERMANENT FIX: Only one company may be "processing" at a time. Clear any other stuck ones (e.g. from crashed iteration).
                    other_stuck = Company.query.filter(
                        Company.campaign_id == campaign_id,
                        Company.status == 'processing',
                        Company.id != company.id
                    ).update({'status': 'pending'})
                    if other_stuck:
                        db.session.commit()
                        print(f"[Sequential] Cleared {other_stuck} other company/companies from 'processing' before starting company {company.id}")

                    company.status = 'processing'
                    db.session.commit()

                    try:
                        page = context.new_page()
                        page.set_default_timeout(25000)
                        page.set_default_navigation_timeout(30000)
                    except Exception as page_err:
                        # Context may be bad after timeouts; try fresh context once
                        try:
                            context.close()
                            context = browser.new_context()
                            page = context.new_page()
                            page.set_default_timeout(25000)
                            page.set_default_navigation_timeout(30000)
                        except Exception as retry_err:
                            print(f"[Sequential] new_page() failed for company {company.id}: {page_err}; retry: {retry_err}")
                            company.status = 'failed'
                            company.error_message = _user_facing_error(str(retry_err))
                            company.processed_at = datetime.utcnow()
                            db.session.commit()
                            campaign.processed_count = Company.query.filter(
                                Company.campaign_id == campaign.id,
                                Company.status != 'pending',
                                Company.status != 'processing'
                            ).count()
                            db.session.commit()
                            ws_manager.broadcast_event(campaign_id, {
                                'type': 'company_completed',
                                'data': {
                                    'company_id': company.id,
                                    'status': company.status,
                                    'screenshot_url': None,
                                    'progress': int((idx + 1) / len(companies) * 100)
                                }
                            })
                            continue
                    # If retry succeeded, page is set and we proceed

                    # Capture ids/names in this thread so inner thread never touches ORM (avoids "Working outside of application context")
                    _company_id = company.id
                    _company_name = getattr(company, 'company_name', '') or ''

                    def live_logger(level, action, message):
                        print(f"[{level}] {action}: {message}")
                        user_msg = _user_friendly_message(level, action, message)
                        ws_manager.broadcast_event(campaign_id, {
                            'type': 'activity',
                            'data': {
                                'company_id': _company_id,
                                'company_name': _company_name,
                                'level': level,
                                'action': action,
                                'message': message,
                                'user_message': user_msg,
                                'timestamp': datetime.utcnow().isoformat()
                            }
                        })

                    result = None
                    try:
                        company_data = company.to_dict()
                        processor = FastCampaignProcessor(
                            page=page,
                            company_data=company_data,
                            message_template=message_template_str,
                            campaign_id=campaign_id,
                            company_id=_company_id,
                            logger=live_logger,
                            subject=subject_str,
                            sender_data=sender_data,
                            deadline_sec=PER_COMPANY_TIMEOUT_SEC,
                            skip_submit=skip_submit
                        )
                        # Direct call - Playwright's global timeout (5s) ensures no operation hangs forever.
                        # The processor's internal deadline checks (_is_timed_out) handle early exit.
                        result = processor.process_company()
                        _m = (result or {}).get('method') or ''
                        _e = ((result or {}).get('error') or '')[:200]
                        print(f"[Sequential] Company {_company_id} result: method={_m!r} error={_e!r}")
                    except Exception as e:
                        result = {'success': False, 'error': str(e), 'method': 'error'}
                        print(f"[Sequential] Company {_company_id} failed with exception: {e}")

                    try:
                        if result is None:
                            company.status = 'failed'
                            company.contact_method = 'error'
                            company.error_message = _user_facing_error('No result from worker')
                        elif result is not None:
                            if result.get('success'):
                                method = result.get('method', '')
                                if method == 'contact_info_found' or method.startswith('email'):
                                    company.status = 'contact_info_found'
                                else:
                                    company.status = 'completed'
                                company.contact_method = (method or '')[:20]
                                company.fields_filled = result.get('fields_filled', 0)
                                company.error_message = None
                                if result.get('form_fields_detected') is not None or result.get('filled_field_patterns'):
                                    company.form_structure = {
                                        'fields_detected': result.get('form_fields_detected') or [],
                                        'fields_filled': result.get('filled_field_patterns') or [],
                                    }
                            else:
                                error_msg = (result.get('error') or '').lower()
                                method = result.get('method') or ''
                                if method == 'timeout':
                                    company.status = 'failed'
                                    company.error_message = _user_facing_error('Processing timed out (limit reached). You can retry this company.')
                                elif 'captcha' in error_msg or method == 'form_with_captcha':
                                    company.status = 'captcha'
                                elif method == 'no_contact_found':
                                    company.status = 'no_contact_found'
                                    company.error_message = 'No contact form found on this site.'
                                else:
                                    company.status = 'failed'
                                    if method == 'error':
                                        print(f"[Sequential] Company {company.id} failed with exception: {result.get('error')}")
                                company.contact_method = (result.get('method') or '')[:20]
                                if company.status == 'failed' and method != 'timeout':
                                    company.error_message = _user_facing_error(result.get('error'))
                                if result.get('form_fields_detected') is not None or result.get('filled_field_patterns'):
                                    company.form_structure = {
                                        'fields_detected': result.get('form_fields_detected') or [],
                                        'fields_filled': result.get('filled_field_patterns') or [],
                                    }
                            screenshot_bytes = result.get('screenshot_bytes')
                            if not screenshot_bytes and result.get('screenshot_url'):
                                local_path = result.get('screenshot_url')
                                try:
                                    path_part = local_path.lstrip('/').replace('/', os.sep)
                                    roots = [os.path.dirname(os.path.abspath(__file__)), os.getcwd()]
                                    for root in roots:
                                        candidate = os.path.join(root, path_part)
                                        if os.path.exists(candidate):
                                            with open(candidate, 'rb') as f:
                                                screenshot_bytes = f.read()
                                            try:
                                                os.remove(candidate)
                                            except OSError:
                                                pass
                                            break
                                except Exception as e:
                                    print(f"[WARN] Screenshot file read error: {e}")
                            if screenshot_bytes:
                                try:
                                    _upload_result = [None]
                                    def _do_upload():
                                        _upload_result[0] = upload_screenshot(screenshot_bytes, campaign_id, company.id)
                                    _up = threading.Thread(target=_do_upload, daemon=True)
                                    _up.start()
                                    _up.join(timeout=30)
                                    sb_url = _upload_result[0] if not _up.is_alive() else None
                                    if sb_url:
                                        company.screenshot_url = sb_url
                                    elif _up.is_alive():
                                        print(f"[WARN] Screenshot upload timed out after 30s")
                                except Exception as e:
                                    print(f"[WARN] Screenshot upload error: {e}")
                            if not company.screenshot_url and result.get('method') == 'error':
                                try:
                                    fb_bytes = page.screenshot(full_page=True)
                                    if fb_bytes:
                                        _upload_result = [None]
                                        def _do_upload_fb():
                                            _upload_result[0] = upload_screenshot(fb_bytes, campaign_id, company.id)
                                        _up = threading.Thread(target=_do_upload_fb, daemon=True)
                                        _up.start()
                                        _up.join(timeout=30)
                                        sb_url = _upload_result[0] if not _up.is_alive() else None
                                        if sb_url:
                                            company.screenshot_url = sb_url
                                except Exception as e:
                                    print(f"[WARN] Fallback screenshot error: {e}")
                        company.processed_at = datetime.utcnow()
                        db.session.commit()
                        # Processed = finished only (exclude "processing" so counts add up)
                        campaign.processed_count = Company.query.filter(
                            Company.campaign_id == campaign.id,
                            Company.status != 'pending',
                            Company.status != 'processing'
                        ).count()
                        campaign.success_count = Company.query.filter_by(campaign_id=campaign.id, status='completed').count() + \
                            Company.query.filter_by(campaign_id=campaign.id, status='contact_info_found').count()
                        campaign.failed_count = Company.query.filter_by(campaign_id=campaign.id, status='failed').count()
                        campaign.captcha_count = Company.query.filter_by(campaign_id=campaign.id, status='captcha').count()
                        db.session.commit()
                        ws_manager.broadcast_event(campaign_id, {
                            'type': 'company_completed',
                            'data': {
                                'company_id': company.id,
                                'status': company.status,
                                'screenshot_url': getattr(company, 'screenshot_url', None),
                                'progress': int((idx + 1) / len(companies) * 100)
                            }
                        })
                    except Exception as e:
                        live_logger('error', 'Execution Error', str(e))
                        try:
                            db.session.rollback()
                            company.status = 'failed'
                            company.error_message = _user_facing_error(str(e))
                            company.processed_at = datetime.utcnow()
                            try:
                                fb_bytes = page.screenshot(full_page=True)
                                if fb_bytes:
                                    sb_url = upload_screenshot(fb_bytes, campaign_id, company.id)
                                    if sb_url:
                                        company.screenshot_url = sb_url
                            except Exception:
                                pass
                            db.session.commit()
                            campaign.processed_count = Company.query.filter(
                                Company.campaign_id == campaign.id,
                                Company.status != 'pending',
                                Company.status != 'processing'
                            ).count()
                            campaign.failed_count = Company.query.filter_by(campaign_id=campaign.id, status='failed').count()
                            campaign.captcha_count = Company.query.filter_by(campaign_id=campaign.id, status='captcha').count()
                            db.session.commit()
                            ws_manager.broadcast_event(campaign_id, {
                                'type': 'company_completed',
                                'data': {
                                    'company_id': company.id,
                                    'status': 'failed',
                                    'screenshot_url': getattr(company, 'screenshot_url', None),
                                    'progress': int((idx + 1) / len(companies) * 100)
                                }
                            })
                        except Exception as e2:
                            print(f"[Sequential] Failed to record execution error for company {company.id}: {e2}")
                            try:
                                db.session.rollback()
                            except Exception:
                                pass
                    finally:
                        # PERMANENT FIX: If this company is still "processing" after we're done (crash/early exit), force to failed and notify so it never stays stuck.
                        try:
                            db.session.refresh(company)
                            if company.status == 'processing':
                                company.status = 'failed'
                                company.error_message = 'Processing stopped unexpectedly. You can retry.'
                                company.processed_at = datetime.utcnow()
                                db.session.commit()
                                ws_manager.broadcast_event(campaign_id, {
                                    'type': 'company_completed',
                                    'data': {
                                        'company_id': company.id,
                                        'status': 'failed',
                                        'screenshot_url': getattr(company, 'screenshot_url', None),
                                        'progress': int((idx + 1) / len(companies) * 100)
                                    }
                                })
                                print(f"[Sequential] Safety: company {company.id} was still processing after iteration; set to failed")
                        except Exception as safe_err:
                            print(f"[Sequential] Safety net error (non-fatal): {safe_err}")
                            try:
                                db.session.rollback()
                            except Exception:
                                pass
                        # Always close the page so we don't accumulate pages. Use a timeout so one stuck close never freezes the whole run.
                        if page:
                            def do_close():
                                try:
                                    page.close()
                                except Exception:
                                    pass
                            closer = threading.Thread(target=do_close, daemon=True)
                            closer.start()
                            closer.join(timeout=PAGE_CLOSE_TIMEOUT_SEC)
                            if closer.is_alive():
                                print(f"[WARN] Page close did not finish in {PAGE_CLOSE_TIMEOUT_SEC}s; continuing to next company")
                except BaseException as outer_err:
                    # ANY uncaught exception in this iteration: mark company failed, broadcast, then CONTINUE to next company (never re-raise so remaining companies still process)
                    _company_id_safe = getattr(company, 'id', None)
                    print(f"[Sequential] Company {_company_id_safe} iteration failed (continuing to next): {outer_err}")
                    import traceback
                    traceback.print_exc()
                    try:
                        db.session.rollback()
                        c = Company.query.get(_company_id_safe) if _company_id_safe else None
                        if c is not None:
                            c.status = 'failed'
                            c.error_message = _user_facing_error(str(outer_err))
                            c.processed_at = datetime.utcnow()
                            db.session.commit()
                            db.session.refresh(campaign)
                            campaign.processed_count = Company.query.filter(
                                Company.campaign_id == campaign.id,
                                Company.status != 'pending',
                                Company.status != 'processing'
                            ).count()
                            campaign.failed_count = Company.query.filter_by(campaign_id=campaign.id, status='failed').count()
                            campaign.captcha_count = Company.query.filter_by(campaign_id=campaign.id, status='captcha').count()
                            db.session.commit()
                            ws_manager.broadcast_event(campaign_id, {
                                'type': 'company_completed',
                                'data': {
                                    'company_id': _company_id_safe,
                                    'status': 'failed',
                                    'screenshot_url': None,
                                    'progress': int((idx + 1) / len(companies) * 100)
                                }
                            })
                    except Exception as e2:
                        print(f"[Sequential] Failed to record iteration error (continuing): {e2}")
                        try:
                            db.session.rollback()
                        except Exception:
                            pass
                    if page:
                        def do_close():
                            try:
                                page.close()
                            except Exception:
                                pass
                        closer = threading.Thread(target=do_close, daemon=True)
                        closer.start()
                        closer.join(timeout=PAGE_CLOSE_TIMEOUT_SEC)
                        if closer.is_alive():
                            print(f"[WARN] Page close (after error) did not finish in {PAGE_CLOSE_TIMEOUT_SEC}s")

            try:
                browser.close()
            except Exception as close_err:
                print(f"[Sequential] Browser close warning (non-fatal): {close_err}")

        # Only mark completed if we didn't break out due to stop/cancel
        if campaign.status not in ['stopping', 'cancelled']:
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
    finally:
        # PERMANENT FIX: Always clear any company still "processing" so they are never stuck (crash/exit/timeout). Never skip.
        if campaign_id is not None:
            try:
                db.session.rollback()
            except Exception:
                pass
            try:
                n = Company.query.filter_by(campaign_id=campaign_id, status='processing').update({'status': 'pending'})
                if n:
                    db.session.commit()
                    print(f"[Sequential] Exit cleanup: cleared {n} company/companies from 'processing' to 'pending' (campaign {campaign_id})")
            except Exception as cleanup_err:
                print(f"[Sequential] Exit cleanup warning: {cleanup_err}")
                try:
                    db.session.rollback()
                except Exception:
                    pass
