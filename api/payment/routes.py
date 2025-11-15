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
        
        # Find user by ID or email (ID preferred for subscriptions, email as fallback)
        # CRITICAL: For subscriptions, user_id is more reliable than email
        # PayFast may not send email_address in subscription webhooks
        user = None
        if user_id:
            try:
                user = User.query.filter_by(id=int(user_id)).first()
                if user:
                    print(f"✅ User found by ID: {user_id} ({user.email})")
            except (ValueError, TypeError):
                pass
        if not user and user_email:
            user = User.query.filter_by(email=user_email).first()
            if user:
                print(f"✅ User found by email: {user_email} (ID: {user.id})")
        
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
                # Get payment date from request (if available) or use current date
                from datetime import datetime
                payment_date_str = data.get('payment_date')
                payment_date = None
                if payment_date_str:
                    try:
                        payment_date = datetime.fromisoformat(payment_date_str.replace('Z', '+00:00'))
                    except:
                        payment_date = datetime.now()
                else:
                    payment_date = datetime.now()
                
                print(f"📧 [UPGRADE] Attempting to send upgrade email to {user.email}...")
                email_sent = send_upgrade_email(
                    user.email, 
                    old_tier, 
                    new_tier, 
                    amount=amount,
                    payment_id=payment_id,
                    payment_date=payment_date
                )
                
                if email_sent:
                    print(f"✅ [UPGRADE] Upgrade email sent successfully to {user.email}")
                else:
                    print(f"❌ [UPGRADE] Failed to send upgrade email to {user.email} - check logs above for details")
                    # Log additional context for debugging
                    print(f"   User: {user.email} (ID: {user.id})")
                    print(f"   Tier change: {old_tier} -> {new_tier}")
                    print(f"   Amount: {amount}")
                    print(f"   Payment ID: {payment_id}")
            except Exception as e:
                print(f"❌ [UPGRADE] Exception while sending upgrade email: {e}")
                import traceback
                traceback.print_exc()
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

