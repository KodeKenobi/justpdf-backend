import requests
import json
import hmac
import hashlib
import time
from datetime import datetime
from models import Webhook, Job, db
from database import db as database
from celery_app import celery_app

def generate_webhook_secret():
    """Generate a secure webhook secret"""
    import secrets
    return secrets.token_urlsafe(32)

def create_webhook_signature(payload, secret):
    """Create HMAC signature for webhook payload"""
    return hmac.new(
        secret.encode('utf-8'),
        payload.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()

def verify_webhook_signature(payload, signature, secret):
    """Verify webhook signature"""
    expected_signature = create_webhook_signature(payload, secret)
    return hmac.compare_digest(signature, expected_signature)

@celery_app.task(bind=True, max_retries=3)
def send_webhook(self, webhook_id, job_id, event_type, payload):
    """Send webhook notification"""
    try:
        webhook = Webhook.query.get(webhook_id)
        if not webhook or not webhook.is_active:
            return

        # Check if webhook should be triggered for this event
        if webhook.events and event_type not in webhook.events:
            return

        # Add webhook headers
        headers = {
            'Content-Type': 'application/json',
            'User-Agent': 'Trevnoctilla-Webhook/1.0',
            'X-Webhook-Event': event_type,
            'X-Webhook-Timestamp': str(int(time.time())),
        }

        # Add signature if secret is configured
        if webhook.secret:
            payload_str = json.dumps(payload, sort_keys=True)
            signature = create_webhook_signature(payload_str, webhook.secret)
            headers['X-Webhook-Signature'] = f'sha256={signature}'

        # Send webhook
        response = requests.post(
            webhook.url,
            data=json.dumps(payload),
            headers=headers,
            timeout=30
        )

        # Update webhook status
        webhook.last_triggered = datetime.utcnow()
        if response.status_code >= 200 and response.status_code < 300:
            webhook.failure_count = 0
        else:
            webhook.failure_count += 1
            if webhook.failure_count >= 5:
                webhook.is_active = False

        database.session.commit()

        return {
            'webhook_id': webhook_id,
            'status_code': response.status_code,
            'success': response.status_code < 300
        }

    except Exception as e:
        # Update failure count
        webhook = Webhook.query.get(webhook_id)
        if webhook:
            webhook.failure_count += 1
            if webhook.failure_count >= 5:
                webhook.is_active = False
            database.session.commit()

        # Retry with exponential backoff
        raise self.retry(
            exc=e,
            countdown=60 * (2 ** self.request.retries),
            max_retries=3
        )

def trigger_webhooks(job_id, event_type, additional_data=None):
    """Trigger webhooks for a job event"""
    try:
        job = Job.query.filter_by(job_id=job_id).first()
        if not job:
            return

        # Get all active webhooks for this API key
        webhooks = Webhook.query.filter_by(
            api_key_id=job.api_key_id,
            is_active=True
        ).all()

        # Prepare payload
        payload = {
            'event': event_type,
            'job_id': job_id,
            'timestamp': datetime.utcnow().isoformat(),
            'job': job.to_dict()
        }

        if additional_data:
            payload.update(additional_data)

        # Send webhooks asynchronously
        for webhook in webhooks:
            send_webhook.delay(webhook.id, job_id, event_type, payload)

    except Exception as e:
        print(f"Error triggering webhooks: {e}")

def register_webhook(api_key_id, url, events=None, secret=None):
    """Register a new webhook"""
    try:
        if not secret:
            secret = generate_webhook_secret()

        webhook = Webhook(
            api_key_id=api_key_id,
            url=url,
            events=events or ['job.completed', 'job.failed'],
            secret=secret
        )

        database.session.add(webhook)
        database.session.commit()

        return webhook

    except Exception as e:
        database.session.rollback()
        raise e

def update_webhook(webhook_id, url=None, events=None, is_active=None):
    """Update webhook configuration"""
    try:
        webhook = Webhook.query.get(webhook_id)
        if not webhook:
            return None

        if url is not None:
            webhook.url = url
        if events is not None:
            webhook.events = events
        if is_active is not None:
            webhook.is_active = is_active

        database.session.commit()
        return webhook

    except Exception as e:
        database.session.rollback()
        raise e

def delete_webhook(webhook_id):
    """Delete a webhook"""
    try:
        webhook = Webhook.query.get(webhook_id)
        if webhook:
            database.session.delete(webhook)
            database.session.commit()
            return True
        return False

    except Exception as e:
        database.session.rollback()
        raise e

def get_webhook_stats(api_key_id):
    """Get webhook statistics for an API key"""
    try:
        webhooks = Webhook.query.filter_by(api_key_id=api_key_id).all()
        
        total_webhooks = len(webhooks)
        active_webhooks = len([w for w in webhooks if w.is_active])
        failed_webhooks = len([w for w in webhooks if w.failure_count > 0])
        
        return {
            'total_webhooks': total_webhooks,
            'active_webhooks': active_webhooks,
            'failed_webhooks': failed_webhooks,
            'webhooks': [w.to_dict() for w in webhooks]
        }

    except Exception as e:
        print(f"Error getting webhook stats: {e}")
        return {
            'total_webhooks': 0,
            'active_webhooks': 0,
            'failed_webhooks': 0,
            'webhooks': []
        }

# Webhook event types
WEBHOOK_EVENTS = {
    'job.created': 'Job created',
    'job.started': 'Job processing started',
    'job.completed': 'Job completed successfully',
    'job.failed': 'Job failed',
    'job.cancelled': 'Job cancelled'
}
