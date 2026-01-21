from flask import Blueprint, request, jsonify
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
        
        # Update allowed fields
        if 'name' in data:
            campaign.name = data['name']
        if 'message_template' in data:
            campaign.message_template = data['message_template']
        if 'status' in data:
            allowed_statuses = ['draft', 'queued', 'processing', 'completed', 'paused', 'failed']
            if data['status'] in allowed_statuses:
                campaign.status = data['status']
        
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

@campaigns_api.route('/<int:campaign_id>/start', methods=['POST'])
def start_campaign(campaign_id):
    """Start processing a campaign"""
    try:
        from models import Campaign, Company
        from database import db
        
        campaign = Campaign.query.get(campaign_id)
        
        if not campaign:
            return jsonify({'error': 'Campaign not found'}), 404
        
        # Check if campaign can be started
        if campaign.status not in ['draft', 'paused']:
            return jsonify({'error': f'Campaign cannot be started from {campaign.status} status'}), 400
        
        # Update campaign status
        campaign.status = 'queued'
        campaign.started_at = datetime.utcnow()
        db.session.commit()
        
        # Queue companies for processing (this will be handled by the scraper service)
        # For now, we just mark the campaign as queued
        
        return jsonify({
            'success': True,
            'message': 'Campaign started successfully',
            'campaign': campaign.to_dict()
        }), 200
        
    except Exception as e:
        print(f"Error starting campaign: {e}")
        import traceback
        traceback.print_exc()
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@campaigns_api.route('/<int:campaign_id>/companies', methods=['GET'])
def get_campaign_companies(campaign_id):
    """Get all companies in a campaign"""
    try:
        from models import Campaign, Company
        
        campaign = Campaign.query.get(campaign_id)
        
        if not campaign:
            return jsonify({'error': 'Campaign not found'}), 404
        
        # Pagination
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 50, type=int)
        
        # Filters
        status = request.args.get('status')
        
        # Build query
        query = Company.query.filter_by(campaign_id=campaign_id)
        
        if status:
            query = query.filter_by(status=status)
        
        # Order by creation date
        query = query.order_by(Company.created_at)
        
        # Paginate
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        companies = pagination.items
        
        return jsonify({
            'success': True,
            'companies': [company.to_dict() for company in companies],
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': pagination.total,
                'pages': pagination.pages
            }
        }), 200
        
    except Exception as e:
        print(f"Error fetching companies: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@campaigns_api.route('/companies/<int:company_id>/logs', methods=['GET'])
def get_company_logs(company_id):
    """Get submission logs for a specific company"""
    try:
        from models import Company, SubmissionLog
        
        company = Company.query.get(company_id)
        
        if not company:
            return jsonify({'error': 'Company not found'}), 404
        
        logs = SubmissionLog.query.filter_by(company_id=company_id).order_by(SubmissionLog.created_at).all()
        
        return jsonify({
            'success': True,
            'company': company.to_dict(),
            'logs': [log.to_dict() for log in logs]
        }), 200
        
    except Exception as e:
        print(f"Error fetching logs: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@campaigns_api.route('/companies/<int:company_id>', methods=['PATCH'])
def update_company(company_id):
    """Update a company (used by worker)"""
    try:
        from models import Company
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
        campaign.success_count = Company.query.filter_by(campaign_id=campaign.id, status='completed').count()
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
def rapid_process_company(campaign_id, company_id):
    """Process a single company quickly without WebSocket overhead (headless mode)"""
    try:
        from models import Company, Campaign
        from database import db
        from services.live_scraper import LiveScraper
        import time
        import asyncio
        
        company = Company.query.filter_by(
            id=company_id,
            campaign_id=campaign_id
        ).first()
        
        if not company:
            return jsonify({'error': 'Company not found'}), 404
        
        campaign = Campaign.query.get(campaign_id)
        if not campaign:
            return jsonify({'error': 'Campaign not found'}), 404
        
        # Mark as processing
        company.status = 'processing'
        db.session.commit()
        
        start_time = time.time()
        
        try:
            # Prepare company data
            company_data = {
                'id': company.id,
                'website_url': company.website_url,
                'company_name': company.company_name,
                'contact_email': company.contact_email,
                'phone': company.phone,
            }

            # Create scraper WITHOUT WebSocket (headless mode)
            scraper = LiveScraper(None, company_data, campaign.message_template, campaign_id, company_id)

            # Run scraper SYNCHRONOUSLY (no event loop issues with parallel processing)
            result = scraper.scrape_and_submit_sync()
            
            processing_time = time.time() - start_time
            
            # Update company based on result
            if result.get('success'):
                company.status = 'completed'
                company.error_message = None
            else:
                # Check if it's a CAPTCHA error
                error_msg = result.get('error', '').lower()
                if 'captcha' in error_msg or 'recaptcha' in error_msg or 'hcaptcha' in error_msg:
                    company.status = 'captcha'
                    company.error_message = 'CAPTCHA detected'
                else:
                    company.status = 'failed'
                    company.error_message = result.get('error', 'Processing failed')
            
            # Save screenshot URL if available
            if result.get('screenshot_url'):
                company.screenshot_url = result.get('screenshot_url')
            
            db.session.commit()
            
            # Update campaign stats
            campaign.processed_count = Company.query.filter_by(campaign_id=campaign.id).filter(Company.status != 'pending').count()
            campaign.success_count = Company.query.filter_by(campaign_id=campaign.id, status='completed').count()
            campaign.failed_count = Company.query.filter_by(campaign_id=campaign.id, status='failed').count()
            campaign.captcha_count = Company.query.filter_by(campaign_id=campaign.id, status='captcha').count()
            
            if campaign.total_companies > 0:
                campaign.progress_percentage = int((campaign.processed_count / campaign.total_companies) * 100)
            
            db.session.commit()
            
            return jsonify({
                'success': result.get('success', False),
                'status': company.status,
                'companyId': company_id,
                'screenshotUrl': company.screenshot_url,
                'errorMessage': company.error_message,
                'processingTime': round(processing_time, 2),
                'company': company.to_dict()
            }), 200
            
        except Exception as e:
            # Processing error - mark as failed
            company.status = 'failed'
            company.error_message = str(e)
            db.session.commit()
            
            return jsonify({
                'success': False,
                'status': 'failed',
                'companyId': company_id,
                'errorMessage': str(e),
                'processingTime': time.time() - start_time
            }), 200
        
    except Exception as e:
        print(f"Error in rapid_process_company: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@campaigns_api.route('/my-campaigns', methods=['GET'])
@jwt_required()
def get_user_campaigns():
    """Get campaigns for the authenticated user"""
    try:
        from models import Campaign
        from database import db
        
        current_user_id = get_jwt_identity()
        
        # Pagination
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        
        # Get user's campaigns
        query = Campaign.query.filter_by(user_id=current_user_id).order_by(desc(Campaign.created_at))
        
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
        print(f"Error fetching user campaigns: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@campaigns_api.route('/stats', methods=['GET'])
@jwt_required()
def get_campaign_stats():
    """Get campaign statistics for the authenticated user"""
    try:
        from models import Campaign, Company
        from database import db
        
        current_user_id = get_jwt_identity()
        
        # Total campaigns for user
        total_campaigns = Campaign.query.filter_by(user_id=current_user_id).count()
        
        # Active campaigns
        active_campaigns = Campaign.query.filter_by(
            user_id=current_user_id,
            status='processing'
        ).count()
        
        # Calculate today's processed companies
        today = datetime.utcnow().date()
        processed_today = db.session.query(func.count(Company.id)).join(Campaign).filter(
            Campaign.user_id == current_user_id,
            func.date(Company.processed_at) == today
        ).scalar() or 0
        
        # Success rate calculation
        user_campaigns = Campaign.query.filter_by(user_id=current_user_id).all()
        total_processed = sum(c.processed_count for c in user_campaigns)
        total_success = sum(c.success_count for c in user_campaigns)
        success_rate = round((total_success / total_processed * 100) if total_processed > 0 else 0, 1)
        
        return jsonify({
            'success': True,
            'stats': {
                'total': total_campaigns,
                'active': active_campaigns,
                'processedToday': processed_today,
                'successRate': success_rate,
                'totalProcessed': total_processed,
                'totalSuccess': total_success
            }
        }), 200
        
    except Exception as e:
        print(f"Error fetching campaign stats: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@campaigns_api.route('/admin/all', methods=['GET'])
@jwt_required()
def get_all_campaigns_admin():
    """Get all campaigns across all users (admin only)"""
    try:
        from models import Campaign, User
        from database import db
        
        # TODO: Add admin role check here
        # For now, allow any authenticated user (should verify admin role)
        
        # Pagination
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 50, type=int)
        
        # Filters
        status = request.args.get('status')
        user_id = request.args.get('user_id', type=int)
        
        # Build query
        query = Campaign.query
        
        if status:
            query = query.filter_by(status=status)
        if user_id:
            query = query.filter_by(user_id=user_id)
        
        # Order by most recent
        query = query.order_by(desc(Campaign.created_at))
        
        # Paginate
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        campaigns = pagination.items
        
        # Enrich with user info
        campaigns_data = []
        for campaign in campaigns:
            campaign_dict = campaign.to_dict()
            if campaign.user_id:
                user = User.query.get(campaign.user_id)
                if user:
                    campaign_dict['user_email'] = user.email
                    campaign_dict['user_tier'] = user.subscription_tier
            campaigns_data.append(campaign_dict)
        
        return jsonify({
            'success': True,
            'campaigns': campaigns_data,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': pagination.total,
                'pages': pagination.pages
            }
        }), 200
        
    except Exception as e:
        print(f"Error fetching all campaigns (admin): {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@campaigns_api.route('/admin/stats', methods=['GET'])
@jwt_required()
def get_admin_campaign_stats():
    """Get comprehensive campaign statistics for admin"""
    try:
        from models import Campaign, Company, User
        from database import db
        
        # TODO: Add admin role check
        
        # Total campaigns across all users
        total_campaigns = Campaign.query.count()
        
        # Campaigns by status
        active_campaigns = Campaign.query.filter_by(status='processing').count()
        completed_campaigns = Campaign.query.filter_by(status='completed').count()
        failed_campaigns = Campaign.query.filter_by(status='failed').count()
        draft_campaigns = Campaign.query.filter_by(status='draft').count()
        
        # Today's activity
        today = datetime.utcnow().date()
        campaigns_today = Campaign.query.filter(
            func.date(Campaign.created_at) == today
        ).count()
        
        processed_today = db.session.query(func.count(Company.id)).filter(
            func.date(Company.processed_at) == today
        ).scalar() or 0
        
        # Campaigns by user tier
        campaigns_by_tier = db.session.query(
            User.subscription_tier,
            func.count(Campaign.id)
        ).join(Campaign, Campaign.user_id == User.id).group_by(User.subscription_tier).all()
        
        tier_breakdown = {tier: count for tier, count in campaigns_by_tier}
        
        # Guest campaigns (no user)
        guest_campaigns = Campaign.query.filter_by(user_id=None).count()
        tier_breakdown['guest'] = guest_campaigns
        
        # Overall success rate
        all_campaigns = Campaign.query.all()
        total_processed = sum(c.processed_count for c in all_campaigns)
        total_success = sum(c.success_count for c in all_campaigns)
        success_rate = round((total_success / total_processed * 100) if total_processed > 0 else 0, 1)
        
        # Top users by campaign count
        top_users = db.session.query(
            User.email,
            User.subscription_tier,
            func.count(Campaign.id).label('campaign_count')
        ).join(Campaign, Campaign.user_id == User.id).group_by(User.id, User.email, User.subscription_tier).order_by(desc('campaign_count')).limit(10).all()
        
        top_users_data = [
            {
                'email': email,
                'tier': tier,
                'campaign_count': count
            }
            for email, tier, count in top_users
        ]
        
        return jsonify({
            'success': True,
            'stats': {
                'total': total_campaigns,
                'active': active_campaigns,
                'completed': completed_campaigns,
                'failed': failed_campaigns,
                'draft': draft_campaigns,
                'createdToday': campaigns_today,
                'processedToday': processed_today,
                'successRate': success_rate,
                'totalProcessed': total_processed,
                'totalSuccess': total_success,
                'byTier': tier_breakdown,
                'topUsers': top_users_data
            }
        }), 200
        
    except Exception as e:
        print(f"Error fetching admin campaign stats: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@campaigns_api.route('/admin/<int:campaign_id>/pause', methods=['POST'])
@jwt_required()
def admin_pause_campaign(campaign_id):
    """Pause a campaign (admin action)"""
    try:
        from models import Campaign
        from database import db
        
        # TODO: Add admin role check
        
        campaign = Campaign.query.get(campaign_id)
        if not campaign:
            return jsonify({'error': 'Campaign not found'}), 404
        
        campaign.status = 'paused'
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Campaign paused successfully',
            'campaign': campaign.to_dict()
        }), 200
        
    except Exception as e:
        print(f"Error pausing campaign: {e}")
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@campaigns_api.route('/admin/<int:campaign_id>/resume', methods=['POST'])
@jwt_required()
def admin_resume_campaign(campaign_id):
    """Resume a paused campaign (admin action)"""
    try:
        from models import Campaign
        from database import db
        
        # TODO: Add admin role check
        
        campaign = Campaign.query.get(campaign_id)
        if not campaign:
            return jsonify({'error': 'Campaign not found'}), 404
        
        if campaign.status == 'paused':
            campaign.status = 'queued'
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Campaign resumed successfully',
            'campaign': campaign.to_dict()
        }), 200
        
    except Exception as e:
        print(f"Error resuming campaign: {e}")
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@campaigns_api.route('/admin/<int:campaign_id>/cancel', methods=['POST'])
@jwt_required()
def admin_cancel_campaign(campaign_id):
    """Cancel a campaign (admin action)"""
    try:
        from models import Campaign
        from database import db
        
        # TODO: Add admin role check
        
        campaign = Campaign.query.get(campaign_id)
        if not campaign:
            return jsonify({'error': 'Campaign not found'}), 404
        
        campaign.status = 'failed'
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Campaign cancelled successfully',
            'campaign': campaign.to_dict()
        }), 200
        
    except Exception as e:
        print(f"Error cancelling campaign: {e}")
        db.session.rollback()
        return jsonify({'error': str(e)}), 500
