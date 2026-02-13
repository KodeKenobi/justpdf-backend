"""
Admin automated ad service management routes
"""
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from database import db
from models import User
from automated_ad_service import start_ad_service, stop_ad_service, get_ad_service_status, reset_ad_stats, trigger_manual_ad_view

ad_service_admin_api = Blueprint('ad_service_admin_api', __name__)

@ad_service_admin_api.route('/ad-service/start', methods=['POST'])
@jwt_required()
def start_ad_service_endpoint():
    """Start the automated ad view service"""
    try:
        current_user_id = get_jwt_identity()

        # Check if user is admin
        user = User.query.get(current_user_id)
        if not user or user.role not in ['admin', 'super_admin']:
            return jsonify({'error': 'Admin access required'}), 403

        success, message = start_ad_service()

        return jsonify({
            'success': success,
            'message': message
        })

    except Exception as e:
        print(f"[ADMIN AD SERVICE] Error starting ad service: {e}")
        return jsonify({'error': 'Failed to start ad service'}), 500

@ad_service_admin_api.route('/ad-service/stop', methods=['POST'])
@jwt_required()
def stop_ad_service_endpoint():
    """Stop the automated ad view service"""
    try:
        current_user_id = get_jwt_identity()

        # Check if user is admin
        user = User.query.get(current_user_id)
        if not user or user.role not in ['admin', 'super_admin']:
            return jsonify({'error': 'Admin access required'}), 403

        success, message = stop_ad_service()

        return jsonify({
            'success': success,
            'message': message
        })

    except Exception as e:
        print(f"[ADMIN AD SERVICE] Error stopping ad service: {e}")
        return jsonify({'error': 'Failed to stop ad service'}), 500

@ad_service_admin_api.route('/ad-service/status', methods=['GET'])
@jwt_required()
def get_ad_service_status_endpoint():
    """Get automated ad service status"""
    try:
        current_user_id = get_jwt_identity()

        # Check if user is admin
        user = User.query.get(current_user_id)
        if not user or user.role not in ['admin', 'super_admin']:
            return jsonify({'error': 'Admin access required'}), 403

        status = get_ad_service_status()

        return jsonify({
            'success': True,
            'status': status
        })

    except Exception as e:
        print(f"[ADMIN AD SERVICE] Error getting ad service status: {e}")
        return jsonify({'error': 'Failed to get ad service status'}), 500

@ad_service_admin_api.route('/ad-service/reset', methods=['POST'])
@jwt_required()
def reset_ad_stats_endpoint():
    """Reset ad view statistics"""
    try:
        current_user_id = get_jwt_identity()

        # Check if user is admin
        user = User.query.get(current_user_id)
        if not user or user.role not in ['admin', 'super_admin']:
            return jsonify({'error': 'Admin access required'}), 403

        success, message = reset_ad_stats()

        return jsonify({
            'success': success,
            'message': message
        })

    except Exception as e:
        print(f"[ADMIN AD SERVICE] Error resetting ad stats: {e}")
        return jsonify({'error': 'Failed to reset ad statistics'}), 500

@ad_service_admin_api.route('/ad-service/trigger-click', methods=['POST'])
@jwt_required()
def trigger_click_endpoint():
    """Trigger a single ad click manually"""
    try:
        current_user_id = get_jwt_identity()

        # Check if user is admin
        user = User.query.get(current_user_id)
        if not user or user.role not in ['admin', 'super_admin']:
            return jsonify({'error': 'Admin access required'}), 403

        success, message = trigger_manual_ad_view()

        return jsonify({
            'success': success,
            'message': message
        })

    except Exception as e:
        print(f"[ADMIN AD SERVICE] Error triggering ad click: {e}")
        return jsonify({'error': 'Failed to trigger ad click'}), 500