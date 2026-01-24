"""
Fast Campaign Processor
Based on fast-contact-analyzer.js logic with form submission and email fallback
Optimized for speed - stops after finding ONE contact method per site
"""

import re
import time
import os
from typing import Dict, List, Optional, Tuple


class FastCampaignProcessor:
    """Fast, optimized campaign processing with early exit strategy"""

    def __init__(self, page, company_data: Dict, message_template: str, 
                 campaign_id: int = None, company_id: int = None, logger=None):
        self.page = page
        self.company = company_data
        self.message_template = message_template
        self.campaign_id = campaign_id
        self.company_id = company_id
        self.logger = logger
        self.found_form = False
        self.found_contact_page = False

    def log(self, level: str, action: str, message: str):
        """Log with live scraper educational format"""
        if self.logger:
            self.logger(level, action, message)
        else:
            print(f"[{level}] {action}: {message}")

    def log_for_live_scraper(self, method: str, selector: str, reason: str, success: bool):
        """Educational logging for live scraper"""
        icon = '✅' if success else '❌'
        message = f"LIVE_SCRAPER: {icon} Method: {method} | Selector: \"{selector}\" | {reason}"
        self.log('info', 'LIVE_SCRAPER', message)

    def process_company(self) -> Dict:
        """
        Main processing method using fast-contact-analyzer.js strategy
        Returns early after finding ONE contact method
        """
        result = {
            'success': False,
            'method': 'no_contact_found',
            'error': None,
            'contact_info': None,
            'fields_filled': 0,
            'screenshot_url': None
        }

        try:
            website_url = self.company['website_url']
            
            # STRATEGY 1: Check homepage for forms FIRST (fastest)
            self.log('info', 'Strategy 1', 'Checking homepage for forms - fastest method')
            homepage_forms = self.page.query_selector_all('form')
            
            if homepage_forms:
                self.log('success', 'Homepage Forms', f'Found {len(homepage_forms)} form(s) on homepage')
                self.log_for_live_scraper('Homepage form check', 'form', 
                                         'Direct form detection on homepage - fastest method', True)
                
                # Try to fill and submit first form
                form_result = self.fill_and_submit_form(homepage_forms[0], 'homepage')
                if form_result['success']:
                    result.update(form_result)
                    result['method'] = 'form_submitted_homepage'
                    self.found_form = True
                    return result  # EARLY EXIT - found and submitted form
            
            # STRATEGY 2: Find contact link and navigate
            self.log('info', 'Strategy 2', 'No form on homepage, searching for contact link...')
            contact_link = self.find_contact_link()
            
            if contact_link:
                self.log('success', 'Contact Link Found', f'Found: {contact_link}')
                self.log_for_live_scraper('Contact link search', 'a[href*="contact"]', 
                                         'Search links with "contact" in href or text', True)
                
                try:
                    self.page.goto(contact_link, wait_until='domcontentloaded', timeout=15000)
                    self.handle_cookie_modal()
                    self.page.wait_for_timeout(500)
                    
                    # Check for form on contact page
                    contact_page_forms = self.page.query_selector_all('form')
                    if contact_page_forms:
                        self.log('success', 'Contact Page Forms', f'Found {len(contact_page_forms)} form(s)')
                        self.log_for_live_scraper('Contact page form check', 'form', 
                                                 'Check for form after navigating to contact page', True)
                        
                        form_result = self.fill_and_submit_form(contact_page_forms[0], 'contact_page')
                        if form_result['success']:
                            result.update(form_result)
                            result['method'] = 'form_submitted_contact_page'
                            self.found_form = True
                            return result  # EARLY EXIT - found and submitted form
                    else:
                        # No form but on contact page - extract emails
                        self.log('info', 'Contact Page Only', 'No form found, extracting contact info')
                        contact_info = self.extract_contact_info()
                        
                        if contact_info and contact_info.get('emails'):
                            self.log('success', 'Email Found', f"Found {len(contact_info['emails'])} email(s)")
                            
                            # SEND EMAIL DIRECTLY
                            email_sent = self.send_email_to_contact(contact_info['emails'][0])
                            
                            if email_sent:
                                result['success'] = True
                                result['method'] = 'email_sent'
                                result['contact_info'] = contact_info
                                self.log('success', 'Email Sent', f"Successfully sent email to {contact_info['emails'][0]}")
                                return result  # EARLY EXIT - email sent
                            else:
                                result['success'] = True  # Found contact info even if email failed
                                result['method'] = 'contact_page_only'
                                result['contact_info'] = contact_info
                                self.log('info', 'Email Not Sent', 'Contact info found but email sending disabled/failed')
                                return result
                        else:
                            result['method'] = 'contact_page_no_email'
                            result['error'] = 'Contact page found but no email addresses'
                            return result
                            
                except Exception as e:
                    self.log('error', 'Contact Page Navigation', f'Failed: {str(e)}')
                    result['error'] = f'Contact page navigation failed: {str(e)}'
            
            # STRATEGY 3: Check iframes (last resort)
            self.log('info', 'Strategy 3', 'Checking iframes for embedded forms...')
            iframes = self.page.query_selector_all('iframe')
            
            if iframes:
                self.log('info', 'Iframes Found', f'Checking {min(len(iframes), 2)} iframe(s)...')
                
                for idx, iframe in enumerate(iframes[:2]):  # Limit to 2 iframes
                    try:
                        frame = iframe.content_frame()
                        if frame:
                            iframe_forms = frame.query_selector_all('form')
                            if iframe_forms:
                                self.log('success', 'Iframe Form Found', f'Found form in iframe {idx + 1}')
                                self.log_for_live_scraper('Iframe form check', 'iframe form', 
                                                         'Check iframe content frames for embedded forms', True)
                                
                                # Note: Filling iframe forms is complex, mark as found but may need manual review
                                result['success'] = True
                                result['method'] = 'form_in_iframe'
                                result['error'] = 'Form found in iframe - may require manual submission'
                                return result
                    except Exception as e:
                        continue  # Cross-origin iframe, skip
            
            # NO CONTACT FOUND
            self.log('error', 'No Contact Found', 'No forms or contact pages detected')
            self.log_for_live_scraper('No contact found', 'N/A', 
                                     'No forms or contact pages detected - website may not have contact mechanism', False)
            result['error'] = 'No contact form or page found'
            
        except Exception as e:
            self.log('error', 'Processing Error', str(e))
            result['error'] = str(e)
        
        return result

    def find_contact_link(self) -> Optional[str]:
        """Find contact page link using fast evaluation"""
        try:
            base_url = self.company['website_url']
            
            contact_links = self.page.evaluate("""
                (baseUrl) => {
                    const links = Array.from(document.querySelectorAll('a'));
                    const found = [];
                    
                    for (const link of links) {
                        const href = (link.getAttribute('href') || '').toLowerCase();
                        const text = (link.textContent || '').toLowerCase();
                        
                        if ((href.includes('contact') || text.includes('contact') || 
                             text.includes('get in touch') || text.includes('reach out')) &&
                            link.offsetParent !== null) {
                            
                            let fullUrl = link.getAttribute('href');
                            if (fullUrl && !fullUrl.startsWith('http')) {
                                try {
                                    fullUrl = new URL(fullUrl, baseUrl).href;
                                } catch {
                                    continue;
                                }
                            }
                            if (fullUrl && fullUrl.startsWith('http')) {
                                found.push(fullUrl);
                            }
                        }
                    }
                    
                    return [...new Set(found)].slice(0, 1);
                }
            """, base_url)
            
            return contact_links[0] if contact_links else None
            
        except Exception as e:
            self.log('error', 'Contact Link Search', str(e))
            return None

    def handle_cookie_modal(self):
        """Quick cookie modal handling"""
        quick_selectors = [
            'button:has-text("Accept")',
            'button:has-text("Accept All")',
            '#accept-cookies',
            '.cookie-accept'
        ]
        
        for selector in quick_selectors:
            try:
                element = self.page.locator(selector).first
                if element.is_visible(timeout=500):
                    element.click()
                    self.page.wait_for_timeout(200)
                    return True
            except:
                continue
        return False

    def extract_contact_info(self) -> Optional[Dict]:
        """Extract emails and phones from page"""
        try:
            contact_info = {}
            
            # Extract emails
            page_text = self.page.text_content() or ''
            email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
            emails = re.findall(email_pattern, page_text)
            
            if emails:
                # Filter out common non-contact emails
                filtered_emails = [e for e in emails if not any(
                    skip in e.lower() for skip in ['example.com', 'test.', 'noreply', 'no-reply', 'wixpress', 'sentry.io']
                )]
                contact_info['emails'] = list(set(filtered_emails))[:5]  # Limit to 5
            
            # Extract phones (basic pattern)
            phone_pattern = r'\+?[\d\s\-\(\)]{10,}'
            phones = re.findall(phone_pattern, page_text)
            if phones:
                contact_info['phones'] = list(set(phones))[:3]  # Limit to 3
            
            return contact_info if contact_info else None
            
        except Exception as e:
            self.log('error', 'Contact Info Extraction', str(e))
            return None

    def fill_and_submit_form(self, form, location: str) -> Dict:
        """Fill and submit form with smart field detection"""
        try:
            self.log('info', 'Form Filling', f'Starting form fill on {location}')
            
            # Check for CAPTCHA first
            if self.detect_captcha(form):
                self.log('warning', 'CAPTCHA Detected', 'Form has CAPTCHA - cannot auto-submit')
                return {
                    'success': False,
                    'error': 'CAPTCHA detected',
                    'method': 'form_with_captcha'
                }
            
            # Get all inputs and textareas
            inputs = form.query_selector_all('input, textarea')
            
            filled_count = 0
            email_filled = False
            message_filled = False
            
            # Prepare message
            message = self.replace_variables(self.message_template)
            
            for input_element in inputs:
                try:
                    input_type = input_element.get_attribute('type') or 'text'
                    name = (input_element.get_attribute('name') or '').lower()
                    placeholder = (input_element.get_attribute('placeholder') or '').lower()
                    input_id = (input_element.get_attribute('id') or '').lower()
                    
                    field_text = f"{name} {placeholder} {input_id}"
                    
                    # Skip hidden, submit, button fields
                    if input_type in ['hidden', 'submit', 'button']:
                        continue
                    
                    # Fill name field
                    if not email_filled and any(kw in field_text for kw in ['name', 'full-name', 'fullname', 'your-name']):
                        input_element.fill(self.company.get('contact_person', 'Business Contact'))
                        filled_count += 1
                        self.log('info', 'Field Filled', f'Name field filled')
                        continue
                    
                    # Fill email field
                    if not email_filled and (input_type == 'email' or 'email' in field_text or 'e-mail' in field_text):
                        email = self.company.get('contact_email', 'contact@business.com')
                        input_element.fill(email)
                        email_filled = True
                        filled_count += 1
                        self.log('info', 'Field Filled', f'Email field filled')
                        continue
                    
                    # Fill phone field
                    if 'phone' in field_text or 'tel' in field_text or input_type == 'tel':
                        if self.company.get('phone'):
                            input_element.fill(self.company['phone'])
                            filled_count += 1
                            self.log('info', 'Field Filled', f'Phone field filled')
                        continue
                    
                    # Fill subject field
                    if 'subject' in field_text or 'topic' in field_text:
                        input_element.fill('Partnership Inquiry')
                        filled_count += 1
                        self.log('info', 'Field Filled', f'Subject field filled')
                        continue
                    
                    # Fill message/comment textarea
                    tag_name = input_element.evaluate('el => el.tagName.toLowerCase()')
                    if tag_name == 'textarea':
                        if not message_filled and any(kw in field_text for kw in ['message', 'comment', 'inquiry', 'details', 'body']):
                            input_element.fill(message)
                            message_filled = True
                            filled_count += 1
                            self.log('info', 'Field Filled', f'Message field filled')
                            continue
                            
                except Exception as e:
                    self.log('warning', 'Field Fill Failed', f'Field error: {str(e)}')
                    continue
            
            # Require at least email and message to be filled
            if not (email_filled and message_filled):
                self.log('warning', 'Form Incomplete', f'Could not fill required fields (email: {email_filled}, message: {message_filled})')
                return {
                    'success': False,
                    'error': 'Could not fill required form fields',
                    'fields_filled': filled_count
                }
            
            self.log('success', 'Form Filled', f'Filled {filled_count} fields successfully')
            
            # Submit the form
            submit_success = self.submit_form(form)
            
            if submit_success:
                self.log('success', 'Form Submitted', 'Form submission successful')
                
                # Take screenshot
                screenshot_url = self.take_screenshot(f'submit_{location}')
                
                return {
                    'success': True,
                    'fields_filled': filled_count,
                    'screenshot_url': screenshot_url
                }
            else:
                return {
                    'success': False,
                    'error': 'Form submission failed',
                    'fields_filled': filled_count
                }
                
        except Exception as e:
            self.log('error', 'Form Fill Error', str(e))
            return {
                'success': False,
                'error': f'Form processing error: {str(e)}'
            }

    def submit_form(self, form) -> bool:
        """Submit form and verify success"""
        try:
            # Find submit button
            submit_selectors = [
                'button[type="submit"]',
                'input[type="submit"]',
                'button:has-text("Send")',
                'button:has-text("Submit")',
                'button:has-text("Contact")',
                'button:has-text("Get in Touch")'
            ]
            
            submit_button = None
            for selector in submit_selectors:
                try:
                    submit_button = form.query_selector(selector)
                    if submit_button and submit_button.is_visible():
                        break
                except:
                    continue
            
            if not submit_button:
                # Try finding any button within form
                submit_button = form.query_selector('button')
            
            if submit_button:
                # Click and wait for response
                submit_button.click()
                self.page.wait_for_timeout(2000)  # Wait for submission
                
                # Check for success indicators
                success_indicators = [
                    'thank',
                    'success',
                    'received',
                    'sent',
                    'submitted',
                    'will be in touch',
                    'get back to you',
                    'message has been sent'
                ]
                
                page_text = self.page.text_content().lower()
                if any(indicator in page_text for indicator in success_indicators):
                    self.log('success', 'Success Indicator', 'Success message detected on page')
                    return True
                
                # If no clear success message, assume success if no error
                self.log('info', 'Submission Complete', 'No error detected, assuming success')
                return True
            else:
                self.log('warning', 'No Submit Button', 'Could not find submit button')
                return False
            
        except Exception as e:
            self.log('error', 'Form Submit Error', str(e))
            return False

    def detect_captcha(self, form) -> bool:
        """Detect CAPTCHA in form"""
        try:
            captcha_selectors = [
                '[class*="captcha" i]',
                '[id*="captcha" i]',
                'iframe[src*="recaptcha"]',
                'iframe[src*="hcaptcha"]',
                '.g-recaptcha',
                '.h-captcha',
                '[data-sitekey]'
            ]
            
            for selector in captcha_selectors:
                try:
                    element = form.query_selector(selector)
                    if element:
                        return True
                except:
                    continue
            
            # Also check page-level (outside form)
            for selector in captcha_selectors:
                try:
                    element = self.page.query_selector(selector)
                    if element:
                        return True
                except:
                    continue
            
            return False
        except:
            return False

    def send_email_to_contact(self, email_address: str) -> bool:
        """
        Send email directly to found contact email using existing email service
        Uses your existing Resend email service (no additional configuration needed!)
        """
        try:
            # Import your existing email service
            from email_service import send_email
            
            # Create message
            message_content = self.replace_variables(self.message_template)
            company_name = self.company.get('company_name', 'your company')
            
            # Create HTML email content
            html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 600px;
            margin: 0 auto;
            padding: 20px;
        }}
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            border-radius: 10px 10px 0 0;
            text-align: center;
        }}
        .content {{
            background: #f9f9f9;
            padding: 30px;
            border-radius: 0 0 10px 10px;
        }}
        .message {{
            background: white;
            padding: 20px;
            border-radius: 8px;
            margin: 20px 0;
            border-left: 4px solid #667eea;
        }}
        .footer {{
            text-align: center;
            color: #999;
            font-size: 12px;
            margin-top: 30px;
            padding-top: 20px;
            border-top: 1px solid #ddd;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h2 style="margin: 0;">Partnership Inquiry</h2>
    </div>
    <div class="content">
        <p>Hello,</p>
        
        <div class="message">
            {message_content.replace(chr(10), '<br>')}
        </div>
        
        <p>Best regards,<br>
        <strong>Campaign Team</strong></p>
        
        <div class="footer">
            <p>This is an automated campaign message from Trevnoctilla.<br>
            If you'd prefer not to receive these messages, please reply to let us know.</p>
        </div>
    </div>
</body>
</html>
"""
            
            # Create plain text version
            text_content = f"""Hello,

{message_content}

Best regards,
Campaign Team

---
This is an automated campaign message.
If you'd prefer not to receive these messages, please reply to let us know.
"""
            
            subject = f"Partnership Inquiry - {company_name}"
            
            self.log('info', 'Sending Email', f'Using existing email service to send to {email_address}')
            
            # Use your existing email service
            success = send_email(
                to_email=email_address,
                subject=subject,
                html_content=html_content,
                text_content=text_content
            )
            
            if success:
                self.log('success', 'Email Sent', f'Email sent to {email_address} via Resend')
                return True
            else:
                self.log('warning', 'Email Send Failed', 'Email service returned False - check logs')
                return False
            
        except ImportError as e:
            self.log('error', 'Email Service Not Found', f'Could not import email_service: {e}')
            return False
        except Exception as e:
            self.log('error', 'Email Send Failed', str(e))
            import traceback
            traceback.print_exc()
            return False

    def replace_variables(self, template: str) -> str:
        """Replace variables in message template"""
        message = template
        
        replacements = {
            '{company_name}': self.company.get('company_name', ''),
            '{website_url}': self.company.get('website_url', ''),
            '{contact_email}': self.company.get('contact_email', ''),
            '{contact_person}': self.company.get('contact_person', ''),
            '{phone}': self.company.get('phone', '')
        }
        
        for key, value in replacements.items():
            if value:
                message = message.replace(key, str(value))
        
        return message

    def take_screenshot(self, prefix: str) -> Optional[str]:
        """Take screenshot and return URL"""
        try:
            # Create screenshots directory if it doesn't exist
            screenshot_dir = 'static/screenshots'
            os.makedirs(screenshot_dir, exist_ok=True)
            
            filename = f"{prefix}_{self.company_id}_{int(time.time())}.png"
            filepath = os.path.join(screenshot_dir, filename)
            
            self.page.screenshot(path=filepath, full_page=False)
            
            # Return URL (adjust based on your static file serving)
            return f"/screenshots/{filename}"
            
        except Exception as e:
            self.log('error', 'Screenshot Failed', str(e))
            return None
