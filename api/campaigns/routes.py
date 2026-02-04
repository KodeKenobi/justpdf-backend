from flask import Blueprint, request, jsonify
import os
from sqlalchemy import desc, or_, func
from datetime import datetime, timedelta
from flask_jwt_extended import jwt_required, get_jwt_identity
import threading

# Add project root for path resolution
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))

# Create Blueprint - All endpoints are public, no authentication required
campaigns_api = Blueprint('campaigns_api', __name__, url_prefix='/api/campaigns')

# Per-campaign company limits by subscription tier
CAMPAIGN_LIMITS = {
    'guest': 5,        # Anonymous users
    'free': 50,        # Signed up free users
    'testing': 50,     # Testing tier (same as free)
    'premium': 100,    # Production ($9/mo)
    'enterprise': -1,  # Unlimited ($19/mo)
    'client': -1,      # Unlimited (client tier)
}

# Daily processed-company limits by tier (companies processed per day)
DAILY_LIMITS = {
    'guest': 5,
    'free': 50,
    'testing': 50,
    'premium': 100,
    'enterprise': -1,
    'client': -1,
}

def get_campaign_limit(user_tier=None):
    """Get campaign company limit for a given user tier"""
    if not user_tier or user_tier not in CAMPAIGN_LIMITS:
        return CAMPAIGN_LIMITS['guest']
    limit = CAMPAIGN_LIMITS[user_tier]
    return float('inf') if limit == -1 else limit

def get_daily_limit(user_tier=None):
    """Get daily processed-company limit for a given user tier"""
    if not user_tier or user_tier not in DAILY_LIMITS:
        return DAILY_LIMITS['guest']
    limit = DAILY_LIMITS[user_tier]
    return float('inf') if limit == -1 else limit

def get_daily_used(user_id=None, session_id=None):
    """Count companies processed today (status != pending, processed_at or created_at today UTC) for this user or guest session."""
    from models import Company, Campaign
    start_of_today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    q = Company.query.join(Campaign).filter(Company.status != 'pending')
    if user_id is not None:
        q = q.filter(Campaign.user_id == user_id)
    else:
        if not session_id:
            return 0
        q = q.filter(Campaign.session_id == session_id, Campaign.user_id.is_(None))
    # Processed today: processed_at >= start_of_today, or no processed_at and created_at >= start_of_today
    q = q.filter(
        or_(
            Company.processed_at >= start_of_today,
            (Company.processed_at.is_(None)) & (Company.created_at >= start_of_today)
        )
    )
    return q.count()

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

@campaigns_api.route('/usage', methods=['GET'])
@jwt_required(optional=True)
def get_usage():
    """Return daily usage for UI: daily_limit, daily_used, daily_remaining. Guest: pass session_id in query."""
    try:
        from models import User
        current_user_id = get_jwt_identity()
        session_id = request.args.get('session_id')
        if current_user_id:
            user = User.query.get(current_user_id)
            tier = (user.subscription_tier or 'free') if user else 'guest'
            daily_limit = get_daily_limit(tier)
            daily_used = get_daily_used(user_id=current_user_id, session_id=None)
        else:
            if not session_id:
                return jsonify({
                    'success': True,
                    'daily_limit': DAILY_LIMITS['guest'],
                    'daily_used': 0,
                    'daily_remaining': DAILY_LIMITS['guest'],
                    'unlimited': False,
                }), 200
            daily_limit = get_daily_limit('guest')
            daily_used = get_daily_used(user_id=None, session_id=session_id)
        unlimited = daily_limit == float('inf')
        daily_remaining = 0 if unlimited else max(0, int(daily_limit) - daily_used)
        return jsonify({
            'success': True,
            'daily_limit': -1 if unlimited else int(daily_limit),
            'daily_used': daily_used,
            'daily_remaining': None if unlimited else daily_remaining,
            'unlimited': unlimited,
        }), 200
    except Exception as e:
        print(f"Error fetching usage: {e}")
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

        # Daily limit: enforce before creating
        tier = 'guest'
        if current_user_id:
            from models import User
            user = User.query.get(current_user_id)
            if user:
                tier = user.subscription_tier or 'free'
        daily_limit = get_daily_limit(tier)
        daily_used = get_daily_used(user_id=current_user_id, session_id=session_id if not current_user_id else None)
        if daily_limit != float('inf') and daily_used + len(companies_data) > daily_limit:
            return jsonify({
                'error': 'Daily limit reached',
                'message': f'You can process {int(daily_limit)} companies per day. You have used {daily_used} today. Resets at midnight UTC.',
                'daily_used': daily_used,
                'daily_limit': int(daily_limit),
                'daily_remaining': max(0, int(daily_limit) - daily_used),
            }), 403
        
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

        # Daily limit check (single company)
        from models import User
        tier = 'guest'
        if campaign.user_id:
            user = User.query.get(campaign.user_id)
            if user:
                tier = user.subscription_tier or 'free'
        daily_limit = get_daily_limit(tier)
        daily_used = get_daily_used(user_id=campaign.user_id, session_id=campaign.session_id)
        if daily_limit != float('inf') and daily_used >= daily_limit:
            return jsonify({
                'error': 'Daily limit reached',
                'message': f'You can process {int(daily_limit)} companies per day. Resets at midnight UTC.',
                'daily_used': daily_used,
                'daily_limit': int(daily_limit),
            }), 403
        
        # Mark as processing
        company.status = 'processing'
        db.session.commit()
        
        start_time = time.time()
        
        try:
            # Parse message_template
            message_template_str = campaign.message_template
            subject_str = 'Partnership Inquiry'
            sender_data = {}
            
            try:
                if isinstance(campaign.message_template, str) and (campaign.message_template.strip().startswith('{') or campaign.message_template.strip().startswith('[')):
                    message_template_parsed = json.loads(campaign.message_template)
                    if isinstance(message_template_parsed, dict):
                        message_template_str = message_template_parsed.get('message', campaign.message_template)
                        subject_str = message_template_parsed.get('subject', 'Partnership Inquiry')
                        sender_data = message_template_parsed
            except Exception:
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
                        subject=subject_str,
                        sender_data=sender_data
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
                    if local_screenshot_path:
                        # Ensure we have the full path for local file operations
                        full_path = os.path.join(project_root, local_screenshot_path) if not os.path.isabs(local_screenshot_path) else local_screenshot_path
                        
                        if os.path.exists(full_path):
                            try:
                                from utils.supabase_storage import upload_screenshot
                                
                                # Read screenshot bytes
                                with open(full_path, 'rb') as f:
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
                                    os.remove(full_path)
                                except:
                                    pass
                            except Exception as e:
                                print(f"[Rapid Process] Error uploading screenshot: {e}")
                                company.screenshot_url = local_screenshot_path # Fallback
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
                elif result.get('method') == 'no_contact_found':
                    company.status = 'no_contact_found'
                    company.contact_method = 'no_contact_found'
                    company.error_message = 'No contact form found on this site.'
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
    Trigger asynchronous sequential campaign processing
    """
    try:
        from models import Campaign, Company, User
        from database import db
        from campaign_sequential import process_campaign_sequential  # no Celery/Redis
        
        data = request.get_json() or {}
        company_ids = data.get('company_ids')  # Optional: if None, processes all pending
        
        campaign = Campaign.query.get(campaign_id)
        if not campaign:
            return jsonify({'error': 'Campaign not found'}), 404

        # How many we're about to process
        if company_ids:
            to_process = Company.query.filter_by(campaign_id=campaign_id).filter(Company.id.in_(company_ids), Company.status == 'pending').count()
        else:
            to_process = Company.query.filter_by(campaign_id=campaign_id, status='pending').count()
        if to_process == 0:
            return jsonify({'success': True, 'message': 'No pending companies to process', 'campaign_id': campaign_id}), 200

        # Daily limit check
        tier = 'guest'
        if campaign.user_id:
            user = User.query.get(campaign.user_id)
            if user:
                tier = user.subscription_tier or 'free'
        daily_limit = get_daily_limit(tier)
        daily_used = get_daily_used(user_id=campaign.user_id, session_id=campaign.session_id)
        if daily_limit != float('inf') and daily_used + to_process > daily_limit:
            remaining = max(0, int(daily_limit) - daily_used)
            return jsonify({
                'error': 'Daily limit reached',
                'message': f'You can process {int(daily_limit)} companies per day. You have used {daily_used} today. Up to {remaining} remaining. Resets at midnight UTC.',
                'daily_used': daily_used,
                'daily_limit': int(daily_limit),
                'daily_remaining': remaining,
            }), 403
            
        # Trigger background processing via threading instead of Celery (Option 2)
        from flask import current_app
        # We need to capture the current app context to pass it to the thread
        app = current_app._get_current_object()
        
        def run_in_background(app_context, campaign_id, company_ids):
            with app_context.app_context():
                try:
                    process_campaign_sequential(campaign_id, company_ids)
                except Exception as e:
                    print(f"Background thread error: {e}")

        thread = threading.Thread(
            target=run_in_background,
            args=(app, campaign_id, company_ids)
        )
        thread.daemon = True
        thread.start()
        
        return jsonify({
            'success': True,
            'message': 'Sequential processing started in background thread',
            'campaign_id': campaign_id
        }), 202

    except Exception as e:
        print(f"Error triggering batch: {e}")
        return jsonify({'error': str(e)}), 500

@campaigns_api.route('/<int:campaign_id>/stop', methods=['POST'])
def stop_campaign(campaign_id):
    """
    Stop a running campaign
    """
    try:
        from models import Campaign
        from database import db
        
        campaign = Campaign.query.get(campaign_id)
        if not campaign:
            return jsonify({'error': 'Campaign not found'}), 404
            
        campaign.status = 'stopping'
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Campaign stopping requested'
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
