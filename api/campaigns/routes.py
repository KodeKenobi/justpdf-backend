from flask import Blueprint, request, jsonify, g
from sqlalchemy import desc, or_
from datetime import datetime
from functools import wraps

# Create Blueprint
campaigns_api = Blueprint('campaigns_api', __name__, url_prefix='/api/campaigns')

def require_auth(f):
    """Decorator to require authentication"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not hasattr(g, 'current_user') or not g.current_user:
            return jsonify({'error': 'Authentication required'}), 401
        return f(*args, **kwargs)
    return decorated_function

@campaigns_api.before_request
def load_user():
    """Set g.current_user from JWT token or email"""
    # Skip authentication for OPTIONS requests (CORS preflight)
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    
    # Try JWT authentication first
    try:
        from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity
        from models import User
        
        verify_jwt_in_request(optional=True)
        user_id = get_jwt_identity()
        if user_id:
            if isinstance(user_id, str):
                user_id = int(user_id)
            g.current_user = User.query.get(user_id)
            if g.current_user:
                return
    except Exception:
        pass
    
    # Fallback to email in request body/params
    email = request.args.get('email')
    if not email:
        try:
            json_data = request.get_json(silent=True)
            if json_data:
                email = json_data.get('email')
        except Exception:
            pass
    
    if email:
        from models import User
        g.current_user = User.query.filter_by(email=email).first()
        if g.current_user:
            return
    
    # If neither worked, create/get demo user for public access
    from models import User, db
    demo_email = 'demo@example.com'
    g.current_user = User.query.filter_by(email=demo_email).first()
    
    if not g.current_user:
        # Create demo user if it doesn't exist
        g.current_user = User(
            email=demo_email,
            name='Demo User',
            role='user',
            is_active=True
        )
        # Set a dummy password (won't be used for login)
        g.current_user.password = 'demo_user_no_login'
        db.session.add(g.current_user)
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            # If commit fails, try to get the user again (race condition)
            g.current_user = User.query.filter_by(email=demo_email).first()

@campaigns_api.route('', methods=['GET'])
def list_campaigns():
    """Get all campaigns (public endpoint - no auth required)"""
    try:
        from models import Campaign
        from database import db
        
        # Pagination
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        
        # Filters
        status = request.args.get('status')
        
        # Build query
        query = Campaign.query.filter_by(user_id=g.current_user.id)
        
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
def create_campaign():
    """Create a new campaign (public endpoint - no auth required)"""
    try:
        from models import Campaign, Company
        from database import db
        
        data = request.get_json()
        name = data.get('name')
        message_template = data.get('message_template')
        companies_data = data.get('companies', [])
        auto_detect_names = data.get('auto_detect_names', True)
        
        # Validate input
        if not name or not message_template:
            return jsonify({'error': 'Name and message template are required'}), 400
        
        if not companies_data or len(companies_data) == 0:
            return jsonify({'error': 'At least one company is required'}), 400
        
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
        
        # Create campaign
        campaign = Campaign(
            user_id=g.current_user.id,
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
        campaign.success_count = Company.query.filter_by(campaign_id=campaign.id, status='success').count()
        campaign.failed_count = Company.query.filter_by(campaign_id=campaign.id, status='failed').count()
        campaign.captcha_count = Company.query.filter_by(campaign_id=campaign.id, status='captcha').count()
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
