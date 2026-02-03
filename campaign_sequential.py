"""
Standalone campaign sequential processor.
No Celery/Redis imports - safe to use when Redis is not running (e.g. Start button).
"""
import os
import json
from datetime import datetime
from playwright.sync_api import sync_playwright
from models import Campaign, Company, db


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
                        error_msg = (result.get('error') or '').lower()
                        if 'captcha' in error_msg or result.get('method') == 'form_with_captcha':
                            company.status = 'captcha'
                        else:
                            company.status = 'failed'
                        company.error_message = result.get('error')
                        company.contact_method = result.get('method')

                    # Screenshots are stored only on Supabase (no local/static fallback)
                    local_path = result.get('screenshot_url')
                    if local_path:
                        try:
                            path_part = local_path.lstrip('/').replace('/', os.sep)
                            roots = [
                                os.path.dirname(os.path.abspath(__file__)),
                                os.getcwd(),
                            ]
                            full_path = None
                            for root in roots:
                                candidate = os.path.join(root, path_part)
                                if os.path.exists(candidate):
                                    full_path = candidate
                                    break
                            if full_path:
                                with open(full_path, 'rb') as f:
                                    screenshot_bytes = f.read()
                                sb_url = upload_screenshot(screenshot_bytes, campaign_id, company.id)
                                if sb_url:
                                    company.screenshot_url = sb_url
                                else:
                                    print(f"[WARN] Supabase upload failed for company {company.id}; screenshot_url not set")
                                try:
                                    os.remove(full_path)
                                except OSError:
                                    pass
                            else:
                                print(f"[WARN] Screenshot file not found (tried {roots}); not set (Supabase only)")
                        except Exception as e:
                            print(f"Screenshot error: {e}")
                            import traceback
                            traceback.print_exc()

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
