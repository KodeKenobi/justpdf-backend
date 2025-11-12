"""
Payment webhook routes for handling subscription upgrades
"""
from flask import Blueprint, request, jsonify
from database import db
from models import User
from email_service import send_upgrade_email
from notification_service import create_subscription_notification

# Create Blueprint
payment_api = Blueprint('payment_api', __name__, url_prefix='/api/payment')

# Tier mapping from plan names/IDs to subscription tiers
TIER_MAPPING = {
    'production': 'premium',
    'premium': 'premium',
    'enterprise': 'enterprise',
    'testing': 'free',
    'free': 'free'
}

# Tier limits mapping
TIER_LIMITS = {
    'free': 5,
    'premium': 5000,
    'enterprise': -1,  # Unlimited
    'client': -1
}

@payment_api.route('/upgrade-subscription', methods=['POST'])
def upgrade_subscription():
    """
    Update user subscription tier after successful payment
    This endpoint can be called from payment webhooks (PayFast ITN)
    
    Expected payload:
    {
        "user_email": "user@example.com",
        "plan_id": "production" | "enterprise",
        "plan_name": "Production Plan" | "Enterprise Plan",
        "amount": 29.00,
        "payment_id": "pf_payment_123"
    }
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        user_email = data.get('user_email', '').strip().lower() if data.get('user_email') else None
        user_id = data.get('user_id')
        plan_id = data.get('plan_id', '').lower()
        plan_name = data.get('plan_name', '')
        amount = data.get('amount', 0)
        payment_id = data.get('payment_id', '')
        
        if not plan_id:
            return jsonify({'error': 'plan_id is required'}), 400
        
        # Find user by email or ID (email preferred, ID as fallback)
        user = None
        if user_email:
            user = User.query.filter_by(email=user_email).first()
        elif user_id:
            try:
                user = User.query.filter_by(id=int(user_id)).first()
            except (ValueError, TypeError):
                pass
        
        if not user:
            identifier = user_email or f"ID {user_id}" or "unknown"
            print(f"⚠️ User not found for: {identifier}")
            return jsonify({'error': 'User not found'}), 404
        
        # Map plan_id to subscription tier
        new_tier = TIER_MAPPING.get(plan_id, 'free')
        old_tier = user.subscription_tier or 'free'
        
        # Only send upgrade email if tier actually changed
        tier_changed = old_tier != new_tier
        
        # Update user subscription
        user.subscription_tier = new_tier
        user.monthly_call_limit = TIER_LIMITS.get(new_tier, 5)
        # Reset monthly_used when upgrading (optional - you might want to keep it)
        # user.monthly_used = 0
        
        db.session.commit()
        
        print(f"✅ Subscription updated for {user_email}: {old_tier} -> {new_tier}")
        
        # Create notification for subscription upgrade
        try:
            create_subscription_notification(
                title=f"Subscription Upgraded: {plan_name}",
                message=f"User {user_email} upgraded from {old_tier} to {new_tier} tier. Payment ID: {payment_id}",
                user_id=user.id,
                user_email=user.email,
                plan_id=plan_id,
                old_tier=old_tier,
                new_tier=new_tier,
                notification_type='success'
            )
        except Exception as e:
            print(f"⚠️ Failed to create notification: {e}")
        
        # Send upgrade email if tier changed
        if tier_changed:
            try:
                send_upgrade_email(user.email, old_tier, new_tier)
            except Exception as e:
                print(f"⚠️ Failed to send upgrade email: {e}")
                # Don't fail the request if email fails
        
        return jsonify({
            'message': 'Subscription updated successfully',
            'user': user.to_dict(),
            'old_tier': old_tier,
            'new_tier': new_tier
        }), 200
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error updating subscription: {e}")
        return jsonify({'error': str(e)}), 500

