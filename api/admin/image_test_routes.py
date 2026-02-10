from flask import Blueprint, jsonify, request
from api.admin.routes import require_admin
from automated_image_test_service import image_test_service

image_test_admin_api = Blueprint('image_test_admin_api', __name__)

@image_test_admin_api.route('/status', methods=['GET'])
@require_admin
def get_status():
    """Get the current status of the automated image test service"""
    return jsonify({
        "is_running": image_test_service.is_running,
        "stats": image_test_service.stats
    })

@image_test_admin_api.route('/start', methods=['POST'])
@require_admin
def start_service():
    """Start the automated image test service"""
    image_test_service.start()
    return jsonify({"message": "Service started", "is_running": True})

@image_test_admin_api.route('/stop', methods=['POST'])
@require_admin
def stop_service():
    """Stop the automated image test service"""
    image_test_service.stop()
    return jsonify({"message": "Service stopped", "is_running": False})

@image_test_admin_api.route('/test-now', methods=['POST'])
@require_admin
def test_now():
    """Force an immediate test run"""
    success = image_test_service.perform_test()
    return jsonify({
        "message": "Manual test completed",
        "success": success,
        "stats": image_test_service.stats
    })

@image_test_admin_api.route('/reset-stats', methods=['POST'])
@require_admin
def reset_stats():
    """Reset the service statistics"""
    image_test_service.stats = {
        "total_tests": 0,
        "failures": 0,
        "last_run": None,
        "next_run": image_test_service.stats.get("next_run"),
        "history": []
    }
    return jsonify({"message": "Stats reset", "stats": image_test_service.stats})
