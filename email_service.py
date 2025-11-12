"""
Email service for sending transactional emails
Uses SMTP to send emails from info@trevnoctilla.com
"""
import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import Optional
from jinja2 import Environment, FileSystemLoader
from pathlib import Path

# Set up Jinja2 environment for email templates
template_dir = Path(__file__).parent / 'templates' / 'emails'
env = Environment(loader=FileSystemLoader(str(template_dir)))

# Email configuration - Afrihost SMTP
SMTP_HOST = os.getenv('SMTP_HOST', 'smtp.afrihost.co.za')
SMTP_PORT = int(os.getenv('SMTP_PORT', '465'))
SMTP_USER = os.getenv('SMTP_USER', 'kodekenobi@gmail.com')
SMTP_PASSWORD = os.getenv('SMTP_PASSWORD', 'Kopenikus0218!')
FROM_EMAIL = 'info@trevnoctilla.com'
FROM_NAME = 'Trevnoctilla Team'

def send_email(to_email: str, subject: str, html_content: str, text_content: Optional[str] = None) -> bool:
    """
    Send an email using SMTP
    
    Args:
        to_email: Recipient email address
        subject: Email subject
        html_content: HTML email body
        text_content: Plain text email body (optional)
    
    Returns:
        True if email sent successfully, False otherwise
    """
    try:
        # Create message
        msg = MIMEMultipart('alternative')
        msg['From'] = f"{FROM_NAME} <{FROM_EMAIL}>"
        msg['To'] = to_email
        msg['Subject'] = subject
        
        # Add text and HTML parts
        if text_content:
            text_part = MIMEText(text_content, 'plain')
            msg.attach(text_part)
        
        html_part = MIMEText(html_content, 'html')
        msg.attach(html_part)
        
        # Send email
        if not SMTP_PASSWORD:
            print(f"⚠️ SMTP_PASSWORD not set, skipping email to {to_email}")
            print(f"   Subject: {subject}")
            return False
        
        # Use SSL for port 465 (Afrihost requires SSL, not STARTTLS)
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as server:
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)
        
        print(f"✅ Email sent successfully to {to_email}")
        return True
        
    except Exception as e:
        print(f"❌ Error sending email to {to_email}: {str(e)}")
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

