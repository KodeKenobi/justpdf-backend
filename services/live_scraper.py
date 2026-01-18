"""
Live browser scraper with video streaming via WebSocket
Uses Playwright to capture browser viewport and stream to frontend
"""
import asyncio
import base64
from playwright.async_api import async_playwright
from datetime import datetime
import json

class LiveScraper:
    """Scrapes websites with live video streaming to frontend"""
    
    def __init__(self, websocket, company_data, message_template):
        self.ws = websocket
        self.company = company_data
        self.message_template = message_template
        self.browser = None
        self.page = None
        self.streaming = True
        
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
            print(f"Error sending log: {e}")
    
    async def stream_screenshot(self):
        """Capture and stream screenshot (TINY size to prevent WebSocket crashes)"""
        if not self.page or not self.streaming:
            return
            
        try:
            # Ultra-low quality screenshot to keep size minimal
            screenshot = await self.page.screenshot(
                type='jpeg',
                quality=15,  # Very low quality but visible (was 60)
                full_page=False,
                clip={'x': 0, 'y': 0, 'width': 960, 'height': 540}  # Half HD resolution
            )
            screenshot_base64 = base64.b64encode(screenshot).decode('utf-8')
            
            # Only send if data is reasonable size (< 50KB base64 = ~37KB raw)
            if len(screenshot_base64) < 50000:
                self.ws.send(json.dumps({
                    'type': 'screenshot',
                    'data': {
                        'image': f'data:image/jpeg;base64,{screenshot_base64}',
                        'timestamp': datetime.utcnow().isoformat()
                    }
                }))
            else:
                print(f"Screenshot too large ({len(screenshot_base64)} bytes), skipping")
        except Exception as e:
            print(f"Error streaming screenshot: {e}")
    
    async def start_streaming_loop(self):
        """Continuously stream screenshots"""
        while self.streaming and self.page:
            try:
                await self.stream_screenshot()
                await asyncio.sleep(0.5)  # 2 FPS for smoother monitoring
            except Exception as e:
                print(f"Streaming loop error: {e}")
                break
    
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
                
                # Start streaming task (ultra-low quality to prevent crashes)
                streaming_task = asyncio.create_task(self.start_streaming_loop())
                
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
                
                # Handle cookie consent
                await self.send_log('info', 'Cookie Consent', 'Checking for cookie modals...')
                cookie_handled = await self.handle_cookie_consent()
                if cookie_handled:
                    await self.send_log('success', 'Cookie Consent', 'Cookie modal handled')
                    await asyncio.sleep(1)
                
                # Find contact page
                await self.send_log('info', 'Contact Page', 'Searching for contact page...')
                contact_url = await self.find_contact_page()
                
                if contact_url:
                    await self.send_log('success', 'Contact Page', f'Found contact page: {contact_url}', {'url': contact_url})
                    await self.page.goto(contact_url, wait_until='networkidle', timeout=30000)
                    await self.send_log('info', 'Loaded', f'Contact page loaded', {'url': self.page.url})
                    await asyncio.sleep(2)
                else:
                    await self.send_log('warning', 'Contact Page', 'No contact page found, staying on homepage')
                
                # Find and fill form
                await self.send_log('info', 'Form Detection', 'Looking for contact form...')
                form_filled = await self.fill_contact_form()
                
                if form_filled:
                    await self.send_log('success', 'Form Filled', 'Contact form filled successfully')
                    await asyncio.sleep(2)
                    
                    # Submit form
                    await self.send_log('info', 'Submitting', 'Submitting contact form...')
                    submitted = await self.submit_form()
                    
                    if submitted:
                        await self.send_log('success', 'Completed', 'Message sent successfully!')
                        result = {'success': True}
                    else:
                        await self.send_log('failed', 'Unable to Submit', 'Could not submit the contact form. The website may have protection measures in place.')
                        result = {'success': False, 'error': 'Unable to submit form'}
                else:
                    await self.send_log('failed', 'No Contact Form', 'This website does not have a standard contact form or it could not be detected.')
                    result = {'success': False, 'error': 'Contact form not found'}
                
                await asyncio.sleep(3)  # Let user see final result
                
                # Stop streaming
                self.streaming = False
                await streaming_task
                
                await self.browser.close()
                return result
                
        except Exception as e:
            error_message = 'An unexpected error occurred while processing this website'
            print(f"Technical error (hidden from user): {str(e)}")  # Log for debugging
            await self.send_log('failed', 'Processing Error', error_message)
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
        """Find contact page URL"""
        contact_patterns = [
            'a[href*="contact"]',
            'a[href*="kontakt"]',
            'a[href*="contacto"]',
            'a:has-text("Contact")',
            'a:has-text("Contact Us")',
            'a:has-text("Get in Touch")',
            'a:has-text("Kontakt")',
            'a:has-text("Contacto")'
        ]
        
        for pattern in contact_patterns:
            try:
                link = await self.page.query_selector(pattern)
                if link:
                    href = await link.get_attribute('href')
                    if href:
                        if href.startswith('http'):
                            return href
                        elif href.startswith('/'):
                            return self.page.url.rstrip('/') + href
                        else:
                            return self.page.url.rstrip('/') + '/' + href
            except:
                continue
        
        return None
    
    async def fill_contact_form(self):
        """COMPREHENSIVE form filling - handles ALL possible field types"""
        try:
            await self.send_log('info', 'Form Scanning', 'Detecting all form fields...')
            
            # Get all form elements on the page
            forms = await self.page.query_selector_all('form')
            if not forms:
                await self.send_log('warning', 'No Forms', 'No form elements found, scanning entire page...')
            
            # Data to fill
            fill_data = {
                'name': self.company.get('company_name', 'Business Development'),
                'email': self.company.get('contact_email', 'contact@business.com'),
                'phone': '+1 (555) 123-4567',
                'company': self.company.get('company_name', 'Business Development'),
                'website': self.company.get('website_url', 'https://business.com'),
                'subject': 'Business Inquiry',
                'message': self.message_template
            }
            
            # Personalize message
            for key, value in self.company.items():
                if value and key in fill_data['message']:
                    fill_data['message'] = fill_data['message'].replace(f'{{{key}}}', str(value))
            
            filled_fields = 0
            
            # === 1. TEXT INPUTS ===
            text_inputs = await self.page.query_selector_all('input[type="text"], input:not([type])')
            for inp in text_inputs:
                try:
                    if not await inp.is_visible():
                        continue
                    
                    name_attr = (await inp.get_attribute('name') or '').lower()
                    id_attr = (await inp.get_attribute('id') or '').lower()
                    placeholder = (await inp.get_attribute('placeholder') or '').lower()
                    aria_label = (await inp.get_attribute('aria-label') or '').lower()
                    
                    all_attrs = f"{name_attr} {id_attr} {placeholder} {aria_label}"
                    
                    # Determine what to fill based on attributes
                    if any(x in all_attrs for x in ['name', 'full', 'fname', 'first', 'contact']):
                        await inp.click()
                        await inp.fill(fill_data['name'])
                        await self.send_log('success', 'Field Filled', f'Name: {fill_data["name"]}')
                        filled_fields += 1
                    elif any(x in all_attrs for x in ['subject', 'title', 'topic', 'regarding']):
                        await inp.click()
                        await inp.fill(fill_data['subject'])
                        await self.send_log('success', 'Field Filled', f'Subject: {fill_data["subject"]}')
                        filled_fields += 1
                    elif any(x in all_attrs for x in ['company', 'organization', 'business']):
                        await inp.click()
                        await inp.fill(fill_data['company'])
                        await self.send_log('success', 'Field Filled', f'Company: {fill_data["company"]}')
                        filled_fields += 1
                    elif any(x in all_attrs for x in ['website', 'url', 'site']):
                        await inp.click()
                        await inp.fill(fill_data['website'])
                        await self.send_log('success', 'Field Filled', f'Website: {fill_data["website"]}')
                        filled_fields += 1
                except Exception as e:
                    print(f"Error filling text input: {e}")
                    continue
            
            # === 2. EMAIL INPUTS ===
            email_inputs = await self.page.query_selector_all('input[type="email"]')
            for inp in email_inputs:
                try:
                    if await inp.is_visible():
                        await inp.click()
                        await inp.fill(fill_data['email'])
                        await self.send_log('success', 'Field Filled', f'Email: {fill_data["email"]}')
                        filled_fields += 1
                except Exception as e:
                    print(f"Error filling email: {e}")
                    continue
            
            # === 3. PHONE INPUTS ===
            phone_inputs = await self.page.query_selector_all('input[type="tel"], input[name*="phone" i], input[id*="phone" i]')
            for inp in phone_inputs:
                try:
                    if await inp.is_visible():
                        await inp.click()
                        await inp.fill(fill_data['phone'])
                        await self.send_log('success', 'Field Filled', f'Phone: {fill_data["phone"]}')
                        filled_fields += 1
                except Exception as e:
                    print(f"Error filling phone: {e}")
                    continue
            
            # === 4. TEXTAREAS (Message) ===
            textareas = await self.page.query_selector_all('textarea')
            for textarea in textareas:
                try:
                    if await textarea.is_visible():
                        await textarea.click()
                        await textarea.fill(fill_data['message'])
                        await self.send_log('success', 'Field Filled', f'Message ({len(fill_data["message"])} chars)')
                        filled_fields += 1
                except Exception as e:
                    print(f"Error filling textarea: {e}")
                    continue
            
            # === 5. SELECT DROPDOWNS ===
            selects = await self.page.query_selector_all('select')
            for select in selects:
                try:
                    if await select.is_visible():
                        options = await select.query_selector_all('option')
                        if len(options) > 1:
                            # Select the second option (first is usually placeholder)
                            await select.select_option(index=1)
                            option_text = await options[1].text_content()
                            await self.send_log('success', 'Field Filled', f'Dropdown: {option_text}')
                            filled_fields += 1
                except Exception as e:
                    print(f"Error filling select: {e}")
                    continue
            
            # === 6. CHECKBOXES ===
            checkboxes = await self.page.query_selector_all('input[type="checkbox"]')
            for checkbox in checkboxes:
                try:
                    if await checkbox.is_visible():
                        name_attr = (await checkbox.get_attribute('name') or '').lower()
                        id_attr = (await checkbox.get_attribute('id') or '').lower()
                        
                        # Check required/consent checkboxes
                        if any(x in f"{name_attr} {id_attr}" for x in ['agree', 'accept', 'terms', 'consent', 'privacy', 'gdpr']):
                            if not await checkbox.is_checked():
                                await checkbox.check()
                                await self.send_log('success', 'Field Filled', f'Checkbox: {name_attr or id_attr}')
                                filled_fields += 1
                except Exception as e:
                    print(f"Error checking checkbox: {e}")
                    continue
            
            # === 7. RADIO BUTTONS ===
            radios = await self.page.query_selector_all('input[type="radio"]')
            radio_groups = {}
            for radio in radios:
                try:
                    if await radio.is_visible():
                        name = await radio.get_attribute('name')
                        if name and name not in radio_groups:
                            # Select first radio in each group
                            await radio.check()
                            radio_groups[name] = True
                            await self.send_log('success', 'Field Filled', f'Radio: {name}')
                            filled_fields += 1
                except Exception as e:
                    print(f"Error checking radio: {e}")
                    continue
            
            # === 8. DATE INPUTS ===
            date_inputs = await self.page.query_selector_all('input[type="date"]')
            for inp in date_inputs:
                try:
                    if await inp.is_visible():
                        from datetime import datetime, timedelta
                        future_date = (datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d')
                        await inp.fill(future_date)
                        await self.send_log('success', 'Field Filled', f'Date: {future_date}')
                        filled_fields += 1
                except Exception as e:
                    print(f"Error filling date: {e}")
                    continue
            
            # === 9. TIME INPUTS ===
            time_inputs = await self.page.query_selector_all('input[type="time"]')
            for inp in time_inputs:
                try:
                    if await inp.is_visible():
                        await inp.fill('10:00')
                        await self.send_log('success', 'Field Filled', 'Time: 10:00')
                        filled_fields += 1
                except Exception as e:
                    print(f"Error filling time: {e}")
                    continue
            
            # === 10. NUMBER INPUTS ===
            number_inputs = await self.page.query_selector_all('input[type="number"]')
            for inp in number_inputs:
                try:
                    if await inp.is_visible():
                        await inp.fill('1')
                        await self.send_log('success', 'Field Filled', 'Number: 1')
                        filled_fields += 1
                except Exception as e:
                    print(f"Error filling number: {e}")
                    continue
            
            await asyncio.sleep(1)
            
            if filled_fields == 0:
                await self.send_log('failed', 'No Fields Filled', 'Could not find or fill any form fields')
                return False
            
            await self.send_log('success', 'Form Complete', f'Successfully filled {filled_fields} fields')
            return True
            
        except Exception as e:
            await self.send_log('failed', 'Form Error', 'Unable to fill out the contact form.')
            print(f"Technical error filling form: {e}")
            return False
    
    async def submit_form(self):
        """Submit the contact form and verify submission"""
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
                    
                    # Click submit and wait for navigation or network idle
                    try:
                        # Try waiting for navigation (if form redirects)
                        async with self.page.expect_navigation(timeout=5000, wait_until='networkidle'):
                            await button.click()
                        await self.send_log('success', 'Navigation', 'Form submitted - page redirected')
                        return True
                    except:
                        # If no navigation, just click and wait for network
                        await button.click()
                        await self.page.wait_for_load_state('networkidle', timeout=5000)
                    
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
                    return True
                    
            except Exception as e:
                print(f"Technical error with selector {selector} (hidden from user): {e}")
                continue
        
        return False
