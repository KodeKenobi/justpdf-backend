"""
Advanced Contact Detection and Form Submission System
Implements 6-method contact detection based on intelligent analysis
"""

import re
import time

class AdvancedContactDetector:
    """Advanced contact detection using multiple methods"""

    def __init__(self, page, company_data, message_template, campaign_id=None, company_id=None, logger=None):
        self.page = page
        self.company = company_data
        self.message_template = message_template
        self.campaign_id = campaign_id
        self.company_id = company_id
        self.logger = logger

    def log(self, level, action, message):
        """Log messages"""
        if self.logger:
            self.logger(level, action, message)
        else:
            print(f"[{level}] {action}: {message}")

    def detect_and_submit(self):
        """
        Main detection and submission method using 6 detection approaches
        Returns: {'success': bool, 'method': str, 'result': dict}
        """

        # ===== METHOD 1: HOMEPAGE FORM CHECK (FASTEST) =====
        self.log('info', 'Method 1: Homepage Form Check', 'Direct form detection on homepage - fastest method')

        homepage_forms = self.page.query_selector_all('form')
        if homepage_forms:
            self.log('success', 'Homepage Forms Found', f'Found {len(homepage_forms)} form(s) on homepage')

            # Try to identify and fill contact forms
            contact_form = self.identify_contact_form(homepage_forms)
            if contact_form:
                result = self.fill_and_submit_form(contact_form)
                if result and result['success']:
                    return result

        # ===== METHOD 2: CONTACT LINK SEARCH =====
        self.log('info', 'Method 2: Contact Link Search', 'Searching for contact page links with regex patterns')

        contact_links = self.find_contact_links()
        if contact_links:
            self.log('success', 'Contact Links Found', f'Found {len(contact_links)} contact link(s)')

            for link_url in contact_links[:3]:  # Try first 3 links
                try:
                    self.log('info', 'Contact Page Navigation', f'Navigating to: {link_url}')
                    self.page.goto(link_url, wait_until='networkidle', timeout=20000)
                    self.page.wait_for_timeout(1000)

                    # ===== METHOD 3: CONTACT PAGE FORM CHECK =====
                    self.log('info', 'Method 3: Contact Page Form Check', 'Checking for forms after navigating to contact page')

                    contact_page_forms = self.page.query_selector_all('form')
                    if contact_page_forms:
                        self.log('success', 'Contact Page Forms Found', f'Found {len(contact_page_forms)} form(s) on contact page')

                        contact_form = self.identify_contact_form(contact_page_forms)
                        if contact_form:
                            result = self.fill_and_submit_form(contact_form)
                            if result and result['success']:
                                return result
                    else:
                        # ===== METHOD 5: CONTACT PAGE ONLY DETECTION =====
                        self.log('info', 'Method 5: Contact Page Only', 'Found contact page but no form - extracting contact information')

                        contact_info = self.extract_contact_info()
                        if contact_info:
                            self.log('success', 'Contact Info Found', 'Contact information extracted from page')
                            return {
                                'success': True,
                                'contact_info_found': True,
                                'contact_info': contact_info,
                                'method': 'contact_page_only'
                            }
                except Exception as e:
                    self.log('warning', 'Contact Link Failed', f'Failed to process {link_url}: {str(e)}')
                    continue

        # ===== METHOD 6: NO CONTACT FOUND =====
        self.log('error', 'Method 6: No Contact Found', 'No forms or contact pages detected - website may not have contact mechanism')

        return {
            'success': False,
            'error': 'No contact form or page found',
            'method': 'no_contact_found'
        }

    def find_contact_links(self):
        """Method 2: Find contact page links using regex patterns"""
        try:
            # Get all links on the page
            links = self.page.query_selector_all('a[href]')
            contact_urls = []

            for link in links:
                try:
                    href = link.get_attribute('href')
                    text = (link.text_content() or '').lower().strip()

                    if not href:
                        continue

                    # Convert relative URLs to absolute
                    if not href.startswith('http'):
                        href = f"{self.company['website_url'].rstrip('/')}/{href.lstrip('/')}"

                    # Check for contact keywords in href or text
                    contact_keywords = ['contact', 'contact-us', 'get-in-touch', 'reach-us', 'touch']
                    if any(keyword in href.lower() or keyword in text for keyword in contact_keywords):
                        if href not in contact_urls:
                            contact_urls.append(href)

                except Exception as e:
                    continue

            return contact_urls[:5]  # Return top 5 matches

        except Exception as e:
            print(f"Error finding contact links: {e}")
            return []

    def identify_contact_form(self, forms):
        """Identify which form is most likely a contact form"""
        try:
            best_form = None
            best_score = 0

            for form in forms:
                try:
                    score = 0

                    # Check form attributes
                    form_id = (form.get_attribute('id') or '').lower()
                    form_class = (form.get_attribute('class') or '').lower()
                    form_action = (form.get_attribute('action') or '').lower()

                    # Score based on contact-related keywords
                    contact_keywords = ['contact', 'inquiry', 'message', 'email', 'form']
                    for keyword in contact_keywords:
                        if keyword in form_id or keyword in form_class or keyword in form_action:
                            score += 10

                    # Check form fields
                    inputs = form.query_selector_all('input, textarea, select')
                    email_count = 0
                    message_count = 0

                    for inp in inputs:
                        try:
                            input_type = inp.get_attribute('type') or 'text'
                            name = (inp.get_attribute('name') or '').lower()
                            placeholder = (inp.get_attribute('placeholder') or '').lower()

                            if input_type == 'email' or 'email' in name or 'email' in placeholder:
                                email_count += 1
                                score += 5

                            if inp.tag_name.lower() == 'textarea' or 'message' in name or 'comment' in placeholder:
                                message_count += 1
                                score += 5

                            if 'name' in name or 'subject' in name:
                                score += 3

                        except Exception as e:
                            continue

                    # Bonus for having both email and message fields
                    if email_count > 0 and message_count > 0:
                        score += 10

                    # Prefer forms with more contact-relevant fields
                    if score > best_score:
                        best_score = score
                        best_form = form

                except Exception as e:
                    continue

            return best_form

        except Exception as e:
            print(f"Error identifying contact form: {e}")
            return None

    def extract_contact_info(self):
        """Method 5: Extract contact information from page when no form exists"""
        try:
            contact_info = {}

            # Extract email addresses using regex
            page_text = self.page.text_content()
            email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
            emails = re.findall(email_pattern, page_text)

            if emails:
                contact_info['emails'] = list(set(emails))  # Remove duplicates

            # Extract phone numbers (basic pattern)
            phone_pattern = r'\b(?:\+?1[-.\s]?)?\(?([0-9]{3})\)?[-.\s]?([0-9]{3})[-.\s]?([0-9]{4})\b'
            phones = re.findall(phone_pattern, page_text)

            if phones:
                formatted_phones = []
                for phone in phones:
                    if isinstance(phone, tuple):
                        formatted_phones.append(f"({phone[0]}) {phone[1]}-{phone[2]}")
                    else:
                        formatted_phones.append(phone)
                contact_info['phones'] = list(set(formatted_phones))

            # Look for social media links
            social_links = []
            social_selectors = [
                'a[href*="linkedin.com"]',
                'a[href*="twitter.com"]',
                'a[href*="facebook.com"]',
                'a[href*="instagram.com"]'
            ]

            for selector in social_selectors:
                try:
                    links = self.page.query_selector_all(selector)
                    for link in links:
                        href = link.get_attribute('href')
                        if href and href not in social_links:
                            social_links.append(href)
                except Exception as e:
                    continue

            if social_links:
                contact_info['social_links'] = social_links

            return contact_info if contact_info else None

        except Exception as e:
            print(f"Error extracting contact info: {e}")
            return None

    def fill_and_submit_form(self, form):
        """Fill and submit a contact form with comprehensive field detection"""
        try:
            self.log('info', 'Form Filling Started', 'Beginning intelligent form filling process')

            # Analyze form structure
            form_data = self.analyze_form_structure(form)
            self.log('info', 'Form Analysis Complete', f'Found {len(form_data["fields"])} fields to fill')

            # Check for CAPTCHA first
            captcha_detected = self.detect_captcha(form)
            if captcha_detected:
                self.log('warning', 'CAPTCHA Detected', 'Form contains CAPTCHA - manual intervention required')
                return {
                    'success': False,
                    'error': 'CAPTCHA detected on form',
                    'status': 'captcha',
                    'method': 'form_with_captcha'
                }

            # Fill form fields
            filled_fields = 0

            for field in form_data['fields']:
                try:
                    field_value = self.generate_field_value(field)
                    success = self.fill_field(form, field, field_value)
                    if success:
                        filled_fields += 1
                        self.log('success', 'Field Filled', f'✓ {field["type"]}: {field_value[:50]}...')

                except Exception as e:
                    self.log('warning', 'Field Fill Failed', f'Failed to fill field {field.get("name", "unknown")}: {str(e)}')
                    continue

            if filled_fields == 0:
                self.log('warning', 'No Fields Filled', 'Form analysis found no suitable fields to fill')
                return {
                    'success': False,
                    'error': 'No suitable fields found to fill',
                    'method': 'form_no_fields'
                }

            # Submit the form
            self.log('info', 'Form Submission', f'Attempting to submit form with {filled_fields} filled fields')

            submit_success = self.submit_form(form)

            if submit_success:
                self.log('success', 'Form Submitted', 'Form submission successful - success message detected')
                return {
                    'success': True,
                    'status': 'completed',
                    'method': 'form_submitted',
                    'fields_filled': filled_fields
                }
            else:
                return {
                    'success': False,
                    'error': 'Form submission failed or unclear result',
                    'status': 'failed',
                    'method': 'form_submit_failed',
                    'fields_filled': filled_fields
                }

        except Exception as e:
            self.log('error', 'Form Filling Failed', f'Critical error: {str(e)}')
            return {
                'success': False,
                'error': f'Form processing error: {str(e)}',
                'status': 'failed',
                'method': 'form_error'
            }

    def detect_captcha(self, form):
        """Detect CAPTCHA elements in the form"""
        try:
            # Check for common CAPTCHA indicators
            captcha_selectors = [
                '.recaptcha', '#captcha', '.hcaptcha',
                '.captcha', '.recaptcha-checkbox',
                'iframe[src*="recaptcha"]',
                'iframe[src*="hcaptcha"]'
            ]

            for selector in captcha_selectors:
                try:
                    if form.query_selector(selector):
                        return True
                except:
                    continue

            return False

        except Exception as e:
            print(f"CAPTCHA detection error: {e}")
            return False

    def analyze_form_structure(self, form):
        """Extract detailed form structure for intelligent filling"""
        try:
            form_data = {
                'id': form.get_attribute('id'),
                'class': form.get_attribute('class'),
                'action': form.get_attribute('action'),
                'method': form.get_attribute('method') or 'post',
                'fields': []
            }

            # Analyze all input fields
            inputs = form.query_selector_all('input, textarea, select')

            for inp in inputs:
                try:
                    field_data = {
                        'tag': inp.tag_name.lower(),
                        'type': inp.get_attribute('type') or ('textarea' if inp.tag_name.lower() == 'textarea' else 'text'),
                        'name': inp.get_attribute('name'),
                        'id': inp.get_attribute('id'),
                        'placeholder': inp.get_attribute('placeholder'),
                        'required': inp.get_attribute('required') is not None,
                        'value': inp.get_attribute('value')
                    }

                    # Additional analysis for select fields
                    if field_data['tag'] == 'select':
                        options = inp.query_selector_all('option')
                        field_data['options'] = [opt.text_content().strip() for opt in options if opt.text_content().strip()]

                    form_data['fields'].append(field_data)

                except Exception as e:
                    continue

            return form_data

        except Exception as e:
            print(f"Error analyzing form structure: {e}")
            return {'fields': []}

    def generate_field_value(self, field):
        """Generate appropriate field values based on field type and context"""
        try:
            field_name = (field.get('name') or '').lower()
            field_type = field.get('type', 'text')
            placeholder = (field.get('placeholder') or '').lower()

            # Email field
            if field_type == 'email' or 'email' in field_name or 'email' in placeholder:
                return self.company.get('contact_email', 'contact@example.com')

            # Name field
            elif 'name' in field_name or 'name' in placeholder:
                return self.company.get('company_name', 'Test Company')

            # Phone field
            elif field_type == 'tel' or 'phone' in field_name or 'tel' in placeholder:
                return self.company.get('phone', '+1-555-0123')

            # Subject field
            elif 'subject' in field_name or 'topic' in placeholder:
                return f"Inquiry from {self.company.get("company_name", "Company")}"

            # Message/textarea field
            elif field_type == 'textarea' or field['tag'] == 'textarea' or 'message' in field_name or 'comment' in placeholder:
                # Apply variable substitution to message template
                message = self.message_template
                message = message.replace('{company_name}', self.company.get('company_name', 'Company'))
                message = message.replace('{website_url}', self.company.get('website_url', 'https://example.com'))
                message = message.replace('{contact_email}', self.company.get('contact_email', 'contact@example.com'))
                return message

            # URL field
            elif field_type == 'url' or 'website' in field_name:
                return self.company.get('website_url', 'https://example.com')

            # Number field
            elif field_type == 'number':
                if 'age' in placeholder or 'year' in field_name:
                    return '30'
                elif 'budget' in placeholder or 'price' in field_name:
                    return '50000'
                else:
                    return '1'

            # Default fallback
            else:
                return self.company.get('company_name', 'Test Company')

        except Exception as e:
            print(f"Error generating field value: {e}")
            return 'Test Value'

    def fill_field(self, form, field, value):
        """Fill a specific form field"""
        try:
            selector = f'[name="{field["name"]}"]' if field.get('name') else f'#{field["id"]}' if field.get('id') else None
            if not selector:
                return False

            element = form.query_selector(selector)
            if not element or not element.is_visible():
                return False

            field_type = field.get('type', 'text')

            if field_type in ['text', 'email', 'tel', 'url', 'search']:
                element.fill(value)
                return True

            elif field_type == 'textarea' or field.get('tag') == 'textarea':
                element.fill(value)
                return True

            elif field_type == 'select':
                # Try to select a reasonable option
                options = element.query_selector_all('option')
                if len(options) > 1:
                    options[1].click()  # Select second option
                    return True

            elif field_type == 'checkbox':
                element.check()
                return True

            elif field_type == 'radio':
                element.check()
                return True

            return False

        except Exception as e:
            print(f"Error filling field {field.get('name', 'unknown')}: {e}")
            return False

    def submit_form(self, form):
        """Submit the form and check for success"""
        try:
            submit_buttons = form.query_selector_all('input[type="submit"], button[type="submit"], button:not([type])')

            for button in submit_buttons:
                try:
                    button.click()
                    self.page.wait_for_timeout(3000)  # Wait for submission

                    # Check for success indicators
                    success_indicators = [
                        'thank you', 'success', 'submitted', 'sent',
                        'message received', 'inquiry submitted', 'form submitted'
                    ]

                    page_text = self.page.text_content().lower()
                    if any(indicator in page_text for indicator in success_indicators):
                        return True

                except Exception as e:
                    continue

            return False

        except Exception as e:
            print(f"Error submitting form: {e}")
            return False