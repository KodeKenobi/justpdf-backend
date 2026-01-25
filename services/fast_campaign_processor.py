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

                    # NEW: Detect hubspot / embedded forms
                    hubspot_divs = self.page.query_selector_all('div.hs-form, div.hs-form-iframe, iframe[src*="hsforms"]')
                    if hubspot_divs:
                        self.log('success', 'HubSpot Form Found', f'Found {len(hubspot_divs)} hubspot form containers')
                        self.log_for_live_scraper('HubSpot form detection', 'div.hs-form / iframe[src*="hsforms"]',
                                                 'HubSpot embedded form detection', True)

                        # Try filling using input search inside entire page
                        form_result = self.fill_and_submit_form_by_inputs('contact_page')
                        if form_result['success']:
                            result.update(form_result)
                            result['method'] = 'hubspot_form_detected'
                            self.found_form = True
                            return result

                    # Check for form inside iframe
                    iframes = self.page.query_selector_all('iframe')
                    if iframes:
                        self.log('info', 'Iframes Found', f'Checking {min(len(iframes), 3)} iframe(s)...')
                        for idx, iframe in enumerate(iframes[:3]):
                            frame = iframe.content_frame()
                            if frame:
                                iframe_forms = frame.query_selector_all('form')
                                if iframe_forms:
                                    self.log('success', 'Iframe Form Found', f'Found form in iframe {idx + 1}')
                                    self.log_for_live_scraper('Iframe form check', 'iframe form',
                                                             'Check iframe content frames for embedded forms', True)
                                    result['success'] = True
                                    result['method'] = 'form_in_iframe'
                                    result['error'] = 'Form found in iframe - may require manual submission'
                                    return result

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
                            return result
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

    def fill_and_submit_form_by_inputs(self, location: str) -> Dict:
        """
        New: Fill form using inputs across page (works for hubspot and JS forms without <form>)
        """
        try:
            self.log('info', 'Form Filling (Input Scan)', f'Starting input scan on {location}')

            inputs = self.page.query_selector_all('input, textarea, select')

            filled_count = 0
            email_filled = False
            message_filled = False

            message = self.replace_variables(self.message_template)

            for input_element in inputs:
                try:
                    input_type = input_element.get_attribute('type') or 'text'
                    name = (input_element.get_attribute('name') or '').lower()
                    placeholder = (input_element.get_attribute('placeholder') or '').lower()
                    input_id = (input_element.get_attribute('id') or '').lower()
                    field_text = f"{name} {placeholder} {input_id}"

                    if input_type in ['hidden', 'submit', 'button']:
                        continue

                    if not email_filled and (input_type == 'email' or 'email' in field_text or 'e-mail' in field_text):
                        email = self.company.get('contact_email', 'contact@business.com')
                        input_element.fill(email)
                        email_filled = True
                        filled_count += 1
                        continue

                    if 'phone' in field_text or 'tel' in field_text or input_type == 'tel':
                        if self.company.get('phone'):
                            input_element.fill(self.company['phone'])
                            filled_count += 1
                        continue

                    if 'subject' in field_text or 'topic' in field_text:
                        input_element.fill(self.subject)
                        filled_count += 1
                        continue

                    if input_element.evaluate('el => el.tagName.toLowerCase()') == 'textarea':
                        if not message_filled and any(kw in field_text for kw in ['message', 'comment', 'inquiry', 'details', 'body']):
                            input_element.fill(message)
                            message_filled = True
                            filled_count += 1
                            continue

                except:
                    continue

            if not (email_filled and message_filled):
                self.log('warning', 'Form Incomplete', f'Could not fill required fields (email: {email_filled}, message: {message_filled})')
                return {
                    'success': False,
                    'error': 'Could not fill required form fields',
                    'fields_filled': filled_count
                }

            self.log('success', 'Form Filled', f'Filled {filled_count} fields successfully')

            # Submit using any visible button
            submit_success = self.submit_form_by_click()

            if submit_success:
                self.log('success', 'Form Submitted', 'Form submission successful')
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

    def submit_form_by_click(self) -> bool:
        """Submit by clicking the first visible submit-like button on page"""
        try:
            submit_buttons = self.page.query_selector_all('button, input[type="submit"]')

            for btn in submit_buttons:
                text = (btn.text_content() or '').lower()
                if any(k in text for k in ['send', 'submit', 'contact', 'get in touch', 'enquire']):
                    btn.click()
                    self.page.wait_for_timeout(2000)
                    return True

            return False

        except:
            return False

    # ... rest of your code unchanged ...
