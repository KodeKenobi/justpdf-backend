"""
Fast Campaign Processor
Based on fast-contact-analyzer.js logic with form submission and email fallback
Optimized for speed - stops after finding ONE contact method per site.
Self-learning: records and uses patterns via brain_service (Supabase); no domains stored.
"""

import json
import os
import re
import time
from typing import Dict, List, Optional, Tuple

def _brain_record_event(event_type: str, outcome: str, pattern_value: Optional[str] = None, metadata: Optional[Dict] = None):
    try:
        from services.brain_service import record_event
        record_event(event_type, outcome, pattern_value=pattern_value, metadata=metadata)
    except Exception:
        pass

def _brain_record_pattern(pattern_type: str, pattern_value: str, success: bool):
    try:
        from services.brain_service import record_pattern_use
        record_pattern_use(pattern_type, pattern_value, success=success)
    except Exception:
        pass

def _brain_get_keywords(pattern_type: str, default: List[str]) -> List[str]:
    try:
        from services.brain_service import get_top_patterns
        learned = get_top_patterns(pattern_type, limit=30)
        if learned:
            return list(dict.fromkeys(learned + default))  # learned first, then defaults, no dupes
    except Exception:
        pass
    return default


class FastCampaignProcessor:
    """Fast, optimized campaign processing with early exit strategy"""

    def __init__(self, page, company_data: Dict, message_template: str, 
                 campaign_id: int = None, company_id: int = None, logger=None, subject: str = None, sender_data: Dict = None):
        self.page = page
        self.company = company_data
        self.campaign_id = campaign_id
        self.company_id = company_id
        self.logger = logger
        self.found_form = False
        self.found_contact_page = False
        self.website_url = self.company.get('website_url', '')

        # Parse message template (could be plain text or JSON)
        self.sender_data = sender_data or {}
        try:
            if isinstance(message_template, str) and (message_template.strip().startswith('{') or message_template.strip().startswith('[')):
                parsed = json.loads(message_template)
                if isinstance(parsed, dict):
                    # If we don't have explicit sender_data, use the parsed one
                    if not self.sender_data:
                        self.sender_data = parsed
                    self.message_body = parsed.get('message', '')
                    self.subject = subject or parsed.get('subject') or 'Partnership Inquiry'
                else:
                    self.message_body = message_template
                    self.subject = subject or 'Partnership Inquiry'
            else:
                self.message_body = message_template
                self.subject = subject or 'Partnership Inquiry'
        except Exception:
            self.message_body = message_template
            self.subject = subject or 'Partnership Inquiry'

    def log(self, level: str, action: str, message: str):
        """Unified logging for campaign activity"""
        if self.logger:
            self.logger(level, action, message)
        else:
            print(f"[{level.upper()}] {action}: {message}")

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
                self._record_brain_mandatory(None, [], False, 'invalid_url')
                return result

            # Track contact keyword when we follow a link (for mandatory brain recording)
            self._contact_keyword_used = None
            
            # Initial navigation
            self.log('info', 'Navigation', f'Opening {website_url}...')
            try:
                self.page.goto(website_url, wait_until='domcontentloaded', timeout=30000) # Increased to 30s
                self.handle_cookie_modal()
                self.page.wait_for_timeout(2000)
            except Exception as e:
                self.log('warning', 'Initial Navigation', f'Failed or timed out: {e}')
                # Continue anyway, Strategy 2 might still work if we have a partial load
            
            # STRATEGY 1: Check homepage for forms FIRST — only treat as contact form if it has 2+ fillable fields (skip newsletter/search)
            self.log('info', 'Strategy 1', 'Checking homepage for forms - fastest method')
            homepage_forms = self.page.query_selector_all('form')
            
            if homepage_forms:
                contact_like_count = self._count_contact_like_fields(homepage_forms[0])
                if contact_like_count >= 2:
                    self.log('success', 'Form Detection', f'Found contact-like form on homepage ({contact_like_count} fillable fields)')
                    form_result = self.fill_and_submit_form(homepage_forms[0], 'homepage')
                    if form_result['success']:
                        result.update(form_result)
                        result['method'] = 'form_submitted_homepage'
                        self.found_form = True
                        self._record_brain_mandatory(getattr(self, '_contact_keyword_used', None), form_result.get('filled_field_patterns', []), True, result.get('method', 'form_submitted_homepage'))
                        return result
                else:
                    self.log('info', 'Strategy 1', f'Skipping homepage form (only {contact_like_count} fillable field(s) — likely newsletter/search)')
            
            # STRATEGY 2: Find contact link and navigate (footer first — contact links are almost always in footer)
            self.log('info', 'Strategy 2', 'No form on homepage, searching for contact link (footer first)...')
            contact_keywords = _brain_get_keywords('contact_keyword', ['contact', 'get-in-touch', 'enquiry', 'support', 'about-us'])
            self.log('info', 'Discovery', 'Strategy 2: Searching for contact links')
            selector = ', '.join([f'a[href*="{kw}"]' for kw in contact_keywords]) + ', ' + \
                       ', '.join([f'a:has-text("{kw}")' for kw in contact_keywords])
            
            contact_link = None
            try:
                links = []
                footer_containers = self.page.query_selector_all('footer, [role="contentinfo"], .footer, #footer, .site-footer, .page-footer')
                for footer_el in (footer_containers or []):
                    try:
                        footer_links = footer_el.query_selector_all('a[href]')
                        for link in (footer_links or []):
                            href = link.get_attribute('href')
                            text = (link.inner_text() or '').strip().lower()
                            if not href or href.startswith('mailto:') or href.startswith('tel:'):
                                continue
                            if any(kw in (href or '').lower() or kw in text for kw in contact_keywords):
                                links.append(link)
                    except Exception:
                        pass
                if not links:
                    links = self.page.query_selector_all(selector)
                self.log('info', 'Discovery', f'Found {len(links)} potential contact links (footer-first)')
                
                for i, link in enumerate(links[:5]):
                    href = link.get_attribute('href')
                    text = (link.inner_text() or '').strip().lower()
                    if not href:
                        continue
                    matched_kw = next((kw for kw in contact_keywords if kw in (href or '').lower() or kw in text), None)
                    self._contact_keyword_used = matched_kw
                    full_href = self.make_absolute_url(href)
                    self.log('info', 'Testing Link', f'Link {i+1}: {text} ({href})')
                    try:
                        self.page.goto(full_href, wait_until='domcontentloaded', timeout=30000)
                        self.handle_cookie_modal()
                        self.page.wait_for_timeout(800)
                        self.handle_cookie_modal()
                        self.log('info', 'Contact Page', 'Scrolling to trigger lazy-loading...')
                        self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                        self.page.wait_for_timeout(1500)
                        self.page.evaluate("window.scrollTo(0, 0)")
                        self.page.wait_for_timeout(1000)
                        self.handle_cookie_modal()
                        try:
                            self.page.wait_for_selector('form, input[type="email"], textarea, [id*="email"], iframe', timeout=15000)
                            self.page.wait_for_timeout(2000)
                        except Exception:
                            self.log('info', 'Contact Page', 'No form elements/iframes appeared within 15s, checking immediately')
                        contact_page_forms = self.page.query_selector_all('form')
                        if contact_page_forms:
                            self.log('success', 'Form Detection', f'Found {len(contact_page_forms)} form(s) on contact page')
                            form_result = self.fill_and_submit_form(contact_page_forms[0], 'contact_page')
                            if form_result['success']:
                                result.update(form_result)
                                result['method'] = 'form_submitted_contact_page'
                                self.found_form = True
                                self._record_brain_mandatory(self._contact_keyword_used, form_result.get('filled_field_patterns', []), True, result.get('method', 'form_submitted_contact_page'))
                                return result
                            else:
                                self._record_brain_mandatory(self._contact_keyword_used, form_result.get('filled_field_patterns', []), False, form_result.get('method', 'form_fill_failed'))
                        else:
                            self.log('info', 'Contact Page Discovery', 'No direct form found, trying fallback extraction...')
                            contact_info = self.extract_contact_info()
                            if contact_info and contact_info.get('emails'):
                                self.log('success', 'Email Found', f"Found {len(contact_info['emails'])} email(s)")
                                email_sent = self.send_email_to_contact(contact_info['emails'][0])
                                if email_sent:
                                    path, screenshot_bytes = self.take_screenshot('email_sent')
                                    result.update({
                                        'success': True,
                                        'method': 'email_sent',
                                        'contact_info': contact_info,
                                        'screenshot_url': path,
                                        'screenshot_bytes': screenshot_bytes,
                                    })
                                    self._record_brain_mandatory(self._contact_keyword_used, [], True, 'email_sent')
                                    return result
                            self._record_brain_mandatory(matched_kw, [], False, 'contact_page_no_form')
                    except Exception as e:
                        self.log('warn', 'Link Failed', f'Could not open {full_href}: {str(e)}')
                        self._record_brain_mandatory(self._contact_keyword_used, [], False, 'link_failed')
                        continue
            except Exception as e:
                self.log('error', 'Strategy 2 Error', str(e))

            # STRATEGY 3: Check ALL frames (HubSpot/Typeform)
            self.log('info', 'Strategy 3', 'Checking all frames for embedded forms...')
            
            # Give frames a moment to load their content
            self.page.wait_for_timeout(2000)
            
            for idx, frame in enumerate(self.page.frames):
                if frame == self.page.main_frame: continue
                try:
                    # Wait slightly for each frame to be ready
                    self.log('info', 'Checking Frame', f'Checking frame {idx}: {frame.url[:50]}...')
                    
                    # Try to find forms in this frame
                    frame_forms = frame.query_selector_all('form')
                    if not frame_forms:
                        # Sometimes forms in iframes don't use <form> but have inputs
                        frame_inputs = frame.query_selector_all('input[type="email"], textarea')
                        if frame_inputs:
                            self.log('success', 'Frame Inputs Found', f'Found form-like inputs in frame: {frame.url[:50]}...')
                            form_result = self.fill_and_submit_form(frame, f'frame_{idx}_heuristic', is_iframe=True, is_heuristic=True, frame=frame)
                            if form_result['success']:
                                result.update(form_result)
                                result['method'] = 'form_submitted_iframe_heuristic'
                                self._record_brain_mandatory(getattr(self, '_contact_keyword_used', None), form_result.get('filled_field_patterns', []), True, result.get('method', 'form_submitted_iframe_heuristic'))
                                return result
                    
                    if frame_forms:
                        self.log('success', 'Frame Form Found', f'Found form in frame: {frame.url[:50]}...')
                        form_result = self.fill_and_submit_form(frame_forms[0], f'frame_{idx}', is_iframe=True, frame=frame)
                        if form_result['success']:
                            result.update(form_result)
                            result['method'] = 'form_submitted_iframe'
                            self._record_brain_mandatory(getattr(self, '_contact_keyword_used', None), form_result.get('filled_field_patterns', []), True, result.get('method', 'form_submitted_iframe'))
                            return result
                except Exception as e: 
                    self.log('warning', 'Frame Check Failed', f'Error checking frame {idx}: {str(e)}')
                    continue

            # STRATEGY 4: Heuristic Field Search (No <form> tag)
            self.log('info', 'Strategy 4', 'Searching for inputs by label heuristics...')
            heuristics_result = self.search_by_heuristics()
            if heuristics_result['success']:
                result.update(heuristics_result)
                result['method'] = 'form_submitted_heuristics'
                self._record_brain_mandatory(getattr(self, '_contact_keyword_used', None), heuristics_result.get('filled_field_patterns', []), True, result.get('method', 'form_submitted_heuristics'))
                return result

            # Last resort: email-only on current page (no form but may have visible emails)
            self.log('info', 'Email-only', 'No form found; checking current page for contact emails...')
            contact_info = self.extract_contact_info()
            if contact_info and contact_info.get('emails'):
                self.log('success', 'Email Found', f"Found {len(contact_info['emails'])} email(s)")
                email_sent = self.send_email_to_contact(contact_info['emails'][0])
                if email_sent:
                    path, screenshot_bytes = self.take_screenshot('email_sent')
                    result.update({
                        'success': True,
                        'method': 'email_sent',
                        'contact_info': contact_info,
                        'screenshot_url': path,
                        'screenshot_bytes': screenshot_bytes,
                    })
                    self._record_brain_mandatory(getattr(self, '_contact_keyword_used', None), [], True, 'email_sent')
                    return result

            # NO CONTACT FOUND
            self.log('error', 'No Contact Found', f'All strategies exhausted for {website_url}')
            result['error'] = f'No discovery method succeeded for {website_url}'
            self._record_brain_mandatory(getattr(self, '_contact_keyword_used', None), [], False, 'no_contact_found')
            
            # Log page source on discovery failure
            _path, _bytes = self.take_screenshot('failed_discovery')
            result['screenshot_url'] = _path
            result['screenshot_bytes'] = _bytes
            
            # Log some page info for debugging
            page_title = self.page.title()
            page_content_snippet = (self.page.content() or "")[:1000].replace('\n', ' ')
            self.log('error', 'Discovery Failed', f"Title: {page_title} | Snippet: {page_content_snippet}")
            return result
            
        except Exception as e:
            self.log('error', 'Processing Error', str(e))
            result['error'] = str(e)
            _path, _bytes = self.take_screenshot('error_processing')
            result['screenshot_url'] = _path
            result['screenshot_bytes'] = _bytes
            self._record_brain_mandatory(getattr(self, '_contact_keyword_used', None), [], False, 'error_processing')
        
        return result

    def _count_contact_like_fields(self, form) -> int:
        """Count inputs/selects that look like contact form fields (not hidden/submit/button). Used to skip newsletter/search forms."""
        try:
            count = 0
            inputs = form.query_selector_all('input, textarea')
            selects = form.query_selector_all('select')
            for el in inputs or []:
                t = (el.get_attribute('type') or 'text').lower()
                if t in ('hidden', 'submit', 'button', 'image'):
                    continue
                count += 1
            for _ in selects or []:
                count += 1
            return count
        except Exception:
            return 0

    def make_absolute_url(self, href: str) -> str:
        """Converts a relative URL to an absolute URL."""
        if href.startswith('http://') or href.startswith('https://'):
            return href
        from urllib.parse import urljoin
        return urljoin(self.website_url, href)

    def _record_brain_mandatory(self, contact_keyword_used: Optional[str], field_patterns: List[Dict], success: bool, outcome: str) -> None:
        """Always record to brain: contact link, field patterns used, outcome. Not optional."""
        if contact_keyword_used:
            _brain_record_pattern('contact_keyword', contact_keyword_used, success=success)
        for fp in (field_patterns or []):
            role = fp.get('role') or 'unknown'
            pattern_value = (fp.get('name') or fp.get('label') or '').strip() or 'unknown'
            if pattern_value and role != 'unknown':
                _brain_record_pattern(f'field_{role}', pattern_value, success=success)
        _brain_record_event('outcome', outcome, metadata={'success': success, 'field_count': len(field_patterns or [])})

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
                    _brain_record_pattern('cookie_selector', selector[:200], success=True)
                    _brain_record_event('cookie_modal', 'dismissed', pattern_value=selector[:200])
                    return True
            except Exception:
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
            filled_field_patterns = []  # For mandatory brain recording: role, name, label per filled field
            
            # Prepare message
            message = self.replace_variables(self.message_body)
            
            for input_element in inputs:
                input_id = (input_element.get_attribute('id') or '').lower()
                name = (input_element.get_attribute('name') or '').lower()
                placeholder = (input_element.get_attribute('placeholder') or '').lower()
                input_type = (input_element.get_attribute('type') or 'text').lower()
                # Include visible label so "First name", "Last Name", "Branch" etc. are matched.
                # Many sites use <span>First name</span><input> or <div>First name</div><input> — use previous sibling text when it looks like a label (short, not dropdown phrasing).
                label_text = ''
                try:
                    label_text = (input_element.evaluate('''el => {
                        const id = el.id;
                        if (id) {
                            const label = document.querySelector('label[for="' + id + '"]');
                            if (label) return (label.textContent || '').trim().toLowerCase();
                        }
                        let p = el.closest('label') || el.parentElement;
                        if (p && p.tagName === 'LABEL') return (p.textContent || '').trim().toLowerCase();
                        for (let n = el.previousElementSibling; n; n = n.previousElementSibling) {
                            if (n.tagName === 'LABEL') return (n.textContent || '').trim().toLowerCase();
                            var t = (n.textContent || '').trim().toLowerCase();
                            if (t.length >= 2 && t.length <= 60 && !/^(choose|select|please select|general enquiry|--|select one)/.test(t) && !/branch\\s*$/.test(t))
                                return t;
                        }
                        const aria = el.getAttribute('aria-label');
                        if (aria) return aria.trim().toLowerCase();
                        return '';
                    }''') or '')
                except Exception:
                    pass
                # If label looks like dropdown phrasing (e.g. "General enquiry" from wrong element), don't use it so we don't mis-identify name fields
                if label_text and any(kw in label_text for kw in ['general enquiry', 'choose a branch', 'choose branch', 'select a branch', 'please select']):
                    label_text = ''
                field_text = f"{name} {placeholder} {input_id} {label_text}"
                self.log('info', 'Checking Field', f'Type: {input_type}, Name: {name}, Label: {label_text[:50]}, Text: {field_text[:80]}')
                
                try:
                    # Skip hidden, submit, button fields
                    if input_type in ['hidden', 'submit', 'button']:
                        continue
                    
                    # 1. Fill email field (Highest priority)
                    if not email_filled and (input_type == 'email' or any(kw in field_text for kw in ['email', 'e-mail'])):
                        email = self.sender_data.get('sender_email') or self.company.get('contact_email', 'contact@business.com')
                        input_element.click()
                        input_element.fill(email)
                        input_element.dispatch_event('input')
                        input_element.dispatch_event('change')
                        email_filled = True
                        filled_count += 1
                        filled_field_patterns.append({'role': 'email', 'name': input_element.get_attribute('name') or '', 'label': label_text})
                        self.log('info', 'Field Filled', f'Email field filled: {email}')
                        continue

                    # 2. Fill name fields (include "first name" from label text)
                    if any(kw in field_text for kw in ['first name', 'first-name', 'fname', 'firstname', 'given-name', 'givenname', 'first_name']):
                        fname = self.sender_data.get('sender_first_name') or self.company.get('contact_person', 'Business').split()[0]
                        input_element.click()
                        input_element.fill(fname)
                        input_element.dispatch_event('input')
                        input_element.dispatch_event('change')
                        filled_count += 1
                        filled_field_patterns.append({'role': 'first_name', 'name': input_element.get_attribute('name') or '', 'label': label_text})
                        self.log('info', 'Field Filled', f'First Name field filled: {fname}')
                        continue

                    if any(kw in field_text for kw in ['last name', 'last-name', 'lname', 'lastname', 'surname', 'family-name', 'familyname', 'last_name']):
                        lname = self.sender_data.get('sender_last_name')
                        if not lname:
                            name_parts = self.company.get('contact_person', 'Contact').split()
                            lname = name_parts[-1] if len(name_parts) > 1 else 'Contact'
                        input_element.click()
                        input_element.fill(lname)
                        input_element.dispatch_event('input')
                        input_element.dispatch_event('change')
                        filled_count += 1
                        filled_field_patterns.append({'role': 'last_name', 'name': input_element.get_attribute('name') or '', 'label': label_text})
                        self.log('info', 'Field Filled', f'Last Name field filled: {lname}')
                        continue

                    if any(kw in field_text for kw in ['full name', 'your name', 'name', 'full-name', 'fullname', 'your-name', 'full_name']) and 'company' not in field_text and 'first' not in field_text and 'last' not in field_text:
                        fullname = self.sender_data.get('sender_name') or self.company.get('contact_person', 'Business Contact')
                        input_element.click()
                        input_element.fill(fullname)
                        input_element.dispatch_event('input')
                        input_element.dispatch_event('change')
                        filled_count += 1
                        filled_field_patterns.append({'role': 'full_name', 'name': input_element.get_attribute('name') or '', 'label': label_text})
                        self.log('info', 'Field Filled', f'Name field filled: {fullname}')
                        continue
                    
                    # 3. Fill Company field
                    if any(kw in field_text for kw in ['company', 'organization', 'business-name', 'firm', 'business_name', 'org_name']) and 'email' not in field_text:
                        company_val = self.sender_data.get('sender_company') or self.company.get('company_name', 'Your Company')
                        input_element.click()
                        input_element.fill(company_val)
                        input_element.dispatch_event('input')
                        input_element.dispatch_event('change')
                        filled_count += 1
                        filled_field_patterns.append({'role': 'company', 'name': input_element.get_attribute('name') or '', 'label': label_text})
                        self.log('info', 'Field Filled', f'Company field filled: {company_val}')
                        continue

                    # 4. Fill phone field
                    if any(kw in field_text for kw in ['phone', 'tel', 'mobile', 'cell', 'telephone']) or input_type == 'tel':
                        phone = self.sender_data.get('sender_phone') or self.company.get('phone') or self.company.get('phone_number')
                        if phone:
                            input_element.click()
                            input_element.fill(phone)
                            input_element.dispatch_event('input')
                            input_element.dispatch_event('change')
                            filled_count += 1
                            filled_field_patterns.append({'role': 'phone', 'name': input_element.get_attribute('name') or '', 'label': label_text})
                            self.log('info', 'Field Filled', f'Phone field filled: {phone}')
                        continue
                    
                    # Fill subject field
                    if any(kw in field_text for kw in ['subject', 'topic', 'reason', 'inquiry_type']):
                        subject_val = self.subject
                        input_element.click()
                        input_element.fill(subject_val)
                        input_element.dispatch_event('input')
                        input_element.dispatch_event('change')
                        filled_count += 1
                        filled_field_patterns.append({'role': 'subject', 'name': input_element.get_attribute('name') or '', 'label': label_text})
                        self.log('info', 'Field Filled', f'Subject field: {subject_val}')
                        continue

                    # Fill country field (text input)
                    if any(kw in field_text for kw in ['country', 'nation', 'region', 'location', 'país', 'pays', 'land']):
                        country_val = self.sender_data.get('sender_country') or 'United Kingdom'
                        input_element.click()
                        input_element.fill(country_val)
                        input_element.dispatch_event('input')
                        input_element.dispatch_event('change')
                        filled_count += 1
                        filled_field_patterns.append({'role': 'country', 'name': input_element.get_attribute('name') or '', 'label': label_text})
                        self.log('info', 'Field Filled', f'Country field filled: {country_val}')
                        continue
                    
                    # Fill message/comment textarea
                    tag_name = input_element.evaluate('el => el.tagName.toLowerCase()')
                    if tag_name == 'textarea':
                        if not message_filled and any(kw in field_text for kw in ['message', 'comment', 'inquiry', 'details', 'body']):
                            input_element.fill(message)
                            input_element.dispatch_event('input')
                            input_element.dispatch_event('change')
                            message_filled = True
                            filled_count += 1
                            filled_field_patterns.append({'role': 'message', 'name': input_element.get_attribute('name') or '', 'label': label_text})
                            self.log('info', 'Field Filled', f'Message field filled')
                            continue
                            
                except Exception as e:
                    self.log('warning', 'Field Fill Failed', f'Field error: {str(e)}')
                    continue
            
            # Handle Selects (Dropdowns) — country first, then generic (branch, department, etc.)
            country_keywords = ['country', 'nation', 'ext', 'region', 'location', 'countrycode', 'country_code', 'dialcode']
            select_keywords_priority = ['branch', 'office', 'department', 'location', 'region', 'enquiry', 'inquiry', 'subject', 'topic', 'how', 'hear', 'source']
            # Reuse same label resolution as inputs so "Country", "Branch" etc. are matched from visible label
            _get_label_js = '''el => {
                const id = el.id;
                if (id) {
                    const label = document.querySelector('label[for="' + id + '"]');
                    if (label) return (label.textContent || '').trim().toLowerCase();
                }
                let p = el.closest('label') || el.parentElement;
                if (p && p.tagName === 'LABEL') return (p.textContent || '').trim().toLowerCase();
                for (let n = el.previousElementSibling; n; n = n.previousElementSibling) {
                    if (n.tagName === 'LABEL') return (n.textContent || '').trim().toLowerCase();
                    var t = (n.textContent || '').trim().toLowerCase();
                    if (t.length >= 2 && t.length <= 60) return t;
                }
                const aria = el.getAttribute('aria-label');
                if (aria) return aria.trim().toLowerCase();
                return '';
            }'''
            for select in selects:
                name = (select.get_attribute('name') or '').lower()
                placeholder = (select.get_attribute('placeholder') or '').lower()
                select_id = (select.get_attribute('id') or '').lower()
                select_label = ''
                try:
                    select_label = (select.evaluate(_get_label_js) or '')
                except Exception:
                    pass
                text = f"{name} {placeholder} {select_id} {select_label}"
                
                try:
                    options = select.query_selector_all('option')
                    if not options:
                        continue
                    handled = False
                    # Country/region dropdown — use campaign sender_country so user-defined country is applied
                    if any(kw in text for kw in country_keywords):
                        raw = (self.sender_data.get('sender_country') or 'United Kingdom').strip().lower()
                        wanted_country = raw
                        if wanted_country == 'uk':
                            wanted_country = 'united kingdom'
                        elif wanted_country == 'usa' or wanted_country == 'us':
                            wanted_country = 'united states'
                        target_val = None
                        target_label = None
                        for opt in options:
                            opt_val = opt.get_attribute('value')
                            opt_text = (opt.inner_text() or '').strip()
                            if not opt_text and not opt_val:
                                continue
                            opt_text_lower = opt_text.lower()
                            if wanted_country in opt_text_lower or opt_text_lower in wanted_country:
                                target_val = opt_val or opt_text
                                target_label = opt_text
                                break
                            if wanted_country == 'united kingdom' and any(x in opt_text_lower or (opt_val and x in (opt_val or '').lower()) for x in ('united kingdom', 'uk', 'britain', 'great britain', 'england')):
                                target_val = opt_val or opt_text
                                target_label = opt_text
                                break
                            if wanted_country == 'south africa' and any(x in opt_text_lower or (opt_val and x in (opt_val or '').lower()) for x in ('south africa', 'za')):
                                target_val = opt_val or opt_text
                                target_label = opt_text
                                break
                            if wanted_country == 'united states' and any(x in opt_text_lower or (opt_val and x in (opt_val or '').lower()) for x in ('united states', 'usa', 'us', 'america')):
                                target_val = opt_val or opt_text
                                target_label = opt_text
                                break
                        if target_val is None and len(options) > 1:
                            target_val = options[1].get_attribute('value') or (options[1].inner_text() or '').strip()
                        elif target_val is None:
                            target_val = options[0].get_attribute('value') or (options[0].inner_text() or '').strip()
                        if target_val:
                            try:
                                select.select_option(value=target_val)
                            except Exception:
                                try:
                                    select.select_option(label=target_label or target_val)
                                except Exception:
                                    select.select_option(index=1 if len(options) > 1 else 0)
                            filled_count += 1
                            filled_field_patterns.append({'role': 'country', 'name': name or '', 'label': select_label})
                            self.log('info', 'Field Filled', f'Country selected: {target_label or target_val}')
                            handled = True
                    # Generic select (branch, department, enquiry type, etc.): skip placeholder option, pick first real one; match sender_branch if present
                    if not handled:
                        # Branch/location: try to match sender_branch or sender_location from campaign, else first real option
                        branch_val = (self.sender_data.get('sender_branch') or self.sender_data.get('sender_location') or '').strip().lower()
                        target_opt_val = None
                        if branch_val:
                            for o in options:
                                ot = (o.inner_text() or '').strip().lower()
                                ov = (o.get_attribute('value') or '').lower()
                                if branch_val in ot or branch_val in ov or ot in branch_val:
                                    target_opt_val = o.get_attribute('value') or (o.inner_text() or '').strip()
                                    break
                        first_val = options[0].get_attribute('value')
                        first_text = (options[0].inner_text() or '').strip().lower()
                        is_placeholder = (not first_val or first_val == '' or
                                          first_text in ('select', 'choose', '--', 'please select', 'select one', 'select...'))
                        idx = 1 if (is_placeholder and len(options) > 1) else 0
                        opt = options[idx]
                        val = opt.get_attribute('value')
                        label = (opt.inner_text() or '').strip()
                        if target_opt_val:
                            val = target_opt_val
                            label = target_opt_val
                        if val is not None or label:
                            try:
                                select.select_option(value=val or label)
                            except Exception:
                                try:
                                    select.select_option(label=label or val)
                                except Exception:
                                    try:
                                        select.select_option(index=idx)
                                    except Exception:
                                        pass
                        else:
                            try:
                                select.select_option(index=idx)
                            except Exception:
                                pass
                        filled_count += 1
                        filled_field_patterns.append({'role': 'branch', 'name': name or '', 'label': select_label})
                        self.log('info', 'Field Filled', f'Select "{name or select_id}" -> {label or val or idx}')
                except Exception:
                    continue

            # Handle Radio groups: ensure one option selected per name (required for many forms)
            radios_by_name = {}
            for inp in inputs:
                if inp.get_attribute('type') == 'radio':
                    name = inp.get_attribute('name')
                    if name and inp.is_visible():
                        if name not in radios_by_name:
                            radios_by_name[name] = []
                        radios_by_name[name].append(inp)
            for name, group in radios_by_name.items():
                try:
                    # Prefer option whose label/value matches enquiry, email, phone, general
                    name_lower = name.lower()
                    group_text = ' '.join([
                        (el.get_attribute('value') or '') + ' ' +
                        (el.get_attribute('aria-label') or '') +
                        (el.evaluate("el => el.parentElement?.innerText || ''") or '')
                        for el in group
                    ]).lower()
                    preferred = ['email', 'phone', 'general', 'enquiry', 'inquiry', 'business', 'sales', 'support']
                    chosen = None
                    for opt in group:
                        val = (opt.get_attribute('value') or '').lower()
                        parent = (opt.evaluate("el => el.parentElement?.innerText || ''") or '').lower()
                        if any(p in val or p in parent for p in preferred):
                            chosen = opt
                            break
                    if chosen is None:
                        chosen = group[0]
                    if chosen and not chosen.evaluate('el => el.checked'):
                        chosen.click()
                        filled_count += 1
                        self.log('info', 'Field Filled', f'Radio "{name}" selected')
                except Exception:
                    continue

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

            # Fill remaining required selects only (first real option). Do NOT blindly fill required text inputs with "General enquiry" — that overwrites first/last name when label matching missed them.
            try:
                required_selects = form.query_selector_all('select[required]')
                for el in required_selects or []:
                    opts = el.query_selector_all('option')
                    if opts and len(opts) > 1:
                        first_text = (opts[1].inner_text() or '').strip().lower()
                        if first_text not in ('select', 'choose', '--', 'please select', 'select one', 'select...'):
                            try:
                                el.select_option(index=1)
                                filled_count += 1
                                self.log('info', 'Required Field', 'Select required: chose first real option')
                            except Exception:
                                pass
                # Only fill empty required textarea if it looks like message/comment (never put generic text in name/email fields)
                required_textareas = form.query_selector_all('textarea[required]')
                for el in required_textareas or []:
                    try:
                        current = (el.evaluate('el => el.value') or '') or ''
                        if current and str(current).strip():
                            continue
                        name = (el.get_attribute('name') or el.get_attribute('id') or '').lower()
                        if any(kw in name for kw in ['message', 'comment', 'inquiry', 'enquiry', 'body', 'details']):
                            el.fill(message)
                            el.dispatch_event('input')
                            el.dispatch_event('change')
                            filled_count += 1
                            self.log('info', 'Required Field', 'Required message textarea filled')
                    except Exception:
                        pass
            except Exception:
                pass

            # Take screenshot of the filled form (before submit)
            screenshot_url, screenshot_bytes = self.take_screenshot(f'filled_{location}')

            # Submit the form after screenshot
            if filled_count > 0:
                self.submit_form(form)
                self.page.wait_for_timeout(2000)
                # Detect validation failure: form still present and invalid inputs or visible error text
                try:
                    invalid = form.query_selector_all('input:invalid, textarea:invalid, select:invalid')
                    error_els = form.query_selector_all('[class*="error" i], [id*="error" i], [role="alert"]')
                    still_has_form = len(form.query_selector_all('input, textarea, select')) > 0
                    has_invalid = invalid and len(invalid) > 0
                    has_visible_error = False
                    for el in (error_els or []):
                        try:
                            if el.is_visible() and (el.inner_text() or '').strip():
                                has_visible_error = True
                                break
                        except Exception:
                            pass
                    has_validation_error = has_invalid or has_visible_error
                    if still_has_form and has_validation_error:
                        self.log('warning', 'Validation', 'Form reported validation errors after submit; attempting to fix required/empty fields')
                        for el in (invalid or []):
                            tag = el.evaluate('el => el.tagName.toLowerCase()')
                            name = (el.get_attribute('name') or '').lower()
                            elem_id = (el.get_attribute('id') or '').lower()
                            placeholder = (el.get_attribute('placeholder') or '').lower()
                            aria = (el.get_attribute('aria-label') or '').lower()
                            field_hint = f"{name} {elem_id} {placeholder} {aria}"
                            try:
                                if tag == 'select':
                                    opts = el.query_selector_all('option')
                                    if opts and len(opts) > 1:
                                        el.select_option(index=1)
                                        filled_count += 1
                                elif tag == 'textarea':
                                    current = el.evaluate('el => el.value') or ''
                                    if not (current and str(current).strip()) and any(kw in field_hint for kw in ['message', 'comment', 'inquiry', 'enquiry', 'body', 'details']):
                                        el.fill(message)
                                        el.dispatch_event('input')
                                        el.dispatch_event('change')
                                        filled_count += 1
                                elif el.get_attribute('type') in ('text', 'email', None):
                                    current = el.evaluate('el => el.value') or ''
                                    if not (current and str(current).strip()):
                                        if 'email' in field_hint or el.get_attribute('type') == 'email':
                                            el.fill(self.sender_data.get('sender_email') or 'contact@example.com')
                                            el.dispatch_event('input')
                                            el.dispatch_event('change')
                                            filled_count += 1
                                        elif any(kw in field_hint for kw in ['first name', 'first-name', 'fname', 'firstname', 'first_name']):
                                            fname = self.sender_data.get('sender_first_name') or self.company.get('contact_person', 'Business').split()[0]
                                            el.fill(fname)
                                            el.dispatch_event('input')
                                            el.dispatch_event('change')
                                            filled_count += 1
                                        elif any(kw in field_hint for kw in ['last name', 'last-name', 'lname', 'lastname', 'surname', 'last_name']):
                                            lname = self.sender_data.get('sender_last_name') or (self.company.get('contact_person', 'Contact').split()[-1] if len(self.company.get('contact_person', 'Contact').split()) > 1 else 'Contact')
                                            el.fill(lname)
                                            el.dispatch_event('input')
                                            el.dispatch_event('change')
                                            filled_count += 1
                                        elif any(kw in field_hint for kw in ['name', 'full name', 'your name']) and 'company' not in field_hint and 'first' not in field_hint and 'last' not in field_hint:
                                            fullname = self.sender_data.get('sender_name') or self.company.get('contact_person', 'Business Contact')
                                            el.fill(fullname)
                                            el.dispatch_event('input')
                                            el.dispatch_event('change')
                                            filled_count += 1
                                        elif any(kw in field_hint for kw in ['message', 'comment', 'inquiry', 'enquiry', 'details', 'body']):
                                            el.fill(message)
                                            el.dispatch_event('input')
                                            el.dispatch_event('change')
                                            filled_count += 1
                                        # Do NOT fill unknown fields with "General enquiry" — avoids overwriting name fields when label was wrong
                            except Exception:
                                pass
                        self.submit_form(form)
                        self.page.wait_for_timeout(2000)
                except Exception:
                    pass
            
            # SUCCESS CRITERIA: Require at least 2 fields filled so we don't mark newsletter/search as contact success
            if filled_count >= 2:
                self.log('success', 'Form Processed', f'Successfully filled {filled_count} fields and captured screenshot')
                res = {
                    'success': True,
                    'method': 'form_filled',
                    'fields_filled': filled_count,
                    'screenshot_url': screenshot_url,
                    'screenshot_bytes': screenshot_bytes,
                    'filled_field_patterns': filled_field_patterns,
                }
                return res
            elif filled_count == 1:
                self.log('warning', 'Form Partial', 'Only one field filled — likely newsletter/search, not contact form')
                res = {
                    'success': False,
                    'error': 'Only one field filled; not treated as contact form',
                    'fields_filled': 1,
                    'screenshot_url': screenshot_url,
                    'screenshot_bytes': screenshot_bytes,
                    'filled_field_patterns': filled_field_patterns,
                }
                return res
            else:
                self.log('warning', 'Form Empty', 'No fields were filled')
                res = {
                    'success': False,
                    'error': 'No fields were filled',
                    'fields_filled': 0,
                    'screenshot_url': screenshot_url,
                    'screenshot_bytes': screenshot_bytes,
                    'filled_field_patterns': filled_field_patterns,
                }
                return res
                
        except Exception as e:
            self.log('error', 'Form Fill Error', str(e))
            path, screenshot_bytes = self.take_screenshot('form_error')
            return {
                'success': False,
                'error': f'Form processing error: {str(e)}',
                'screenshot_url': path,
                'screenshot_bytes': screenshot_bytes,
                'filled_field_patterns': [],
            }

    def submit_form(self, form) -> bool:
        """Submit the form by clicking submit button or calling form.submit(). Returns True if submit was attempted."""
        try:
            # Prefer clicking submit button so JS submit handlers run
            submit_selectors = [
                'input[type="submit"]',
                'button[type="submit"]',
                'button[type="button"]',  # some forms use type=button with onclick submit
                '[type="submit"]',
                'button',
                'input[type="image"]',
            ]
            for sel in submit_selectors:
                try:
                    btn = form.query_selector(sel)
                    if btn and btn.is_visible():
                        self.log('info', 'Submitting', 'Clicking submit button')
                        btn.click()
                        return True
                except Exception:
                    continue
            # Fallback: native form submit (may not trigger React/JS handlers)
            form.evaluate('el => el.submit()')
            self.log('info', 'Submitting', 'Form submitted via submit()')
            return True
        except Exception as e:
            self.log('warning', 'Submit Failed', str(e))
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
                    if element and element.is_visible():
                        self.log('info', 'Captcha', f'Detected visible captcha: {selector}')
                        return True
                except: continue
            
            # Also check page-level (outside form) but only if it's very likely blocking
            for selector in ['.g-recaptcha', '.h-captcha', 'iframe[src*="recaptcha"]']:
                try:
                    element = self.page.query_selector(selector)
                    if element and element.is_visible():
                        self.log('info', 'Captcha', f'Detected page-level captcha: {selector}')
                        return True
                except: continue
            
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

    def take_screenshot(self, prefix: str):
        """Take screenshot; return (path_or_url, bytes). Uses in-memory only so no filesystem on Railway."""
        try:
            self.handle_cookie_modal()
            self.page.wait_for_timeout(300)
            # No path = Playwright returns bytes directly; no temp file, works on read-only Railway
            raw = self.page.screenshot(full_page=True)
            screenshot_bytes = raw if isinstance(raw, bytes) and len(raw) > 0 else None
            if not screenshot_bytes:
                self.log('warning', 'Screenshot', 'page.screenshot() returned no bytes (type=%s)' % type(raw).__name__)
                return (None, None)
            return (f"/temp/{prefix}_{self.company_id}_{int(time.time())}.png", screenshot_bytes)
        except Exception as e:
            self.log('error', 'Screenshot Failed', str(e))
            return (None, None)
