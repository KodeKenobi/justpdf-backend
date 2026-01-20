from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from models import User, db
from auth import jwt
import re
from datetime import datetime

enterprise_api = Blueprint('enterprise_api', __name__)

# Team member interface
class TeamMember:
    def __init__(self, id, email, is_active, created_at, last_login=None):
        self.id = id
        self.email = email
        self.is_active = is_active
        self.created_at = created_at
        self.last_login = last_login

    def to_dict(self):
        return {
            'id': self.id,
            'email': self.email,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if isinstance(self.created_at, datetime) else self.created_at,
            'last_login': self.last_login.isoformat() if isinstance(self.last_login, datetime) and self.last_login else None
        }

@enterprise_api.route('/api/enterprise/team', methods=['GET'])
@jwt_required()
def get_team_members():
    """Get team members for the current enterprise user"""
    try:
        current_user_id = get_jwt_identity()

        # Get current user
        current_user = User.query.get(current_user_id)
        if not current_user:
            return jsonify({'error': 'User not found'}), 404

        # Check if user is enterprise
        is_enterprise = (
            current_user.role == 'enterprise' or
            current_user.role == 'admin' or
            current_user.role == 'super_admin' or
            (current_user.subscription_tier and current_user.subscription_tier.lower() == 'enterprise') or
            (hasattr(current_user, 'monthly_call_limit') and current_user.monthly_call_limit == -1) or
            (hasattr(current_user, 'monthly_call_limit') and current_user.monthly_call_limit and current_user.monthly_call_limit >= 100000)
        )

        if not is_enterprise:
            return jsonify({'error': 'Enterprise access required'}), 403

        # For now, return empty array as team management isn't fully implemented yet
        # In a real implementation, you'd query a team_members table
        team_members = []

        return jsonify({'teamMembers': team_members})

    except Exception as e:
        print(f"Error fetching team members: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@enterprise_api.route('/api/enterprise/team', methods=['POST'])
@jwt_required()
def invite_team_member():
    """Invite a new team member"""
    try:
        current_user_id = get_jwt_identity()

        # Get current user
        current_user = User.query.get(current_user_id)
        if not current_user:
            return jsonify({'error': 'User not found'}), 404

        # Check if user is enterprise
        is_enterprise = (
            current_user.role == 'enterprise' or
            current_user.role == 'admin' or
            current_user.role == 'super_admin' or
            (current_user.subscription_tier and current_user.subscription_tier.lower() == 'enterprise') or
            (hasattr(current_user, 'monthly_call_limit') and current_user.monthly_call_limit == -1) or
            (hasattr(current_user, 'monthly_call_limit') and current_user.monthly_call_limit and current_user.monthly_call_limit >= 100000)
        )

        if not is_enterprise:
            return jsonify({'error': 'Enterprise access required'}), 403

        data = request.get_json()
        email = data.get('email')

        if not email or not isinstance(email, str):
            return jsonify({'error': 'Email is required'}), 400

        # Validate email format
        email_regex = r'^[^\s@]+@[^\s@]+\.[^\s@]+$'
        if not re.match(email_regex, email):
            return jsonify({'error': 'Invalid email format'}), 400

        # Check if email already exists as a user
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            return jsonify({'error': 'User with this email already exists'}), 400

        # TODO: Implement team invitation logic
        # For now, just return success message
        # In a real implementation, you'd:
        # 1. Create a team invitation record
        # 2. Send an email invitation
        # 3. Handle invitation acceptance

        return jsonify({
            'message': f'Team member invited successfully',
            'email': email
        })

    except Exception as e:
        print(f"Error inviting team member: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@enterprise_api.route('/api/enterprise/team/<int:member_id>', methods=['DELETE'])
@jwt_required()
def remove_team_member(member_id):
    """Remove a team member"""
    try:
        current_user_id = get_jwt_identity()

        # Get current user
        current_user = User.query.get(current_user_id)
        if not current_user:
            return jsonify({'error': 'User not found'}), 404

        # Check if user is enterprise
        is_enterprise = (
            current_user.role == 'enterprise' or
            current_user.role == 'admin' or
            current_user.role == 'super_admin' or
            (current_user.subscription_tier and current_user.subscription_tier.lower() == 'enterprise') or
            (hasattr(current_user, 'monthly_call_limit') and current_user.monthly_call_limit == -1) or
            (hasattr(current_user, 'monthly_call_limit') and current_user.monthly_call_limit and current_user.monthly_call_limit >= 100000)
        )

        if not is_enterprise:
            return jsonify({'error': 'Enterprise access required'}), 403

        # TODO: Implement team member removal logic
        # For now, just return success message
        # In a real implementation, you'd:
        # 1. Verify the team member belongs to this user's team
        # 2. Remove the team member from the team
        # 3. Optionally deactivate their account or change their role

        return jsonify({
            'message': 'Team member removed successfully'
        })

    except Exception as e:
        print(f"Error removing team member: {e}")
        return jsonify({'error': 'Internal server error'}), 500