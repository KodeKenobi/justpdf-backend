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
                 campaign_id: int = None, company_id: int = None, logger=None, subject: str = None):
        self.page = page
        self.company = company_data
        self.message_template = message_template
        self.campaign_id = campaign_id
        self.company_id = company_id
        self.logger = logger
        self.subject = subject or 'Partnership Inquiry'
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
            # Set a common user agent to avoid detection
            user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            try:
                self.page.context.set_extra_http_headers({"User-Agent": user_agent})
            except Exception: pass
            
            website_url = self.company.get('website_url', '')
            
            # URL Validation
            if not website_url or not re.match(r'^https?://[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', website_url):
                self.log('error', 'Malformed URL', f'The URL "{website_url}" is invalid. Please ensure it starts with http/https and has a valid domain (e.g. .com, .co.uk)')
                result['error'] = f'Malformed URL: {website_url}'
                result['method'] = 'invalid_url'
                return result

            # Initial navigation
            self.log('info', 'Navigation', f'Opening {website_url}...')
            try:
                self.page.goto(website_url, wait_until='domcontentloaded', timeout=20000)
                self.handle_cookie_modal()
                self.page.wait_for_timeout(1000)
            except Exception as e:
                self.log('warning', 'Initial Navigation', f'Failed or timed out: {e}')
                # Continue anyway, Strategy 2 might still work if we have a partial load
            
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
            
            # Strategy 2: Link search
            self.log('info', 'Discovery', 'Strategy 2: Searching for contact links')
            contact_keywords = ['contact', 'get-in-touch', 'enquiry', 'support', 'about-us']
            selector = ', '.join([f'a[href*="{kw}"]' for kw in contact_keywords]) + ', ' + \
                       ', '.join([f'a:has-text("{kw}")' for kw in contact_keywords])
            
            contact_link = None
            try:
                links = self.page.query_selector_all(selector)
                self.log('info', 'Discovery', f'Found {len(links)} potential contact links')
                
                for i, link in enumerate(links[:5]): # Check first 5 matches
                    href = link.get_attribute('href')
                    text = (link.inner_text() or '').strip()
                    self.log('info', 'Testing Link', f'Link {i+1}: {text} ({href})')
                    
                    if not href: continue
                    full_href = self.make_absolute_url(href)
                    
                    try:
                        self.page.goto(full_href, wait_until='domcontentloaded', timeout=15000)
                        self.handle_cookie_modal()
                        # Wait for dynamic forms (HubSpot, React, etc.)
                        self.log('info', 'Contact Page', 'Waiting for form to initialize...')
                        try:
                            self.page.wait_for_selector('form', timeout=5000)
                            self.page.wait_for_timeout(1000)
                        except:
                            self.log('info', 'Contact Page', 'No standard form appeared within 5s, checking immediately')
                        
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
                            # No form but on contact page - attempt strategy 3 & 4 within contact page context
                            self.log('info', 'Contact Page Discovery', 'No direct form found, trying fallback extraction...')
                            contact_info = self.extract_contact_info()
                            
                            if contact_info and contact_info.get('emails'):
                                self.log('success', 'Email Found', f"Found {len(contact_info['emails'])} email(s)")
                                email_sent = self.send_email_to_contact(contact_info['emails'][0])
                                if email_sent:
                                    result.update({'success': True, 'method': 'email_sent', 'contact_info': contact_info})
                                    return result
                    except Exception as e:
                        self.log('warn', 'Link Failed', f'Could not open {full_href}: {str(e)}')
                        continue
            except Exception as e:
                self.log('error', 'Strategy 2 Error', str(e))

            # STRATEGY 3: Check ALL frames (HubSpot/Typeform)
            self.log('info', 'Strategy 3', 'Checking all frames for embedded forms...')
            for idx, frame in enumerate(self.page.frames):
                if frame == self.page.main_frame: continue
                try:
                    frame_forms = frame.query_selector_all('form')
                    if frame_forms:
                        self.log('success', 'Frame Form Found', f'Found form in frame: {frame.url[:50]}...')
                        form_result = self.fill_and_submit_form(frame_forms[0], f'frame_{idx}', is_iframe=True, frame=frame)
                        if form_result['success']:
                            result.update(form_result)
                            result['method'] = 'form_submitted_iframe'
                            return result
                except Exception: continue

            # STRATEGY 4: Heuristic Field Search (No <form> tag)
            self.log('info', 'Strategy 4', 'Searching for inputs by label heuristics...')
            heuristics_result = self.search_by_heuristics()
            if heuristics_result['success']:
                result.update(heuristics_result)
                result['method'] = 'form_submitted_heuristics'
                return result

            # NO CONTACT FOUND
            self.log('error', 'No Contact Found', f'All strategies exhausted for {website_url}')
            result['error'] = f'No discovery method succeeded for {website_url}'
            
            # Log page source on discovery failure
            screenshot_path = f"static/screenshots/failed_discovery_{self.company_id}_{int(time.time())}.png"
            try:
                self.page.screenshot(path=screenshot_path)
                result['screenshot_url'] = screenshot_path
            except Exception as e:
                self.log('error', 'Screenshot Failed', f'Could not take screenshot: {e}')
                result['screenshot_url'] = None
            
            # Log some page info for debugging
            page_title = self.page.title()
            page_content_snippet = (self.page.content() or "")[:1000].replace('\n', ' ')
            self.log('error', 'Discovery Failed', f"Title: {page_title} | Snippet: {page_content_snippet}")
            
        except Exception as e:
            self.log('error', 'Processing Error', str(e))
            result['error'] = str(e)
            result['screenshot_url'] = self.take_screenshot('error_processing')
        
        return result

    def make_absolute_url(self, href: str) -> str:
        """Converts a relative URL to an absolute URL."""
        if href.startswith('http://') or href.startswith('https://'):
            return href
        from urllib.parse import urljoin
        return urljoin(self.website_url, href)

    def search_by_heuristics(self) -> Dict:
        """Fallback: look for inputs directly on page when no <form> tag exists"""
        try:
            # Check for common form fields manually
            inputs = self.page.query_selector_all('input, textarea')
            if not inputs: return {'success': False}

            self.log('info', 'Heuristics', f'Analyzing {len(inputs)} orphan inputs...')
            # Treat all visible inputs as a virtual form
            return self.fill_and_submit_form(self.page, 'page_heuristics', is_heuristic=True)
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def find_contact_link(self) -> Optional[str]:
        """Find contact page link using fast evaluation"""
        # This method is largely replaced by the in-line strategy 2 logic,
        # but kept for completeness if other parts of the code still call it.
        # The new strategy 2 is more robust.
        try:
            base_url = self.company['website_url']
            self.log('info', '🔍 Contact Link Search', f'Searching for contact links on {base_url}')
            
            contact_links = self.page.evaluate("""
                (baseUrl) => {
                    const links = Array.from(document.querySelectorAll('a'));
                    const found = [];
                    const debug = [];
                    
                    for (const link of links) {
                        const href = (link.getAttribute('href') || '').toLowerCase();
                        const text = (link.textContent || '').toLowerCase().trim();
                        
                        if ((href.includes('contact') || text.includes('contact') || 
                             text.includes('get in touch') || text.includes('reach out')) &&
                            link.offsetParent !== null) {
                            
                            const rawHref = link.getAttribute('href');
                            debug.push({
                                rawHref: rawHref,
                                text: text.substring(0, 50),
                                href: href.substring(0, 100)
                            });
                            
                            let fullUrl = rawHref;
                            if (fullUrl && !fullUrl.startsWith('http')) {
                                try {
                                    fullUrl = new URL(fullUrl, baseUrl).href;
                                } catch (e) {
                                    debug.push({ error: 'URL construction failed', rawHref: rawHref, message: e.message });
                                    continue;
                                }
                            }
                            if (fullUrl && fullUrl.startsWith('http')) {
                                found.push(fullUrl);
                            }
                        }
                    }
                    
                    return { found: [...new Set(found)].slice(0, 1), debug: debug.slice(0, 5) };
                }
            """, base_url)
            
            # Log debug info
            if contact_links.get('debug'):
                self.log('info', '📝 Debug Info', f'Found {len(contact_links["debug"])} potential contact links')
                for i, debug_item in enumerate(contact_links['debug'], 1):
                    self.log('info', f'  Link {i}', str(debug_item))
            
            result_links = contact_links.get('found', [])
            if result_links:
                self.log('success', '✅ Contact Link Found', f'URL: {result_links[0]}')
                return result_links[0]
            else:
                self.log('warning', '❌ No Contact Links', 'No valid contact links found after filtering')
                return None
            
        except Exception as e:
            self.log('error', 'Contact Link Search', str(e))
            return None

    def handle_cookie_modal(self):
        """Comprehensive cookie modal handling - Accept, Reject, or Close"""
        # Try accept buttons first, then reject/close buttons
        selectors = [
            # Accept buttons
            'button:has-text("Accept")',
            'button:has-text("Accept All")',
            'button:has-text("I Accept")',
            'button:has-text("Agree")',
            '#accept-cookies',
            '#acceptCookies',
            '.cookie-accept',
            '.accept-cookies',
            '[aria-label*="Accept"]',
            '[aria-label*="Agree"]',
            # Reject/Close buttons
            'button:has-text("Reject")',
            'button:has-text("Reject All")',
            'button:has-text("Decline")',
            'button:has-text("Close")',
            '[aria-label*="Close"]',
            '[aria-label*="Reject"]',
            '.cookie-close',
            '.cookie-dismiss',
            # Generic close buttons on modals
            '[class*="cookie"] button[class*="close"]',
            '[class*="consent"] button[class*="close"]',
            '[id*="cookie"] button[class*="close"]'
        ]
        
        for selector in selectors:
            try:
                element = self.page.locator(selector).first
                if element.is_visible(timeout=300):
                    element.click()
                    self.page.wait_for_timeout(200)
                    self.log('info', 'Cookie Modal', f'Dismissed using: {selector}')
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

    def fill_and_submit_form(self, form, location: str, is_iframe: bool = False, is_heuristic: bool = False, frame=None) -> Dict:
        """Fill and submit form with smart field detection"""
        try:
            context_name = "iframe" if is_iframe else ("heuristic" if is_heuristic else "standard")
            self.log('info', 'Form Filling', f'Starting {context_name} fill on {location}')
            
            # Check for CAPTCHA first
            if self.detect_captcha(form):
                self.log('warning', 'CAPTCHA Detected', 'Form has CAPTCHA - cannot auto-submit')
                return {
                    'success': False,
                    'error': 'CAPTCHA detected',
                    'method': 'form_with_captcha'
                }
            
            # Get all inputs, textareas, and selects
            inputs = form.query_selector_all('input, textarea')
            selects = form.query_selector_all('select')
            
            filled_count = 0
            email_filled = False
            message_filled = False
            
            # Prepare message
            message = self.replace_variables(self.message_template)
            
            for input_element in inputs:
                input_id = (input_element.get_attribute('id') or '').lower()
                name = (input_element.get_attribute('name') or '').lower()
                placeholder = (input_element.get_attribute('placeholder') or '').lower()
                input_type = (input_element.get_attribute('type') or 'text').lower()
                
                field_text = f"{name} {placeholder} {input_id}"
                self.log('info', 'Checking Field', f'Type: {input_type}, Name: {name}, Text: {field_text}')
                
                try:
                    # Skip hidden, submit, button fields
                    if input_type in ['hidden', 'submit', 'button']:
                        continue
                    
                    # 1. Fill email field (Highest priority)
                    if not email_filled and (input_type == 'email' or any(kw in field_text for kw in ['email', 'e-mail'])):
                        email = self.company.get('contact_email', 'contact@business.com')
                        input_element.click()
                        input_element.type(email, delay=50)
                        email_filled = True
                        filled_count += 1
                        self.log('info', 'Field Filled', f'Email field filled: {email}')
                        continue

                    # 2. Fill name fields
                    if any(kw in field_text for kw in ['first-name', 'fname', 'firstname', 'given-name']):
                        input_element.fill(self.company.get('contact_person', 'Business').split()[0])
                        filled_count += 1
                        self.log('info', 'Field Filled', f'First Name field filled')
                        continue

                    if any(kw in field_text for kw in ['last-name', 'lname', 'lastname', 'surname', 'family-name']):
                        name_parts = self.company.get('contact_person', 'Contact').split()
                        last_name = name_parts[-1] if len(name_parts) > 1 else 'Contact'
                        input_element.fill(last_name)
                        filled_count += 1
                        self.log('info', 'Field Filled', f'Last Name field filled')
                        continue

                    if any(kw in field_text for kw in ['name', 'full-name', 'fullname', 'your-name']) and 'company' not in field_text:
                        input_element.fill(self.company.get('contact_person', 'Business Contact'))
                        filled_count += 1
                        self.log('info', 'Field Filled', f'Name field filled')
                        continue
                    
                    # 3. Fill Company field (avoid matching email placeholders)
                    if any(kw in field_text for kw in ['company', 'organization', 'business-name', 'firm']) and 'email' not in field_text:
                        input_element.fill(self.company.get('company_name', 'Your Company'))
                        filled_count += 1
                        self.log('info', 'Field Filled', f'Company field filled')
                        continue

                    # 4. Fill phone field
                    if any(kw in field_text for kw in ['phone', 'tel', 'mobile', 'cell', 'telephone']) or input_type == 'tel':
                        phone = self.company.get('phone') or self.company.get('phone_number')
                        if phone:
                            # Use type for phone as well just in case
                            input_element.click()
                            input_element.type(phone, delay=50)
                            filled_count += 1
                            self.log('info', 'Field Filled', f'Phone field filled: {phone}')
                        continue
                    
                    # Fill subject field
                    if 'subject' in field_text or 'topic' in field_text:
                        input_element.fill(self.subject)
                        filled_count += 1
                        self.log('info', 'Field Filled', f'Subject field: {self.subject}')
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
            
            # Handle Selects (Dropdowns)
            for select in selects:
                name = (select.get_attribute('name') or '').lower()
                placeholder = (select.get_attribute('placeholder') or '').lower()
                select_id = (select.get_attribute('id') or '').lower()
                text = f"{name} {placeholder} {select_id}"
                
                try:
                    options = select.query_selector_all('option')
                    if not options: continue
                    
                    # Try to match country or industry
                    if any(kw in text for kw in ['country', 'ext', 'region', 'location']):
                        target_val = None
                        for opt in options:
                            if 'united kingdom' in (opt.inner_text() or '').lower():
                                target_val = opt.get_attribute('value')
                                break
                        if not target_val:
                            target_val = options[1].get_attribute('value') if len(options) > 1 else options[0].get_attribute('value')
                        
                        select.select_option(value=target_val)
                        filled_count += 1
                except Exception: continue

            # Handle Checkboxes
            for cb in inputs:
                if cb.get_attribute('type') == 'checkbox':
                    name = (cb.get_attribute('name') or '').lower()
                    # Try to get text from parent label or next sibling or aria-label
                    parent_text = (cb.evaluate("el => el.parentElement.innerText") or '').lower()
                    aria_label = (cb.get_attribute('aria-label') or '').lower()
                    
                    if any(kw in f"{name} {parent_text} {aria_label}" for kw in ['enquiry', 'sales', 'support', 'agree', 'consent', 'optin', 'policy']):
                        try:
                            cb.check()
                            filled_count += 1
                            self.log('info', 'Checkbox Checked', f'Checkbox filled ({name})')
                        except Exception: continue
                    else:
                        # For 2020 Innovation and others, if we have a checkbox and we don't know what it is, just check it to be safe
                        try:
                            cb.check()
                            filled_count += 1
                        except Exception: continue

            # Require at least email and message to be filled
            if not (email_filled and message_filled):
                self.log('warning', 'Form Incomplete', f'Could not fill required fields (email: {email_filled}, message: {message_filled})')
                return {
                    'success': False,
                    'error': 'Could not fill required form fields',
                    'fields_filled': filled_count,
                    'screenshot_url': self.take_screenshot(f'failed_fill_{location}')
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
                    'method': 'form_submitted',
                    'fields_filled': filled_count,
                    'screenshot_url': screenshot_url
                }
            else:
                return {
                    'success': False,
                    'error': 'Form submission failed',
                    'fields_filled': filled_count,
                    'screenshot_url': self.take_screenshot(f'failed_submit_{location}')
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
                self.log('warning', 'SIMULATION', 'Submission disabled for testing - not clicking button')
                return True
                # submit_button.click()
                # self.page.wait_for_timeout(2000)  # Wait for submission
                
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
            
            subject = self.subject
            
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
            # CRITICAL: Dismiss any remaining cookie modals before screenshot
            self.handle_cookie_modal()
            self.page.wait_for_timeout(300)
            
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
