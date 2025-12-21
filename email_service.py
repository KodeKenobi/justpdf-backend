"""
Email service for sending transactional emails
Uses Resend API to send emails (works on all Railway plans)
"""
import os
import requests
import base64
import uuid
from datetime import datetime
from typing import Optional, Dict, Any
from jinja2 import Environment, FileSystemLoader
from pathlib import Path

# Set up Jinja2 environment for email templates
template_dir = Path(__file__).parent / 'templates' / 'emails'
env = Environment(loader=FileSystemLoader(str(template_dir)))

# Resend API configuration
RESEND_API_KEY = os.getenv('RESEND_API_KEY')
RESEND_API_URL = 'https://api.resend.com/emails'
# FROM_EMAIL should be in format: "Name <email@domain.com>" for proper inbox display
raw_from_email = os.getenv('FROM_EMAIL', 'noreply@trevnoctilla.com')
if not raw_from_email or (not '<' in raw_from_email and not '>' in raw_from_email):
    # If just email address, format it with name
    FROM_EMAIL = f'Trevnoctilla <{raw_from_email}>'
else:
    FROM_EMAIL = raw_from_email
FROM_NAME = os.getenv('FROM_NAME', 'Trevnoctilla Team')

def generate_subscription_pdf(tier: str, amount: float = 0.0, user_email: str = "", subscription_id: str = "", payment_id: str = "", payment_date: Optional[datetime] = None, billing_cycle: str = "Monthly", payment_method: str = "PayFast", old_tier: Optional[str] = None) -> Optional[bytes]:
    """
    Generate PDF subscription document from HTML template using html-to-pdf endpoint
    
    Args:
        tier: Subscription tier (free, premium, enterprise)
        amount: Subscription amount (0.0 for free tier)
        user_email: User email address
        subscription_id: Subscription ID (optional)
        payment_id: Payment/transaction ID (optional)
        payment_date: Payment/start date (uses this for subscription date if provided)
        billing_cycle: Billing cycle (Monthly, Yearly, etc.)
        payment_method: Payment method used
    
    Returns:
        PDF bytes if successful, None otherwise
    """
    try:
        tier_names = {
            'free': 'Free Tier',
            'premium': 'Production Plan',
            'enterprise': 'Enterprise Plan',
            'client': 'Client Plan'
        }
        
        # Use payment date if provided, otherwise use current date
        subscription_date_obj = payment_date if payment_date else datetime.now()
        subscription_date_str = subscription_date_obj.strftime('%B %d, %Y')
        
        # Calculate next billing date (add 1 month for monthly, 1 year for yearly)
        try:
            from dateutil.relativedelta import relativedelta
            if billing_cycle.lower() == "yearly":
                next_billing_date_obj = subscription_date_obj + relativedelta(years=1)
            else:
                next_billing_date_obj = subscription_date_obj + relativedelta(months=1)
        except ImportError:
            # Fallback if dateutil not available - just add 30 days
            from datetime import timedelta
            if billing_cycle.lower() == "yearly":
                next_billing_date_obj = subscription_date_obj + timedelta(days=365)
            else:
                next_billing_date_obj = subscription_date_obj + timedelta(days=30)
        next_billing_date_str = next_billing_date_obj.strftime('%B %d, %Y')
        
        # Generate subscription ID if not provided
        if not subscription_id:
            subscription_id = f"SUB-{subscription_date_obj.strftime('%Y%m%d')}-{str(uuid.uuid4())[:8].upper()}"
        
        # Download and embed logo as base64 for PDF compatibility
        logo_base64 = None
        try:
            logo_url = "https://www.trevnoctilla.com/logo.png"
            logo_response = requests.get(logo_url, timeout=10)
            if logo_response.status_code == 200:
                import base64
                logo_base64 = base64.b64encode(logo_response.content).decode('utf-8')
                logo_data_uri = f"data:image/png;base64,{logo_base64}"
                print(f"✅ [SUBSCRIPTION] Logo downloaded and embedded as base64 ({len(logo_base64)} chars)")
            else:
                print(f"⚠️ [SUBSCRIPTION] Failed to download logo: HTTP {logo_response.status_code}")
        except Exception as e:
            print(f"⚠️ [SUBSCRIPTION] Error downloading logo: {e}")
            # Continue without logo if download fails
        
        # Generate subscription HTML with embedded logo
        subscription_template = env.get_template('upgrade.html')
        old_tier_name = tier_names.get(old_tier.lower(), old_tier) if old_tier else "Free Tier"
        new_tier_name = tier_names.get(tier.lower(), tier)
        subscription_html = subscription_template.render(
            old_tier_name=old_tier_name,
            new_tier_name=new_tier_name
        )
        
        # Save HTML to temp file
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as f:
            f.write(subscription_html)
            html_path = f.name
        
        # Debug: Log HTML size and preview
        html_size = len(subscription_html)
        print(f"📄 [SUBSCRIPTION] Generated HTML ({html_size} chars)")
        print(f"📄 [SUBSCRIPTION] HTML preview (first 500 chars): {subscription_html[:500]}")
        print(f"📄 [SUBSCRIPTION] HTML saved to: {html_path}")
        
        # Get API URL for PDF conversion
        # Use frontend domain if available (Next.js rewrites proxy to backend)
        # Otherwise fall back to direct backend URL
        frontend_url = os.getenv('NEXTJS_URL') or os.getenv('FRONTEND_URL') or os.getenv('NEXT_PUBLIC_BASE_URL')
        if frontend_url and frontend_url.startswith('http'):
            api_url = frontend_url
            print(f"📄 [SUBSCRIPTION] Using frontend domain for PDF conversion: {api_url}")
        else:
            api_url = os.getenv('BACKEND_URL', 'https://web-production-737b.up.railway.app')
            if not api_url.startswith('http'):
                api_url = f'https://{api_url}'
            print(f"📄 [SUBSCRIPTION] Using direct backend URL for PDF conversion: {api_url}")
        
        # Convert HTML to PDF using backend endpoint
        print(f"📄 [SUBSCRIPTION] Converting HTML to PDF via {api_url}/convert_html_to_pdf...")
        response = None
        with open(html_path, 'rb') as html_file:
            files = {'html': ('subscription.html', html_file, 'text/html')}
            try:
                response = requests.post(
                    f"{api_url}/convert_html_to_pdf",
                    files=files,
                    timeout=60  # Increased timeout for PDF generation
                )
            except requests.exceptions.Timeout:
                print(f"❌ [SUBSCRIPTION] PDF conversion timed out after 60 seconds")
                # Clean up temp HTML file
                try:
                    os.unlink(html_path)
                except:
                    pass
                return None
            except requests.exceptions.RequestException as e:
                print(f"❌ [SUBSCRIPTION] PDF conversion request failed: {e}")
                # Clean up temp HTML file
                try:
                    os.unlink(html_path)
                except:
                    pass
                return None
        
        # Clean up temp HTML file
        try:
            os.unlink(html_path)
        except:
            pass
        
        if response and response.status_code == 200:
            data = response.json()
            print(f"📄 [SUBSCRIPTION] Conversion response: {data}")
            if data.get('status') == 'success' and data.get('download_url'):
                # Download the PDF
                pdf_url = data['download_url']
                if not pdf_url.startswith('http'):
                    pdf_url = f"{api_url}{pdf_url}"
                
                print(f"📄 [SUBSCRIPTION] Downloading PDF from: {pdf_url}")
                pdf_response = requests.get(pdf_url, timeout=30)
                if pdf_response.status_code == 200:
                    pdf_size = len(pdf_response.content)
                    print(f"✅ [SUBSCRIPTION] PDF generated successfully ({pdf_size} bytes)")
                    if pdf_size < 1000:
                        print(f"⚠️ [SUBSCRIPTION] WARNING: PDF size is very small ({pdf_size} bytes), might be blank!")
                    return pdf_response.content
                else:
                    print(f"❌ [SUBSCRIPTION] Failed to download PDF: {pdf_response.status_code} - {pdf_response.text[:200]}")
            else:
                error_msg = data.get('error', data.get('message', 'Unknown error'))
                print(f"❌ [SUBSCRIPTION] Conversion failed: {error_msg}")
                print(f"   Full response: {data}")
        else:
            error_text = response.text[:500] if response.text else "No error message"
            print(f"❌ [SUBSCRIPTION] HTML to PDF conversion failed: {response.status_code}")
            print(f"   Error response: {error_text}")
        
        return None
        
    except Exception as e:
        print(f"❌ [SUBSCRIPTION] Error generating subscription PDF: {e}")
        import traceback
        traceback.print_exc()
        return None

def generate_invoice_pdf(tier: str, amount: float = 0.0, user_email: str = "", payment_id: str = "", payment_date: Optional[datetime] = None, item_description: Optional[str] = None, template_name: str = 'emails/invoice.html') -> Optional[bytes]:
    """
    Generate PDF invoice from HTML template using html-to-pdf endpoint
    
    Args:
        tier: Subscription tier (free, premium, enterprise)
        amount: Invoice amount (0.0 for free tier)
        user_email: User email address
        payment_id: Payment/transaction ID (optional)
        payment_date: Payment/start date (uses this for invoice date if provided)
        item_description: Custom item description (optional, defaults to tier subscription)
        template_name: HTML template to use ('emails/invoice.html' for welcome, 'subscription-invoice.html' for upgrades)
    
    Returns:
        PDF bytes if successful, None otherwise
    """
    try:
        # Tier pricing
        tier_pricing = {
            'free': 0.00,
            'premium': 29.00,
            'enterprise': 49.00,
            'client': 0.00  # Custom pricing
        }
        
        tier_names = {
            'free': 'Free Tier',
            'premium': 'Production Plan',
            'enterprise': 'Enterprise Plan',
            'client': 'Client Plan'
        }
        
        # Use provided amount or tier pricing
        invoice_amount = amount if amount > 0 else tier_pricing.get(tier.lower(), 0.0)
        
        # Use payment date if provided, otherwise use current date
        invoice_date_obj = payment_date if payment_date else datetime.now()
        invoice_date_str = invoice_date_obj.strftime('%B %d, %Y')
        
        # Generate invoice number based on payment date
        invoice_number = f"INV-{invoice_date_obj.strftime('%Y%m%d')}-{str(uuid.uuid4())[:8].upper()}"
        
        # Download and embed logo as base64 for PDF compatibility
        logo_base64 = None
        try:
            logo_url = "https://www.trevnoctilla.com/logo.png"
            logo_response = requests.get(logo_url, timeout=10)
            if logo_response.status_code == 200:
                import base64
                logo_base64 = base64.b64encode(logo_response.content).decode('utf-8')
                logo_data_uri = f"data:image/png;base64,{logo_base64}"
                print(f"✅ [INVOICE] Logo downloaded and embedded as base64 ({len(logo_base64)} chars)")
            else:
                print(f"⚠️ [INVOICE] Failed to download logo: HTTP {logo_response.status_code}")
        except Exception as e:
            print(f"⚠️ [INVOICE] Error downloading logo: {e}")
            # Continue without logo if download fails
        
        # Generate invoice HTML with embedded logo
        # Handle both 'emails/invoice.html' and 'invoice.html' template names
        template_to_load = template_name.replace('emails/', '') if 'emails/' in template_name else template_name
        invoice_template = env.get_template(template_to_load)
        # Use provided item_description or default to tier subscription
        final_item_description = item_description or f"{tier_names.get(tier.lower(), tier)} Subscription"
        
        # Render template with appropriate variables based on template type
        if template_to_load == 'subscription-invoice.html':
            # subscription-invoice.html uses different variable structure
            invoice_html = invoice_template.render(
                invoice_number=invoice_number,
                invoice_date=invoice_date_str,
                user_email=user_email,
                tier_name=tier_names.get(tier.lower(), tier),
                item_description=final_item_description,
                unit_price=f"{invoice_amount:.2f}",
                total_amount=f"{invoice_amount:.2f}",
                amount=f"{invoice_amount:.2f}",
                currency_symbol="$",
                tax_amount=0.0,
                tax_rate=0,
                status="Paid" if invoice_amount > 0 else "Free"
            )
        else:
            # emails/invoice.html (default for welcome emails)
            invoice_html = invoice_template.render(
                invoice_number=invoice_number,
                invoice_date=invoice_date_str,
                user_email=user_email,
                tier_name=tier_names.get(tier.lower(), tier),
                item_description=final_item_description,
                unit_price=f"{invoice_amount:.2f}",
                total_amount=f"{invoice_amount:.2f}",
                currency_symbol="$",
                tax_amount=0.0,
                tax_rate=0,
                status="Paid" if invoice_amount > 0 else "Free",
                status_class="status-paid" if invoice_amount > 0 else "status-free",
                logo_url=logo_data_uri if logo_base64 else "https://www.trevnoctilla.com/logo.png"  # Fallback to URL if base64 failed
            )
        
        # Save HTML to temp file
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as f:
            f.write(invoice_html)
            html_path = f.name
        
        # Debug: Log HTML size and preview
        html_size = len(invoice_html)
        print(f"📄 [INVOICE] Generated HTML ({html_size} chars)")
        print(f"📄 [INVOICE] HTML preview (first 500 chars): {invoice_html[:500]}")
        print(f"📄 [INVOICE] HTML saved to: {html_path}")
        
        # Get API URL for PDF conversion
        # Use frontend domain if available (Next.js rewrites proxy to backend)
        # Otherwise fall back to direct backend URL
        frontend_url = os.getenv('NEXTJS_URL') or os.getenv('FRONTEND_URL') or os.getenv('NEXT_PUBLIC_BASE_URL')
        if frontend_url and frontend_url.startswith('http'):
            api_url = frontend_url
            print(f"📄 [INVOICE] Using frontend domain for PDF conversion: {api_url}")
        else:
            api_url = os.getenv('BACKEND_URL', 'https://web-production-737b.up.railway.app')
            if not api_url.startswith('http'):
                api_url = f'https://{api_url}'
            print(f"📄 [INVOICE] Using direct backend URL for PDF conversion: {api_url}")
        
        # Convert HTML to PDF using backend endpoint
        print(f"📄 [INVOICE] Converting HTML to PDF via {api_url}/convert_html_to_pdf...")
        response = None
        with open(html_path, 'rb') as html_file:
            files = {'html': ('invoice.html', html_file, 'text/html')}
            try:
                response = requests.post(
                    f"{api_url}/convert_html_to_pdf",
                    files=files,
                    timeout=60  # Increased timeout for PDF generation
                )
            except requests.exceptions.Timeout:
                print(f"❌ [INVOICE] PDF conversion timed out after 60 seconds")
                # Clean up temp HTML file
                try:
                    os.unlink(html_path)
                except:
                    pass
                return None
            except requests.exceptions.RequestException as e:
                print(f"❌ [INVOICE] PDF conversion request failed: {e}")
                # Clean up temp HTML file
                try:
                    os.unlink(html_path)
                except:
                    pass
                return None
        
        # Clean up temp HTML file
        try:
            os.unlink(html_path)
        except:
            pass
        
        if response and response.status_code == 200:
            data = response.json()
            print(f"📄 [INVOICE] Conversion response: {data}")
            if data.get('status') == 'success' and data.get('download_url'):
                # Download the PDF
                pdf_url = data['download_url']
                if not pdf_url.startswith('http'):
                    pdf_url = f"{api_url}{pdf_url}"
                
                print(f"📄 [INVOICE] Downloading PDF from: {pdf_url}")
                pdf_response = requests.get(pdf_url, timeout=30)
                if pdf_response.status_code == 200:
                    pdf_size = len(pdf_response.content)
                    print(f"✅ [INVOICE] PDF generated successfully ({pdf_size} bytes)")
                    if pdf_size < 1000:
                        print(f"⚠️ [INVOICE] WARNING: PDF size is very small ({pdf_size} bytes), might be blank!")
                    return pdf_response.content
                else:
                    print(f"❌ [INVOICE] Failed to download PDF: {pdf_response.status_code} - {pdf_response.text[:200]}")
            else:
                error_msg = data.get('error', data.get('message', 'Unknown error'))
                print(f"❌ [INVOICE] Conversion failed: {error_msg}")
                print(f"   Full response: {data}")
        else:
            error_text = response.text[:500] if response.text else "No error message"
            print(f"❌ [INVOICE] HTML to PDF conversion failed: {response.status_code}")
            print(f"   Error response: {error_text}")
        
        return None
        
    except Exception as e:
        print(f"❌ [INVOICE] Error generating invoice PDF: {e}")
        import traceback
        traceback.print_exc()
        return None

def send_email(to_email: str, subject: str, html_content: str, text_content: Optional[str] = None, attachments: Optional[list] = None) -> bool:
    """
    Send an email using Next.js API route (which uses Resend Node.js SDK)
    
    Args:
        to_email: Recipient email address
        subject: Email subject
        html_content: HTML email body
        text_content: Plain text email body (optional)
    
    Returns:
        True if email sent successfully, False otherwise
    """
    try:
        import os
        
        # Get Next.js API URL
        nextjs_url = os.getenv('NEXTJS_API_URL', 'https://www.trevnoctilla.com')
        email_api_url = f"{nextjs_url}/api/email/send"
        
        # Prepare email payload
        payload = {
            'to': to_email,
            'subject': subject,
            'html': html_content
        }
        
        # Add text content if provided
        if text_content:
            payload['text'] = text_content
        
        # Add attachments if provided
        # Format: [{ filename: "invoice.pdf", content: base64String, contentType: "application/pdf" }]
        if attachments:
            payload['attachments'] = attachments
            print(f"📎 [EMAIL] Including {len(attachments)} attachment(s) in email payload")
            for i, att in enumerate(attachments, 1):
                print(f"   {i}. {att.get('filename', 'unknown')} ({len(att.get('content', ''))} base64 chars)")
        
        print(f"📤 [EMAIL] Sending email to {to_email} via Next.js API")
        print(f"📤 [EMAIL] API URL: {email_api_url}")
        print(f"📤 [EMAIL] Subject: {subject}")
        print(f"📤 [EMAIL] Has attachments: {bool(attachments)}")
        
        # Send email via Next.js API route
        response = requests.post(email_api_url, json=payload, timeout=30)
        
        print(f"📥 [EMAIL] Response status: {response.status_code}")
        print(f"📥 [EMAIL] Response body: {response.text[:200]}")
        
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                print(f"✅ [EMAIL] Email sent successfully to {to_email} (ID: {data.get('email_id', 'N/A')})")
                return True
            else:
                print(f"❌ [EMAIL] Email send failed: {data.get('error', 'Unknown error')}")
                return False
        else:
            error_msg = response.text
            print(f"❌ [EMAIL] Error sending email to {to_email}: HTTP {response.status_code} - {error_msg}")
            return False
        
    except Exception as e:
        error_msg = str(e)
        error_type = type(e).__name__
        print(f"❌ [EMAIL] Error sending email to {to_email}: {error_type}: {error_msg}")
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
            'upgrade_message': 'Ready for more? Upgrade to Production ($9/month) for 5,000 API calls or Enterprise ($19/month) for unlimited calls!'
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
            'upgrade_message': 'Need unlimited calls? Upgrade to Enterprise ($19/month) for unlimited API calls and enterprise features!'
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

def get_file_invoice_email_html(item_name: str, amount: float, payment_id: str = "") -> str:
    """
    Generate file and invoice email HTML content from template
    
    Args:
        item_name: Name of the purchased item
        amount: Payment amount
        payment_id: Payment/transaction ID (optional)
    
    Returns:
        HTML content string
    """
    # Format amount to 2 decimal places
    amount_str = f"{amount:.2f}"
    
    # Load and render HTML template
    html_template = env.get_template('file-invoice.html')
    html_content = html_template.render(
        item_name=item_name,
        amount=amount_str,
        payment_id=payment_id
    )
    
    return html_content

def send_welcome_email(user_email: str, tier: str = 'free', amount: float = 0.0, payment_id: str = "", payment_date: Optional[datetime] = None) -> bool:
    """
    Send welcome email to newly registered user with invoice attachment
    
    Args:
        user_email: User's email address
        tier: Subscription tier
        amount: Payment amount (0.0 for free tier)
        payment_id: Payment/transaction ID (optional)
    
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
    
    # Generate and attach invoice PDF
    attachments = []
    try:
        print(f"📄 [WELCOME EMAIL] Generating invoice PDF for {user_email} (tier: {tier}, amount: {amount})")
        invoice_pdf = generate_invoice_pdf(tier, amount, user_email, payment_id, payment_date)
        if invoice_pdf:
            # Convert PDF bytes to base64
            pdf_base64 = base64.b64encode(invoice_pdf).decode('utf-8')
            date_str = payment_date.strftime("%Y%m%d") if payment_date else datetime.now().strftime("%Y%m%d")
            filename = f'invoice_{tier}_{date_str}.pdf'
            attachments.append({
                'filename': filename,
                'content': pdf_base64,
                'contentType': 'application/pdf'
            })
            print(f"✅ [WELCOME EMAIL] Invoice PDF generated and attached: {filename} ({len(invoice_pdf)} bytes, base64: {len(pdf_base64)} chars)")
        else:
            print(f"⚠️ [WELCOME EMAIL] Failed to generate invoice PDF, sending email without attachment")
            print(f"   Check generate_invoice_pdf() logs for details")
    except Exception as e:
        print(f"⚠️ [WELCOME EMAIL] Error generating invoice: {e}")
        import traceback
        traceback.print_exc()
        # Continue without attachment if invoice generation fails
    
    return send_email(user_email, subject, html_content, text_content, attachments if attachments else None)

def send_upgrade_email(user_email: str, old_tier: str, new_tier: str, amount: float = 0.0, payment_id: str = "", payment_date: Optional[datetime] = None) -> bool:
    """
    Send upgrade confirmation email with subscription PDF attachment
    
    Args:
        user_email: User's email address
        old_tier: Previous subscription tier
        new_tier: New subscription tier
        amount: Payment amount
        payment_id: Payment/transaction ID (optional)
        payment_date: Payment date (optional)
    
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
    
    # Generate and attach invoice PDF (more reliable than subscription PDF)
    # Use invoice PDF generation which is tested and working
    attachments = []
    try:
        print(f"📄 [UPGRADE EMAIL] Generating invoice PDF for {user_email} (tier: {new_tier}, amount: {amount})")
        
        # Use invoice PDF generation instead of subscription PDF (more reliable)
        invoice_pdf = generate_invoice_pdf(
            tier=new_tier,
            amount=amount,
            user_email=user_email,
            payment_id=payment_id,
            payment_date=payment_date,
            item_description=f"{tier_names.get(new_tier.lower(), new_tier)} - Monthly Subscription",
            template_name='emails/invoice.html'
        )
        
        if invoice_pdf:
            # Convert PDF bytes to base64
            import base64
            pdf_base64 = base64.b64encode(invoice_pdf).decode('utf-8')
            date_str = payment_date.strftime("%Y%m%d") if payment_date else datetime.now().strftime("%Y%m%d")
            attachments.append({
                'filename': f'subscription_{new_tier}_{date_str}.pdf',
                'content': pdf_base64,
                'contentType': 'application/pdf'
            })
            print(f"✅ [UPGRADE EMAIL] Invoice PDF attached ({len(invoice_pdf)} bytes, base64: {len(pdf_base64)} chars)")
        else:
            print(f"⚠️ [UPGRADE EMAIL] Failed to generate invoice PDF, trying subscription PDF as fallback...")
            # Fallback to subscription PDF if invoice fails
            subscription_pdf = generate_subscription_pdf(
                tier=new_tier,
                amount=amount,
                user_email=user_email,
                subscription_id=payment_id,
                payment_id=payment_id,
                payment_date=payment_date,
                billing_cycle="Monthly",
                payment_method="PayFast",
                old_tier=old_tier
            )
            if subscription_pdf:
                pdf_base64 = base64.b64encode(subscription_pdf).decode('utf-8')
                date_str = payment_date.strftime("%Y%m%d") if payment_date else datetime.now().strftime("%Y%m%d")
                attachments.append({
                    'filename': f'subscription_{new_tier}_{date_str}.pdf',
                    'content': pdf_base64,
                    'contentType': 'application/pdf'
                })
                print(f"✅ [UPGRADE EMAIL] Subscription PDF attached as fallback ({len(subscription_pdf)} bytes)")
            else:
                print(f"⚠️ [UPGRADE EMAIL] Both invoice and subscription PDF generation failed, continuing without attachment")
                print(f"   Check generate_invoice_pdf() and generate_subscription_pdf() logs for details")
    except Exception as e:
        print(f"❌ [UPGRADE EMAIL] Error generating PDF attachment: {e}")
        import traceback
        traceback.print_exc()
        # Continue without attachments if PDF generation fails
    
    return send_email(user_email, subject, html_content, text_content, attachments if attachments else None)

