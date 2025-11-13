"""
Email service for sending transactional emails
Uses Resend API to send emails (works on all Railway plans)
"""
import os
import requests
from typing import Optional
from jinja2 import Environment, FileSystemLoader
from pathlib import Path

# Set up Jinja2 environment for email templates
template_dir = Path(__file__).parent / 'templates' / 'emails'
env = Environment(loader=FileSystemLoader(str(template_dir)))

# Resend API configuration
RESEND_API_KEY = os.getenv('RESEND_API_KEY', 're_5yGT4cPu_HkYqbboXDhEy9Kmo2T8Ec2uC')
RESEND_API_URL = 'https://api.resend.com/emails'
FROM_EMAIL = os.getenv('FROM_EMAIL', 'Trevnoctilla <onboarding@resend.dev>')
FROM_NAME = os.getenv('FROM_NAME', 'Trevnoctilla Team')

def send_email(to_email: str, subject: str, html_content: str, text_content: Optional[str] = None) -> bool:
    """
    Send an email using Resend API
    
    Args:
        to_email: Recipient email address
        subject: Email subject
        html_content: HTML email body
        text_content: Plain text email body (optional)
    
    Returns:
        True if email sent successfully, False otherwise
    """
    try:
        if not RESEND_API_KEY:
            print(f"⚠️ RESEND_API_KEY not set, skipping email to {to_email}")
            print(f"   Subject: {subject}")
            return False
        
        # Prepare email payload
        payload = {
            'from': FROM_EMAIL,
            'to': to_email,
            'subject': subject,
            'html': html_content
        }
        
        # Add text content if provided
        if text_content:
            payload['text'] = text_content
        
        # Send email via Resend API
        headers = {
            'Authorization': f'Bearer {RESEND_API_KEY}',
            'Content-Type': 'application/json'
        }
        
        response = requests.post(RESEND_API_URL, json=payload, headers=headers, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Email sent successfully to {to_email} (ID: {data.get('id', 'N/A')})")
            return True
        else:
            error_msg = response.text
            print(f"❌ Error sending email to {to_email}: HTTP {response.status_code} - {error_msg}")
            return False
        
    except Exception as e:
        error_msg = str(e)
        error_type = type(e).__name__
        print(f"❌ Error sending email to {to_email}: {error_type}: {error_msg}")
        import traceback
        traceback.print_exc()
        # Don't re-raise - return False so registration/upgrade can still succeed
        return False

def get_welcome_email_html(user_email: str, tier: str = 'free') -> tuple[str, str]:
    """
    Generate welcome email HTML and text content from templates
    
    Args:
        user_email: User's email address
        tier: Subscription tier (free, premium, enterprise)
    
    Returns:
        Tuple of (html_content, text_content)
    """
    tier_info = {
        'free': {
            'name': 'Free Tier',
            'calls': '5 API calls per month',
            'features': [
                'PDF text extraction',
                'Basic image conversion',
                'QR code generation',
                'Admin dashboard access',
                'Community support'
            ],
            'upgrade_message': 'Ready for more? Upgrade to Production ($29/month) for 5,000 API calls or Enterprise ($49/month) for unlimited calls!'
        },
        'premium': {
            'name': 'Production Plan',
            'calls': '5,000 API calls per month',
            'features': [
                'PDF operations (merge, split, extract)',
                'Video/audio conversion',
                'Image processing',
                'QR code generation',
                'Admin dashboard access',
                'Priority support'
            ],
            'upgrade_message': 'Need unlimited calls? Upgrade to Enterprise ($49/month) for unlimited API calls and enterprise features!'
        },
        'enterprise': {
            'name': 'Enterprise Plan',
            'calls': 'Unlimited API calls',
            'features': [
                'All file processing capabilities',
                'Enterprise client dashboard',
                'Dedicated support',
                'Custom SLAs',
                'White-label options',
                'Unlimited API calls'
            ],
            'upgrade_message': 'You\'re on our highest tier! Enjoy unlimited access to all features.'
        }
    }
    
    info = tier_info.get(tier.lower(), tier_info['free'])
    
    # Load and render HTML template
    html_template = env.get_template('welcome.html')
    html_content = html_template.render(tier_info=info)
    
    # Load and render text template
    text_template = env.get_template('welcome.txt')
    text_content = text_template.render(tier_info=info)
    
    return html_content, text_content

def get_upgrade_email_html(user_email: str, old_tier: str, new_tier: str) -> tuple[str, str]:
    """
    Generate upgrade email HTML and text content from templates
    
    Args:
        user_email: User's email address
        old_tier: Previous subscription tier
        new_tier: New subscription tier
    
    Returns:
        Tuple of (html_content, text_content)
    """
    tier_names = {
        'free': 'Free Tier',
        'premium': 'Production Plan',
        'enterprise': 'Enterprise Plan'
    }
    
    old_tier_name = tier_names.get(old_tier.lower(), old_tier)
    new_tier_name = tier_names.get(new_tier.lower(), new_tier)
    
    # Load and render HTML template
    html_template = env.get_template('upgrade.html')
    html_content = html_template.render(
        old_tier_name=old_tier_name,
        new_tier_name=new_tier_name
    )
    
    # Load and render text template
    text_template = env.get_template('upgrade.txt')
    text_content = text_template.render(
        old_tier_name=old_tier_name,
        new_tier_name=new_tier_name
    )
    
    return html_content, text_content

def send_welcome_email(user_email: str, tier: str = 'free') -> bool:
    """
    Send welcome email to newly registered user
    
    Args:
        user_email: User's email address
        tier: Subscription tier
    
    Returns:
        True if email sent successfully
    """
    html_content, text_content = get_welcome_email_html(user_email, tier)
    tier_info = {
        'free': {'name': 'Free Tier'},
        'premium': {'name': 'Production Plan'},
        'enterprise': {'name': 'Enterprise Plan'}
    }
    subject = f"Welcome to Trevnoctilla - {tier_info.get(tier.lower(), tier_info['free'])['name']} Activated! 🎉"
    return send_email(user_email, subject, html_content, text_content)

def send_upgrade_email(user_email: str, old_tier: str, new_tier: str) -> bool:
    """
    Send upgrade confirmation email
    
    Args:
        user_email: User's email address
        old_tier: Previous subscription tier
        new_tier: New subscription tier
    
    Returns:
        True if email sent successfully
    """
    html_content, text_content = get_upgrade_email_html(user_email, old_tier, new_tier)
    tier_names = {
        'free': 'Free Tier',
        'premium': 'Production Plan',
        'enterprise': 'Enterprise Plan'
    }
    subject = f"Trevnoctilla - Successfully Upgraded to {tier_names.get(new_tier.lower(), new_tier)}! 🚀"
    return send_email(user_email, subject, html_content, text_content)

