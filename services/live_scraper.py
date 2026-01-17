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
        """Capture and stream screenshot"""
        if not self.page or not self.streaming:
            return
            
        try:
            screenshot = await self.page.screenshot(type='png')
            screenshot_base64 = base64.b64encode(screenshot).decode('utf-8')
            
            self.ws.send(json.dumps({
                'type': 'screenshot',
                'data': {
                    'image': f'data:image/png;base64,{screenshot_base64}',
                    'timestamp': datetime.utcnow().isoformat()
                }
            }))
        except Exception as e:
            print(f"Error streaming screenshot: {e}")
    
    async def start_streaming_loop(self):
        """Continuously stream screenshots"""
        while self.streaming and self.page:
            try:
                await self.stream_screenshot()
                await asyncio.sleep(0.5)  # 2 FPS
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
                    viewport={'width': 1280, 'height': 720},
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                )
                
                self.page = await context.new_page()
                
                # Start streaming task
                streaming_task = asyncio.create_task(self.start_streaming_loop())
                
                # Navigate to website
                website_url = self.company['website_url']
                await self.send_log('info', 'Navigating', f'Visiting {website_url}')
                
                try:
                    await self.page.goto(website_url, wait_until='networkidle', timeout=30000)
                    await self.send_log('success', 'Loaded', f'Successfully loaded homepage')
                except Exception as e:
                    await self.send_log('failed', 'Error', f'Failed to load homepage: {str(e)}')
                    return {'success': False, 'error': str(e)}
                
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
                    await self.send_log('success', 'Contact Page', f'Found contact page: {contact_url}')
                    await self.page.goto(contact_url, wait_until='networkidle', timeout=30000)
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
                        await self.send_log('success', 'Completed', 'Form submitted successfully!')
                        result = {'success': True}
                    else:
                        await self.send_log('failed', 'Submit Failed', 'Could not submit form')
                        result = {'success': False, 'error': 'Form submission failed'}
                else:
                    await self.send_log('failed', 'No Form', 'Could not find or fill contact form')
                    result = {'success': False, 'error': 'No form found'}
                
                await asyncio.sleep(3)  # Let user see final result
                
                # Stop streaming
                self.streaming = False
                await streaming_task
                
                await self.browser.close()
                return result
                
        except Exception as e:
            await self.send_log('failed', 'Error', f'Scraping failed: {str(e)}')
            if self.browser:
                await self.browser.close()
            return {'success': False, 'error': str(e)}
    
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
        """Fill contact form with message"""
        try:
            # Find form fields
            name_field = await self.page.query_selector('input[name*="name"], input[id*="name"], input[placeholder*="name"]')
            email_field = await self.page.query_selector('input[type="email"], input[name*="email"], input[id*="email"]')
            message_field = await self.page.query_selector('textarea[name*="message"], textarea[id*="message"], textarea[placeholder*="message"]')
            
            if not message_field:
                return False
            
            # Fill fields
            if name_field:
                await name_field.fill(self.company.get('company_name', 'Business Inquiry'))
            
            if email_field:
                await email_field.fill(self.company.get('contact_email', 'inquiry@business.com'))
            
            if message_field:
                # Personalize message
                message = self.message_template
                for key, value in self.company.items():
                    message = message.replace(f'{{{key}}}', str(value))
                
                await message_field.fill(message)
            
            await asyncio.sleep(1)
            return True
            
        except Exception as e:
            print(f"Error filling form: {e}")
            return False
    
    async def submit_form(self):
        """Submit the contact form"""
        submit_selectors = [
            'button[type="submit"]',
            'input[type="submit"]',
            'button:has-text("Send")',
            'button:has-text("Submit")',
            'button:has-text("Contact")',
            '[class*="submit"]'
        ]
        
        for selector in submit_selectors:
            try:
                button = await self.page.query_selector(selector)
                if button:
                    await button.click()
                    await asyncio.sleep(2)
                    return True
            except:
                continue
        
        return False
