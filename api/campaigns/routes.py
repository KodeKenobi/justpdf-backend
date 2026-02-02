from flask import Blueprint, request, jsonify
import os
from sqlalchemy import desc, or_, func
from datetime import datetime
from flask_jwt_extended import jwt_required, get_jwt_identity

# Create Blueprint - All endpoints are public, no authentication required
campaigns_api = Blueprint('campaigns_api', __name__, url_prefix='/api/campaigns')

# Campaign company limits by subscription tier
CAMPAIGN_LIMITS = {
    'guest': 5,        # Anonymous users
    'free': 50,        # Signed up free users
    'testing': 50,     # Testing tier (same as free)
    'premium': 100,    # Production ($9/mo)
    'enterprise': -1,  # Unlimited ($19/mo)
    'client': -1,      # Unlimited (client tier)
}

def get_campaign_limit(user_tier=None):
    """Get campaign company limit for a given user tier"""
    if not user_tier or user_tier not in CAMPAIGN_LIMITS:
        return CAMPAIGN_LIMITS['guest']
    
    limit = CAMPAIGN_LIMITS[user_tier]
    return float('inf') if limit == -1 else limit

@campaigns_api.before_request
def handle_options():
    """Handle OPTIONS requests (CORS preflight)"""
    if request.method == 'OPTIONS':
        return jsonify({}), 200

@campaigns_api.route('', methods=['GET'])
@jwt_required(optional=True)
def list_campaigns():
    """Get campaigns filtered by user or session (supports both authenticated and guest users)"""
    try:
        from models import Campaign
        from database import db
        
        # Get user ID if authenticated
        current_user_id = get_jwt_identity()
        
        # Get session_id from query params for guest users
        session_id = request.args.get('session_id')
        
        # Pagination
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        
        # Filters
        status = request.args.get('status')
        
        # Build query with proper filtering
        query = Campaign.query
        
        # Filter by user_id for authenticated users, or session_id for guests
        if current_user_id:
            # Authenticated user - show only their campaigns
            query = query.filter_by(user_id=current_user_id)
        elif session_id:
            # Guest user - show only campaigns from their session
            query = query.filter_by(session_id=session_id, user_id=None)
        else:
            # No user or session - return empty list for security
            return jsonify({
                'success': True,
                'campaigns': [],
                'pagination': {
                    'page': 1,
                    'per_page': per_page,
                    'total': 0,
                    'pages': 0
                }
            }), 200
        
        if status:
            query = query.filter_by(status=status)
        
        # Order by creation date
        query = query.order_by(desc(Campaign.created_at))
        
        # Paginate
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        campaigns = pagination.items
        
        return jsonify({
            'success': True,
            'campaigns': [campaign.to_dict() for campaign in campaigns],
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': pagination.total,
                'pages': pagination.pages
            }
        }), 200
        
    except Exception as e:
        print(f"Error fetching campaigns: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@campaigns_api.route('/detect-companies', methods=['POST'])
def detect_companies():
    """Auto-detect company names from URLs"""
    try:
        import subprocess
        import json
        
        data = request.get_json()
        urls = data.get('urls', [])
        
        if not urls or len(urls) == 0:
            return jsonify({'error': 'At least one URL is required'}), 400
        
        # Call Node.js service to detect companies
        result = subprocess.run(
            ['node', '-e', f'''
const {{ CompanyDetector }} = require('../services/company-detector.ts');
const detector = new CompanyDetector();
(async () => {{
    const urls = {json.dumps(urls)};
    const results = await detector.detectBatch(urls);
    await detector.close();
    console.log(JSON.stringify(Object.fromEntries(results)));
}})();
            '''],
            capture_output=True,
            text=True,
            timeout=60
        )
        
        if result.returncode == 0:
            detected = json.loads(result.stdout)
            return jsonify({
                'success': True,
                'companies': detected
            }), 200
        else:
            print(f"Error detecting companies: {result.stderr}")
            return jsonify({'error': 'Failed to detect companies'}), 500
        
    except Exception as e:
        print(f"Error in detect_companies: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@campaigns_api.route('', methods=['POST'])
@jwt_required(optional=True)
def create_campaign():
    """Create a new campaign (supports both authenticated and guest users)"""
    try:
        from models import Campaign, Company
        from database import db
        
        # Get user ID if authenticated, otherwise None for guest
        current_user_id = get_jwt_identity()
        
        data = request.get_json()
        name = data.get('name')
        message_template = data.get('message_template')
        companies_data = data.get('companies', [])
        auto_detect_names = data.get('auto_detect_names', True)
        session_id = data.get('session_id')  # For guest users
        
        # Validate input
        if not name or not message_template:
            return jsonify({'error': 'Name and message template are required'}), 400
        
        if not companies_data or len(companies_data) == 0:
            return jsonify({'error': 'At least one company is required'}), 400
        
        # For guests, session_id is required
        if not current_user_id and not session_id:
            return jsonify({'error': 'Session ID is required for guest users'}), 400
        
        # Auto-detect missing company names if enabled
        if auto_detect_names:
            urls_to_detect = []
            for company_data in companies_data:
                if not company_data.get('company_name') or company_data.get('company_name').strip() == '':
                    urls_to_detect.append(company_data.get('website_url'))
            
            if urls_to_detect:
                print(f"Auto-detecting company names for {len(urls_to_detect)} URLs...")
                # This will be handled by the worker later
                # For now, use domain name as fallback
                for company_data in companies_data:
                    if not company_data.get('company_name') or company_data.get('company_name').strip() == '':
                        url = company_data.get('website_url', '')
                        # Extract domain and use as company name
                        try:
                            from urllib.parse import urlparse
                            parsed = urlparse(url if url.startswith('http') else f'https://{url}')
                            domain = parsed.hostname or url
                            domain = domain.replace('www.', '')
                            company_name = domain.split('.')[0].capitalize()
                            company_data['company_name'] = company_name
                            print(f"Auto-detected company name: {company_name} from {url}")
                        except:
                            company_data['company_name'] = url
        
        # Create campaign with user_id or session_id
        campaign = Campaign(
            user_id=current_user_id,  # Will be None for guests, user ID for authenticated users
            session_id=session_id if not current_user_id else None,  # Store session_id only for guests
            name=name,
            message_template=message_template,
            status='draft',
            total_companies=len(companies_data)
        )
        db.session.add(campaign)
        db.session.flush()  # Get campaign ID
        
        # Create companies
        for company_data in companies_data:
            company = Company(
                campaign_id=campaign.id,
                company_name=company_data.get('company_name', ''),
                website_url=company_data.get('website_url', ''),
                contact_email=company_data.get('contact_email'),
                contact_person=company_data.get('contact_person'),
                phone=company_data.get('phone'),
                additional_data=company_data.get('additional_data', {})
            )
            db.session.add(company)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Campaign created successfully',
            'campaign': campaign.to_dict()
        }), 201
        
    except Exception as e:
        print(f"Error creating campaign: {e}")
        import traceback
        traceback.print_exc()
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@campaigns_api.route('/<int:campaign_id>', methods=['GET'])
def get_campaign(campaign_id):
    """Get a specific campaign with details"""
    try:
        from models import Campaign
        
        campaign = Campaign.query.get(campaign_id)
        
        if not campaign:
            return jsonify({'error': 'Campaign not found'}), 404
        
        include_companies = request.args.get('include_companies', 'false').lower() == 'true'
        
        return jsonify({
            'success': True,
            'campaign': campaign.to_dict(include_companies=include_companies)
        }), 200
        
    except Exception as e:
        print(f"Error fetching campaign: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@campaigns_api.route('/<int:campaign_id>', methods=['PATCH'])
def update_campaign(campaign_id):
    """Update a campaign"""
    try:
        from models import Campaign
        from database import db
        
        campaign = Campaign.query.get(campaign_id)
        
        if not campaign:
            return jsonify({'error': 'Campaign not found'}), 404
        
        data = request.get_json()
        
        if 'name' in data:
            campaign.name = data['name']
        if 'message_template' in data:
            campaign.message_template = data['message_template']
        if 'status' in data:
            campaign.status = data['status']
            if data['status'] == 'queued':
                campaign.started_at = datetime.utcnow()
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Campaign updated successfully',
            'campaign': campaign.to_dict()
        }), 200
        
    except Exception as e:
        print(f"Error updating campaign: {e}")
        import traceback
        traceback.print_exc()
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@campaigns_api.route('/<int:campaign_id>', methods=['DELETE'])
def delete_campaign(campaign_id):
    """Delete a campaign"""
    try:
        from models import Campaign
        from database import db
        
        campaign = Campaign.query.get(campaign_id)
        
        if not campaign:
            return jsonify({'error': 'Campaign not found'}), 404
        
        db.session.delete(campaign)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Campaign deleted successfully'
        }), 200
        
    except Exception as e:
        print(f"Error deleting campaign: {e}")
        import traceback
        traceback.print_exc()
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@campaigns_api.route('/<int:campaign_id>/companies', methods=['GET'])
def get_campaign_companies(campaign_id):
    """Get all companies for a specific campaign"""
    try:
        from models import Campaign, Company
        
        campaign = Campaign.query.get(campaign_id)
        
        if not campaign:
            return jsonify({'error': 'Campaign not found'}), 404
        
        # Get all companies for this campaign
        companies = Company.query.filter_by(campaign_id=campaign_id).all()
        
        return jsonify({
            'success': True,
            'companies': [company.to_dict() for company in companies]
        }), 200
        
    except Exception as e:
        print(f"Error fetching campaign companies: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@campaigns_api.route('/companies/<int:company_id>', methods=['PATCH'])
def update_company(company_id):
    """Update a specific company in a campaign"""
    try:
        from models import Company, Campaign
        from database import db
        from datetime import datetime
        
        company = Company.query.get(company_id)
        
        if not company:
            return jsonify({'error': 'Company not found'}), 404
        
        data = request.get_json()
        
        # Update allowed fields
        if 'status' in data:
            company.status = data['status']
        if 'error_message' in data:
            company.error_message = data['error_message']
        if 'contact_page_url' in data:
            company.contact_page_url = data['contact_page_url']
        if 'contact_page_found' in data:
            company.contact_page_found = data['contact_page_found']
        if 'form_found' in data:
            company.form_found = data['form_found']
        if 'contact_method' in data:
            company.contact_method = data['contact_method']
        if 'emails_found' in data:
            # Handle both JSON string and list
            if isinstance(data['emails_found'], str):
                import json
                company.emails_found = json.loads(data['emails_found'])
            else:
                company.emails_found = data['emails_found']
        if 'emails_sent' in data:
            # Handle both JSON string and list
            if isinstance(data['emails_sent'], str):
                import json
                company.emails_sent = json.loads(data['emails_sent'])
            else:
                company.emails_sent = data['emails_sent']
        if 'email_sent_at' in data:
            if data['email_sent_at']:
                company.email_sent_at = datetime.fromisoformat(data['email_sent_at'].replace('Z', '+00:00'))
        if 'form_structure' in data:
            if isinstance(data['form_structure'], str):
                import json
                company.form_structure = json.loads(data['form_structure'])
            else:
                company.form_structure = data['form_structure']
        if 'field_mappings' in data:
            if isinstance(data['field_mappings'], str):
                import json
                company.field_mappings = json.loads(data['field_mappings'])
            else:
                company.field_mappings = data['field_mappings']
        if 'form_complexity' in data:
            company.form_complexity = data['form_complexity']
        if 'pattern_learned' in data:
            company.pattern_learned = data['pattern_learned']
        if 'screenshot_url' in data:
            company.screenshot_url = data['screenshot_url']
        if 'processed_at' in data:
            company.processed_at = datetime.fromisoformat(data['processed_at'].replace('Z', '+00:00'))
        if 'submitted_at' in data:
            if data['submitted_at']:
                company.submitted_at = datetime.fromisoformat(data['submitted_at'].replace('Z', '+00:00'))
        
        db.session.commit()
        
        # Update campaign statistics
        campaign = company.campaign
        campaign.processed_count = Company.query.filter_by(campaign_id=campaign.id).filter(Company.status != 'pending').count()
        # Count success as both 'success' status and companies with emails_sent (email fallback)
        success_companies = Company.query.filter_by(campaign_id=campaign.id).filter(
            db.or_(Company.status == 'success', Company.emails_sent.isnot(None))
        ).count()
        campaign.success_count = success_companies
        campaign.failed_count = Company.query.filter_by(campaign_id=campaign.id, status='failed').count()
        campaign.captcha_count = Company.query.filter_by(campaign_id=campaign.id, status='captcha').count()
        
        # Check if all companies are processed and update campaign status
        total_companies = campaign.total_companies
        if campaign.processed_count >= total_companies and campaign.status != 'completed':
            # All companies processed, mark campaign as completed
            campaign.status = 'completed'
            campaign.completed_at = datetime.utcnow()
            print(f"[Campaign {campaign.id}] All {total_companies} companies processed. Marking campaign as completed.")
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Company updated successfully',
            'company': company.to_dict()
        }), 200
        
    except Exception as e:
        print(f"Error updating company: {e}")
        import traceback
        traceback.print_exc()
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@campaigns_api.route('/companies/<int:company_id>/logs', methods=['POST'])
def create_company_logs(company_id):
    """Create submission logs for a company (used by worker)"""
    try:
        from models import Company, SubmissionLog
        from database import db
        
        company = Company.query.get(company_id)
        
        if not company:
            return jsonify({'error': 'Company not found'}), 404
        
        data = request.get_json()
        logs_data = data.get('logs', [])
        
        for log_data in logs_data:
            log = SubmissionLog(
                company_id=company_id,
                action=log_data.get('action', ''),
                status=log_data.get('status', ''),
                message=log_data.get('message', ''),
                details=log_data.get('details')
            )
            db.session.add(log)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Logs created successfully'
        }), 201
        
    except Exception as e:
        print(f"Error creating logs: {e}")
        import traceback
        traceback.print_exc()
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@campaigns_api.route('/companies/<int:company_id>/process', methods=['POST'])
def process_company_live(company_id):
    """Process a single company with live monitoring"""
    try:
        from models import Company
        from database import db
        import threading
        
        company = Company.query.get(company_id)
        
        if not company:
            return jsonify({'error': 'Company not found'}), 404
        
        # Mark as processing
        company.status = 'processing'
        db.session.commit()
        
        # Start processing in background thread
        def process_in_background():
            try:
                # Call Node.js worker to process this company with live updates
                import subprocess
                subprocess.run(
                    ['node', 'services/campaign-worker.ts', '--company-id', str(company_id), '--live'],
                    cwd=os.path.join(os.path.dirname(__file__), '../..'),
                    timeout=300  # 5 minute timeout
                )
            except Exception as e:
                print(f"Error processing company {company_id}: {e}")
        
        thread = threading.Thread(target=process_in_background)
        thread.daemon = True
        thread.start()
        
        return jsonify({
            'success': True,
            'message': 'Processing started',
            'company': company.to_dict()
        }), 200
        
    except Exception as e:
        print(f"Error starting company processing: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

# Internal API for Workers (no auth required)
@campaigns_api.route('/internal/queued', methods=['GET'])
def get_queued_campaigns_internal():
    """Internal endpoint for workers to fetch queued campaigns (no auth required)"""
    try:
        from models import Campaign
        from database import db
        
        # Fetch campaigns with status 'queued' or 'processing'
        campaigns = Campaign.query.filter(
            or_(Campaign.status == 'queued', Campaign.status == 'processing')
        ).order_by(Campaign.created_at).all()
        
        return jsonify({
            'success': True,
            'campaigns': [campaign.to_dict() for campaign in campaigns]
        }), 200
        
    except Exception as e:
        print(f"Error fetching queued campaigns: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@campaigns_api.route('/<int:campaign_id>/companies/<int:company_id>/rapid-process', methods=['POST'])
def rapid_process_single(campaign_id, company_id):
    """
    Fast campaign processing using JavaScript rapid-process-single.js
    - Uses proven JavaScript scraper that works reliably
    - Submits forms when found
    - Handles client-side rendered forms correctly
    """
    try:
        from models import Company, Campaign
        from database import db
        import subprocess
        import json
        import time
        import os
        
        campaign = Campaign.query.get(campaign_id)
        if not campaign:
            return jsonify({'error': 'Campaign not found'}), 404
        
        company = Company.query.filter_by(id=company_id, campaign_id=campaign_id).first()
        if not company:
            return jsonify({'error': 'Company not found'}), 404
        
        # Mark as processing
        company.status = 'processing'
        db.session.commit()
        
        start_time = time.time()
        
        try:
            # Parse message_template
            message_template_str = campaign.message_template
            subject_str = 'Partnership Inquiry'  # Default subject
            
            try:
                if isinstance(campaign.message_template, str):
                    message_template_parsed = json.loads(campaign.message_template)
                    if isinstance(message_template_parsed, dict):
                        message_template_str = message_template_parsed.get('message', campaign.message_template)
                        subject_str = message_template_parsed.get('subject', 'Partnership Inquiry')
                    else:
                        message_template_str = campaign.message_template
            except (json.JSONDecodeError, AttributeError):
                message_template_str = campaign.message_template if isinstance(campaign.message_template, str) else str(campaign.message_template)
            
            try:
                # Use Python FastCampaignProcessor instead of Node script
                # This ensures consistent logic and safety controls
                from services.fast_campaign_processor import FastCampaignProcessor
                from playwright.sync_api import sync_playwright
                
                result = None
                
                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-setuid-sandbox'])
                    page = browser.new_page()
                    
                    # Setup processor
                    company_data = company.to_dict()
                    processor = FastCampaignProcessor(
                        page=page,
                        company_data=company_data,
                        message_template=message_template_str,
                        campaign_id=campaign_id,
                        company_id=company_id,
                        subject=subject_str
                    )
                    
                    # Execute
                    print(f"[Rapid Process] Starting Python processing for {company.website_url}")
                    result = processor.process_company()
                    browser.close()

            except Exception as e:
                print(f"[Rapid Process] Script error: {e}")
                import traceback
                traceback.print_exc()
                
                # Return error
                return jsonify({
                    'success': False,
                    'error': 'Script execution failed',
                    'details': str(e)
                }), 500
            
            # Update company based on result
            if result.get('success'):
                method = result.get('method', '')
                if method.startswith('email'):
                    company.status = 'contact_info_found'
                    company.contact_method = method
                    company.error_message = None
                    if result.get('contact_info'):
                        contact_info_json = json.dumps(result['contact_info'])
                        company.contact_info = contact_info_json
                elif method.startswith('form_submitted'):
                    company.status = 'completed'
                    company.contact_method = method
                    company.error_message = None
                    company.fields_filled = result.get('fields_filled', 0)
                    
                    # Upload screenshot to Supabase if available
                    local_screenshot_path = result.get('screenshot_url')
                    if local_screenshot_path and os.path.exists(local_screenshot_path):
                        try:
                            from utils.supabase_storage import upload_screenshot
                            
                            # Read screenshot bytes
                            with open(local_screenshot_path, 'rb') as f:
                                screenshot_bytes = f.read()
                            
                            # Upload to Supabase
                            supabase_url = upload_screenshot(screenshot_bytes, campaign_id, company_id)
                            
                            if supabase_url:
                                company.screenshot_url = supabase_url
                                print(f"[Rapid Process] Screenshot uploaded to Supabase: {supabase_url}")
                            else:
                                # Fallback to local path
                                company.screenshot_url = local_screenshot_path
                                print(f"[Rapid Process] Screenshot upload failed, using local path")
                            
                            # Delete local file after upload
                            try:
                                os.remove(local_screenshot_path)
                            except:
                                pass
                        except Exception as e:
                            print(f"[Rapid Process] Error uploading screenshot: {e}")
                            company.screenshot_url = local_screenshot_path
                    else:
                        company.screenshot_url = local_screenshot_path
                else:
                    company.status = 'completed'
                    company.contact_method = result['method']
                    company.error_message = None
            else:
                if 'captcha' in result.get('error', '').lower() or result.get('method') == 'form_with_captcha':
                    company.status = 'captcha'
                    company.contact_method = 'form_with_captcha'
                    company.error_message = result.get('error', 'CAPTCHA detected')
                elif result.get('method') == 'form_in_iframe':
                    company.status = 'captcha'  # Treat as needs review
                    company.contact_method = 'form_in_iframe'
                    company.error_message = result.get('error', 'Form in iframe')
                elif result.get('method') == 'contact_page_only':
                    company.status = 'contact_info_found'
                    company.contact_method = 'contact_page_only'
                    company.error_message = result.get('error')
                else:
                    company.status = 'failed'
                    company.error_message = result.get('error', 'Processing failed')
                    company.detection_method = result.get('method', 'unknown')
            
            db.session.commit()
            
            return jsonify({
                'success': result.get('success', False),
                'status': company.status,
                'method': result.get('method'),
                'contactMethod': company.contact_method,
                'errorMessage': company.error_message,
                'contactInfo': result.get('contact_info'),
                'fieldsFilled': result.get('fields_filled'),
                'screenshotUrl': result.get('screenshot_url'),
                'processingTime': time.time() - start_time
            }), 200
            
        except subprocess.TimeoutExpired:
            print(f"[Rapid Process] Timeout processing company {company_id}")
            company.status = 'failed'
            company.error_message = 'Processing timeout after 60 seconds'
            db.session.commit()
            
            return jsonify({
                'success': False,
                'status': 'failed',
                'error': 'Processing timeout',
                'processingTime': time.time() - start_time
            }), 200
            
        except Exception as e:
            print(f"[Rapid Process] Error processing company {company_id}: {e}")
            import traceback
            traceback.print_exc()
            
            company.status = 'failed'
            company.error_message = str(e)
            db.session.commit()
            
            return jsonify({
                'success': False,
                'status': 'failed',
                'error': str(e),
                'processingTime': time.time() - start_time
            }), 200
            
    except Exception as e:
        print(f"[Rapid Process] Error in rapid_process_single: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@campaigns_api.route('/<int:campaign_id>/rapid-process-batch', methods=['POST'])
def rapid_process_batch(campaign_id):
    """
    REVAMPED: Fast campaign processing using fast-contact-analyzer logic
    - Stops after finding ONE contact method per site (optimized)
    - Submits forms when found
    - Sends emails when no form but email found
    Based on scripts/fast-contact-analyzer.js strategy
    """
    try:
        from models import Company, Campaign
        from database import db
        from services.fast_campaign_processor import FastCampaignProcessor
        from playwright.sync_api import sync_playwright
        import time
        
        data = request.get_json()
        company_ids = data.get('company_ids', [])
        
        if not company_ids:
            return jsonify({'error': 'No company IDs provided'}), 400
        
        campaign = Campaign.query.get(campaign_id)
        if not campaign:
            return jsonify({'error': 'Campaign not found'}), 404
        
        # Fetch all companies
        companies = Company.query.filter(
            Company.id.in_(company_ids),
            Company.campaign_id == campaign_id
        ).all()
        
        if not companies:
            return jsonify({'error': 'No companies found'}), 404
        
        # Verify all companies have the same website URL
        website_url = companies[0].website_url
        if not all(c.website_url == website_url for c in companies):
            return jsonify({'error': 'All companies must have same URL for batch processing'}), 400
        
        # Mark all as processing
        for company in companies:
            company.status = 'processing'
        db.session.commit()
        
        start_time = time.time()
        results = []
        
        try:
            # Create logger function
            def logger(level, action, message):
                print(f"[{level}] {action}: {message}")
            
            # Parse message_template if it's a JSON string
            import json
            import subprocess
            from datetime import datetime
            import os
            
            message_template_str = campaign.message_template
            subject_str = 'Partnership Inquiry'
            
            try:
                if isinstance(campaign.message_template, str):
                    message_template_parsed = json.loads(campaign.message_template)
                    if isinstance(message_template_parsed, dict):
                        message_template_str = message_template_parsed.get('message', campaign.message_template)
                        subject_str = message_template_parsed.get('subject', 'Partnership Inquiry')
            except:
                pass

            # Get script path
            backend_dir = os.path.dirname(os.path.abspath(__file__))
            project_root = os.path.dirname(os.path.dirname(backend_dir))
            possible_paths = [
                os.path.join(project_root, 'Scripts', 'rapid-process-single.js'),
                os.path.join(project_root, 'scripts', 'rapid-process-single.js'),
            ]
            script_path = next((p for p in possible_paths if os.path.exists(p)), None)
            if not script_path:
                raise Exception("Node.js script not found")
            
            # Process each company in the batch
            for idx, company in enumerate(companies):
                try:
                    logger('info', f'Batch Processing [{idx+1}/{len(companies)}]', f'Processing {company.company_name}')
                    
                    args = [
                        'node', script_path,
                        company.website_url,
                        company.company_name or 'Company',
                        message_template_str,
                        company.contact_email or 'contact@business.com',
                        company.phone or '',
                        company.contact_person or 'Business Contact',
                        subject_str,
                        campaign.message_template if isinstance(campaign.message_template, str) else json.dumps(campaign.message_template)
                    ]
                    
                    process_result = subprocess.run(
                        args, capture_output=True, text=True, timeout=90, cwd=project_root
                    )
                    
                    # Parse result
                    try:
                        stdout = process_result.stdout.strip()
                        import re
                        json_match = re.search(r'\{[\s\S]*\}', stdout)
                        result = json.loads(json_match.group()) if json_match else {'success': False, 'error': 'No JSON output'}
                    except:
                        result = {'success': False, 'error': f'Script error: {process_result.stderr[:100]}'}

                    # Update company
                    if result.get('success'):
                        if result.get('method') == 'email_found':
                            company.status = 'contact_info_found'
                            company.contact_method = 'email_found'
                            if result.get('contact_info'):
                                company.contact_info = json.dumps(result['contact_info'])
                        else:
                            company.status = 'completed'
                            company.contact_method = result.get('method', 'form_submitted')
                            company.fields_filled = result.get('fields_filled', 0)
                    else:
                        error_msg = result.get('error', '').lower()
                        if 'captcha' in error_msg or result.get('method') in ['form_with_captcha', 'form_in_iframe']:
                            company.status = 'captcha'
                            company.contact_method = result.get('method', 'form_with_captcha')
                        else:
                            company.status = 'failed'
                        company.error_message = result.get('error', 'Processing failed')
                    
                    # Screenshot upload
                    local_path = result.get('screenshot_url')
                    if local_path:
                        full_path = os.path.join(project_root, local_path) if not os.path.isabs(local_path) else local_path
                        if os.path.exists(full_path):
                            try:
                                from utils.supabase_storage import upload_screenshot
                                with open(full_path, 'rb') as f:
                                    sb = upload_screenshot(f.read(), campaign_id, company.id)
                                if sb:
                                    company.screenshot_url = sb
                                    os.remove(full_path)
                                else:
                                    company.screenshot_url = local_path
                            except:
                                company.screenshot_url = local_path
                    
                    company.processed_at = datetime.utcnow()
                    db.session.commit()
                    
                    results.append({
                        'companyId': company.id,
                        'status': company.status,
                        'screenshotUrl': company.screenshot_url,
                        'errorMessage': company.error_message
                    })
                except Exception as e:
                    logger('error', 'Batch Company Error', str(e))
                    company.status = 'failed'
                    company.error_message = str(e)
                    db.session.commit()

            # Final response
            processing_time = time.time() - start_time
            from sqlalchemy import or_
            campaign.processed_count = Company.query.filter_by(campaign_id=campaign_id).filter(Company.status != 'pending').count()
            campaign.success_count = Company.query.filter_by(campaign_id=campaign_id).filter(or_(Company.status == 'completed', Company.status == 'contact_info_found')).count()
            campaign.failed_count = Company.query.filter_by(campaign_id=campaign_id, status='failed').count()
            campaign.progress_percentage = int((campaign.processed_count / campaign.total_companies) * 100) if campaign.total_companies > 0 else 0
            db.session.commit()
            
            return jsonify({
                'success': True,
                'companiesProcessed': len(companies),
                'processingTime': round(processing_time, 2),
                'results': results
            }), 200

        except Exception as e:
            logger('error', 'Batch Loop Error', str(e))
            return jsonify({'success': False, 'error': str(e)}), 500
    except Exception as e:
        print(f"Outer Batch Error: {e}")
        return jsonify({'error': str(e)}), 500
