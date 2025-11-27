"""
Payment webhook routes for handling subscription upgrades
"""
from flask import Blueprint, request, jsonify
from database import db
from models import User, Notification
from email_service import send_upgrade_email, generate_invoice_pdf, get_file_invoice_email_html
from notification_service import create_subscription_notification, create_payment_notification
import base64
from datetime import datetime

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
        # Use robust lookup to handle case sensitivity issues
        user = None
        if user_id:
            try:
                user = User.query.filter_by(id=int(user_id)).first()
                if user:
                    print(f"✅ [UPGRADE] User found by ID: {user_id} ({user.email}, tier: {user.subscription_tier})")
            except (ValueError, TypeError):
                print(f"⚠️ [UPGRADE] Invalid user_id format: {user_id}")
                pass
        
        # If not found by ID, try email (case-insensitive lookup)
        if not user and user_email:
            # First try exact match
            user = User.query.filter_by(email=user_email).first()
            if user:
                print(f"✅ [UPGRADE] User found by email (exact): {user_email} (ID: {user.id}, tier: {user.subscription_tier})")
            else:
                # Try case-insensitive lookup
                all_users = User.query.all()
                for u in all_users:
                    if u.email.lower().strip() == user_email.lower().strip():
                        print(f"⚠️ [UPGRADE] Found user with different email casing: '{u.email}' (requested: '{user_email}')")
                        print(f"   Using existing user ID: {u.id}, tier: {u.subscription_tier}")
                        user = u
                        break
        
        if not user:
            identifier = user_email or f"ID {user_id}" or "unknown"
            print(f"❌ [UPGRADE] User not found for: {identifier}")
            print(f"   Searched by user_id: {user_id}")
            print(f"   Searched by email: {user_email}")
            # Log all users for debugging
            all_users = User.query.all()
            print(f"   Existing users in database: {[(u.id, u.email) for u in all_users]}")
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
        
        # Verify the update by re-fetching the user
        db.session.refresh(user)
        print(f"✅ Subscription updated for {user_email}: {old_tier} -> {new_tier}")
        print(f"[UPGRADE] Verified - User {user.id} ({user.email}) now has tier: {user.subscription_tier}")
        print(f"[UPGRADE] User monthly_call_limit: {user.monthly_call_limit}")
        
        # Sync tier update to Supabase (synchronously to ensure it completes)
        try:
            import os
            import psycopg2
            from psycopg2.extras import RealDictCursor
            from datetime import datetime
            
            # Get Supabase connection string
            database_url = os.getenv("DATABASE_URL", "postgresql://postgres:Kopenikus0218!@db.pqdxqvxyrahvongbhtdb.supabase.co:5432/postgres")
            
            # Convert to pooler format
            if database_url and "db." in database_url and ".supabase.co" in database_url:
                import re
                match = re.match(r'postgresql?://([^:]+):([^@]+)@db\.([^.]+)\.supabase\.co:(\d+)/(.+)', database_url)
                if match:
                    user_part, password, project_ref, port, database = match.groups()
                    database_url = f"postgresql://postgres.{project_ref}:{password}@aws-1-eu-west-1.pooler.supabase.com:6543/{database}"
            
            # Connect and update Supabase
            conn = psycopg2.connect(database_url, sslmode='require')
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            # Update user tier in Supabase
            cursor.execute("""
                UPDATE users SET
                    subscription_tier = %s,
                    monthly_call_limit = %s
                WHERE email = %s
            """, (
                new_tier,
                TIER_LIMITS.get(new_tier, 5),
                user.email
            ))
            
            conn.commit()
            cursor.close()
            conn.close()
            
            print(f"✅ [UPGRADE] Synced tier update to Supabase: {user_email} -> {new_tier}")
        except Exception as e:
            print(f"⚠️ [UPGRADE] Failed to sync tier to Supabase: {e}")
            import traceback
            traceback.print_exc()
            # Don't fail the request if Supabase sync fails
        
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
            # Also create payment notification for billing history
            if amount > 0:
                create_payment_notification(
                    title=f"Payment Received: {plan_name}",
                    message=f"Payment of ${amount:.2f} received for {plan_name}. User upgraded from {old_tier} to {new_tier}.",
                    payment_id=payment_id,
                    user_id=user.id,
                    user_email=user.email,
                    amount=amount,
                    notification_type='payment'
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

@payment_api.route('/generate-invoice-pdf', methods=['POST'])
def generate_invoice_pdf_endpoint():
    """
    Generate invoice PDF and return as base64
    Used for sending invoices via email
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        tier = data.get('tier', 'free')
        amount = data.get('amount', 0.0)
        user_email = data.get('user_email', '')
        payment_id = data.get('payment_id', '')
        payment_date_str = data.get('payment_date')
        item_description = data.get('item_description', 'File Download')
        
        # Parse payment date
        payment_date = None
        if payment_date_str:
            try:
                payment_date = datetime.fromisoformat(payment_date_str.replace('Z', '+00:00'))
            except:
                payment_date = datetime.now()
        else:
            payment_date = datetime.now()
        
        print(f"📄 [INVOICE PDF] Generating invoice PDF for {user_email} (tier: {tier}, amount: {amount})")
        
        # Use existing generate_invoice_pdf function
        invoice_pdf = generate_invoice_pdf(tier, amount, user_email, payment_id, payment_date, item_description)
        
        if invoice_pdf:
            pdf_base64 = base64.b64encode(invoice_pdf).decode('utf-8')
            print(f"✅ [INVOICE PDF] Invoice PDF generated ({len(invoice_pdf)} bytes)")
            return jsonify({
                'success': True,
                'pdf_base64': pdf_base64,
                'size': len(invoice_pdf)
            }), 200
        else:
            print(f"❌ [INVOICE PDF] Failed to generate invoice PDF")
            return jsonify({
                'success': False,
                'error': 'Failed to generate invoice PDF'
            }), 500
            
    except Exception as e:
        print(f"❌ [INVOICE PDF] Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@payment_api.route('/get-file-invoice-email-html', methods=['POST'])
def get_file_invoice_email_html_endpoint():
    """
    Get file and invoice email HTML content from template
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        item_name = data.get('item_name', 'File Download')
        amount = data.get('amount', 1.0)
        payment_id = data.get('payment_id', '')
        
        print(f"📧 [FILE INVOICE EMAIL] Generating email HTML for {item_name} (amount: {amount})")
        
        # Use existing get_file_invoice_email_html function
        html_content = get_file_invoice_email_html(item_name, amount, payment_id)
        
        return jsonify({
            'success': True,
            'html': html_content
        }), 200
            
    except Exception as e:
        print(f"❌ [FILE INVOICE EMAIL] Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@payment_api.route('/billing-history', methods=['GET'])
def get_billing_history():
    """
    Get user's billing history from payment/subscription notifications
    Requires authentication via Authorization header
    """
    try:
        # Get auth token from header
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({'error': 'Authorization required'}), 401
        
        token = auth_header.replace('Bearer ', '')
        
        # Get user from token (simplified - you may need to verify token properly)
        # For now, we'll get user_id from request args or token
        user_id = request.args.get('user_id')
        user_email = request.args.get('user_email')
        
        if not user_id and not user_email:
            return jsonify({'error': 'user_id or user_email required'}), 400
        
        # Get user to check their subscription tier and created date
        from models import User
        user = None
        if user_id:
            try:
                user = User.query.get(int(user_id))
            except:
                pass
        if not user and user_email:
            user = User.query.filter_by(email=user_email).first()
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        # CRITICAL: Only show invoices for the CURRENT user account
        # Filter by user ID (not just email) to prevent old invoices from deleted accounts
        # Also only show invoices created AFTER the user's account was created
        user_account_created_at = user.created_at if user.created_at else datetime.now()
        
        # Query notifications for this user with payment/subscription category
        # SQLite stores JSON as text, so we'll filter in Python
        all_notifications = Notification.query.filter(
            db.or_(
                Notification.category == 'payment',
                Notification.category == 'subscription'
            )
        ).order_by(Notification.created_at.desc()).all()
        
        # Filter by user_id AND ensure notification was created after user account creation
        # This prevents old invoices from deleted accounts from appearing
        notifications = []
        for notif in all_notifications:
            metadata = notif.notification_metadata or {}
            notif_user_id = metadata.get('user_id')
            
            # CRITICAL: Only include notifications that:
            # 1. Belong to the current user (by ID, not email)
            # 2. Were created AFTER the user's account was created
            if notif_user_id and (notif_user_id == user.id or str(notif_user_id) == str(user.id)):
                # Check if notification was created after user account creation
                if notif.created_at and notif.created_at >= user_account_created_at:
                    notifications.append(notif)
                else:
                    print(f"⚠️ [BILLING HISTORY] Skipping notification {notif.id} - created before user account ({notif.created_at} < {user_account_created_at})")
        
        # Transform notifications to billing history format
        billing_history = []
        for notif in notifications:
            metadata = notif.notification_metadata or {}
            amount = metadata.get('amount', 0.0)
            payment_id = metadata.get('payment_id', '')
            tier = metadata.get('new_tier') or metadata.get('tier', 'free')
            plan_name = notif.title.replace('Payment Received: ', '').replace('Subscription Upgraded: ', '')
            
            billing_history.append({
                'id': str(notif.id),
                'invoice': plan_name or f"Invoice #{payment_id[:8] if payment_id else notif.id}",
                'amount': float(amount),
                'date': notif.created_at.isoformat() if notif.created_at else datetime.now().isoformat(),
                'status': 'Paid' if amount > 0 else 'Free',
                'payment_id': payment_id,
                'tier': tier,
                'notification_id': notif.id,
                'metadata': metadata
            })
        
        print(f"📊 [BILLING HISTORY] Found {len(notifications)} notifications for user {user.id} (account created: {user_account_created_at}), created {len(billing_history)} billing history entries")
        
        # Always add initial free tier subscription (from signup)
        # This shows when they first signed up, regardless of current tier
        # Check if we already have an initial subscription in the history
        has_initial = any(
            item.get('metadata', {}).get('is_initial') or 
            (item.get('amount', 0) == 0 and item.get('tier', '').lower() == 'free' and item.get('notification_id') is None)
            for item in billing_history
        )
        
        if not has_initial:
            subscription_date = user.created_at if user.created_at else datetime.now()
            billing_history.insert(0, {
                'id': f"initial_{user.id}",
                'invoice': 'Free Tier - Initial Subscription',
                'amount': 0.0,
                'date': subscription_date.isoformat(),
                'status': 'Free',
                'payment_id': '',
                'tier': 'free',
                'notification_id': None,
                'metadata': {
                    'user_id': user.id,
                    'user_email': user.email,
                    'tier': 'free',
                    'is_initial': True
                }
            })
            print(f"✅ [BILLING HISTORY] Added initial free tier subscription for user {user.email} (signup: {subscription_date})")
        
        # If user is on premium/enterprise but has no payment notifications, add current subscription
        # This handles cases where upgrade notifications weren't created
            current_tier = user.subscription_tier or 'free'
            has_payment_notification = any(
                item.get('amount', 0) > 0 and item.get('status') == 'Paid'
                for item in billing_history
            )
            
            # Only add current subscription if user is on paid tier but has no payment notifications
            if current_tier.lower() in ['premium', 'production', 'enterprise'] and not has_payment_notification:
                tier_name = {'free': 'Free Tier', 'premium': 'Production Plan', 'enterprise': 'Enterprise Plan', 'production': 'Production Plan'}
                plan_name = tier_name.get(current_tier.lower(), current_tier)
                
                # Determine amount based on tier
                tier_amounts = {'free': 0.0, 'premium': 29.0, 'production': 29.0, 'enterprise': 49.0}
                subscription_amount = tier_amounts.get(current_tier.lower(), 0.0)
                
                # Use most recent notification date or user created_at
                latest_notification_date = None
                if notifications:
                    latest_notification_date = max((n.created_at for n in notifications if n.created_at), default=None)
                subscription_date = latest_notification_date or user.created_at or datetime.now()
                
                billing_history.append({
                    'id': f"current_{user.id}",
                    'invoice': f"{plan_name} - Subscription",
                    'amount': subscription_amount,
                    'date': subscription_date.isoformat(),
                    'status': 'Paid' if subscription_amount > 0 else 'Free',
                    'payment_id': '',
                    'tier': current_tier,
                    'notification_id': None,
                    'metadata': {
                        'user_id': user.id,
                        'user_email': user.email,
                        'tier': current_tier,
                        'is_current': True
                    }
                })
                print(f"✅ [BILLING HISTORY] Added current {current_tier} subscription for user {user.email} (amount: ${subscription_amount})")
        
        # Sort by date (oldest first)
        billing_history.sort(key=lambda x: x['date'])
        
        return jsonify({
            'success': True,
            'billing_history': billing_history
        }), 200
        
    except Exception as e:
        print(f"❌ [BILLING HISTORY] Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@payment_api.route('/download-invoice', methods=['POST'])
def download_invoice():
    """
    Regenerate and return invoice PDF for download
    Requires authentication via Authorization header
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        # Get auth token from header
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({'error': 'Authorization required'}), 401
        
        # Extract invoice details from request
        payment_id = data.get('payment_id', '')
        user_email = data.get('user_email', '')
        amount = data.get('amount', 0.0)
        tier = data.get('tier', 'free')
        payment_date_str = data.get('payment_date')
        item_description = data.get('item_description', f"{tier.title()} Plan - Monthly Subscription")
        
        # Parse payment date
        payment_date = None
        if payment_date_str:
            try:
                payment_date = datetime.fromisoformat(payment_date_str.replace('Z', '+00:00'))
            except:
                payment_date = datetime.now()
        else:
            payment_date = datetime.now()
        
        print(f"📄 [DOWNLOAD INVOICE] Generating invoice PDF for {user_email} (tier: {tier}, amount: {amount})")
        
        # Determine which template to use based on tier
        template_name = 'subscription-invoice.html' if tier in ['premium', 'production', 'enterprise', 'client'] else 'emails/invoice.html'
        
        # Generate invoice PDF
        invoice_pdf = generate_invoice_pdf(
            tier=tier,
            amount=amount,
            user_email=user_email,
            payment_id=payment_id,
            payment_date=payment_date,
            item_description=item_description,
            template_name=template_name
        )
        
        if invoice_pdf:
            pdf_base64 = base64.b64encode(invoice_pdf).decode('utf-8')
            print(f"✅ [DOWNLOAD INVOICE] Invoice PDF generated ({len(invoice_pdf)} bytes)")
            return jsonify({
                'success': True,
                'pdf_base64': pdf_base64,
                'size': len(invoice_pdf),
                'filename': f'invoice_{tier}_{payment_date.strftime("%Y%m%d")}.pdf'
            }), 200
        else:
            print(f"❌ [DOWNLOAD INVOICE] Failed to generate invoice PDF")
            return jsonify({
                'success': False,
                'error': 'Failed to generate invoice PDF'
            }), 500
            
    except Exception as e:
        print(f"❌ [DOWNLOAD INVOICE] Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

