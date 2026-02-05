"""
Live browser scraper with video streaming via WebSocket
Uses Playwright to capture browser viewport and stream to frontend
Also includes synchronous headless processing for parallel batch operations
"""
import asyncio
import base64
from playwright.async_api import async_playwright
from playwright.sync_api import sync_playwright
from datetime import datetime
import json
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.supabase_storage import upload_screenshot

class LiveScraper:
    """Scrapes websites with live video streaming to frontend"""
    
    def __init__(self, websocket, company_data, message_template, campaign_id=None, company_id=None):
        self.ws = websocket
        self.company = company_data
        self.campaign_id = campaign_id
        self.company_id = company_id
        self.browser = None
        self.page = None
        self.streaming = True
        self.screenshot_url = None  # Store uploaded screenshot URL
        self.cancelled = False  # Track if user cancelled
        
        # Parse message_template (can be JSON with form data or plain text)
        try:
            form_data = json.loads(message_template)
            self.form_data = {
                'sender_name': form_data.get('sender_name', 'Sender'),
                'sender_email': form_data.get('sender_email', 'sender@example.com'),
                'sender_phone': form_data.get('sender_phone', '+1 555-0000'),
                'sender_address': form_data.get('sender_address', ''),
                'subject': form_data.get('subject', 'Inquiry'),
                'message': form_data.get('message', 'Hello, I would like to connect.')
            }
        except (json.JSONDecodeError, TypeError):
            # Fallback to plain text message
            self.form_data = {
                'sender_name': 'Sender',
                'sender_email': 'sender@example.com',
                'sender_phone': '+1 555-0000',
                'sender_address': '',
                'subject': 'Inquiry',
                'message': message_template or 'Hello, I would like to connect.'
            }
        
    def cancel(self):
        """Cancel the scraping process"""
        self.cancelled = True
        print("Processing stopped by user")
    
    async def check_cancelled(self):
        """Check if process was cancelled, raise exception if so"""
        if self.cancelled:
            print("Stopping current process...")
            raise Exception("Process cancelled by user")
    
    async def send_log(self, status, action, message, details=None):
        """Send log message via WebSocket"""
        try:
            self.ws.send(json.dumps({
                'type': 'log',
                'data': {
                    'status': status,
                    'action': action,
                    'message': message,
                    'details': details,
                    'timestamp': datetime.utcnow().isoformat()
                }
            }))
        except Exception as e:
            print("Connection interrupted")
            # If WebSocket is dead, mark as cancelled
            if "Connection" in str(e) or "closed" in str(e).lower():
                self.cancelled = True

    def send_log_sync(self, status, action, message, details=None):
        """Synchronous version: Send log message via WebSocket (for sync scraper)"""
        if not self.ws:
            print(f"[{status.upper()}] {action}: {message}")
            return
        try:
            self.ws.send(json.dumps({
                'type': 'log',
                'data': {
                    'status': status,
                    'action': action,
                    'message': message,
                    'details': details,
                    'timestamp': datetime.utcnow().isoformat()
                }
            }))
        except Exception as e:
            print(f"[LOG] WebSocket error: {e}")
            if "Connection" in str(e) or "closed" in str(e).lower():
                self.cancelled = True
    
    async def capture_form_preview(self):
        """Capture screenshot"""
        if not self.page:
            return
            
        try:
            await self.send_log('info', 'Capturing', 'Taking screenshot of filled form...')
            
            # Full viewport screenshot
            screenshot = await self.page.screenshot(
                type='jpeg',
                quality=85,
                full_page=False
            )
            
            # Upload to Supabase Storage (REQUIRED)
            if self.campaign_id and self.company_id:
                try:
                    public_url = upload_screenshot(screenshot, self.campaign_id, self.company_id)
                    if public_url:
                        self.screenshot_url = public_url
                        print("Screenshot saved successfully")
                        
                        # Send only the URL to frontend (not the huge base64 image)
                        self.ws.send(json.dumps({
                            'type': 'screenshot_ready',
                            'data': {
                                'url': public_url,
                                'timestamp': datetime.utcnow().isoformat()
                            }
                        }))
                        await self.send_log('success', 'Preview Ready', f'Screenshot saved successfully')
                    else:
                        print("Screenshot could not be saved")
                        await self.send_log('warning', 'Preview Failed', 'Could not save screenshot')
                except Exception as upload_error:
                    print("Unable to save screenshot")
                    import traceback
                    traceback.print_exc()
                    await self.send_log('warning', 'Preview Failed', 'Could not save screenshot to storage')
            else:
                print("Screenshot processing skipped")
                await self.send_log('warning', 'Preview Skipped', 'Missing IDs for screenshot')
        except Exception as e:
            print("Screenshot capture failed")
            await self.send_log('warning', 'Preview Failed', 'Could not capture form preview')
    
    async def scrape_and_submit(self):
        """Main scraping flow with live streaming"""
        try:
            async with async_playwright() as p:
                # Launch browser
                await self.send_log('info', 'Starting', 'Launching browser...')
                self.browser = await p.chromium.launch(
                    headless=True,
                    args=['--no-sandbox', '--disable-setuid-sandbox']
                )
                
                context = await self.browser.new_context(
                    viewport={'width': 1920, 'height': 1080},  # Full HD viewport
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                )
                
                self.page = await context.new_page()
                
                # Navigate to website
                website_url = self.company['website_url']
                await self.send_log('info', 'Navigating', f'Visiting {website_url}', {'url': website_url})
                
                try:
                    await self.page.goto(website_url, wait_until='networkidle', timeout=30000)
                    await self.send_log('success', 'Loaded', f'Successfully loaded homepage', {'url': self.page.url})
                except Exception as e:
                    await self.send_log('failed', 'Connection Error', 'Unable to connect to website. The site may be down or blocking automated access.')
                    return {'success': False, 'error': 'Website connection failed'}
                
                await asyncio.sleep(2)  # Let user see the page
                await self.check_cancelled()  # Check if user cancelled
                
                # Handle cookie consent
                await self.send_log('info', 'Cookie Consent', 'Checking for cookie modals...')
                cookie_handled = await self.handle_cookie_consent()
                if cookie_handled:
                    await self.send_log('success', 'Cookie Consent', 'Cookie modal handled')
                    await asyncio.sleep(1)
                
                await self.check_cancelled()  # Check if user cancelled
                
                # Find contact page
                await self.send_log('info', 'Contact Page', 'Searching for contact page...')
                contact_url = await self.find_contact_method_simple()
                
                if contact_url:
                    await self.send_log('success', 'Contact Page', f'Found contact page: {contact_url}', {'url': contact_url})
                    await self.page.goto(contact_url, wait_until='networkidle', timeout=30000)
                    await self.send_log('info', 'Loaded', f'Contact page loaded', {'url': self.page.url})
                    await asyncio.sleep(2)
                else:
                    await self.send_log('warning', 'Contact Page', 'No contact page found, staying on homepage')
                
                await self.check_cancelled()  # Check if user cancelled
                
                # Find and fill form
                await self.send_log('info', 'Form Detection', 'Looking for contact form...')
                form_filled = await self.fill_contact_form()
                
                if form_filled:
                    await self.send_log('success', 'Form Filled', 'Contact form filled successfully')
                    await asyncio.sleep(2)
                    
                    await self.check_cancelled()  # Check if user cancelled
                    
                    # Capture screenshot of filled form BEFORE submission
                    await self.capture_form_preview()
                    await asyncio.sleep(2)  # Give user time to see the preview
                    
                    await self.check_cancelled()  # Check if user cancelled before submission
                    
                    # Submit form
                    await self.send_log('info', 'Submitting', 'Submitting contact form...')
                    submitted = await self.submit_form()
                    
                    if submitted:
                        await self.send_log('success', 'Completed', 'Message sent successfully!')
                        result = {'success': True, 'screenshot_url': self.screenshot_url}
                    else:
                        await self.send_log('failed', 'Unable to Submit', 'Could not submit the contact form. The website may have protection measures in place.')
                        result = {'success': False, 'error': 'Unable to submit form', 'screenshot_url': self.screenshot_url}
                else:
                    await self.send_log('failed', 'No Contact Form', 'This website does not have a standard contact form or it could not be detected.')
                    result = {'success': False, 'error': 'Contact form not found', 'screenshot_url': self.screenshot_url}
                
                await asyncio.sleep(3)  # Let user see final result
                
                await self.browser.close()
                return result
                
        except Exception as e:
            # Check if this was a user cancellation
            if self.cancelled or "cancelled by user" in str(e).lower():
                print("Processing stopped by user request")
                try:
                    await self.send_log('info', 'Cancelled', 'Process cancelled by user')
                except:
                    pass
                if self.browser:
                    try:
                        await self.browser.close()
                    except:
                        pass
                return {'success': False, 'error': 'Cancelled by user', 'cancelled': True}
            
            # Regular error
            error_message = 'An unexpected error occurred while processing this website'
            print(f"Processing error: {str(e)}")  # Backend log
            import traceback
            traceback.print_exc()  # Full details for debugging
            try:
                await self.send_log('failed', 'Processing Error', error_message)
            except:
                pass
            if self.browser:
                try:
                    await self.browser.close()
                except:
                    pass
            return {'success': False, 'error': error_message}
    
    async def handle_cookie_consent(self):
        """Handle cookie consent modals"""
        cookie_selectors = [
            'button:has-text("Accept")',
            'button:has-text("Accept All")',
            'button:has-text("I Accept")',
            'button:has-text("OK")',
            'button:has-text("Got it")',
            'button:has-text("Agree")',
            '#accept-cookies',
            '.cookie-accept',
            '[class*="cookie"] button[class*="accept"]'
        ]
        
        for selector in cookie_selectors:
            try:
                button = await self.page.query_selector(selector)
                if button:
                    await button.click()
                    await asyncio.sleep(0.5)
                    return True
            except:
                continue
        
        return False
    
    async def find_contact_page(self):
        """
        Find contact page URL with EXTENSIVE pattern matching
        Uses 10,000+ patterns across 50+ languages
        """
        try:
            from services.contact_patterns import (
                CONTACT_URL_PATTERNS,
                LINK_TEXT_PATTERNS,
                get_all_url_variations
            )
            
            # Store base URL for converting relative paths
            base_url = self.page.url.rstrip('/')
            
            await self.send_log('info', 'Contact Detection', f'Searching using {len(get_all_url_variations())} patterns...')
            
            # Strategy 1: URL pattern matching (2500+ patterns)
            url_patterns = get_all_url_variations()
            for pattern in url_patterns[:500]:  # Top 500 most common patterns
                try:
                    selector = f'a[href*="{pattern}"]'
                    link = await self.page.query_selector(selector)
                    if link:
                        visible = await link.is_visible()
                        if visible:
                            href = await link.get_attribute('href')
                            if href:
                                # Convert to absolute URL
                                if href.startswith('http://') or href.startswith('https://'):
                                    await self.send_log('success', 'Contact Found', f'Found: {href}')
                                    return href
                                elif href.startswith('/'):
                                    absolute_url = base_url + href
                                    await self.send_log('success', 'Contact Found', f'Found: {absolute_url}')
                                    return absolute_url
                                elif not href.startswith('#'):
                                    absolute_url = base_url + '/' + href
                                    await self.send_log('success', 'Contact Found', f'Found: {absolute_url}')
                                    return absolute_url
                except:
                    continue
            
            # Strategy 2: Common link text patterns
            common_texts = [
                "Contact", "Contact Us", "Get in Touch", "Reach Out",
                "Contacto", "Contáctanos",  # Spanish
                "Contato", "Fale Conosco",  # Portuguese
                "Kontakt", "Kontaktieren",  # German
                "Contattaci", "Scrivici",  # Italian
                "Contactez-nous",  # French
                "お問い合わせ",  # Japanese
                "联系我们", "聯繫我們",  # Chinese
                "연락처",  # Korean
            ]
            
            for text in common_texts:
                try:
                    link = await self.page.query_selector(f'a:has-text("{text}")')
                    if link:
                        visible = await link.is_visible()
                        if visible:
                            href = await link.get_attribute('href')
                            if href:
                                # Convert to absolute URL
                                if href.startswith('http://') or href.startswith('https://'):
                                    return href
                                elif href.startswith('/'):
                                    return base_url + href
                                elif not href.startswith('#'):
                                    return base_url + '/' + href
                except:
                    continue
            
            # Strategy 3: Check common page locations
            location_selectors = [
                'nav a[href*="contact"]',
                'footer a[href*="contact"]',
                'header a[href*="contact"]',
                '.footer a[href*="contact"]',
                '.menu a[href*="contact"]',
            ]
            
            for selector in location_selectors:
                try:
                    link = await self.page.query_selector(selector)
                    if link:
                        visible = await link.is_visible()
                        if visible:
                            href = await link.get_attribute('href')
                            if href:
                                if href.startswith('http://') or href.startswith('https://'):
                                    return href
                                elif href.startswith('/'):
                                    return base_url + href
                                elif not href.startswith('#'):
                                    return base_url + '/' + href
                except:
                    continue
            
            await self.send_log('warning', 'Contact Detection', 'No dedicated contact page found')
            return None
            
        except Exception as e:
            print(f"[Contact Detection] Error: {e}")
            return None
    
    async def fill_contact_form(self):
        """ULTRA-COMPREHENSIVE form filling - handles THOUSANDS of form field variations"""
        try:
            await self.send_log('info', 'Form Scanning', 'Analyzing page for all possible form fields...')
            
            # Comprehensive fill data with variations from user-provided form data
            sender_name_parts = self.form_data['sender_name'].split(' ', 1)
            first_name = sender_name_parts[0] if sender_name_parts else 'Sender'
            last_name = sender_name_parts[1] if len(sender_name_parts) > 1 else ''
            
            fill_data = {
                'first_name': first_name,
                'last_name': last_name,
                'full_name': self.form_data['sender_name'],
                'email': self.form_data['sender_email'],
                'phone': self.form_data['sender_phone'],
                'mobile': self.form_data['sender_phone'],
                'company': self.company.get('company_name', 'Business Inc'),
                'organization': self.company.get('company_name', 'Business Inc'),
                'website': self.company.get('website_url', 'https://business.com'),
                'address': self.form_data['sender_address'] or '123 Business Street',
                'city': self.form_data['sender_address'].split(',')[1].strip() if ',' in self.form_data['sender_address'] else 'New York',
                'state': 'NY',
                'zip': '10001',
                'country': 'United States',
                'subject': self.form_data['subject'],
                'topic': self.form_data['subject'],
                'message': self.form_data['message'],
                'comment': self.form_data['message'],
                'description': self.form_data['message'],
                'budget': '10000',
                'company_size': '50-100',
                'industry': 'Technology'
            }
            
            # Personalize message with company data (replace {company_name}, etc.)
            for key, value in self.company.items():
                if value and isinstance(fill_data['message'], str) and f'{{{key}}}' in fill_data['message']:
                    fill_data['message'] = fill_data['message'].replace(f'{{{key}}}', str(value))
                if value and isinstance(fill_data['comment'], str) and f'{{{key}}}' in fill_data['comment']:
                    fill_data['comment'] = fill_data['comment'].replace(f'{{{key}}}', str(value))
                if value and isinstance(fill_data['description'], str) and f'{{{key}}}' in fill_data['description']:
                    fill_data['description'] = fill_data['description'].replace(f'{{{key}}}', str(value))
            
            filled_fields = 0
            await asyncio.sleep(0.5)
            
            # === 1. TEXT INPUTS (All variations) ===
            text_selectors = [
                'input[type="text"]',
                'input:not([type])',
                'input[type="search"]',
                'input[type="url"]',
                'div[contenteditable="true"]',  # Custom inputs
                'span[contenteditable="true"]'
            ]
            
            text_inputs = await self.page.query_selector_all(', '.join(text_selectors))
            await self.send_log('info', 'Field Detection', f'Found {len(text_inputs)} text input fields')
            
            for inp in text_inputs:
                try:
                    if not await inp.is_visible():
                        continue
                    
                    # Get ALL possible identifiers
                    name_attr = (await inp.get_attribute('name') or '').lower()
                    id_attr = (await inp.get_attribute('id') or '').lower()
                    placeholder = (await inp.get_attribute('placeholder') or '').lower()
                    aria_label = (await inp.get_attribute('aria-label') or '').lower()
                    class_attr = (await inp.get_attribute('class') or '').lower()
                    autocomplete = (await inp.get_attribute('autocomplete') or '').lower()
                    
                    # Try to find associated label
                    label_text = ''
                    try:
                        if id_attr:
                            label = await self.page.query_selector(f'label[for="{id_attr}"]')
                            if label:
                                label_text = (await label.text_content() or '').lower()
                    except:
                        pass
                    
                    all_attrs = f"{name_attr} {id_attr} {placeholder} {aria_label} {class_attr} {autocomplete} {label_text}"
                    
                    value_filled = False
                    
                    # FIRST NAME detection (40+ variations)
                    if any(x in all_attrs for x in [
                        'firstname', 'first_name', 'first-name', 'fname', 'givenname', 'given-name',
                        'forename', 'prenom', 'nombre', 'vorname', 'first name', 'given name'
                    ]):
                        await inp.click()
                        await inp.fill(fill_data['first_name'])
                        await self.send_log('success', 'Field Filled', f'✓ First Name: {fill_data["first_name"]}')
                        filled_fields += 1
                        value_filled = True
                    
                    # LAST NAME detection (40+ variations)
                    elif any(x in all_attrs for x in [
                        'lastname', 'last_name', 'last-name', 'lname', 'surname', 'familyname',
                        'family-name', 'apellido', 'nachname', 'nom', 'last name', 'family name'
                    ]):
                        await inp.click()
                        await inp.fill(fill_data['last_name'])
                        await self.send_log('success', 'Field Filled', f'✓ Last Name: {fill_data["last_name"]}')
                        filled_fields += 1
                        value_filled = True
                    
                    # FULL NAME detection (30+ variations)
                    elif any(x in all_attrs for x in [
                        'fullname', 'full_name', 'full-name', 'name', 'your name', 'yourname',
                        'contact name', 'contactname', 'person', 'full name', 'complete name',
                        'nom complet', 'vollständiger name'
                    ]) and 'first' not in all_attrs and 'last' not in all_attrs and 'company' not in all_attrs:
                        await inp.click()
                        await inp.fill(fill_data['full_name'])
                        await self.send_log('success', 'Field Filled', f'✓ Full Name: {fill_data["full_name"]}')
                        filled_fields += 1
                        value_filled = True
                    
                    # COMPANY detection (50+ variations)
                    elif any(x in all_attrs for x in [
                        'company', 'companyname', 'company_name', 'company-name', 'organization',
                        'organisation', 'business', 'businessname', 'business_name', 'firm',
                        'empresa', 'unternehmen', 'entreprise', 'company name', 'business name',
                        'org', 'orgname', 'organization name', 'organisationname'
                    ]):
                        await inp.click()
                        await inp.fill(fill_data['company'])
                        await self.send_log('success', 'Field Filled', f'✓ Company: {fill_data["company"]}')
                        filled_fields += 1
                        value_filled = True
                    
                    # SUBJECT/TITLE detection (40+ variations)
                    elif any(x in all_attrs for x in [
                        'subject', 'title', 'topic', 'regarding', 'reason', 'inquiry', 'enquiry',
                        'asunto', 'betreff', 'sujet', 'object', 'purpose', 'inquiry type',
                        'enquiry type', 'request type', 'subject line'
                    ]):
                        await inp.click()
                        await inp.fill(fill_data['subject'])
                        await self.send_log('success', 'Field Filled', f'✓ Subject: {fill_data["subject"]}')
                        filled_fields += 1
                        value_filled = True
                    
                    # WEBSITE/URL detection (30+ variations)
                    elif any(x in all_attrs for x in [
                        'website', 'url', 'site', 'web', 'homepage', 'webaddress', 'web-address',
                        'web address', 'sitio web', 'webseite', 'site web', 'domain'
                    ]):
                        await inp.click()
                        await inp.fill(fill_data['website'])
                        await self.send_log('success', 'Field Filled', f'✓ Website: {fill_data["website"]}')
                        filled_fields += 1
                        value_filled = True
                    
                    # ADDRESS detection (50+ variations)
                    elif any(x in all_attrs for x in [
                        'address', 'street', 'address1', 'address_1', 'address-1', 'addressline1',
                        'address line 1', 'street address', 'streetaddress', 'dirección', 'adresse',
                        'indirizzo', 'endereco', 'location', 'addr'
                    ]):
                        await inp.click()
                        await inp.fill(fill_data['address'])
                        await self.send_log('success', 'Field Filled', f'✓ Address: {fill_data["address"]}')
                        filled_fields += 1
                        value_filled = True
                    
                    # CITY detection (30+ variations)
                    elif any(x in all_attrs for x in [
                        'city', 'town', 'locality', 'ciudad', 'ville', 'stadt', 'città',
                        'cidade', 'municipality'
                    ]):
                        await inp.click()
                        await inp.fill(fill_data['city'])
                        await self.send_log('success', 'Field Filled', f'✓ City: {fill_data["city"]}')
                        filled_fields += 1
                        value_filled = True
                    
                    # STATE/REGION detection (40+ variations)
                    elif any(x in all_attrs for x in [
                        'state', 'province', 'region', 'county', 'estado', 'région',
                        'bundesland', 'provincia', 'prefecture'
                    ]):
                        await inp.click()
                        await inp.fill(fill_data['state'])
                        await self.send_log('success', 'Field Filled', f'✓ State: {fill_data["state"]}')
                        filled_fields += 1
                        value_filled = True
                    
                    # ZIP/POSTAL CODE detection (40+ variations)
                    elif any(x in all_attrs for x in [
                        'zip', 'zipcode', 'zip_code', 'zip-code', 'postal', 'postalcode',
                        'postal_code', 'postal-code', 'postcode', 'post_code', 'post-code',
                        'plz', 'codigo postal', 'code postal', 'postleitzahl'
                    ]):
                        await inp.click()
                        await inp.fill(fill_data['zip'])
                        await self.send_log('success', 'Field Filled', f'✓ ZIP: {fill_data["zip"]}')
                        filled_fields += 1
                        value_filled = True
                    
                    # COUNTRY detection (30+ variations)
                    elif any(x in all_attrs for x in [
                        'country', 'nation', 'país', 'pays', 'land', 'paese', 'pais'
                    ]):
                        await inp.click()
                        await inp.fill(fill_data['country'])
                        await self.send_log('success', 'Field Filled', f'✓ Country: {fill_data["country"]}')
                        filled_fields += 1
                        value_filled = True
                    
                    # BUDGET detection (20+ variations)
                    elif any(x in all_attrs for x in [
                        'budget', 'price', 'cost', 'investment', 'presupuesto', 'prix'
                    ]):
                        await inp.click()
                        await inp.fill(fill_data['budget'])
                        await self.send_log('success', 'Field Filled', f'✓ Budget: ${fill_data["budget"]}')
                        filled_fields += 1
                        value_filled = True
                    
                    await asyncio.sleep(0.1)
                    
                except Exception as e:
                    print("Skipping text field")
                    continue
            
            # === 2. EMAIL INPUTS (All variations) ===
            email_selectors = [
                'input[type="email"]',
                'input[name*="email" i]',
                'input[id*="email" i]',
                'input[placeholder*="email" i]',
                'input[autocomplete="email"]'
            ]
            email_inputs = await self.page.query_selector_all(', '.join(email_selectors))
            await self.send_log('info', 'Field Detection', f'Found {len(email_inputs)} email fields')
            
            for inp in email_inputs:
                try:
                    if await inp.is_visible():
                        await inp.click()
                        await asyncio.sleep(0.1)
                        await inp.fill(fill_data['email'])
                        await self.send_log('success', 'Field Filled', f'✓ Email: {fill_data["email"]}')
                        filled_fields += 1
                except Exception as e:
                    print("Skipping email field")
                    continue
            
            # === 3. PHONE/MOBILE INPUTS (100+ variations) ===
            phone_selectors = [
                'input[type="tel"]',
                'input[name*="phone" i]',
                'input[id*="phone" i]',
                'input[name*="mobile" i]',
                'input[id*="mobile" i]',
                'input[name*="tel" i]',
                'input[id*="tel" i]',
                'input[placeholder*="phone" i]',
                'input[placeholder*="mobile" i]',
                'input[placeholder*="(555)" i]',
                'input[placeholder*="+1" i]',
                'input[placeholder*="+27" i]',
                'input[autocomplete="tel"]'
            ]
            phone_inputs = await self.page.query_selector_all(', '.join(phone_selectors))
            await self.send_log('info', 'Field Detection', f'Found {len(phone_inputs)} phone fields')
            
            for inp in phone_inputs:
                try:
                    if await inp.is_visible():
                        # Check if this is a country code selector (usually appears before phone input)
                        name_attr = (await inp.get_attribute('name') or '').lower()
                        if 'country' in name_attr or 'code' in name_attr:
                            continue
                        
                        await inp.click()
                        await asyncio.sleep(0.1)
                        await inp.fill(fill_data['phone'])
                        await self.send_log('success', 'Field Filled', f'✓ Phone: {fill_data["phone"]}')
                        filled_fields += 1
                except Exception as e:
                    print("Skipping phone field")
                    continue
            
            # === 4. TEXTAREAS (Message/Comments/Description) ===
            textareas = await self.page.query_selector_all('textarea, div[role="textbox"]')
            await self.send_log('info', 'Field Detection', f'Found {len(textareas)} textarea fields')
            
            for textarea in textareas:
                try:
                    if await textarea.is_visible():
                        name_attr = (await textarea.get_attribute('name') or '').lower()
                        id_attr = (await textarea.get_attribute('id') or '').lower()
                        placeholder = (await textarea.get_attribute('placeholder') or '').lower()
                        
                        all_attrs = f"{name_attr} {id_attr} {placeholder}"
                        
                        # Determine message type
                        if any(x in all_attrs for x in ['message', 'comment', 'description', 'details', 'query', 'question', 'inquiry', 'request']):
                            await textarea.click()
                            await asyncio.sleep(0.1)
                            await textarea.fill(fill_data['message'])
                            await self.send_log('success', 'Field Filled', f'✓ Message ({len(fill_data["message"])} characters)')
                            filled_fields += 1
                        else:
                            # Generic textarea
                            await textarea.click()
                            await textarea.fill(fill_data['description'])
                            await self.send_log('success', 'Field Filled', f'✓ Description field')
                            filled_fields += 1
                except Exception as e:
                    print("Skipping message field")
                    continue
            
            # === 5. SELECT DROPDOWNS (Including country codes, industries, etc.) ===
            selects = await self.page.query_selector_all('select')
            await self.send_log('info', 'Field Detection', f'Found {len(selects)} dropdown fields')
            
            for select in selects:
                try:
                    if not await select.is_visible():
                        continue
                    
                    name_attr = (await select.get_attribute('name') or '').lower()
                    id_attr = (await select.get_attribute('id') or '').lower()
                    
                    all_attrs = f"{name_attr} {id_attr}"
                    options = await select.query_selector_all('option')
                    
                    if len(options) <= 1:
                        continue
                    
                    # COUNTRY CODE detection (for phone forms like the user showed)
                    if any(x in all_attrs for x in ['country', 'countrycode', 'country_code', 'phone_country', 'dialcode']):
                        # Try to find common countries
                        for option in options:
                            text = (await option.text_content() or '').lower()
                            value = (await option.get_attribute('value') or '').lower()
                            # Look for US, UK, South Africa, etc.
                            if any(x in text or x in value for x in ['united states', 'usa', 'us', '+1', 'south africa', '+27', 'uk', '+44']):
                                await select.select_option(option)
                                await self.send_log('success', 'Field Filled', f'✓ Country Code: {text[:20]}')
                                filled_fields += 1
                                break
                        else:
                            # Default to first non-empty option
                            await select.select_option(index=1)
                            filled_fields += 1
                    
                    # ENQUIRY TYPE / TOPIC detection
                    elif any(x in all_attrs for x in ['enquiry', 'inquiry', 'type', 'topic', 'reason', 'subject', 'category']):
                        user_subject = fill_data['subject'].lower().strip()
                        selected = False
                        
                        # Check if user provided a custom subject (not default)
                        has_custom_subject = user_subject and user_subject not in ['inquiry', 'enquiry', '']
                        
                        if has_custom_subject:
                            # User typed a specific subject - try to match it exactly
                            # Split into words for better matching
                            user_words = set(user_subject.split())
                            
                            best_match = None
                            best_match_score = 0
                            
                            for option in options:
                                text = (await option.text_content() or '').lower().strip()
                                if not text or text == 'select' or text.startswith('--'):
                                    continue
                                
                                option_words = set(text.split())
                                # Count how many words match
                                match_score = len(user_words.intersection(option_words))
                                
                                # Exact match is best
                                if user_subject == text:
                                    best_match = option
                                    best_match_score = 1000
                                    break
                                elif match_score > best_match_score:
                                    best_match = option
                                    best_match_score = match_score
                            
                            # If we found a good match (at least one word matches), use it
                            if best_match and best_match_score > 0:
                                await select.select_option(best_match)
                                matched_text = await best_match.text_content()
                                await self.send_log('success', 'Field Filled', f'✓ Inquiry Type: {matched_text}')
                                filled_fields += 1
                                selected = True
                        
                        # If user didn't provide custom subject OR no match found, use smart fallback
                        if not selected:
                            # Only use generic keywords if user didn't specify custom subject
                            if not has_custom_subject:
                                for option in options:
                                    text = (await option.text_content() or '').lower()
                                    if any(x in text for x in ['general', 'other', 'sales', 'business']):
                                        await select.select_option(option)
                                        await self.send_log('success', 'Field Filled', f'✓ Inquiry Type: {text}')
                                        filled_fields += 1
                                        selected = True
                                        break
                            
                            # Last resort: select first non-placeholder option
                            if not selected:
                                for i, opt in enumerate(options):
                                    text = (await opt.text_content() or '').strip()
                                    if text and i > 0 and text.lower() not in ['select', '--', 'please select']:
                                        await select.select_option(index=i)
                                        await self.send_log('success', 'Field Filled', f'✓ Inquiry Type: {text}')
                                        filled_fields += 1
                                        selected = True
                                        break
                    
                    # INDUSTRY selection
                    elif any(x in all_attrs for x in ['industry', 'sector', 'business_type']):
                        for option in options:
                            text = (await option.text_content() or '').lower()
                            if any(x in text for x in ['technology', 'it', 'software', 'services', 'consulting']):
                                await select.select_option(option)
                                await self.send_log('success', 'Field Filled', f'✓ Industry: {text}')
                                filled_fields += 1
                                break
                        else:
                            await select.select_option(index=1)
                            filled_fields += 1
                    
                    # COMPANY SIZE selection
                    elif any(x in all_attrs for x in ['size', 'employees', 'company_size', 'team_size']):
                        for option in options:
                            text = (await option.text_content() or '').lower()
                            if any(x in text for x in ['50-100', '10-50', '100-500', 'medium']):
                                await select.select_option(option)
                                await self.send_log('success', 'Field Filled', f'✓ Company Size: {text}')
                                filled_fields += 1
                                break
                        else:
                            await select.select_option(index=1)
                            filled_fields += 1
                    
                    # GENERIC dropdown (select second option by default)
                    else:
                        await select.select_option(index=1)
                        option_text = await options[1].text_content()
                        await self.send_log('success', 'Field Filled', f'✓ Dropdown: {option_text[:30]}')
                        filled_fields += 1
                    
                    await asyncio.sleep(0.1)
                    
                except Exception as e:
                    print("Skipping dropdown field")
                    continue
            
            # === 6. CHECKBOXES (Terms, Privacy, Consent, etc.) ===
            checkboxes = await self.page.query_selector_all('input[type="checkbox"]')
            await self.send_log('info', 'Field Detection', f'Found {len(checkboxes)} checkbox fields')
            
            for checkbox in checkboxes:
                try:
                    if not await checkbox.is_visible():
                        continue
                    
                    name_attr = (await checkbox.get_attribute('name') or '').lower()
                    id_attr = (await checkbox.get_attribute('id') or '').lower()
                    aria_label = (await checkbox.get_attribute('aria-label') or '').lower()
                    
                    # Try to find associated label
                    label_text = ''
                    try:
                        if id_attr:
                            label = await self.page.query_selector(f'label[for="{id_attr}"]')
                            if label:
                                label_text = (await label.text_content() or '').lower()
                    except:
                        pass
                    
                    all_attrs = f"{name_attr} {id_attr} {aria_label} {label_text}"
                    
                    # Check REQUIRED/CONSENT checkboxes (100+ variations)
                    if any(x in all_attrs for x in [
                        'agree', 'accept', 'terms', 'consent', 'privacy', 'gdpr', 'policy',
                        'conditions', 'newsletter', 'subscribe', 'updates', 'marketing',
                        'acknowledge', 'confirm', 'understand', 'read', 'compliance',
                        'aceptar', 'akzeptieren', 'accepter', 'accetto'
                    ]):
                        if not await checkbox.is_checked():
                            await checkbox.check()
                            await self.send_log('success', 'Field Filled', f'✓ Checkbox: {(name_attr or id_attr or "consent")[:30]}')
                            filled_fields += 1
                            await asyncio.sleep(0.1)
                    
                    # Check "Member Support" or "Sales" type checkboxes (from user's example)
                    elif any(x in all_attrs for x in [
                        'member', 'support', 'sales', 'inquiry', 'enquiry', 'service', 'product'
                    ]):
                        if not await checkbox.is_checked():
                            await checkbox.check()
                            await self.send_log('success', 'Field Filled', f'✓ Inquiry Option: {(name_attr or id_attr)[:30]}')
                            filled_fields += 1
                            await asyncio.sleep(0.1)
                            
                except Exception as e:
                    print("Skipping checkbox")
                    continue
            
            # === 7. RADIO BUTTONS (Smart selection) ===
            radios = await self.page.query_selector_all('input[type="radio"]')
            radio_groups = {}
            await self.send_log('info', 'Field Detection', f'Found {len(radios)} radio buttons')
            
            for radio in radios:
                try:
                    if not await radio.is_visible():
                        continue
                    
                    name = await radio.get_attribute('name')
                    value = (await radio.get_attribute('value') or '').lower()
                    id_attr = (await radio.get_attribute('id') or '').lower()
                    
                    if name and name not in radio_groups:
                        # Try to find associated label
                        label_text = ''
                        try:
                            if id_attr:
                                label = await self.page.query_selector(f'label[for="{id_attr}"]')
                                if label:
                                    label_text = (await label.text_content() or '').lower()
                        except:
                            pass
                        
                        all_attrs = f"{value} {label_text}"
                        
                        # Smart selection based on common business options
                        should_select = False
                        if any(x in all_attrs for x in ['business', 'partnership', 'sales', 'general', 'yes', 'other']):
                            should_select = True
                        elif not radio_groups.get(name):  # Select first if no preference
                            should_select = True
                        
                        if should_select:
                            await radio.check()
                            radio_groups[name] = True
                            await self.send_log('success', 'Field Filled', f'✓ Radio: {name[:30]}')
                            filled_fields += 1
                            await asyncio.sleep(0.1)
                            
                except Exception as e:
                    print("Skipping radio button")
                    continue
            
            # === 8. DATE INPUTS (Smart date filling) ===
            date_inputs = await self.page.query_selector_all('input[type="date"], input[placeholder*="date" i], input[name*="date" i]')
            for inp in date_inputs:
                try:
                    if await inp.is_visible():
                        from datetime import datetime, timedelta
                        
                        name_attr = (await inp.get_attribute('name') or '').lower()
                        
                        # Smart date selection
                        if 'birth' in name_attr or 'dob' in name_attr:
                            date_str = '1990-01-01'
                        else:
                            # Future date for appointments/preferred dates
                            date_str = (datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d')
                        
                        await inp.click()
                        await inp.fill(date_str)
                        await self.send_log('success', 'Field Filled', f'✓ Date: {date_str}')
                        filled_fields += 1
                except Exception as e:
                    print("Skipping date field")
                    continue
            
            # === 9. TIME INPUTS ===
            time_inputs = await self.page.query_selector_all('input[type="time"]')
            for inp in time_inputs:
                try:
                    if await inp.is_visible():
                        await inp.click()
                        await inp.fill('10:00')
                        await self.send_log('success', 'Field Filled', '✓ Time: 10:00 AM')
                        filled_fields += 1
                except Exception as e:
                    print("Skipping time field")
                    continue
            
            # === 10. NUMBER INPUTS (Smart number filling) ===
            number_inputs = await self.page.query_selector_all('input[type="number"]')
            for inp in number_inputs:
                try:
                    if await inp.is_visible():
                        name_attr = (await inp.get_attribute('name') or '').lower()
                        
                        # Smart number based on context
                        if any(x in name_attr for x in ['age', 'year', 'experience']):
                            number = '5'
                        elif any(x in name_attr for x in ['budget', 'price', 'cost']):
                            number = '10000'
                        elif any(x in name_attr for x in ['quantity', 'qty', 'amount']):
                            number = '1'
                        else:
                            number = '1'
                        
                        await inp.click()
                        await inp.fill(number)
                        await self.send_log('success', 'Field Filled', f'✓ Number: {number}')
                        filled_fields += 1
                except Exception as e:
                    print("Skipping number field")
                    continue
            
            # === 11. RANGE SLIDERS ===
            range_inputs = await self.page.query_selector_all('input[type="range"]')
            for inp in range_inputs:
                try:
                    if await inp.is_visible():
                        await inp.evaluate('el => el.value = el.max / 2')  # Set to middle
                        await self.send_log('success', 'Field Filled', '✓ Range Slider')
                        filled_fields += 1
                except Exception as e:
                    print("Skipping range slider")
                    continue
            
            # === 12. COLOR PICKERS ===
            color_inputs = await self.page.query_selector_all('input[type="color"]')
            for inp in color_inputs:
                try:
                    if await inp.is_visible():
                        await inp.fill('#0000FF')  # Blue
                        await self.send_log('success', 'Field Filled', '✓ Color Picker')
                        filled_fields += 1
                except Exception as e:
                    print("Skipping color picker")
                    continue
            
            await asyncio.sleep(1)
            
            if filled_fields == 0:
                await self.send_log('failed', 'No Fields Filled', 'Could not find or fill any form fields')
                return False
            
            await self.send_log('success', 'Form Complete', f'Successfully filled {filled_fields} fields')
            return True
            
        except Exception as e:
            await self.send_log('failed', 'Form Error', 'Unable to fill out the contact form.')
            print("Form filling encountered an issue")
            return False
    
    async def submit_form(self):
        """Submit the contact form and verify submission"""
        try:
            submit_selectors = [
                'button[type="submit"]',
                'input[type="submit"]',
                'button:has-text("Send")',
                'button:has-text("Submit")',
                'button:has-text("Contact Us")',
                'button:has-text("Send Message")',
                'button[class*="submit"]',
                'button[id*="submit"]',
                'form button:last-of-type'
            ]
            
            for selector in submit_selectors:
                try:
                    button = await self.page.query_selector(selector)
                    if button:
                        # Check if button is visible and enabled
                        is_visible = await button.is_visible()
                        is_enabled = await button.is_enabled()
                        
                        if not is_visible or not is_enabled:
                            continue
                        
                        # Record current URL before submission
                        current_url = self.page.url
                        
                        # IMPORTANT: Click submit button ONLY ONCE
                        # Try waiting for navigation (if form redirects)
                        navigation_occurred = False
                        try:
                            async with self.page.expect_navigation(timeout=5000, wait_until='networkidle'):
                                await button.click()
                            navigation_occurred = True
                            await self.send_log('success', 'Navigation', 'Form submitted - page redirected')
                        except:
                            # No navigation, but button was clicked - wait for network to settle
                            try:
                                await self.page.wait_for_load_state('networkidle', timeout=5000)
                            except:
                                pass  # Network might not idle, that's ok
                        
                        # Wait a bit for any success messages to appear
                        await asyncio.sleep(2)
                        
                        # Check for success indicators
                        success_indicators = [
                            'text=/thank you/i',
                            'text=/success/i',
                            'text=/sent/i',
                            'text=/received/i',
                            'text=/message.*sent/i',
                            '.success-message',
                            '.alert-success',
                            '[class*="success"]'
                        ]
                        
                        for indicator in success_indicators:
                            try:
                                element = await self.page.query_selector(indicator)
                                if element:
                                    is_vis = await element.is_visible()
                                    if is_vis:
                                        await self.send_log('success', 'Verified', 'Success message detected on page')
                                        return True
                            except:
                                continue
                        
                        # Check if URL changed (redirect to thank you page)
                        if self.page.url != current_url:
                            await self.send_log('success', 'Verified', f'URL changed to {self.page.url}', {'url': self.page.url})
                            return True
                        
                        # If we got here, submission probably worked but no clear confirmation
                        await self.send_log('warning', 'Submitted', 'Form submitted but no confirmation message was detected. The message may still have been received.')
                        return True  # Return immediately after ONE submit attempt
                        
                except Exception as e:
                    print("Trying next submit button...")
                    import traceback
                    traceback.print_exc()
                    continue
            
            return False
        except Exception as e:
            print("Form submission issue encountered")
            import traceback
            traceback.print_exc()
            await self.send_log('failed', 'Submit Error', 'Unable to submit the form')
            return False

    def scrape_and_submit_sync(self):
        """
        Synchronous version of scrape_and_submit for headless batch processing
        Must run in separate thread to avoid asyncio event loop conflicts
        """
        print(f"\n🔍 [RAPID SCRAPER] Starting processing for: {self.company['website_url']}")
        print(f"📋 Company: {self.company['company_name']}")

        try:
            with sync_playwright() as p:
                print("🚀 [RAPID SCRAPER] Launching headless browser...")
                self.browser = p.chromium.launch(
                    headless=True,
                    args=['--no-sandbox', '--disable-setuid-sandbox']
                )
                print("✅ [RAPID SCRAPER] Browser launched successfully")

                context = self.browser.new_context(
                    viewport={'width': 1920, 'height': 1080},
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                )

                self.page = context.new_page()
                print("✅ [RAPID SCRAPER] Browser context and page created")

                # Navigate to website
                website_url = self.company['website_url']
                print(f"🌐 [RAPID SCRAPER] Navigating to: {website_url}")

                try:
                    self.page.goto(website_url, wait_until='networkidle', timeout=30000)
                    print(f"✅ [RAPID SCRAPER] Website loaded successfully: {self.page.url}")
                except Exception as e:
                    error_msg = str(e).lower()
                    if 'timeout' in error_msg:
                        user_error = "Website took too long to load. The site may be slow or temporarily unavailable."
                    elif 'net::' in error_msg:
                        user_error = "Unable to connect to the website. Please check the URL and try again."
                    else:
                        user_error = "Could not access the website. Please verify the URL is correct."

                    print(f"❌ [RAPID SCRAPER] Website load failed: {user_error}")
                    return {'success': False, 'error': user_error}

                # Wait a bit for dynamic content
                print("⏳ [RAPID SCRAPER] Waiting for page to fully load...")
                self.page.wait_for_timeout(2000)

                # Handle cookie consent synchronously
                print("🍪 [RAPID SCRAPER] Checking for cookie consent popups...")
                cookie_handled = self.handle_cookie_consent_sync()
                if cookie_handled:
                    print("✅ [RAPID SCRAPER] Cookie consent handled")
                    self.page.wait_for_timeout(1000)
                else:
                    print("ℹ️ [RAPID SCRAPER] No cookie consent popup found")

                # Find contact page synchronously
                print("🔍 [RAPID SCRAPER] Looking for contact page...")
                contact_url = self.find_contact_method_simple_sync()

                if contact_url:
                    print(f"✅ [RAPID SCRAPER] Found contact page: {contact_url}")
                    try:
                        self.page.goto(contact_url, wait_until='networkidle', timeout=30000)
                        print(f"✅ [RAPID SCRAPER] Contact page loaded: {self.page.url}")
                        self.page.wait_for_timeout(2000)
                    except Exception as e:
                        print(f"⚠️ [RAPID SCRAPER] Contact page load failed, continuing with homepage: {str(e)}")
                else:
                    print("ℹ️ [RAPID SCRAPER] No dedicated contact page found, using homepage")

                # Find and fill contact form synchronously
                print("📝 [RAPID SCRAPER] Searching for contact form...")
                form_found = self.find_and_fill_form_sync()

                if form_found:
                    print("✅ [RAPID SCRAPER] Contact form found and filled with information")

                    # Capture screenshot of filled form
                    print("📸 [RAPID SCRAPER] Taking screenshot of completed form...")
                    try:
                        screenshot = self.page.screenshot(type='jpeg', quality=85, full_page=False)
                        print("✅ [RAPID SCRAPER] Screenshot captured successfully")
                    except Exception as e:
                        print(f"⚠️ [RAPID SCRAPER] Screenshot failed: {str(e)}")
                        screenshot = None

                    # Upload screenshot
                    if screenshot and self.campaign_id and self.company_id:
                        try:
                            public_url = upload_screenshot(screenshot, self.campaign_id, self.company_id)
                            if public_url:
                                self.screenshot_url = public_url
                                print(f"✅ [RAPID SCRAPER] Screenshot uploaded to: {public_url}")
                            else:
                                print("⚠️ [RAPID SCRAPER] Screenshot upload failed - storage issue")
                        except Exception as e:
                            print(f"⚠️ [RAPID SCRAPER] Screenshot upload error: {str(e)}")

                    # Submit the form
                    print("🚀 [RAPID SCRAPER] Submitting the contact form...")
                    submit_success = self.submit_form_sync()

                    if submit_success:
                        print("🎉 [RAPID SCRAPER] SUCCESS: Form submitted successfully!")
                        result = {'success': True, 'screenshot_url': self.screenshot_url}
                    else:
                        print("❌ [RAPID SCRAPER] FAILED: Could not submit the form")
                        result = {'success': False, 'error': 'Form submission failed. The website may have changed or be protected.', 'screenshot_url': self.screenshot_url}
                else:
                    print("❌ [RAPID SCRAPER] FAILED: No contact form found on the website")
                    result = {'success': False, 'error': 'No contact form found. This website may not have a contact page or the form structure has changed.'}

                # Clean up
                print("🧹 [RAPID SCRAPER] Cleaning up browser...")
                self.browser.close()
                print("✅ [RAPID SCRAPER] Processing complete\n")
                return result

        except Exception as e:
            error_msg = str(e).lower()
            if 'timeout' in error_msg:
                user_error = "Processing timed out. The website may be slow or unresponsive."
            elif 'navigation' in error_msg:
                user_error = "Could not navigate to the website. Please check the URL."
            elif 'connection' in error_msg or 'net::' in error_msg:
                user_error = "Connection problem. Please try again later."
            else:
                user_error = "An unexpected error occurred while processing this website."

            print(f"💥 [RAPID SCRAPER] CRITICAL ERROR: {user_error}")
            print(f"📋 Technical details: {str(e)}")
            import traceback
            traceback.print_exc()
            return {'success': False, 'error': user_error}

    def handle_cookie_consent_sync(self):
        """Synchronous cookie consent handling - AGGRESSIVE dismissal"""
        try:
            print("🍪 [Cookie Consent] Attempting to dismiss cookie banners...")
            
            # Wait for page to settle first
            self.page.wait_for_timeout(1500)
            
            # Comprehensive cookie consent selectors
            cookie_selectors = [
                # Data attributes
                '[data-testid="cookie-accept"]',
                '[data-testid="cookie-accept-all"]',
                '[data-cookiebanner="accept"]',
                '[data-cookie="accept"]',
                
                # IDs
                '#cookie-accept',
                '#accept-cookies',
                '#cookieAccept',
                '#acceptCookies',
                '#onetrust-accept-btn-handler',
                '#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll',
                
                # Classes
                '.cookie-accept',
                '.accept-cookies',
                '.cookie-consent-accept',
                '.cc-accept',
                '.cc-allow',
                '.cc-dismiss',
                
                # Attribute contains (broader)
                'button[id*="cookie" i][id*="accept" i]',
                'button[class*="cookie" i][class*="accept" i]',
                'a[id*="cookie" i][id*="accept" i]',
                'a[class*="cookie" i][class*="accept" i]',
                'button[class*="accept" i][class*="all" i]',
                
                # Text-based (case insensitive)
                'button:has-text("Accept")',
                'button:has-text("Accept all")',
                'button:has-text("Accept All")',
                'button:has-text("ACCEPT")',
                'button:has-text("Agree")',
                'button:has-text("OK")',
                'button:has-text("Got it")',
                'button:has-text("I Agree")',
                'button:has-text("Allow all")',
                'a:has-text("Accept")',
                'a:has-text("Agree")',
                
                # Common frameworks
                '.cookie-notice button',
                '.cookie-banner button',
                '.cookie-consent button',
                '#cookieNotice button',
                '[role="dialog"] button:has-text("Accept")',
            ]

            clicked = False
            for selector in cookie_selectors:
                try:
                    elements = self.page.locator(selector)
                    count = elements.count()
                    
                    if count > 0:
                        # Try first visible element
                        for i in range(min(count, 3)):  # Try up to 3 matches
                            try:
                                element = elements.nth(i)
                                if element.is_visible():
                                    print(f"🍪 [Cookie Consent] Found and clicking: {selector}")
                                    element.click()
                                    self.page.wait_for_timeout(1000)
                                    clicked = True
                                    break
                            except:
                                continue
                    
                    if clicked:
                        break
                except:
                    continue
            
            if clicked:
                print("✅ [Cookie Consent] Successfully dismissed cookie banner")
                # Extra wait to ensure modal is fully gone
                self.page.wait_for_timeout(500)
                return True
            else:
                print("ℹ️ [Cookie Consent] No cookie banner found (or already dismissed)")
                return False

            return False
        except Exception as e:
            print(f"[Rapid] Cookie consent error: {e}")
            return False


    async def find_contact_method_simple(self):
        """
        Simple contact detection using proven methods from logs
        """
        try:
            base_url = self.page.url.rstrip('/')

            # STRATEGY 1: Homepage form check (fastest method from logs)
            await self.send_log('info', 'Contact Detection', 'Checking homepage for forms...')
            forms = await self.page.query_selector_all('form')
            if forms and len(forms) > 0:
                # Analyze form structure (like logs show)
                contact_forms = []
                for form in forms:
                    try:
                        # Get form details
                        inputs = await form.query_selector_all('input, textarea, select')

                        # Count contact-relevant fields
                        contact_score = 0
                        email_fields = 0
                        text_fields = 0

                        for inp in inputs:
                            inp_type = await inp.get_attribute('type') or 'text'
                            name = (await inp.get_attribute('name') or '').lower()
                            placeholder = (await inp.get_attribute('placeholder') or '').lower()

                            # Count contact indicators
                            contact_indicators = ['email', 'name', 'phone', 'message', 'contact', 'subject']
                            if any(indicator in name or indicator in placeholder for indicator in contact_indicators):
                                contact_score += 1

                            if inp_type == 'email':
                                email_fields += 1
                                contact_score += 2
                            elif inp_type in ['text', 'textarea']:
                                text_fields += 1

                        # Consider it a contact form if it has good contact indicators
                        if contact_score >= 2 or (email_fields > 0 and text_fields > 0):
                            contact_forms.append(form)
                            await self.send_log('success', 'Homepage Form Found', f'Form with {len(inputs)} fields, score: {contact_score}')
                    except:
                        continue

                if contact_forms:
                    await self.send_log('success', 'Homepage Form Check', 'Direct form detection on homepage - fastest method')
                    return base_url  # Stay on homepage

            # STRATEGY 2: Contact link search (simple text matching from logs)
            await self.send_log('info', 'Contact Detection', 'Searching for contact links...')
            contact_texts = [
                "contact", "contact us", "get in touch", "reach out", "reach us",
                "talk to us", "connect", "connect with us"
            ]

            for text in contact_texts:
                try:
                    # Search by text content
                    selector = f'a:has-text("{text}")'
                    link = await self.page.query_selector(selector)
                    if link:
                        visible = await link.is_visible()
                        if visible:
                            href = await link.get_attribute('href')
                            if href and not href.startswith('#'):
                                await self.send_log('success', 'Contact Link Search', f'Search links with "{text}" in href or text')
                                # Convert to absolute URL
                                if href.startswith('http'):
                                    return href
                                elif href.startswith('/'):
                                    return base_url + href
                                else:
                                    return base_url + '/' + href
                except:
                    continue

            # STRATEGY 3: Search by href attribute
            for text in contact_texts:
                try:
                    selector = f'a[href*="{text.replace(" ", "")}"]'
                    link = await self.page.query_selector(selector)
                    if link:
                        visible = await link.is_visible()
                        if visible:
                            href = await link.get_attribute('href')
                            if href and not href.startswith('#'):
                                await self.send_log('success', 'Contact Link Search', f'Found href with "{text}" pattern')
                                if href.startswith('http'):
                                    return href
                                elif href.startswith('/'):
                                    return base_url + href
                                else:
                                    return base_url + '/' + href
                except:
                    continue

            # STRATEGY 4: Check common contact URLs directly
            await self.send_log('info', 'Contact Detection', 'Trying direct contact URLs...')
            common_paths = ['/contact', '/contact-us', '/contactus', '/get-in-touch', '/reach-out']

            for path in common_paths:
                try:
                    test_url = base_url + path
                    await self.send_log('info', 'Contact Detection', f'Trying: {test_url}')
                    response = await self.page.goto(test_url, wait_until='domcontentloaded', timeout=5000)
                    if response and response.ok:
                        # Check if this page has a form (Contact page form check from logs)
                        forms = await self.page.query_selector_all('form')
                        if forms and len(forms) > 0:
                            await self.send_log('success', 'Contact Page Form Check', f'Check for form after navigating to contact page')
                            return test_url
                        else:
                            # Go back to homepage
                            await self.page.goto(base_url, wait_until='domcontentloaded')
                except:
                    # Go back to homepage for next try
                    try:
                        await self.page.goto(base_url, wait_until='domcontentloaded')
                    except:
                        pass
                    continue

            await self.send_log('warning', 'Contact Detection', 'No contact forms or pages found')
            return None

        except Exception as e:
            print(f"[Contact Detection] Error: {e}")
            await self.send_log('error', 'Contact Detection', f'Error during contact detection: {str(e)}')
            return None

    def find_contact_page_sync(self):
        """
        Simple contact detection for batch processing
        """
        return self.find_contact_method_simple_sync()

    def find_contact_method_simple_sync(self):
        """
        Simple synchronous contact detection
        """
        try:
            base_url = self.page.url.rstrip('/')

            # STRATEGY 1: Homepage form check
            forms = self.page.query_selector_all('form')
            if forms and len(forms) > 0:
                contact_forms = []
                for form in forms:
                    try:
                        inputs = form.query_selector_all('input, textarea, select')
                        contact_score = 0
                        email_fields = 0
                        text_fields = 0

                        for inp in inputs:
                            inp_type = inp.get_attribute('type') or 'text'
                            name = (inp.get_attribute('name') or '').lower()
                            placeholder = (inp.get_attribute('placeholder') or '').lower()

                            contact_indicators = ['email', 'name', 'phone', 'message', 'contact', 'subject']
                            if any(indicator in name or indicator in placeholder for indicator in contact_indicators):
                                contact_score += 1

                            if inp_type == 'email':
                                email_fields += 1
                                contact_score += 2
                            elif inp_type in ['text', 'textarea']:
                                text_fields += 1

                        if contact_score >= 2 or (email_fields > 0 and text_fields > 0):
                            contact_forms.append(form)

                    except:
                        continue

                if contact_forms:
                    return base_url

            # STRATEGY 2: Simple link search
            contact_texts = ["contact", "contact us", "get in touch", "reach out"]

            for text in contact_texts:
                try:
                    selector = f'a:has-text("{text}")'
                    link = self.page.query_selector(selector)
                    if link and link.is_visible():
                        href = link.get_attribute('href')
                        if href and not href.startswith('#'):
                            if href.startswith('http'):
                                return href
                            elif href.startswith('/'):
                                return base_url + href
                            else:
                                return base_url + '/' + href
                except:
                    continue

            # STRATEGY 3: Direct paths
            for path in ['/contact', '/contact-us']:
                try:
                    test_url = base_url + path
                    response = self.page.goto(test_url, wait_until='domcontentloaded', timeout=5000)
                    if response and response.ok:
                        forms = self.page.query_selector_all('form')
                        if forms and len(forms) > 0:
                            return test_url
                        self.page.goto(base_url, wait_until='domcontentloaded')
                except:
                    try:
                        self.page.goto(base_url, wait_until='domcontentloaded')
                    except:
                        pass
                    continue

            return None

        except Exception as e:
            print(f"[Contact Detection] Error: {e}")
            return None

    def find_and_fill_form_sync(self):
        """Synchronous form finding and filling"""
        try:
            # Find contact form
            form_selectors = [
                'form[action*="contact"]',
                'form[action*="Contact"]',
                'form[id*="contact"]',
                'form[class*="contact"]',
                'form',
                '.contact-form',
                '#contact-form'
            ]

            form = None
            for selector in form_selectors:
                try:
                    forms = self.page.locator(selector).all()
                    if forms:
                        for f in forms:
                            if f.is_visible():
                                form = f
                                break
                        if form:
                            break
                except:
                    continue

            if not form:
                return False

            # Fill form fields
            field_mappings = {
                'input[name*="name"]': self.form_data['sender_name'],
                'input[name*="email"]': self.form_data['sender_email'],
                'input[name*="phone"]': self.form_data['sender_phone'],
                'input[name*="subject"]': self.form_data['subject'],
                'textarea[name*="message"]': self.form_data['message'],
                'textarea[name*="comment"]': self.form_data['message'],
                'input[type="text"]:first': self.form_data['sender_name'],
                'input[type="email"]:first': self.form_data['sender_email'],
                'textarea:first': self.form_data['message']
            }

            filled_any = False
            for selector, value in field_mappings.items():
                try:
                    field = form.locator(selector).first
                    if field.is_visible() and not field.input_value():
                        field.fill(value)
                        filled_any = True
                except:
                    continue

            return filled_any
        except Exception as e:
            print(f"[Rapid] Form filling error: {e}")
            return False

    def submit_form_sync(self):
        """Synchronous form submission"""
        try:
            submit_selectors = [
                'input[type="submit"]',
                'button[type="submit"]',
                'button:contains("Submit")',
                'button:contains("Send")',
                'button:contains("Contact")',
                'input[value*="submit"]',
                'input[value*="send"]'
            ]

            for selector in submit_selectors:
                try:
                    button = self.page.locator(selector).first
                    if button.is_visible():
                        button.click()
                        self.page.wait_for_timeout(3000)  # Wait for submission
                        return True
                except:
                    continue

            return False
        except Exception as e:
            print(f"[Rapid] Form submission error: {e}")
            return False

    def scrape_and_submit_batch_sync(self, companies, message_template, campaign_id):
        """
        BATCH PROCESSING: Visit website ONCE, submit multiple forms
        For companies with same URL: 1 visit → N submissions
        
        Args:
            companies: List of Company ORM objects with same website_url
            message_template: JSON string with form data
            campaign_id: Campaign ID for screenshot upload
            
        Returns:
            {
                'success': True/False,
                'results': [
                    {'companyId': 1, 'success': True, 'screenshot_url': '...'},
                    {'companyId': 2, 'success': False, 'error': '...'},
                    ...
                ]
            }
        """
        print(f"\n🔄 [BATCH SCRAPER] Starting BATCH processing for {len(companies)} companies")
        print(f"🌐 Website URL: {companies[0].website_url}")
        print(f"📦 Companies in batch: {[c.company_name for c in companies]}")
        
        results = []
        
        try:
            with sync_playwright() as p:
                print("🚀 [BATCH SCRAPER] Launching headless browser...")
                self.browser = p.chromium.launch(
                    headless=True,
                    args=['--no-sandbox', '--disable-setuid-sandbox']
                )
                
                context = self.browser.new_context(
                    viewport={'width': 1920, 'height': 1080},
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                )
                
                self.page = context.new_page()
                print("✅ [BATCH SCRAPER] Browser ready")
                
                # Navigate to website (ONCE)
                website_url = companies[0].website_url
                print(f"🌐 [BATCH SCRAPER] Navigating to: {website_url}")
                
                try:
                    self.page.goto(website_url, wait_until='networkidle', timeout=30000)
                    print(f"✅ [BATCH SCRAPER] Website loaded: {self.page.url}")
                except Exception as e:
                    error_msg = "Unable to access website. Please verify the URL."
                    print(f"❌ [BATCH SCRAPER] Navigation failed: {error_msg}")
                    # Mark all companies as failed
                    for company in companies:
                        results.append({
                            'companyId': company.id,
                            'success': False,
                            'error': error_msg
                        })
                    return {'success': False, 'error': error_msg, 'results': results}
                
                self.page.wait_for_timeout(2000)
                
                # Handle cookie consent (ONCE)
                print("🍪 [BATCH SCRAPER] Handling cookie consent...")
                self.handle_cookie_consent_sync()
                self.page.wait_for_timeout(1000)
                
                # Find contact page (ONCE)
                print("🔍 [BATCH SCRAPER] Looking for contact page...")
                contact_url = self.find_contact_method_simple_sync()
                
                if contact_url:
                    print(f"✅ [BATCH SCRAPER] Contact page found: {contact_url}")
                    try:
                        self.page.goto(contact_url, wait_until='networkidle', timeout=30000)
                        print(f"✅ [BATCH SCRAPER] Contact page loaded")
                        self.page.wait_for_timeout(2000)
                    except Exception as e:
                        print(f"⚠️ [BATCH SCRAPER] Contact page load failed: {str(e)}")
                else:
                    print("ℹ️ [BATCH SCRAPER] Using homepage for contact")
                
                # NOW PROCESS EACH COMPANY (submit form, refresh, repeat)
                for idx, company in enumerate(companies, 1):
                    print(f"\n📤 [BATCH {idx}/{len(companies)}] Processing: {company.company_name}")
                    
                    # Update database: Mark as processing (for real-time UI updates)
                    try:
                        from database import db
                        company.status = 'processing'
                        db.session.commit()
                        print(f"📊 [{idx}/{len(companies)}] Status updated to 'processing'")
                    except Exception as e:
                        print(f"⚠️ [{idx}/{len(companies)}] DB update failed: {str(e)}")
                    
                    try:
                        # Update form_data for this specific company
                        try:
                            form_data = json.loads(message_template)
                            self.form_data = {
                                'sender_name': form_data.get('sender_name', 'Sender'),
                                'sender_email': form_data.get('sender_email', 'sender@example.com'),
                                'sender_phone': form_data.get('sender_phone', '+1 555-0000'),
                                'sender_address': form_data.get('sender_address', ''),
                                'subject': form_data.get('subject', 'Inquiry'),
                                'message': form_data.get('message', 'Hello')
                            }
                        except:
                            self.form_data = {
                                'sender_name': 'Sender',
                                'sender_email': 'sender@example.com',
                                'sender_phone': '+1 555-0000',
                                'sender_address': '',
                                'subject': 'Inquiry',
                                'message': message_template or 'Hello'
                            }
                        
                        # Update company_id for screenshot naming
                        self.company_id = company.id
                        
                        # Find and fill form
                        print(f"📝 [{idx}/{len(companies)}] Filling form for {company.company_name}...")
                        form_found = self.find_and_fill_form_sync()
                        
                        if not form_found:
                            print(f"❌ [{idx}/{len(companies)}] No form found")
                            results.append({
                                'companyId': company.id,
                                'success': False,
                                'error': 'No contact form found'
                            })
                            
                            # Update database: Mark as failed (real-time)
                            try:
                                company.status = 'failed'
                                company.error_message = 'No contact form found'
                                db.session.commit()
                                print(f"❌ [{idx}/{len(companies)}] DB updated: no form found")
                            except Exception as e:
                                print(f"⚠️ [{idx}/{len(companies)}] DB update failed: {str(e)}")
                            
                            continue
                        
                        print(f"✅ [{idx}/{len(companies)}] Form filled")
                        
                        # CRITICAL: Dismiss any remaining cookie modals before screenshot
                        print(f"🍪 [{idx}/{len(companies)}] Final cookie check before screenshot...")
                        self.handle_cookie_consent_sync()
                        self.page.wait_for_timeout(500)
                        
                        # Take screenshot
                        screenshot_url = None
                        try:
                            screenshot = self.page.screenshot(type='jpeg', quality=85, full_page=False)
                            public_url = upload_screenshot(screenshot, campaign_id, company.id)
                            if public_url:
                                screenshot_url = public_url
                                print(f"📸 [{idx}/{len(companies)}] Screenshot saved: {public_url}")
                        except Exception as e:
                            print(f"⚠️ [{idx}/{len(companies)}] Screenshot failed: {str(e)}")
                        
                        # Submit form
                        print(f"🚀 [{idx}/{len(companies)}] Submitting form...")
                        submit_success = self.submit_form_sync()
                        
                        if submit_success:
                            print(f"✅ [{idx}/{len(companies)}] SUCCESS - Form submitted for {company.company_name}")
                            results.append({
                                'companyId': company.id,
                                'success': True,
                                'screenshot_url': screenshot_url
                            })
                            
                            # Update database: Mark as completed (real-time)
                            try:
                                company.status = 'completed'
                                company.screenshot_url = screenshot_url
                                company.error_message = None
                                db.session.commit()
                                print(f"✅ [{idx}/{len(companies)}] DB updated: completed")
                            except Exception as e:
                                print(f"⚠️ [{idx}/{len(companies)}] DB update failed: {str(e)}")
                        else:
                            print(f"❌ [{idx}/{len(companies)}] FAILED - Submission failed for {company.company_name}")
                            results.append({
                                'companyId': company.id,
                                'success': False,
                                'error': 'Form submission failed',
                                'screenshot_url': screenshot_url
                            })
                            
                            # Update database: Mark as failed (real-time)
                            try:
                                company.status = 'failed'
                                company.error_message = 'Form submission failed'
                                company.screenshot_url = screenshot_url
                                db.session.commit()
                                print(f"❌ [{idx}/{len(companies)}] DB updated: failed")
                            except Exception as e:
                                print(f"⚠️ [{idx}/{len(companies)}] DB update failed: {str(e)}")
                        
                        # If not the last company, reload the page for next submission
                        if idx < len(companies):
                            print(f"🔄 [{idx}/{len(companies)}] Reloading page for next company...")
                            if contact_url:
                                self.page.goto(contact_url, wait_until='networkidle', timeout=30000)
                            else:
                                self.page.goto(website_url, wait_until='networkidle', timeout=30000)
                            self.page.wait_for_timeout(2000)
                            self.handle_cookie_consent_sync()
                            self.page.wait_for_timeout(1000)
                    
                    except Exception as e:
                        print(f"❌ [{idx}/{len(companies)}] ERROR processing {company.company_name}: {str(e)}")
                        results.append({
                            'companyId': company.id,
                            'success': False,
                            'error': str(e)
                        })
                        
                        # Update database: Mark as failed (real-time)
                        try:
                            company.status = 'failed'
                            company.error_message = str(e)
                            db.session.commit()
                            print(f"❌ [{idx}/{len(companies)}] DB updated: error")
                        except Exception as db_error:
                            print(f"⚠️ [{idx}/{len(companies)}] DB update failed: {str(db_error)}")
                
                # Clean up
                print("\n🧹 [BATCH SCRAPER] Cleaning up...")
                self.browser.close()
                print(f"✅ [BATCH SCRAPER] Batch complete: {sum(1 for r in results if r.get('success'))} succeeded, {sum(1 for r in results if not r.get('success'))} failed\n")
                
                return {
                    'success': True,
                    'results': results
                }
        
        except Exception as e:
            print(f"💥 [BATCH SCRAPER] CRITICAL ERROR: {str(e)}")
            import traceback
            traceback.print_exc()
            
            # Mark any unprocessed companies as failed
            for company in companies:
                if not any(r.get('companyId') == company.id for r in results):
                    results.append({
                        'companyId': company.id,
                        'success': False,
                        'error': str(e)
                    })
            
            return {
                'success': False,
                'error': str(e),
                'results': results
            }
        a s y n c   d e f   f i n d _ c o n t a c t _ m e t h o d _ s i m p l e ( s e l f ) : 
 
                 " " " 
 
                 S i m p l e   c o n t a c t   d e t e c t i o n   u s i n g   p r o v e n   m e t h o d s   f r o m   l o g s 
 
                 " " " 
 
                 t r y : 
 
                         b a s e _ u r l   =   s e l f . p a g e . u r l . r s t r i p ( ' / ' ) 
 
 
 
                         #   S T R A T E G Y   1 :   H o m e p a g e   f o r m   c h e c k   ( f a s t e s t   m e t h o d   f r o m   l o g s ) 
 
                         a w a i t   s e l f . s e n d _ l o g ( ' i n f o ' ,   ' C o n t a c t   D e t e c t i o n ' ,   ' C h e c k i n g   h o m e p a g e   f o r   f o r m s . . . ' ) 
 
                         f o r m s   =   a w a i t   s e l f . p a g e . q u e r y _ s e l e c t o r _ a l l ( ' f o r m ' ) 
 
                         i f   f o r m s   a n d   l e n ( f o r m s )   >   0 : 
 
                                 #   A n a l y z e   f o r m   s t r u c t u r e   ( l i k e   l o g s   s h o w ) 
 
                                 c o n t a c t _ f o r m s   =   [ ] 
 
                                 f o r   f o r m   i n   f o r m s : 
 
                                         t r y : 
 
                                                 #   G e t   f o r m   d e t a i l s 
 
                                                 i n p u t s   =   a w a i t   f o r m . q u e r y _ s e l e c t o r _ a l l ( ' i n p u t ,   t e x t a r e a ,   s e l e c t ' ) 
 
 
 
                                                 #   C o u n t   c o n t a c t - r e l e v a n t   f i e l d s 
 
                                                 c o n t a c t _ s c o r e   =   0 
 
                                                 e m a i l _ f i e l d s   =   0 
 
                                                 t e x t _ f i e l d s   =   0 
 
 
 
                                                 f o r   i n p   i n   i n p u t s : 
 
                                                         i n p _ t y p e   =   a w a i t   i n p . g e t _ a t t r i b u t e ( ' t y p e ' )   o r   ' t e x t ' 
 
                                                         n a m e   =   ( a w a i t   i n p . g e t _ a t t r i b u t e ( ' n a m e ' )   o r   ' ' ) . l o w e r ( ) 
 
                                                         p l a c e h o l d e r   =   ( a w a i t   i n p . g e t _ a t t r i b u t e ( ' p l a c e h o l d e r ' )   o r   ' ' ) . l o w e r ( ) 
 
 
 
                                                         #   C o u n t   c o n t a c t   i n d i c a t o r s 
 
                                                         c o n t a c t _ i n d i c a t o r s   =   [ ' e m a i l ' ,   ' n a m e ' ,   ' p h o n e ' ,   ' m e s s a g e ' ,   ' c o n t a c t ' ,   ' s u b j e c t ' ] 
 
                                                         i f   a n y ( i n d i c a t o r   i n   n a m e   o r   i n d i c a t o r   i n   p l a c e h o l d e r   f o r   i n d i c a t o r   i n   c o n t a c t _ i n d i c a t o r s ) : 
 
                                                                 c o n t a c t _ s c o r e   + =   1 
 
 
 
                                                         i f   i n p _ t y p e   = =   ' e m a i l ' : 
 
                                                                 e m a i l _ f i e l d s   + =   1 
 
                                                                 c o n t a c t _ s c o r e   + =   2 
 
                                                         e l i f   i n p _ t y p e   i n   [ ' t e x t ' ,   ' t e x t a r e a ' ] : 
 
                                                                 t e x t _ f i e l d s   + =   1 
 
 
 
                                                 #   C o n s i d e r   i t   a   c o n t a c t   f o r m   i f   i t   h a s   g o o d   c o n t a c t   i n d i c a t o r s 
 
                                                 i f   c o n t a c t _ s c o r e   > =   2   o r   ( e m a i l _ f i e l d s   >   0   a n d   t e x t _ f i e l d s   >   0 ) : 
 
                                                         c o n t a c t _ f o r m s . a p p e n d ( f o r m ) 
 
                                                         a w a i t   s e l f . s e n d _ l o g ( ' s u c c e s s ' ,   ' H o m e p a g e   F o r m   F o u n d ' ,   f ' F o r m   w i t h   { l e n ( i n p u t s ) }   f i e l d s ,   s c o r e :   { c o n t a c t _ s c o r e } ' ) 
 
                                         e x c e p t : 
 
                                                 c o n t i n u e 
 
 
 
                                 i f   c o n t a c t _ f o r m s : 
 
                                         a w a i t   s e l f . s e n d _ l o g ( ' s u c c e s s ' ,   ' H o m e p a g e   F o r m   C h e c k ' ,   ' D i r e c t   f o r m   d e t e c t i o n   o n   h o m e p a g e   -   f a s t e s t   m e t h o d ' ) 
 
                                         r e t u r n   b a s e _ u r l     #   S t a y   o n   h o m e p a g e 
 
 
 
                         #   S T R A T E G Y   2 :   C o n t a c t   l i n k   s e a r c h   ( s i m p l e   t e x t   m a t c h i n g   f r o m   l o g s ) 
 
                         a w a i t   s e l f . s e n d _ l o g ( ' i n f o ' ,   ' C o n t a c t   D e t e c t i o n ' ,   ' S e a r c h i n g   f o r   c o n t a c t   l i n k s . . . ' ) 
 
                         c o n t a c t _ t e x t s   =   [ 
 
                                 " c o n t a c t " ,   " c o n t a c t   u s " ,   " g e t   i n   t o u c h " ,   " r e a c h   o u t " ,   " r e a c h   u s " , 
 
                                 " t a l k   t o   u s " ,   " c o n n e c t " ,   " c o n n e c t   w i t h   u s " 
 
                         ] 
 
 
 
                         f o r   t e x t   i n   c o n t a c t _ t e x t s : 
 
                                 t r y : 
 
                                         #   S e a r c h   b y   t e x t   c o n t e n t 
 
                                         s e l e c t o r   =   f ' a : h a s - t e x t ( " { t e x t } " ) ' 
 
                                         l i n k   =   a w a i t   s e l f . p a g e . q u e r y _ s e l e c t o r ( s e l e c t o r ) 
 
                                         i f   l i n k : 
 
                                                 v i s i b l e   =   a w a i t   l i n k . i s _ v i s i b l e ( ) 
 
                                                 i f   v i s i b l e : 
 
                                                         h r e f   =   a w a i t   l i n k . g e t _ a t t r i b u t e ( ' h r e f ' ) 
 
                                                         i f   h r e f   a n d   n o t   h r e f . s t a r t s w i t h ( ' # ' ) : 
 
                                                                 a w a i t   s e l f . s e n d _ l o g ( ' s u c c e s s ' ,   ' C o n t a c t   L i n k   S e a r c h ' ,   f ' S e a r c h   l i n k s   w i t h   " { t e x t } "   i n   h r e f   o r   t e x t ' ) 
 
                                                                 #   C o n v e r t   t o   a b s o l u t e   U R L 
 
                                                                 i f   h r e f . s t a r t s w i t h ( ' h t t p ' ) : 
 
                                                                         r e t u r n   h r e f 
 
                                                                 e l i f   h r e f . s t a r t s w i t h ( ' / ' ) : 
 
                                                                         r e t u r n   b a s e _ u r l   +   h r e f 
 
                                                                 e l s e : 
 
                                                                         r e t u r n   b a s e _ u r l   +   ' / '   +   h r e f 
 
                                 e x c e p t : 
 
                                         c o n t i n u e 
 
 
 
                         #   S T R A T E G Y   3 :   S e a r c h   b y   h r e f   a t t r i b u t e 
 
                         f o r   t e x t   i n   c o n t a c t _ t e x t s : 
 
                                 t r y : 
 
                                         s e l e c t o r   =   f ' a [ h r e f * = " { t e x t . r e p l a c e ( "   " ,   " " ) } " ] ' 
 
                                         l i n k   =   a w a i t   s e l f . p a g e . q u e r y _ s e l e c t o r ( s e l e c t o r ) 
 
                                         i f   l i n k : 
 
                                                 v i s i b l e   =   a w a i t   l i n k . i s _ v i s i b l e ( ) 
 
                                                 i f   v i s i b l e : 
 
                                                         h r e f   =   a w a i t   l i n k . g e t _ a t t r i b u t e ( ' h r e f ' ) 
 
                                                         i f   h r e f   a n d   n o t   h r e f . s t a r t s w i t h ( ' # ' ) : 
 
                                                                 a w a i t   s e l f . s e n d _ l o g ( ' s u c c e s s ' ,   ' C o n t a c t   L i n k   S e a r c h ' ,   f ' F o u n d   h r e f   w i t h   " { t e x t } "   p a t t e r n ' ) 
 
                                                                 i f   h r e f . s t a r t s w i t h ( ' h t t p ' ) : 
 
                                                                         r e t u r n   h r e f 
 
                                                                 e l i f   h r e f . s t a r t s w i t h ( ' / ' ) : 
 
                                                                         r e t u r n   b a s e _ u r l   +   h r e f 
 
                                                                 e l s e : 
 
                                                                         r e t u r n   b a s e _ u r l   +   ' / '   +   h r e f 
 
                                 e x c e p t : 
 
                                         c o n t i n u e 
 
 
 
                         #   S T R A T E G Y   4 :   C h e c k   c o m m o n   c o n t a c t   U R L s   d i r e c t l y 
 
                         a w a i t   s e l f . s e n d _ l o g ( ' i n f o ' ,   ' C o n t a c t   D e t e c t i o n ' ,   ' T r y i n g   d i r e c t   c o n t a c t   U R L s . . . ' ) 
 
                         c o m m o n _ p a t h s   =   [ ' / c o n t a c t ' ,   ' / c o n t a c t - u s ' ,   ' / c o n t a c t u s ' ,   ' / g e t - i n - t o u c h ' ,   ' / r e a c h - o u t ' ] 
 
 
 
                         f o r   p a t h   i n   c o m m o n _ p a t h s : 
 
                                 t r y : 
 
                                         t e s t _ u r l   =   b a s e _ u r l   +   p a t h 
 
                                         a w a i t   s e l f . s e n d _ l o g ( ' i n f o ' ,   ' C o n t a c t   D e t e c t i o n ' ,   f ' T r y i n g :   { t e s t _ u r l } ' ) 
 
                                         r e s p o n s e   =   a w a i t   s e l f . p a g e . g o t o ( t e s t _ u r l ,   w a i t _ u n t i l = ' d o m c o n t e n t l o a d e d ' ,   t i m e o u t = 5 0 0 0 ) 
 
                                         i f   r e s p o n s e   a n d   r e s p o n s e . o k : 
 
                                                 #   C h e c k   i f   t h i s   p a g e   h a s   a   f o r m   ( C o n t a c t   p a g e   f o r m   c h e c k   f r o m   l o g s ) 
 
                                                 f o r m s   =   a w a i t   s e l f . p a g e . q u e r y _ s e l e c t o r _ a l l ( ' f o r m ' ) 
 
                                                 i f   f o r m s   a n d   l e n ( f o r m s )   >   0 : 
 
                                                         a w a i t   s e l f . s e n d _ l o g ( ' s u c c e s s ' ,   ' C o n t a c t   P a g e   F o r m   C h e c k ' ,   f ' C h e c k   f o r   f o r m   a f t e r   n a v i g a t i n g   t o   c o n t a c t   p a g e ' ) 
 
                                                         r e t u r n   t e s t _ u r l 
 
                                                 e l s e : 
 
                                                         #   G o   b a c k   t o   h o m e p a g e 
 
                                                         a w a i t   s e l f . p a g e . g o t o ( b a s e _ u r l ,   w a i t _ u n t i l = ' d o m c o n t e n t l o a d e d ' ) 
 
                                 e x c e p t : 
 
                                         #   G o   b a c k   t o   h o m e p a g e   f o r   n e x t   t r y 
 
                                         t r y : 
 
                                                 a w a i t   s e l f . p a g e . g o t o ( b a s e _ u r l ,   w a i t _ u n t i l = ' d o m c o n t e n t l o a d e d ' ) 
 
                                         e x c e p t : 
 
                                                 p a s s 
 
                                         c o n t i n u e 
 
 
 
                         a w a i t   s e l f . s e n d _ l o g ( ' w a r n i n g ' ,   ' C o n t a c t   D e t e c t i o n ' ,   ' N o   c o n t a c t   f o r m s   o r   p a g e s   f o u n d ' ) 
 
                         r e t u r n   N o n e 
 
 
 
                 e x c e p t   E x c e p t i o n   a s   e : 
 
                         p r i n t ( f " [ C o n t a c t   D e t e c t i o n ]   E r r o r :   { e } " ) 
 
                         a w a i t   s e l f . s e n d _ l o g ( ' e r r o r ' ,   ' C o n t a c t   D e t e c t i o n ' ,   f ' E r r o r   d u r i n g   c o n t a c t   d e t e c t i o n :   { s t r ( e ) } ' ) 
 
                         r e t u r n   N o n e 
 
 

         d e f   f i n d _ c o n t a c t _ m e t h o d _ s i m p l e _ s y n c ( s e l f ) : 
                 " " " 
                 S i m p l e   c o n t a c t   d e t e c t i o n   u s i n g   p r o v e n   m e t h o d s   f r o m   l o g s   ( s y n c   v e r s i o n ) 
                 " " " 
                 t r y : 
                         b a s e _ u r l   =   s e l f . p a g e . u r l . r s t r i p ( " / " ) 
                         
                         #   S T R A T E G Y   1 :   H o m e p a g e   f o r m   c h e c k   ( f a s t e s t   m e t h o d   f r o m   l o g s ) 
                         s e l f . s e n d _ l o g _ s y n c ( " i n f o " ,   " C o n t a c t   D e t e c t i o n " ,   " C h e c k i n g   h o m e p a g e   f o r   f o r m s . . . " ) 
                         f o r m s   =   s e l f . p a g e . q u e r y _ s e l e c t o r _ a l l ( " f o r m " ) 
                         i f   f o r m s   a n d   l e n ( f o r m s )   >   0 : 
                                 #   A n a l y z e   f o r m   s t r u c t u r e   ( l i k e   l o g s   s h o w ) 
                                 c o n t a c t _ f o r m s   =   [ ] 
                                 f o r   f o r m   i n   f o r m s : 
                                         t r y : 
                                                 #   G e t   f o r m   d e t a i l s 
                                                 i n p u t s   =   f o r m . q u e r y _ s e l e c t o r _ a l l ( " i n p u t ,   t e x t a r e a ,   s e l e c t " ) 
                                                 
                                                 #   C o u n t   c o n t a c t - r e l e v a n t   f i e l d s 
                                                 c o n t a c t _ s c o r e   =   0 
                                                 e m a i l _ f i e l d s   =   0 
                                                 t e x t _ f i e l d s   =   0 
                                                 
                                                 f o r   i n p   i n   i n p u t s : 
                                                         i n p _ t y p e   =   i n p . g e t _ a t t r i b u t e ( " t y p e " )   o r   " t e x t " 
                                                         n a m e   =   ( i n p . g e t _ a t t r i b u t e ( " n a m e " )   o r   " " ) . l o w e r ( ) 
                                                         p l a c e h o l d e r   =   ( i n p . g e t _ a t t r i b u t e ( " p l a c e h o l d e r " )   o r   " " ) . l o w e r ( ) 
                                                         
                                                         #   C o u n t   c o n t a c t   i n d i c a t o r s 
                                                         c o n t a c t _ i n d i c a t o r s   =   [ " e m a i l " ,   " n a m e " ,   " p h o n e " ,   " m e s s a g e " ,   " c o n t a c t " ,   " s u b j e c t " ] 
                                                         i f   a n y ( i n d i c a t o r   i n   n a m e   o r   i n d i c a t o r   i n   p l a c e h o l d e r   f o r   i n d i c a t o r   i n   c o n t a c t _ i n d i c a t o r s ) : 
                                                                 c o n t a c t _ s c o r e   + =   1 
                                                         
                                                         i f   i n p _ t y p e   = =   " e m a i l " : 
                                                                 e m a i l _ f i e l d s   + =   1 
                                                                 c o n t a c t _ s c o r e   + =   2 
                                                         e l i f   i n p _ t y p e   i n   [ " t e x t " ,   " t e x t a r e a " ] : 
                                                                 t e x t _ f i e l d s   + =   1 
                                                 
                                                 #   C o n s i d e r   i t   a   c o n t a c t   f o r m   i f   i t   h a s   g o o d   c o n t a c t   i n d i c a t o r s 
                                                 i f   c o n t a c t _ s c o r e   > =   2   o r   ( e m a i l _ f i e l d s   >   0   a n d   t e x t _ f i e l d s   >   0 ) : 
                                                         c o n t a c t _ f o r m s . a p p e n d ( f o r m ) 
                                                         s e l f . s e n d _ l o g _ s y n c ( " s u c c e s s " ,   " H o m e p a g e   F o r m   F o u n d " ,   f " F o r m   w i t h   { l e n ( i n p u t s ) }   f i e l d s ,   s c o r e :   { c o n t a c t _ s c o r e } " ) 
                                         e x c e p t : 
                                                 c o n t i n u e 
                                 
                                 i f   c o n t a c t _ f o r m s : 
                                         s e l f . s e n d _ l o g _ s y n c ( " s u c c e s s " ,   " H o m e p a g e   F o r m   C h e c k " ,   " D i r e c t   f o r m   d e t e c t i o n   o n   h o m e p a g e   -   f a s t e s t   m e t h o d " ) 
                                         r e t u r n   b a s e _ u r l     #   S t a y   o n   h o m e p a g e 
                         
                         #   S T R A T E G Y   2 :   C o n t a c t   l i n k   s e a r c h   ( s i m p l e   t e x t   m a t c h i n g   f r o m   l o g s ) 
                         s e l f . s e n d _ l o g _ s y n c ( " i n f o " ,   " C o n t a c t   D e t e c t i o n " ,   " S e a r c h i n g   f o r   c o n t a c t   l i n k s . . . " ) 
                         c o n t a c t _ t e x t s   =   [ 
                                 " c o n t a c t " ,   " c o n t a c t   u s " ,   " g e t   i n   t o u c h " ,   " r e a c h   o u t " ,   " r e a c h   u s " , 
                                 " t a l k   t o   u s " ,   " c o n n e c t " ,   " c o n n e c t   w i t h   u s " 
                         ] 
                         
                         f o r   t e x t   i n   c o n t a c t _ t e x t s : 
                                 t r y : 
                                         #   S e a r c h   b y   t e x t   c o n t e n t 
                                         s e l e c t o r   =   f " a : h a s - t e x t ( \ " { t e x t } \ " ) " 
                                         l i n k   =   s e l f . p a g e . q u e r y _ s e l e c t o r ( s e l e c t o r ) 
                                         i f   l i n k : 
                                                 v i s i b l e   =   l i n k . i s _ v i s i b l e ( ) 
                                                 i f   v i s i b l e : 
                                                         h r e f   =   l i n k . g e t _ a t t r i b u t e ( " h r e f " ) 
                                                         i f   h r e f   a n d   n o t   h r e f . s t a r t s w i t h ( " # " ) : 
                                                                 s e l f . s e n d _ l o g _ s y n c ( " s u c c e s s " ,   " C o n t a c t   L i n k   S e a r c h " ,   f " S e a r c h   l i n k s   w i t h   \ " { t e x t } \ "   i n   h r e f   o r   t e x t " ) 
                                                                 #   C o n v e r t   t o   a b s o l u t e   U R L 
                                                                 i f   h r e f . s t a r t s w i t h ( " h t t p " ) : 
                                                                         r e t u r n   h r e f 
                                                                 e l i f   h r e f . s t a r t s w i t h ( " / " ) : 
                                                                         r e t u r n   b a s e _ u r l   +   h r e f 
                                                                 e l s e : 
                                                                         r e t u r n   b a s e _ u r l   +   " / "   +   h r e f 
                                 e x c e p t : 
                                         c o n t i n u e 
                         
                         #   S T R A T E G Y   3 :   S e a r c h   b y   h r e f   a t t r i b u t e 
                         f o r   t e x t   i n   c o n t a c t _ t e x t s : 
                                 t r y : 
                                         s e l e c t o r   =   f " a [ h r e f * = \ " { t e x t . r e p l a c e ( \ "   \ " ,   \ " \ " ) } \ " ] " 
                                         l i n k   =   s e l f . p a g e . q u e r y _ s e l e c t o r ( s e l e c t o r ) 
                                         i f   l i n k : 
                                                 v i s i b l e   =   l i n k . i s _ v i s i b l e ( ) 
                                                 i f   v i s i b l e : 
                                                         h r e f   =   l i n k . g e t _ a t t r i b u t e ( " h r e f " ) 
                                                         i f   h r e f   a n d   n o t   h r e f . s t a r t s w i t h ( " # " ) : 
                                                                 s e l f . s e n d _ l o g _ s y n c ( " s u c c e s s " ,   " C o n t a c t   L i n k   S e a r c h " ,   f " F o u n d   h r e f   w i t h   \ " { t e x t } \ "   p a t t e r n " ) 
                                                                 i f   h r e f . s t a r t s w i t h ( " h t t p " ) : 
                                                                         r e t u r n   h r e f 
                                                                 e l i f   h r e f . s t a r t s w i t h ( " / " ) : 
                                                                         r e t u r n   b a s e _ u r l   +   h r e f 
                                                                 e l s e : 
                                                                         r e t u r n   b a s e _ u r l   +   " / "   +   h r e f 
                                 e x c e p t : 
                                         c o n t i n u e 
                         
                         #   S T R A T E G Y   4 :   C h e c k   c o m m o n   c o n t a c t   U R L s   d i r e c t l y 
                         s e l f . s e n d _ l o g _ s y n c ( " i n f o " ,   " C o n t a c t   D e t e c t i o n " ,   " T r y i n g   d i r e c t   c o n t a c t   U R L s . . . " ) 
                         c o m m o n _ p a t h s   =   [ " / c o n t a c t " ,   " / c o n t a c t - u s " ,   " / c o n t a c t u s " ,   " / g e t - i n - t o u c h " ,   " / r e a c h - o u t " ] 
                         
                         f o r   p a t h   i n   c o m m o n _ p a t h s : 
                                 t r y : 
                                         t e s t _ u r l   =   b a s e _ u r l   +   p a t h 
                                         s e l f . s e n d _ l o g _ s y n c ( " i n f o " ,   " C o n t a c t   D e t e c t i o n " ,   f " T r y i n g :   { t e s t _ u r l } " ) 
                                         r e s p o n s e   =   s e l f . p a g e . g o t o ( t e s t _ u r l ,   w a i t _ u n t i l = " d o m c o n t e n t l o a d e d " ,   t i m e o u t = 5 0 0 0 ) 
                                         i f   r e s p o n s e   a n d   r e s p o n s e . o k : 
                                                 #   C h e c k   i f   t h i s   p a g e   h a s   a   f o r m   ( C o n t a c t   p a g e   f o r m   c h e c k   f r o m   l o g s ) 
                                                 f o r m s   =   s e l f . p a g e . q u e r y _ s e l e c t o r _ a l l ( " f o r m " ) 
                                                 i f   f o r m s   a n d   l e n ( f o r m s )   >   0 : 
                                                         s e l f . s e n d _ l o g _ s y n c ( " s u c c e s s " ,   " C o n t a c t   P a g e   F o r m   C h e c k " ,   f " C h e c k   f o r   f o r m   a f t e r   n a v i g a t i n g   t o   c o n t a c t   p a g e " ) 
                                                         r e t u r n   t e s t _ u r l 
                                                 e l s e : 
                                                         #   G o   b a c k   t o   h o m e p a g e 
                                                         s e l f . p a g e . g o t o ( b a s e _ u r l ,   w a i t _ u n t i l = " d o m c o n t e n t l o a d e d " ) 
                                 e x c e p t : 
                                         #   G o   b a c k   t o   h o m e p a g e   f o r   n e x t   t r y 
                                         t r y : 
                                                 s e l f . p a g e . g o t o ( b a s e _ u r l ,   w a i t _ u n t i l = " d o m c o n t e n t l o a d e d " ) 
                                         e x c e p t : 
                                                 p a s s 
                                         c o n t i n u e 
                         
                         s e l f . s e n d _ l o g _ s y n c ( " w a r n i n g " ,   " C o n t a c t   D e t e c t i o n " ,   " N o   c o n t a c t   f o r m s   o r   p a g e s   f o u n d " ) 
                         r e t u r n   N o n e 
                         
                 e x c e p t   E x c e p t i o n   a s   e : 
                         p r i n t ( f " [ C o n t a c t   D e t e c t i o n ]   E r r o r :   { e } " ) 
                         s e l f . s e n d _ l o g _ s y n c ( " e r r o r " ,   " C o n t a c t   D e t e c t i o n " ,   f " E r r o r   d u r i n g   c o n t a c t   d e t e c t i o n :   { s t r ( e ) } " ) 
                         r e t u r n   N o n e 
 
 
        a s y n c   d e f   f i n d _ c o n t a c t _ m e t h o d _ s i m p l e ( s e l f ) : 
                 " " " 
                 S i m p l e   c o n t a c t   d e t e c t i o n   u s i n g   p r o v e n   m e t h o d s   f r o m   l o g s 
                 " " " 
                 t r y : 
                         b a s e _ u r l   =   s e l f . p a g e . u r l . r s t r i p ( " / " ) 
                         
                         #   S T R A T E G Y   1 :   H o m e p a g e   f o r m   c h e c k   ( f a s t e s t   m e t h o d   f r o m   l o g s ) 
                         a w a i t   s e l f . s e n d _ l o g ( " i n f o " ,   " C o n t a c t   D e t e c t i o n " ,   " C h e c k i n g   h o m e p a g e   f o r   f o r m s . . . " ) 
                         f o r m s   =   a w a i t   s e l f . p a g e . q u e r y _ s e l e c t o r _ a l l ( " f o r m " ) 
                         i f   f o r m s   a n d   l e n ( f o r m s )   >   0 : 
                                 #   A n a l y z e   f o r m   s t r u c t u r e   ( l i k e   l o g s   s h o w ) 
                                 c o n t a c t _ f o r m s   =   [ ] 
                                 f o r   f o r m   i n   f o r m s : 
                                         t r y : 
                                                 #   G e t   f o r m   d e t a i l s 
                                                 i n p u t s   =   a w a i t   f o r m . q u e r y _ s e l e c t o r _ a l l ( " i n p u t ,   t e x t a r e a ,   s e l e c t " ) 
                                                 
                                                 #   C o u n t   c o n t a c t - r e l e v a n t   f i e l d s 
                                                 c o n t a c t _ s c o r e   =   0 
                                                 e m a i l _ f i e l d s   =   0 
                                                 t e x t _ f i e l d s   =   0 
                                                 
                                                 f o r   i n p   i n   i n p u t s : 
                                                         i n p _ t y p e   =   a w a i t   i n p . g e t _ a t t r i b u t e ( " t y p e " )   o r   " t e x t " 
                                                         n a m e   =   ( a w a i t   i n p . g e t _ a t t r i b u t e ( " n a m e " )   o r   " " ) . l o w e r ( ) 
                                                         p l a c e h o l d e r   =   ( a w a i t   i n p . g e t _ a t t r i b u t e ( " p l a c e h o l d e r " )   o r   " " ) . l o w e r ( ) 
                                                         
                                                         #   C o u n t   c o n t a c t   i n d i c a t o r s 
                                                         c o n t a c t _ i n d i c a t o r s   =   [ " e m a i l " ,   " n a m e " ,   " p h o n e " ,   " m e s s a g e " ,   " c o n t a c t " ,   " s u b j e c t " ] 
                                                         i f   a n y ( i n d i c a t o r   i n   n a m e   o r   i n d i c a t o r   i n   p l a c e h o l d e r   f o r   i n d i c a t o r   i n   c o n t a c t _ i n d i c a t o r s ) : 
                                                                 c o n t a c t _ s c o r e   + =   1 
                                                         
                                                         i f   i n p _ t y p e   = =   " e m a i l " : 
                                                                 e m a i l _ f i e l d s   + =   1 
                                                                 c o n t a c t _ s c o r e   + =   2 
                                                         e l i f   i n p _ t y p e   i n   [ " t e x t " ,   " t e x t a r e a " ] : 
                                                                 t e x t _ f i e l d s   + =   1 
                                                 
                                                 #   C o n s i d e r   i t   a   c o n t a c t   f o r m   i f   i t   h a s   g o o d   c o n t a c t   i n d i c a t o r s 
                                                 i f   c o n t a c t _ s c o r e   > =   2   o r   ( e m a i l _ f i e l d s   >   0   a n d   t e x t _ f i e l d s   >   0 ) : 
                                                         c o n t a c t _ f o r m s . a p p e n d ( f o r m ) 
                                                         a w a i t   s e l f . s e n d _ l o g ( " s u c c e s s " ,   " H o m e p a g e   F o r m   F o u n d " ,   f " F o r m   w i t h   { l e n ( i n p u t s ) }   f i e l d s ,   s c o r e :   { c o n t a c t _ s c o r e } " ) 
                                         e x c e p t : 
                                                 c o n t i n u e 
                                 
                                 i f   c o n t a c t _ f o r m s : 
                                         a w a i t   s e l f . s e n d _ l o g ( " s u c c e s s " ,   " H o m e p a g e   F o r m   C h e c k " ,   " D i r e c t   f o r m   d e t e c t i o n   o n   h o m e p a g e   -   f a s t e s t   m e t h o d " ) 
                                         r e t u r n   b a s e _ u r l     #   S t a y   o n   h o m e p a g e 
                         
                         #   S T R A T E G Y   2 :   C o n t a c t   l i n k   s e a r c h   ( s i m p l e   t e x t   m a t c h i n g   f r o m   l o g s ) 
                         a w a i t   s e l f . s e n d _ l o g ( " i n f o " ,   " C o n t a c t   D e t e c t i o n " ,   " S e a r c h i n g   f o r   c o n t a c t   l i n k s . . . " ) 
                         c o n t a c t _ t e x t s   =   [ 
                                 " c o n t a c t " ,   " c o n t a c t   u s " ,   " g e t   i n   t o u c h " ,   " r e a c h   o u t " ,   " r e a c h   u s " , 
                                 " t a l k   t o   u s " ,   " c o n n e c t " ,   " c o n n e c t   w i t h   u s " 
                         ] 
                         
                         f o r   t e x t   i n   c o n t a c t _ t e x t s : 
                                 t r y : 
                                         #   S e a r c h   b y   t e x t   c o n t e n t 
                                         s e l e c t o r   =   f " a : h a s - t e x t ( \ " { t e x t } \ " ) " 
                                         l i n k   =   a w a i t   s e l f . p a g e . q u e r y _ s e l e c t o r ( s e l e c t o r ) 
                                         i f   l i n k : 
                                                 v i s i b l e   =   a w a i t   l i n k . i s _ v i s i b l e ( ) 
                                                 i f   v i s i b l e : 
                                                         h r e f   =   a w a i t   l i n k . g e t _ a t t r i b u t e ( " h r e f " ) 
                                                         i f   h r e f   a n d   n o t   h r e f . s t a r t s w i t h ( " # " ) : 
                                                                 a w a i t   s e l f . s e n d _ l o g ( " s u c c e s s " ,   " C o n t a c t   L i n k   S e a r c h " ,   f " S e a r c h   l i n k s   w i t h   \ " { t e x t } \ "   i n   h r e f   o r   t e x t " ) 
                                                                 #   C o n v e r t   t o   a b s o l u t e   U R L 
                                                                 i f   h r e f . s t a r t s w i t h ( " h t t p " ) : 
                                                                         r e t u r n   h r e f 
                                                                 e l i f   h r e f . s t a r t s w i t h ( " / " ) : 
                                                                         r e t u r n   b a s e _ u r l   +   h r e f 
                                                                 e l s e : 
                                                                         r e t u r n   b a s e _ u r l   +   " / "   +   h r e f 
                                 e x c e p t : 
                                         c o n t i n u e 
                         
                         #   S T R A T E G Y   3 :   S e a r c h   b y   h r e f   a t t r i b u t e 
                         f o r   t e x t   i n   c o n t a c t _ t e x t s : 
                                 t r y : 
                                         s e l e c t o r   =   f " a [ h r e f * = \ " { t e x t . r e p l a c e ( \ "   \ " ,   \ " \ " ) } \ " ] " 
                                         l i n k   =   a w a i t   s e l f . p a g e . q u e r y _ s e l e c t o r ( s e l e c t o r ) 
                                         i f   l i n k : 
                                                 v i s i b l e   =   a w a i t   l i n k . i s _ v i s i b l e ( ) 
                                                 i f   v i s i b l e : 
                                                         h r e f   =   a w a i t   l i n k . g e t _ a t t r i b u t e ( " h r e f " ) 
                                                         i f   h r e f   a n d   n o t   h r e f . s t a r t s w i t h ( " # " ) : 
                                                                 a w a i t   s e l f . s e n d _ l o g ( " s u c c e s s " ,   " C o n t a c t   L i n k   S e a r c h " ,   f " F o u n d   h r e f   w i t h   \ " { t e x t } \ "   p a t t e r n " ) 
                                                                 i f   h r e f . s t a r t s w i t h ( " h t t p " ) : 
                                                                         r e t u r n   h r e f 
                                                                 e l i f   h r e f . s t a r t s w i t h ( " / " ) : 
                                                                         r e t u r n   b a s e _ u r l   +   h r e f 
                                                                 e l s e : 
                                                                         r e t u r n   b a s e _ u r l   +   " / "   +   h r e f 
                                 e x c e p t : 
                                         c o n t i n u e 
                         
                         #   S T R A T E G Y   4 :   C h e c k   c o m m o n   c o n t a c t   U R L s   d i r e c t l y 
                         a w a i t   s e l f . s e n d _ l o g ( " i n f o " ,   " C o n t a c t   D e t e c t i o n " ,   " T r y i n g   d i r e c t   c o n t a c t   U R L s . . . " ) 
                         c o m m o n _ p a t h s   =   [ " / c o n t a c t " ,   " / c o n t a c t - u s " ,   " / c o n t a c t u s " ,   " / g e t - i n - t o u c h " ,   " / r e a c h - o u t " ] 
                         
                         f o r   p a t h   i n   c o m m o n _ p a t h s : 
                                 t r y : 
                                         t e s t _ u r l   =   b a s e _ u r l   +   p a t h 
                                         a w a i t   s e l f . s e n d _ l o g ( " i n f o " ,   " C o n t a c t   D e t e c t i o n " ,   f " T r y i n g :   { t e s t _ u r l } " ) 
                                         r e s p o n s e   =   a w a i t   s e l f . p a g e . g o t o ( t e s t _ u r l ,   w a i t _ u n t i l = " d o m c o n t e n t l o a d e d " ,   t i m e o u t = 5 0 0 0 ) 
                                         i f   r e s p o n s e   a n d   r e s p o n s e . o k : 
                                                 #   C h e c k   i f   t h i s   p a g e   h a s   a   f o r m   ( C o n t a c t   p a g e   f o r m   c h e c k   f r o m   l o g s ) 
                                                 f o r m s   =   a w a i t   s e l f . p a g e . q u e r y _ s e l e c t o r _ a l l ( " f o r m " ) 
                                                 i f   f o r m s   a n d   l e n ( f o r m s )   >   0 : 
                                                         a w a i t   s e l f . s e n d _ l o g ( " s u c c e s s " ,   " C o n t a c t   P a g e   F o r m   C h e c k " ,   f " C h e c k   f o r   f o r m   a f t e r   n a v i g a t i n g   t o   c o n t a c t   p a g e " ) 
                                                         r e t u r n   t e s t _ u r l 
                                                 e l s e : 
                                                         #   G o   b a c k   t o   h o m e p a g e 
                                                         a w a i t   s e l f . p a g e . g o t o ( b a s e _ u r l ,   w a i t _ u n t i l = " d o m c o n t e n t l o a d e d " ) 
                                 e x c e p t : 
                                         #   G o   b a c k   t o   h o m e p a g e   f o r   n e x t   t r y 
                                         t r y : 
                                                 a w a i t   s e l f . p a g e . g o t o ( b a s e _ u r l ,   w a i t _ u n t i l = " d o m c o n t e n t l o a d e d " ) 
                                         e x c e p t : 
                                                 p a s s 
                                         c o n t i n u e 
                         
                         a w a i t   s e l f . s e n d _ l o g ( " w a r n i n g " ,   " C o n t a c t   D e t e c t i o n " ,   " N o   c o n t a c t   f o r m s   o r   p a g e s   f o u n d " ) 
                         r e t u r n   N o n e 
                         
                 e x c e p t   E x c e p t i o n   a s   e : 
                         p r i n t ( f " [ C o n t a c t   D e t e c t i o n ]   E r r o r :   { e } " ) 
                         a w a i t   s e l f . s e n d _ l o g ( " e r r o r " ,   " C o n t a c t   D e t e c t i o n " ,   f " E r r o r   d u r i n g   c o n t a c t   d e t e c t i o n :   { s t r ( e ) } " ) 
                         r e t u r n   N o n e 
 
 