"""
Notification service for creating system-wide notifications
"""
from datetime import datetime
from database import db
from models import Notification

def create_notification(
    title: str,
    message: str,
    notification_type: str = 'info',
    category: str = 'system',
    metadata: dict = None
) -> Notification:
    """
    Create a new notification
    
    Args:
        title: Notification title
        message: Notification message
        notification_type: Type of notification ('info', 'warning', 'error', 'success', 'payment', 'subscription')
        category: Category of notification ('system', 'payment', 'subscription', 'user', 'api')
        metadata: Additional data to store with the notification
    
    Returns:
        Created Notification object
    """
    try:
        notification = Notification(
            title=title,
            message=message,
            type=notification_type,
            category=category,
            metadata=metadata or {}
        )
        
        db.session.add(notification)
        db.session.commit()
        
        print(f"✅ Notification created: {title}")
        return notification
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error creating notification: {e}")
        raise

def create_payment_notification(
    title: str,
    message: str,
    payment_id: str = None,
    user_id: int = None,
    user_email: str = None,
    amount: float = None,
    notification_type: str = 'payment'
) -> Notification:
    """Create a payment-related notification"""
    metadata = {}
    if payment_id:
        metadata['payment_id'] = payment_id
    if user_id:
        metadata['user_id'] = user_id
    if user_email:
        metadata['user_email'] = user_email
    if amount:
        metadata['amount'] = amount
    
    return create_notification(
        title=title,
        message=message,
        notification_type=notification_type,
        category='payment',
        metadata=metadata
    )

def create_subscription_notification(
    title: str,
    message: str,
    user_id: int = None,
    user_email: str = None,
    plan_id: str = None,
    old_tier: str = None,
    new_tier: str = None,
    notification_type: str = 'subscription'
) -> Notification:
    """Create a subscription-related notification"""
    metadata = {}
    if user_id:
        metadata['user_id'] = user_id
    if user_email:
        metadata['user_email'] = user_email
    if plan_id:
        metadata['plan_id'] = plan_id
    if old_tier:
        metadata['old_tier'] = old_tier
    if new_tier:
        metadata['new_tier'] = new_tier
    
    return create_notification(
        title=title,
        message=message,
        notification_type=notification_type,
        category='subscription',
        metadata=metadata
    )

