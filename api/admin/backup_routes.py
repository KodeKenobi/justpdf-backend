"""
Admin backup management routes
"""
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from database import db
from models import User
from backup_service import backup_service, run_manual_backup

backup_admin_api = Blueprint('backup_admin_api', __name__)

@backup_admin_api.route('/backup/run', methods=['POST'])
@jwt_required()
def run_backup():
    """Manually trigger a database backup"""
    try:
        current_user_id = get_jwt_identity()

        # Check if user is admin
        user = User.query.get(current_user_id)
        if not user or user.role != 'admin':
            return jsonify({'error': 'Admin access required'}), 403

        # Run backup in background thread to avoid timeout
        import threading

        def run_backup_async():
            try:
                success, message = run_manual_backup()
                print(f"[ADMIN BACKUP] Manual backup {'succeeded' if success else 'failed'}: {message}")
            except Exception as e:
                print(f"[ADMIN BACKUP] Manual backup error: {e}")

        backup_thread = threading.Thread(target=run_backup_async, daemon=True)
        backup_thread.start()

        return jsonify({
            'success': True,
            'message': 'Backup started in background. Check logs for completion status.'
        })

    except Exception as e:
        print(f"[ADMIN BACKUP] Error starting manual backup: {e}")
        return jsonify({'error': 'Failed to start backup'}), 500

@backup_admin_api.route('/backup/status', methods=['GET'])
@jwt_required()
def get_backup_status():
    """Get backup service status"""
    try:
        current_user_id = get_jwt_identity()

        # Check if user is admin
        user = User.query.get(current_user_id)
        if not user or user.role != 'admin':
            return jsonify({'error': 'Admin access required'}), 403

        # Get backup files info
        import os
        from pathlib import Path

        backup_dir = Path("backups")
        if backup_dir.exists():
            backup_files = []
            for backup_file in backup_dir.glob("*.gz"):
                stat = backup_file.stat()
                backup_files.append({
                    'name': backup_file.name,
                    'size_mb': round(stat.st_size / (1024 * 1024), 2),
                    'created': stat.st_mtime,
                    'path': str(backup_file)
                })

            # Sort by creation time (newest first)
            backup_files.sort(key=lambda x: x['created'], reverse=True)
        else:
            backup_files = []

        return jsonify({
            'success': True,
            'backup_files': backup_files[:10],  # Last 10 backups
            'total_backups': len(backup_files),
            'backup_directory': str(backup_dir.absolute())
        })

    except Exception as e:
        print(f"[ADMIN BACKUP] Error getting backup status: {e}")
        return jsonify({'error': 'Failed to get backup status'}), 500