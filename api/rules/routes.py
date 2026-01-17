from flask import Blueprint, request, jsonify, g
from sqlalchemy import desc, or_
from datetime import datetime
from functools import wraps

# Create Blueprint
rules_api = Blueprint('rules_api', __name__, url_prefix='/api/rules')

def require_auth(f):
    """Decorator to require authentication"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not hasattr(g, 'current_user') or not g.current_user:
            return jsonify({'error': 'Authentication required'}), 401
        return f(*args, **kwargs)
    return decorated_function

def require_admin(f):
    """Decorator to require admin access"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not hasattr(g, 'current_user') or not g.current_user:
            return jsonify({'error': 'Authentication required'}), 401
        if not g.current_user.is_admin:
            return jsonify({'error': 'Admin access required'}), 403
        return f(*args, **kwargs)
    return decorated_function

@rules_api.before_request
def load_user():
    """Set g.current_user from JWT token or email"""
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    
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
    
    g.current_user = None

# Scraping Rules Management

@rules_api.route('', methods=['GET'])
@require_auth
def list_scraping_rules():
    """Get all scraping rules (global + user-specific)"""
    try:
        from models import ScrapingRule
        from database import db
        
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 50, type=int)
        rule_type = request.args.get('type')
        target_domain = request.args.get('domain')
        
        # Build query: global rules + user's own rules
        query = ScrapingRule.query.filter(
            or_(
                ScrapingRule.user_id == None,  # Global rules
                ScrapingRule.user_id == g.current_user.id  # User's rules
            )
        )
        
        if rule_type:
            query = query.filter_by(rule_type=rule_type)
        
        if target_domain:
            query = query.filter_by(target_domain=target_domain)
        
        query = query.filter_by(is_active=True).order_by(ScrapingRule.priority, ScrapingRule.created_at)
        
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        rules = pagination.items
        
        return jsonify({
            'success': True,
            'rules': [rule.to_dict() for rule in rules],
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': pagination.total,
                'pages': pagination.pages
            }
        }), 200
        
    except Exception as e:
        print(f"Error fetching scraping rules: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@rules_api.route('', methods=['POST'])
@require_auth
def create_scraping_rule():
    """Create a new scraping rule"""
    try:
        from models import ScrapingRule, WebsiteRule, FormRule
        from database import db
        
        data = request.get_json()
        name = data.get('name')
        rule_type = data.get('rule_type')
        
        if not name or not rule_type:
            return jsonify({'error': 'Name and rule_type are required'}), 400
        
        # Create scraping rule
        scraping_rule = ScrapingRule(
            user_id=g.current_user.id,
            name=name,
            description=data.get('description'),
            rule_type=rule_type,
            target_domain=data.get('target_domain'),
            priority=data.get('priority', 100),
            is_active=data.get('is_active', True)
        )
        db.session.add(scraping_rule)
        db.session.flush()
        
        # Add website rules
        website_rules = data.get('website_rules', [])
        for rule_data in website_rules:
            website_rule = WebsiteRule(
                scraping_rule_id=scraping_rule.id,
                rule_category=rule_data.get('rule_category'),
                rule_type=rule_data.get('rule_type'),
                selector=rule_data.get('selector'),
                text_pattern=rule_data.get('text_pattern'),
                url_pattern=rule_data.get('url_pattern'),
                action=rule_data.get('action'),
                action_value=rule_data.get('action_value'),
                language=rule_data.get('language'),
                order=rule_data.get('order', 1),
                is_active=rule_data.get('is_active', True)
            )
            db.session.add(website_rule)
        
        # Add form rules
        form_rules = data.get('form_rules', [])
        for rule_data in form_rules:
            form_rule = FormRule(
                scraping_rule_id=scraping_rule.id,
                field_name=rule_data.get('field_name'),
                rule_type=rule_data.get('rule_type'),
                selector=rule_data.get('selector'),
                pattern=rule_data.get('pattern'),
                value_source=rule_data.get('value_source'),
                static_value=rule_data.get('static_value'),
                order=rule_data.get('order', 1),
                is_active=rule_data.get('is_active', True)
            )
            db.session.add(form_rule)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Scraping rule created successfully',
            'rule': scraping_rule.to_dict()
        }), 201
        
    except Exception as e:
        print(f"Error creating scraping rule: {e}")
        import traceback
        traceback.print_exc()
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@rules_api.route('/<int:rule_id>', methods=['GET'])
@require_auth
def get_scraping_rule(rule_id):
    """Get a specific scraping rule with all sub-rules"""
    try:
        from models import ScrapingRule
        
        rule = ScrapingRule.query.get(rule_id)
        
        if not rule:
            return jsonify({'error': 'Rule not found'}), 404
        
        # Check access: global rules or user's own rules
        if rule.user_id and rule.user_id != g.current_user.id:
            return jsonify({'error': 'Unauthorized'}), 403
        
        # Include sub-rules
        rule_dict = rule.to_dict()
        rule_dict['website_rules'] = [wr.to_dict() for wr in rule.website_rules]
        rule_dict['form_rules'] = [fr.to_dict() for fr in rule.form_rules]
        
        return jsonify({
            'success': True,
            'rule': rule_dict
        }), 200
        
    except Exception as e:
        print(f"Error fetching scraping rule: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@rules_api.route('/<int:rule_id>', methods=['PATCH'])
@require_auth
def update_scraping_rule(rule_id):
    """Update a scraping rule"""
    try:
        from models import ScrapingRule
        from database import db
        
        rule = ScrapingRule.query.get(rule_id)
        
        if not rule:
            return jsonify({'error': 'Rule not found'}), 404
        
        # Check ownership
        if rule.user_id != g.current_user.id:
            return jsonify({'error': 'Unauthorized'}), 403
        
        data = request.get_json()
        
        # Update allowed fields
        if 'name' in data:
            rule.name = data['name']
        if 'description' in data:
            rule.description = data['description']
        if 'target_domain' in data:
            rule.target_domain = data['target_domain']
        if 'priority' in data:
            rule.priority = data['priority']
        if 'is_active' in data:
            rule.is_active = data['is_active']
        
        rule.updated_at = datetime.utcnow()
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Rule updated successfully',
            'rule': rule.to_dict()
        }), 200
        
    except Exception as e:
        print(f"Error updating scraping rule: {e}")
        import traceback
        traceback.print_exc()
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@rules_api.route('/<int:rule_id>', methods=['DELETE'])
@require_auth
def delete_scraping_rule(rule_id):
    """Delete a scraping rule"""
    try:
        from models import ScrapingRule
        from database import db
        
        rule = ScrapingRule.query.get(rule_id)
        
        if not rule:
            return jsonify({'error': 'Rule not found'}), 404
        
        # Check ownership
        if rule.user_id != g.current_user.id:
            return jsonify({'error': 'Unauthorized'}), 403
        
        db.session.delete(rule)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Rule deleted successfully'
        }), 200
        
    except Exception as e:
        print(f"Error deleting scraping rule: {e}")
        import traceback
        traceback.print_exc()
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

# Global Rules Management (Admin only)

@rules_api.route('/global', methods=['POST'])
@require_admin
def create_global_rule():
    """Create a global scraping rule (admin only)"""
    try:
        from models import ScrapingRule, WebsiteRule, FormRule
        from database import db
        
        data = request.get_json()
        name = data.get('name')
        rule_type = data.get('rule_type')
        
        if not name or not rule_type:
            return jsonify({'error': 'Name and rule_type are required'}), 400
        
        # Create global scraping rule (user_id = None)
        scraping_rule = ScrapingRule(
            user_id=None,  # Global rule
            name=name,
            description=data.get('description'),
            rule_type=rule_type,
            target_domain=data.get('target_domain'),
            priority=data.get('priority', 100),
            is_active=data.get('is_active', True)
        )
        db.session.add(scraping_rule)
        db.session.flush()
        
        # Add website rules
        website_rules = data.get('website_rules', [])
        for rule_data in website_rules:
            website_rule = WebsiteRule(
                scraping_rule_id=scraping_rule.id,
                rule_category=rule_data.get('rule_category'),
                rule_type=rule_data.get('rule_type'),
                selector=rule_data.get('selector'),
                text_pattern=rule_data.get('text_pattern'),
                url_pattern=rule_data.get('url_pattern'),
                action=rule_data.get('action'),
                action_value=rule_data.get('action_value'),
                language=rule_data.get('language'),
                order=rule_data.get('order', 1),
                is_active=rule_data.get('is_active', True)
            )
            db.session.add(website_rule)
        
        # Add form rules
        form_rules = data.get('form_rules', [])
        for rule_data in form_rules:
            form_rule = FormRule(
                scraping_rule_id=scraping_rule.id,
                field_name=rule_data.get('field_name'),
                rule_type=rule_data.get('rule_type'),
                selector=rule_data.get('selector'),
                pattern=rule_data.get('pattern'),
                value_source=rule_data.get('value_source'),
                static_value=rule_data.get('static_value'),
                order=rule_data.get('order', 1),
                is_active=rule_data.get('is_active', True)
            )
            db.session.add(form_rule)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Global scraping rule created successfully',
            'rule': scraping_rule.to_dict()
        }), 201
        
    except Exception as e:
        print(f"Error creating global scraping rule: {e}")
        import traceback
        traceback.print_exc()
        db.session.rollback()
        return jsonify({'error': str(e)}), 500
