"""
Standalone campaign sequential processor.
No Celery/Redis imports - safe to use when Redis is not running (e.g. Start button).
"""
import os
import json
import re
from datetime import datetime
from playwright.sync_api import sync_playwright
from models import Campaign, Company, db

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
    return s


def process_campaign_sequential(campaign_id, company_ids=None):
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

        campaign.status = 'processing'
        campaign.started_at = datetime.utcnow()
        db.session.commit()

        if company_ids:
            companies = Company.query.filter(
                Company.id.in_(company_ids),
                Company.campaign_id == campaign_id
            ).order_by(Company.id).all()
        else:
            companies = Company.query.filter_by(
                campaign_id=campaign_id,
                status='pending'
            ).order_by(Company.id).all()

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

        # Mark first company as processing immediately so UI shows "Processing" right after Start
        first = companies[0]
        first.status = 'processing'
        db.session.commit()
        ws_manager.broadcast_event(campaign_id, {
            'type': 'company_processing',
            'data': {'company_id': first.id, 'company_name': getattr(first, 'company_name', '')}
        })

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-setuid-sandbox'])
            context = browser.new_context()

            for idx, company in enumerate(companies):
                db.session.refresh(campaign)
                if campaign.status in ['stopping', 'cancelled']:
                    ws_manager.broadcast_event(campaign_id, {
                        'type': 'campaign_stopped',
                        'data': {'message': 'Processing stopped by user'}
                    })
                    break

                company.status = 'processing'
                db.session.commit()

                page = context.new_page()
                page.set_default_timeout(25000)
                page.set_default_navigation_timeout(30000)

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

                try:
                    result = None
                    company_data = company.to_dict()
                    processor = FastCampaignProcessor(
                        page=page,
                        company_data=company_data,
                        message_template=message_template_str,
                        campaign_id=campaign_id,
                        company_id=_company_id,
                        logger=live_logger,
                        subject=subject_str,
                        sender_data=sender_data
                    )
                    result = processor.process_company()
                except Exception as e:
                    result = {'success': False, 'error': str(e), 'method': 'error'}

                try:
                    if result is not None:
                        if result.get('success'):
                            method = result.get('method', '')
                            if method.startswith('email'):
                                company.status = 'contact_info_found'
                            else:
                                company.status = 'completed'
                            company.contact_method = (method or '')[:20]
                            company.fields_filled = result.get('fields_filled', 0)
                            company.error_message = None
                        else:
                            error_msg = (result.get('error') or '').lower()
                            method = result.get('method') or ''
                            if 'captcha' in error_msg or method == 'form_with_captcha':
                                company.status = 'captcha'
                            elif method == 'no_contact_found':
                                company.status = 'no_contact_found'
                                company.error_message = 'No contact form found on this site.'
                            else:
                                company.status = 'failed'
                                if method == 'error':
                                    print(f"[Sequential] Company {company.id} failed with exception: {result.get('error')}")
                            company.contact_method = (result.get('method') or '')[:20]
                            if company.status == 'failed':
                                company.error_message = _user_facing_error(result.get('error'))
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
                                sb_url = upload_screenshot(screenshot_bytes, campaign_id, company.id)
                                if sb_url:
                                    company.screenshot_url = sb_url
                            except Exception as e:
                                print(f"[WARN] Screenshot upload error: {e}")
                        if not company.screenshot_url and result.get('method') == 'error':
                            try:
                                fb_bytes = page.screenshot()
                                if fb_bytes:
                                    sb_url = upload_screenshot(fb_bytes, campaign_id, company.id)
                                    if sb_url:
                                        company.screenshot_url = sb_url
                            except Exception as e:
                                print(f"[WARN] Fallback screenshot error: {e}")
                    company.processed_at = datetime.utcnow()
                    db.session.commit()
                    campaign.processed_count = Company.query.filter_by(campaign_id=campaign.id).filter(Company.status != 'pending').count()
                    campaign.success_count = Company.query.filter_by(campaign_id=campaign.id, status='completed').count() + \
                        Company.query.filter_by(campaign_id=campaign.id, status='contact_info_found').count()
                    campaign.failed_count = Company.query.filter_by(campaign_id=campaign.id, status='failed').count()
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
                    company.status = 'failed'
                    company.error_message = _user_facing_error(str(e))
                    try:
                        fb_bytes = page.screenshot()
                        if fb_bytes:
                            sb_url = upload_screenshot(fb_bytes, campaign_id, company.id)
                            if sb_url:
                                company.screenshot_url = sb_url
                    except Exception:
                        pass
                    db.session.commit()
                finally:
                    page.close()

            browser.close()

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
