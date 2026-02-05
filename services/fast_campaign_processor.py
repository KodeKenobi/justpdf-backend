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
                 campaign_id: int = None, company_id: int = None, logger=None, subject: str = None, sender_data: Dict = None,
                 deadline_sec: float = None):
        self.page = page
        self.company = company_data
        self.campaign_id = campaign_id
        self.company_id = company_id
        self.logger = logger
        self.deadline = (time.time() + deadline_sec) if deadline_sec else None
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

    def _is_timed_out(self) -> bool:
        """True if per-company deadline exceeded (avoids one stuck site blocking the run)."""
        if self.deadline is None:
            return False
        return time.time() > self.deadline

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
            if self._is_timed_out():
                result['success'] = False
                result['error'] = 'Processing timed out'
                result['method'] = 'timeout'
                return result
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
                self.page.goto(website_url, wait_until='domcontentloaded', timeout=20000)
                self.handle_cookie_modal()
                self.page.wait_for_timeout(600)
            except Exception as e:
                self.log('warning', 'Initial Navigation', f'Failed or timed out: {e}')
                # Continue anyway, Strategy 2 might still work if we have a partial load

            # STRATEGY 0: Footer first — contact links are almost always in footer; go to contact page before trying homepage forms
            self.log('info', 'Strategy 0', 'Checking footer first for contact link…')
            seen = set()
            unique = []
            contact_keywords = _brain_get_keywords('contact_keyword', [
                'contact', 'contact us', 'get in touch', 'get-in-touch', 'enquiry', 'enquiries', 'support', 'about-us'
            ])
            footer_candidates = []
            try:
                # Scroll to bottom so lazy-loaded footers appear, then find footer
                try:
                    self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    self.page.wait_for_timeout(400)
                except Exception:
                    pass
                footer_containers = self.page.query_selector_all(
                    'footer, [role="contentinfo"], .footer, #footer, .site-footer, .page-footer, [class*="footer"], [class*="Footer"]'
                )
                for footer_el in (footer_containers or []):
                    try:
                        footer_links = footer_el.query_selector_all('a[href]')
                        for link in (footer_links or []):
                            try:
                                href = link.get_attribute('href')
                                text = (link.inner_text() or '').strip().lower()
                                if not href or href.startswith('mailto:') or href.startswith('tel:'):
                                    continue
                                if any(kw in (href or '').lower() or kw in text for kw in contact_keywords):
                                    footer_candidates.append((href, text))
                            except Exception:
                                pass
                    except Exception:
                        pass
                seen = set()
                unique = []
                for href, text in footer_candidates:
                    h = (href or '').strip().lower()
                    if h and h not in seen:
                        seen.add(h)
                        unique.append((href, text))
                def _contact_priority(item):
                    href, text = item
                    h, t = (href or '').lower(), (text or '').lower()
                    if 'contact' in h or 'contact' in t or 'get in touch' in t or 'get-in-touch' in h:
                        return 0
                    if 'enquiry' in h or 'enquiry' in t or 'inquiry' in h or 'inquiry' in t:
                        return 1
                    if 'support' in h or 'support' in t:
                        return 2
                    if 'about-us' in h or 'about-us' in t or 'about us' in t:
                        return 3
                    return 2
                unique.sort(key=_contact_priority)
                if unique:
                    self.log('info', 'Strategy 0', f'Found {len(unique)} contact link(s) in footer; trying contact page first')
                    href, text = unique[0]
                    matched_kw = next((kw for kw in contact_keywords if kw in (href or '').lower() or kw in (text or '')), None)
                    self._contact_keyword_used = matched_kw
                    full_href = self.make_absolute_url(href)
                    if not (href or '').strip().startswith('#'):
                        try:
                            self.page.goto(full_href, wait_until='domcontentloaded', timeout=20000)
                            self.handle_cookie_modal()
                            self.page.wait_for_timeout(400)
                            self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                            self.page.wait_for_timeout(400)
                            self.page.evaluate("window.scrollTo(0, 0)")
                            self.page.wait_for_timeout(300)
                            try:
                                self.page.wait_for_selector('form, input[type="email"], textarea, [id*="email"]', timeout=6000)
                                self.page.wait_for_timeout(500)
                            except Exception:
                                pass
                            contact_page_forms = self.page.query_selector_all('form')
                            if contact_page_forms:
                                for form_idx in range(len(contact_page_forms)):
                                    if self._count_contact_like_fields(contact_page_forms[form_idx]) < 2:
                                        continue
                                    if self._is_newsletter_or_signup_form(contact_page_forms[form_idx]):
                                        continue
                                    try:
                                        self.page.locator('form').nth(form_idx).scroll_into_view_if_needed(timeout=2000)
                                        self.page.wait_for_timeout(300)
                                    except Exception:
                                        pass
                                    forms_refresh = self.page.query_selector_all('form')
                                    if form_idx < len(forms_refresh):
                                        form_result = self.fill_and_submit_form(forms_refresh[form_idx], 'contact_page')
                                        if form_result['success']:
                                            self.log('success', 'Form Detection', 'Filled contact form from footer link')
                                            result.update(form_result)
                                            result['method'] = 'form_submitted_contact_page'
                                            self.found_form = True
                                            self._record_brain_mandatory(self._contact_keyword_used, form_result.get('filled_field_patterns', []), True, result.get('method', 'form_submitted_contact_page'))
                                            return result
                                        self._record_brain_mandatory(self._contact_keyword_used, form_result.get('filled_field_patterns', []), False, form_result.get('method', 'form_fill_failed'))
                                self.log('info', 'Strategy 0', 'Contact page form(s) did not succeed; falling back to homepage')
                            else:
                                self.log('info', 'Strategy 0', 'No form on contact page; falling back to homepage')
                            self.page.goto(website_url, wait_until='domcontentloaded', timeout=15000)
                            self.handle_cookie_modal()
                            self.page.wait_for_timeout(400)
                        except Exception as e:
                            self.log('warning', 'Strategy 0', f'Footer contact link failed: {e}; continuing to homepage forms')
                            try:
                                self.page.goto(website_url, wait_until='domcontentloaded', timeout=15000)
                                self.handle_cookie_modal()
                                self.page.wait_for_timeout(400)
                            except Exception:
                                pass
                    else:
                        # Same-page anchor: scroll to section
                        anchor_id = (href or '').strip().lstrip('#').split()[0] or 'contact'
                        try:
                            self.page.locator(f'#{anchor_id}, [id="{anchor_id}"]').first.scroll_into_view_if_needed(timeout=3000)
                            self.page.wait_for_timeout(500)
                        except Exception:
                            self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                            self.page.wait_for_timeout(500)
                        contact_page_forms = self.page.query_selector_all('form')
                        if contact_page_forms:
                            for form_idx in range(len(contact_page_forms)):
                                if self._count_contact_like_fields(contact_page_forms[form_idx]) < 2:
                                    continue
                                if self._is_newsletter_or_signup_form(contact_page_forms[form_idx]):
                                    continue
                                forms_refresh = self.page.query_selector_all('form')
                                if form_idx < len(forms_refresh):
                                    form_result = self.fill_and_submit_form(forms_refresh[form_idx], 'contact_page')
                                    if form_result['success']:
                                        result.update(form_result)
                                        result['method'] = 'form_submitted_contact_page'
                                        self.found_form = True
                                        self._record_brain_mandatory(self._contact_keyword_used, form_result.get('filled_field_patterns', []), True, result.get('method', 'form_submitted_contact_page'))
                                        return result
            except Exception as e:
                self.log('warning', 'Strategy 0', str(e))
            if not unique:
                self.log('info', 'Strategy 0', 'No contact link in footer; will try homepage forms')

            if self._is_timed_out():
                result['success'] = False
                result['error'] = 'Processing timed out'
                result['method'] = 'timeout'
                return result
            # STRATEGY 1: Check homepage forms (skip newsletter/signup — e.g. "Stay in the loop", "Newsletter Sign up")
            self.log('info', 'Strategy 1', 'Checking homepage for a contact form (skipping newsletter/signup)…')
            all_forms = self.page.query_selector_all('form')
            if all_forms:
                for idx in range(len(all_forms)):
                    try:
                        form_el = all_forms[idx]
                        if self._is_newsletter_or_signup_form(form_el):
                            self.log('info', 'Strategy 1', f'Skipping form {idx + 1} (newsletter/signup)')
                            continue
                        contact_like_count = self._count_contact_like_fields(form_el)
                        if contact_like_count < 2:
                            continue
                        self.log('info', 'Strategy 1', f'Trying form {idx + 1}…')
                        try:
                            self.page.locator('form').nth(idx).scroll_into_view_if_needed(timeout=3000)
                            self.page.wait_for_timeout(400)
                        except Exception:
                            pass
                        # Re-get form after scroll (handles may go stale)
                        forms_after = self.page.query_selector_all('form')
                        if idx < len(forms_after):
                            form_result = self.fill_and_submit_form(forms_after[idx], 'homepage')
                            if form_result['success']:
                                self.log('success', 'Form Detection', f'Filled form {idx + 1} on page ({contact_like_count} fields)')
                                result.update(form_result)
                                result['method'] = 'form_submitted_homepage'
                                self.found_form = True
                                self._record_brain_mandatory(getattr(self, '_contact_keyword_used', None), form_result.get('filled_field_patterns', []), True, result.get('method', 'form_submitted_homepage'))
                                return result
                    except Exception as e:
                        self.log('warning', 'Strategy 1', f'Form {idx + 1} failed: {e}')
                        continue
                self.log('info', 'Strategy 1', f'No form with 2+ fillable fields succeeded among {len(all_forms)} form(s)')

            # Quick scroll and retry Strategy 1 once (below-fold form)
            try:
                self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                self.page.wait_for_timeout(400)
                self.page.evaluate("window.scrollTo(0, 0)")
                self.page.wait_for_timeout(400)
            except Exception:
                pass
            all_forms = self.page.query_selector_all('form')
            if all_forms:
                for idx in range(len(all_forms)):
                    try:
                        form_el = all_forms[idx]
                        if self._is_newsletter_or_signup_form(form_el):
                            continue
                        if self._count_contact_like_fields(form_el) < 2:
                            continue
                        try:
                            self.page.locator('form').nth(idx).scroll_into_view_if_needed(timeout=3000)
                            self.page.wait_for_timeout(300)
                        except Exception:
                            pass
                        forms_after = self.page.query_selector_all('form')
                        if idx < len(forms_after):
                            form_result = self.fill_and_submit_form(forms_after[idx], 'homepage')
                            if form_result['success']:
                                result.update(form_result)
                                result['method'] = 'form_submitted_homepage'
                                self.found_form = True
                                self._record_brain_mandatory(getattr(self, '_contact_keyword_used', None), form_result.get('filled_field_patterns', []), True, result.get('method', 'form_submitted_homepage'))
                                return result
                    except Exception:
                        continue

            # STRATEGY 1b: No <form> tag? Scan page for input/textarea (contact form may be div-based)
            self.log('info', 'Strategy 1b', 'Checking for inputs/textareas on page (no form tag)...')
            heuristics_result = self.search_by_heuristics()
            if heuristics_result['success']:
                result.update(heuristics_result)
                result['method'] = 'form_submitted_homepage_heuristics'
                self.found_form = True
                self._record_brain_mandatory(getattr(self, '_contact_keyword_used', None), heuristics_result.get('filled_field_patterns', []), True, result.get('method', 'form_submitted_homepage_heuristics'))
                return result
            
            # STRATEGY 2: Find contact link and navigate (footer first — contact links are almost always in footer)
            self.log('info', 'Strategy 2', 'No form on homepage, searching for contact link (footer first)...')
            contact_keywords = _brain_get_keywords('contact_keyword', ['contact', 'get-in-touch', 'enquiry', 'support', 'about-us'])
            self.log('info', 'Discovery', 'Strategy 2: Searching for contact links')
            selector = ', '.join([f'a[href*="{kw}"]' for kw in contact_keywords]) + ', ' + \
                       ', '.join([f'a:has-text("{kw}")' for kw in contact_keywords])
            
            contact_link = None
            try:
                # Collect (href, text) from footer/selector while still on homepage so we don't hold stale handles after navigation
                candidates = []
                footer_containers = self.page.query_selector_all(
                    'footer, [role="contentinfo"], .footer, #footer, .site-footer, .page-footer, [class*="footer"], [class*="Footer"]'
                )
                for footer_el in (footer_containers or []):
                    try:
                        footer_links = footer_el.query_selector_all('a[href]')
                        for link in (footer_links or []):
                            try:
                                href = link.get_attribute('href')
                                text = (link.inner_text() or '').strip().lower()
                                if not href or href.startswith('mailto:') or href.startswith('tel:'):
                                    continue
                                if any(kw in (href or '').lower() or kw in text for kw in contact_keywords):
                                    candidates.append((href, text))
                            except Exception:
                                pass
                    except Exception:
                        pass
                if not candidates:
                    fallback_links = self.page.query_selector_all(selector)
                    for link in (fallback_links or []):
                        try:
                            href = link.get_attribute('href')
                            text = (link.inner_text() or '').strip().lower()
                            if href and not href.startswith('mailto:') and not href.startswith('tel:'):
                                candidates.append((href, text))
                        except Exception:
                            pass
                # Dedupe by normalized href (keep first)
                seen = set()
                unique = []
                for href, text in candidates:
                    h = (href or '').strip().lower()
                    if h and h not in seen:
                        seen.add(h)
                        unique.append((href, text))
                # Prioritize: "contact" / "get-in-touch" / "enquiry" first; "support" / "about-us" last (so we don't open "fire-rated fixings & support" instead of Contact)
                def contact_priority(item):
                    href, text = item
                    h, t = (href or '').lower(), (text or '').lower()
                    if 'contact' in h or 'contact' in t or 'get in touch' in t or 'get-in-touch' in h:
                        return 0
                    if 'enquiry' in h or 'enquiry' in t or 'inquiry' in h or 'inquiry' in t:
                        return 1
                    if 'support' in h or 'support' in t:
                        return 2
                    if 'about-us' in h or 'about-us' in t or 'about us' in t:
                        return 3
                    return 2
                unique.sort(key=contact_priority)
                self.log('info', 'Discovery', f'Found {len(unique)} potential contact links (contact/enquiry first, support last)')

                for i, (href, text) in enumerate(unique[:5]):
                    if not href:
                        continue
                    matched_kw = next((kw for kw in contact_keywords if kw in (href or '').lower() or kw in (text or '')), None)
                    self._contact_keyword_used = matched_kw
                    full_href = self.make_absolute_url(href)
                    self.log('info', 'Testing Link', f'Link {i+1}: {text or "(no text)"} ({href})')
                    try:
                        # Same-page anchor (#contact, #contact-us): scroll to it, don't goto
                        if (href or '').strip().startswith('#'):
                            anchor_id = (href or '').strip().lstrip('#').split()[0] or 'contact'
                            self.log('info', 'Contact Page', 'Loading contact section…')
                            try:
                                self.page.locator(f'#{anchor_id}, [id="{anchor_id}"]').first.scroll_into_view_if_needed(timeout=3000)
                                self.page.wait_for_timeout(500)
                            except Exception:
                                self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                                self.page.wait_for_timeout(500)
                            self.handle_cookie_modal()
                        else:
                            self.page.goto(full_href, wait_until='domcontentloaded', timeout=20000)
                            self.handle_cookie_modal()
                            self.page.wait_for_timeout(400)
                            self.log('info', 'Contact Page', 'Loading contact page…')
                            self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                            self.page.wait_for_timeout(500)
                            self.page.evaluate("window.scrollTo(0, 0)")
                            self.page.wait_for_timeout(400)
                            self.handle_cookie_modal()
                        try:
                            self.page.wait_for_selector('form, input[type="email"], textarea, [id*="email"], iframe', timeout=6000)
                            self.page.wait_for_timeout(800)
                        except Exception:
                            self.log('info', 'Contact Page', 'No form elements/iframes appeared within 15s, checking immediately')
                        contact_page_forms = self.page.query_selector_all('form')
                        if contact_page_forms:
                            self.log('success', 'Form Detection', f'Found {len(contact_page_forms)} form(s) on contact page')
                            for form_idx in range(len(contact_page_forms)):
                                if self._count_contact_like_fields(contact_page_forms[form_idx]) < 2:
                                    continue
                                if self._is_newsletter_or_signup_form(contact_page_forms[form_idx]):
                                    continue
                                try:
                                    self.page.locator('form').nth(form_idx).scroll_into_view_if_needed(timeout=2000)
                                    self.page.wait_for_timeout(300)
                                except Exception:
                                    pass
                                forms_refresh = self.page.query_selector_all('form')
                                if form_idx < len(forms_refresh):
                                    form_result = self.fill_and_submit_form(forms_refresh[form_idx], 'contact_page')
                                    if form_result['success']:
                                        result.update(form_result)
                                        result['method'] = 'form_submitted_contact_page'
                                        self.found_form = True
                                        self._record_brain_mandatory(self._contact_keyword_used, form_result.get('filled_field_patterns', []), True, result.get('method', 'form_submitted_contact_page'))
                                        return result
                                    self._record_brain_mandatory(self._contact_keyword_used, form_result.get('filled_field_patterns', []), False, form_result.get('method', 'form_fill_failed'))
                            # No main-doc form succeeded — form may be in iframe (e.g. HubSpot on 2020innovation). Check iframes before trying next link.
                            self.log('info', 'Contact Page Discovery', 'No main-page form succeeded; checking iframes (e.g. HubSpot)...')
                            self.page.wait_for_timeout(2000)
                            for idx, frame in enumerate(self.page.frames):
                                if frame == self.page.main_frame:
                                    continue
                                try:
                                    frame_forms = frame.query_selector_all('form')
                                    if frame_forms:
                                        self.log('success', 'Form in iframe', f'Found form in frame {idx} on contact page')
                                        form_result = self.fill_and_submit_form(frame_forms[0], f'contact_page_frame_{idx}', is_iframe=True, frame=frame)
                                        if form_result['success']:
                                            result.update(form_result)
                                            result['method'] = 'form_submitted_contact_page_iframe'
                                            self.found_form = True
                                            self._record_brain_mandatory(self._contact_keyword_used, form_result.get('filled_field_patterns', []), True, result.get('method', 'form_submitted_contact_page_iframe'))
                                            return result
                                    else:
                                        frame_inputs = frame.query_selector_all('input[type="email"], textarea')
                                        if frame_inputs:
                                            form_result = self.fill_and_submit_form(frame, f'contact_page_frame_{idx}_heuristic', is_iframe=True, is_heuristic=True, frame=frame)
                                            if form_result['success']:
                                                result.update(form_result)
                                                result['method'] = 'form_submitted_contact_page_iframe_heuristic'
                                                self.found_form = True
                                                self._record_brain_mandatory(self._contact_keyword_used, form_result.get('filled_field_patterns', []), True, result.get('method', 'form_submitted_contact_page_iframe_heuristic'))
                                                return result
                                except Exception as e:
                                    self.log('warning', 'Contact page frame', f'Frame {idx} check failed: {e}')
                                    continue
                            continue  # No form succeeded on this link, try next
                        else:
                            # No <form> in main document — form may be in iframe (e.g. HubSpot on 2020innovation). Check frames before email fallback.
                            self.log('info', 'Contact Page Discovery', 'No form in main page; checking iframes (e.g. HubSpot) before email fallback...')
                            self.page.wait_for_timeout(2000)
                            for idx, frame in enumerate(self.page.frames):
                                if frame == self.page.main_frame:
                                    continue
                                try:
                                    frame_forms = frame.query_selector_all('form')
                                    if frame_forms:
                                        self.log('success', 'Form in iframe', f'Found form in frame {idx} on contact page')
                                        form_result = self.fill_and_submit_form(frame_forms[0], f'contact_page_frame_{idx}', is_iframe=True, frame=frame)
                                        if form_result['success']:
                                            result.update(form_result)
                                            result['method'] = 'form_submitted_contact_page_iframe'
                                            self.found_form = True
                                            self._record_brain_mandatory(self._contact_keyword_used, form_result.get('filled_field_patterns', []), True, result.get('method', 'form_submitted_contact_page_iframe'))
                                            return result
                                    else:
                                        frame_inputs = frame.query_selector_all('input[type="email"], textarea')
                                        if frame_inputs:
                                            form_result = self.fill_and_submit_form(frame, f'contact_page_frame_{idx}_heuristic', is_iframe=True, is_heuristic=True, frame=frame)
                                            if form_result['success']:
                                                result.update(form_result)
                                                result['method'] = 'form_submitted_contact_page_iframe_heuristic'
                                                self.found_form = True
                                                self._record_brain_mandatory(self._contact_keyword_used, form_result.get('filled_field_patterns', []), True, result.get('method', 'form_submitted_contact_page_iframe_heuristic'))
                                                return result
                                except Exception as e:
                                    self.log('warning', 'Contact page frame', f'Frame {idx} check failed: {e}')
                                    continue
                            self.log('info', 'Contact Page Discovery', 'No direct form found, trying fallback extraction...')
                            contact_info = self.extract_contact_info()
                            if contact_info and contact_info.get('emails'):
                                self.log('success', 'Email Found', f"Found {len(contact_info['emails'])} email(s)")
                                email_found_when_no_form = self.sender_data.get('email_found_when_no_form', False)
                                if not email_found_when_no_form:
                                    self.log('info', 'Email option off', 'Skipping email send (user disabled "email found when no form")')
                                    path, screenshot_bytes = self.take_screenshot('contact_info_found')
                                    result.update({
                                        'success': True,
                                        'contact_info': contact_info,
                                        'method': 'contact_info_found',
                                        'screenshot_url': path,
                                        'screenshot_bytes': screenshot_bytes,
                                    })
                                    self._record_brain_mandatory(self._contact_keyword_used, [], True, 'contact_info_found')
                                    return result
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
            self.page.wait_for_timeout(500)
            
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
                email_found_when_no_form = self.sender_data.get('email_found_when_no_form', False)
                if not email_found_when_no_form:
                    self.log('info', 'Email option off', 'Skipping email send (user disabled "email found when no form")')
                    path, screenshot_bytes = self.take_screenshot('contact_info_found')
                    result.update({
                        'success': True,
                        'contact_info': contact_info,
                        'method': 'contact_info_found',
                        'screenshot_url': path,
                        'screenshot_bytes': screenshot_bytes,
                    })
                    self._record_brain_mandatory(getattr(self, '_contact_keyword_used', None), [], True, 'contact_info_found')
                    return result
                else:
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
            result['method'] = 'error'  # so we report failed, not no_contact_found
            try:
                _path, _bytes = self.take_screenshot('error_processing')
                result['screenshot_url'] = _path
                result['screenshot_bytes'] = _bytes
            except Exception:
                pass
            try:
                self._record_brain_mandatory(getattr(self, '_contact_keyword_used', None), [], False, 'error_processing')
            except Exception:
                pass
        return result

    def _is_newsletter_or_signup_form(self, form) -> bool:
        """Return True if form is clearly newsletter/signup or lacks a real contact message field. Contact forms must have message/textarea."""
        try:
            # Form inside footer is almost always newsletter/signup — never treat as contact form
            in_footer = form.evaluate('''el => {
                const footer = el.closest('footer, [role="contentinfo"], .footer, #footer, .site-footer, .page-footer, [class*="footer"], [class*="Footer"]');
                return !!footer;
            }''')
            if in_footer:
                return True
            # Form context: id, name, class, action, aria-label, or nearby text
            ctx = form.evaluate('''el => {
                const id = (el.id || '').toLowerCase();
                const name = (el.getAttribute('name') || '').toLowerCase();
                const cls = (el.className || '').toLowerCase();
                const action = (el.getAttribute('action') || '').toLowerCase();
                const aria = (el.getAttribute('aria-label') || '').toLowerCase();
                let prev = '';
                let p = el.previousElementSibling;
                for (let i = 0; i < 3 && p; i++) { prev += (p.textContent || '').toLowerCase(); p = p.previousElementSibling; }
                const inner = (el.textContent || '').toLowerCase().slice(0, 500);
                return id + ' ' + name + ' ' + cls + ' ' + action + ' ' + aria + ' ' + prev + ' ' + inner;
            }''') or ''
            newsletter_keywords = ['newsletter', 'sign up', 'signup', 'stay in the loop', 'subscribe', 'subscribe to our', 'join our list', 'get the latest', 'email signup', 'mailing list']
            if any(kw in ctx for kw in newsletter_keywords):
                return True
            # Contact forms must have a message/enquiry field (textarea or message-like input). No message field = newsletter/signup.
            has_message_field = form.evaluate('''el => {
                const textareas = el.querySelectorAll('textarea');
                if (textareas.length > 0) return true;
                const msgKeywords = ['message', 'enquiry', 'inquiry', 'comment', 'comments', 'details', 'your message', 'how can we help', 'describe', 'body'];
                const inputs = el.querySelectorAll('input[type="text"], input:not([type])');
                for (const i of inputs) {
                    const name = (i.getAttribute('name') || '').toLowerCase();
                    const id = (i.getAttribute('id') || '').toLowerCase();
                    const placeholder = (i.getAttribute('placeholder') || '').toLowerCase();
                    const aria = (i.getAttribute('aria-label') || '').toLowerCase();
                    const combined = name + ' ' + id + ' ' + placeholder + ' ' + aria;
                    if (msgKeywords.some(k => combined.includes(k))) return true;
                }
                return false;
            }''')
            if not has_message_field:
                return True  # No message/textarea = newsletter or signup, not contact
            return False
        except Exception:
            return False

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
            # Termly and similar consent prompts (aria-label "Cookie Consent Prompt")
            '[aria-label*="Cookie Consent"] button:has-text("Accept")',
            '[aria-label*="Cookie Consent"] button:has-text("Accept All")',
            'div[role="alertdialog"][aria-label*="Cookie"] button:has-text("Accept")',
            'div[role="alertdialog"][aria-label*="Cookie"] button:has-text("Close")',
            'div[role="alertdialog"] button:has-text("Accept")',
            'div[role="alertdialog"] button:has-text("Close")',
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
            
            # Extract emails (Page.text_content requires selector; use body)
            page_text = (self.page.locator('body').text_content() or '')
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

    def _extract_form_fields(self, form) -> List[Dict]:
        """Extract field list from the current form (same shape as extract-contact-form-fields.js). One website at a time: extract then fill."""
        out = []
        try:
            inputs = form.query_selector_all('input, textarea')
            for el in (inputs or []):
                try:
                    itype = (el.get_attribute('type') or 'text').lower()
                    if itype in ('hidden', 'submit', 'button', 'image'):
                        continue
                    name = el.get_attribute('name')
                    id_ = el.get_attribute('id')
                    placeholder = el.get_attribute('placeholder')
                    tag = el.evaluate('el => el.tagName.toLowerCase()') or 'input'
                    label = ''
                    try:
                        label = (el.evaluate('''el => {
                            const id = el.id;
                            if (id) { const l = document.querySelector('label[for="' + id + '"]'); if (l) return (l.textContent || '').trim(); }
                            const p = el.closest('label') || el.previousElementSibling;
                            if (p && (p.tagName === 'LABEL' || p.textContent)) return (p.textContent || '').trim();
                            return el.getAttribute('aria-label') || '';
                        }''') or '')
                    except Exception:
                        pass
                    out.append({'tag': tag, 'type': itype, 'name': name, 'id': id_, 'placeholder': placeholder, 'label': label})
                except Exception:
                    continue
            selects = form.query_selector_all('select')
            for el in (selects or []):
                try:
                    name = el.get_attribute('name')
                    id_ = el.get_attribute('id')
                    label = ''
                    try:
                        label = (el.evaluate('''el => {
                            const id = el.id;
                            if (id) { const l = document.querySelector('label[for="' + id + '"]'); if (l) return (l.textContent || '').trim(); }
                            const p = el.previousElementSibling; return p ? (p.textContent || '').trim() : (el.getAttribute('aria-label') || '');
                        }''') or '')
                    except Exception:
                        pass
                    options = []
                    for opt in (el.query_selector_all('option') or []):
                        try:
                            options.append({'value': opt.get_attribute('value'), 'text': (opt.inner_text() or '').strip()})
                        except Exception:
                            pass
                    out.append({'tag': 'select', 'type': 'select', 'name': name, 'id': id_, 'label': label, 'options': options})
                except Exception:
                    continue
        except Exception:
            pass
        return out

    def _fill_using_field_list(self, form, field_list: List[Dict]) -> Tuple[int, List[Dict]]:
        """Fill form using extracted field list (extract on this website, then fill). Returns (filled_count, filled_field_patterns)."""
        filled_count = 0
        filled_field_patterns = []
        if not field_list or not isinstance(field_list, list):
            return 0, []
        message = self.replace_variables(self.message_body)
        email_val = self.sender_data.get('sender_email') or self.company.get('contact_email', 'contact@business.com')
        fname_val = self.sender_data.get('sender_first_name') or self.company.get('contact_person', 'Business').split()[0]
        lname_val = self.sender_data.get('sender_last_name') or (self.company.get('contact_person', 'Contact').split()[-1] if len((self.company.get('contact_person') or 'Contact').split()) > 1 else 'Contact')
        fullname_val = self.sender_data.get('sender_name') or self.company.get('contact_person', 'Business Contact')
        company_val = self.sender_data.get('sender_company') or self.company.get('company_name', 'Your Company')
        phone_val = self.sender_data.get('sender_phone') or self.company.get('phone') or self.company.get('phone_number') or ''
        subject_val = self.subject
        country_val = self.sender_data.get('sender_country') or 'United Kingdom'

        def field_hint(f):
            name = (f.get('name') or '').lower()
            label = (f.get('label') or '').lower()
            placeholder = (f.get('placeholder') or '').lower()
            return f"{name} {label} {placeholder}"

        for field in field_list:
            if self._is_timed_out():
                return filled_count, filled_field_patterns
            tag = (field.get('tag') or 'input').lower()
            ftype = (field.get('type') or 'text').lower()
            name = field.get('name')
            id_ = field.get('id')
            if not name and not id_:
                continue
            hint = field_hint(field)
            try:
                name_safe = (name or '').replace('\\', '\\\\').replace('"', '\\"')
                id_safe = (id_ or '').replace('\\', '\\\\').replace('"', '\\"')
                if tag == 'select':
                    sel = f'select[name="{name_safe}"]' if name else f'select[id="{id_safe}"]'
                else:
                    sel = f'{tag}[name="{name_safe}"]' if name else f'{tag}[id="{id_safe}"]'
                el = form.locator(sel).first
                if not el.count():
                    continue
                if not el.is_visible():
                    continue
            except Exception:
                continue

            filled_this = False
            if ftype == 'email' or 'email' in hint or 'e-mail' in hint:
                try:
                    el.fill(email_val)
                    el.dispatch_event('input')
                    el.dispatch_event('change')
                    filled_count += 1
                    filled_field_patterns.append({'role': 'email', 'name': name or '', 'label': field.get('label') or '', 'value': email_val})
                    self.log('info', 'Field Filled (mapped)', f'Email -> {name or id_}')
                    filled_this = True
                except Exception:
                    pass
            if not filled_this and any(k in hint for k in ['first name', 'first-name', 'fname', 'firstname', 'first_name']):
                try:
                    el.fill(fname_val)
                    el.dispatch_event('input')
                    el.dispatch_event('change')
                    filled_count += 1
                    filled_field_patterns.append({'role': 'first_name', 'name': name or '', 'label': field.get('label') or '', 'value': fname_val})
                    self.log('info', 'Field Filled (mapped)', f'First name -> {name or id_}')
                    filled_this = True
                except Exception:
                    pass
            if not filled_this and any(k in hint for k in ['last name', 'last-name', 'lname', 'lastname', 'last_name']):
                try:
                    el.fill(lname_val)
                    el.dispatch_event('input')
                    el.dispatch_event('change')
                    filled_count += 1
                    filled_field_patterns.append({'role': 'last_name', 'name': name or '', 'label': field.get('label') or '', 'value': lname_val})
                    self.log('info', 'Field Filled (mapped)', f'Last name -> {name or id_}')
                    filled_this = True
                except Exception:
                    pass
            if not filled_this and any(k in hint for k in ['full name', 'your name', 'name']) and 'company' not in hint and 'first' not in hint and 'last' not in hint:
                try:
                    el.fill(fullname_val)
                    el.dispatch_event('input')
                    el.dispatch_event('change')
                    filled_count += 1
                    filled_field_patterns.append({'role': 'full_name', 'name': name or '', 'label': field.get('label') or '', 'value': fullname_val})
                    self.log('info', 'Field Filled (mapped)', f'Full name -> {name or id_}')
                    filled_this = True
                except Exception:
                    pass
            if not filled_this and any(k in hint for k in ['company', 'organization', 'business']) and 'email' not in hint:
                try:
                    el.fill(company_val)
                    el.dispatch_event('input')
                    el.dispatch_event('change')
                    filled_count += 1
                    filled_field_patterns.append({'role': 'company', 'name': name or '', 'label': field.get('label') or '', 'value': company_val})
                    self.log('info', 'Field Filled (mapped)', f'Company -> {name or id_}')
                    filled_this = True
                except Exception:
                    pass
            if not filled_this and (ftype == 'tel' or 'phone' in hint or 'tel' in hint) and phone_val:
                try:
                    el.fill(phone_val)
                    el.dispatch_event('input')
                    el.dispatch_event('change')
                    filled_count += 1
                    filled_field_patterns.append({'role': 'phone', 'name': name or '', 'label': field.get('label') or '', 'value': phone_val or ''})
                    self.log('info', 'Field Filled (mapped)', f'Phone -> {name or id_}')
                    filled_this = True
                except Exception:
                    pass
            if not filled_this and any(k in hint for k in ['subject', 'topic', 'reason']):
                try:
                    el.fill(subject_val)
                    el.dispatch_event('input')
                    el.dispatch_event('change')
                    filled_count += 1
                    filled_field_patterns.append({'role': 'subject', 'name': name or '', 'label': field.get('label') or '', 'value': subject_val})
                    self.log('info', 'Field Filled (mapped)', f'Subject -> {name or id_}')
                    filled_this = True
                except Exception:
                    pass
            if not filled_this and any(k in hint for k in ['country', 'nation', 'region']) and tag != 'select':
                try:
                    el.fill(country_val)
                    el.dispatch_event('input')
                    el.dispatch_event('change')
                    filled_count += 1
                    filled_field_patterns.append({'role': 'country', 'name': name or '', 'label': field.get('label') or '', 'value': country_val})
                    self.log('info', 'Field Filled (mapped)', f'Country -> {name or id_}')
                    filled_this = True
                except Exception:
                    pass
            if not filled_this and (tag == 'textarea' or any(k in hint for k in ['message', 'comment', 'inquiry', 'details', 'body'])):
                try:
                    el.fill(message)
                    el.dispatch_event('input')
                    el.dispatch_event('change')
                    filled_count += 1
                    filled_field_patterns.append({'role': 'message', 'name': name or '', 'label': field.get('label') or '', 'value': (message or '')[:200]})
                    self.log('info', 'Field Filled (mapped)', f'Message -> {name or id_}')
                    filled_this = True
                except Exception:
                    pass
            if not filled_this and tag == 'select' and any(k in hint for k in ['country', 'nation', 'region']):
                try:
                    opts = field.get('options') or []
                    for o in opts:
                        v = o.get('value') or o.get('text') or ''
                        if v and 'united' in v.lower():
                            ok = self._select_option_by_click(el, value=o.get('value'), label=o.get('text'))
                            if not ok:
                                el.select_option(value=v) if o.get('value') else el.select_option(label=v)
                                self._dispatch_select_events(el)
                            filled_count += 1
                            filled_field_patterns.append({'role': 'country', 'name': name or '', 'label': field.get('label') or '', 'value': v or ''})
                            self.log('info', 'Field Filled (mapped)', f'Country select -> {name or id_}')
                            break
                except Exception:
                    pass

        return filled_count, filled_field_patterns

    def _dispatch_select_events(self, select_el):
        """Dispatch change/input on select so Wix and other custom dropdowns update their visible UI."""
        try:
            select_el.dispatch_event('change')
            select_el.dispatch_event('input')
        except Exception:
            pass

    def _select_option_by_click(self, select_el, value=None, label=None, index=None):
        """Select an option by actually clicking the select then clicking the option (required for many sites; you cannot just set value)."""
        try:
            try:
                select_el.scroll_into_view_if_needed(timeout=3000)
            except Exception:
                pass
            self.page.wait_for_timeout(100)
            select_el.click(timeout=2000)
            self.page.wait_for_timeout(250)
            # Support both ElementHandle (query_selector_all) and Locator (evaluate)
            opts_info = []
            if hasattr(select_el, 'query_selector_all') and callable(select_el.query_selector_all):
                opts = select_el.query_selector_all('option')
                if not opts:
                    return False
                for i, o in enumerate(opts):
                    opts_info.append({
                        'value': (o.get_attribute('value') or '').strip(),
                        'text': (o.inner_text() or '').strip(),
                        'index': i
                    })
            else:
                opts_info = select_el.evaluate('''el => {
                    const opts = el.options;
                    return Array.from(opts).map((o, i) => ({ value: (o.value || '').trim(), text: (o.innerText || '').trim(), index: i }));
                }''') or []
            if not opts_info:
                return False
            target_idx = None
            if index is not None and 0 <= index < len(opts_info):
                target_idx = index
            elif label:
                label_lower = (label or '').strip().lower()
                for o in opts_info:
                    t = (o.get('text') or '').lower()
                    v = (o.get('value') or '').lower()
                    if label_lower in t or label_lower in v or t == label_lower:
                        target_idx = o.get('index', 0)
                        break
            elif value:
                val_str = (value or '').strip()
                for o in opts_info:
                    if (o.get('value') or '').strip() == val_str or (o.get('text') or '').strip() == val_str:
                        target_idx = o.get('index', 0)
                        break
            if target_idx is None and len(opts_info) > 0:
                target_idx = 1 if len(opts_info) > 1 else 0  # skip placeholder if possible
            if target_idx is not None:
                if hasattr(select_el, 'query_selector_all') and callable(select_el.query_selector_all):
                    opts = select_el.query_selector_all('option')
                    if target_idx < len(opts):
                        opts[target_idx].click()
                else:
                    select_el.locator('option').nth(target_idx).click()
                self.page.wait_for_timeout(100)
                self._dispatch_select_events(select_el)
                return True
        except Exception:
            pass
        return False

    def fill_and_submit_form(self, form, location: str, is_iframe: bool = False, is_heuristic: bool = False, frame=None) -> Dict:
        """Fill and submit form with smart field detection. Uses pre-extracted field_mappings when present (intelligent fill)."""
        try:
            if self._is_timed_out():
                return {'success': False, 'error': 'Processing timed out', 'method': 'timeout'}
            # Dismiss cookie/overlay so it doesn't block field clicks (e.g. Termly on contact page)
            self.handle_cookie_modal()
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
            
            # Per company: extract form fields on this page, then fill (one website at a time: extract → fill)
            extracted = self._extract_form_fields(form)
            if extracted:
                self.log('info', 'Form Filling', f'Extracted {len(extracted)} fields from this form; filling by mapping')
                filled_count, filled_field_patterns = self._fill_using_field_list(form, extracted)
                if self._is_timed_out():
                    return {'success': False, 'error': 'Processing timed out', 'method': 'timeout'}
                if filled_count >= 2:
                    if self.submit_form(form):
                        self.page.wait_for_timeout(1000)
                    path, screenshot_bytes = self.take_screenshot('form_filled')
                    self.log('success', 'Form Processed', f'Filled {filled_count} fields (extract-then-fill) and submitted')
                    return {
                        'success': True,
                        'method': 'form_filled',
                        'fields_filled': filled_count,
                        'screenshot_url': path,
                        'screenshot_bytes': screenshot_bytes,
                        'filled_field_patterns': filled_field_patterns,
                        'form_fields_detected': extracted,
                    }
                elif filled_count == 1:
                    self.log('warning', 'Form Partial', 'Only one field filled from extract; falling back to discovery')

            # Fallback: fill by iterating inputs (when extract-then-fill did not get enough)
            filled_count = 0
            inputs = form.query_selector_all('input, textarea')
            selects = form.query_selector_all('select')
            email_filled = False
            message_filled = False
            filled_field_patterns = []  # For mandatory brain recording: role, name, label per filled field
            
            # Prepare message
            message = self.replace_variables(self.message_body)
            
            for input_element in inputs:
                if self._is_timed_out():
                    break
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
                        filled_field_patterns.append({'role': 'email', 'name': input_element.get_attribute('name') or '', 'label': label_text, 'value': email})
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
                        filled_field_patterns.append({'role': 'first_name', 'name': input_element.get_attribute('name') or '', 'label': label_text, 'value': fname})
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
                        filled_field_patterns.append({'role': 'last_name', 'name': input_element.get_attribute('name') or '', 'label': label_text, 'value': lname})
                        self.log('info', 'Field Filled', f'Last Name field filled: {lname}')
                        continue

                    if any(kw in field_text for kw in ['full name', 'your name', 'name', 'full-name', 'fullname', 'your-name', 'full_name']) and 'company' not in field_text and 'first' not in field_text and 'last' not in field_text:
                        fullname = self.sender_data.get('sender_name') or self.company.get('contact_person', 'Business Contact')
                        input_element.click()
                        input_element.fill(fullname)
                        input_element.dispatch_event('input')
                        input_element.dispatch_event('change')
                        filled_count += 1
                        filled_field_patterns.append({'role': 'full_name', 'name': input_element.get_attribute('name') or '', 'label': label_text, 'value': fullname})
                        self.log('info', 'Field Filled', f'Name field filled: {fullname}')
                        continue
                    
                    # 3. Fill Company field
                    if any(kw in field_text for kw in ['company', 'organization', 'organisation', 'business-name', 'firm', 'business_name', 'org_name']) and 'email' not in field_text:
                        company_val = self.sender_data.get('sender_company') or self.company.get('company_name', 'Your Company')
                        input_element.click()
                        input_element.fill(company_val)
                        input_element.dispatch_event('input')
                        input_element.dispatch_event('change')
                        filled_count += 1
                        filled_field_patterns.append({'role': 'company', 'name': input_element.get_attribute('name') or '', 'label': label_text, 'value': company_val})
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
                            filled_field_patterns.append({'role': 'phone', 'name': input_element.get_attribute('name') or '', 'label': label_text, 'value': phone})
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
                        filled_field_patterns.append({'role': 'subject', 'name': input_element.get_attribute('name') or '', 'label': label_text, 'value': subject_val})
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
                        filled_field_patterns.append({'role': 'country', 'name': input_element.get_attribute('name') or '', 'label': label_text, 'value': country_val})
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
                            filled_field_patterns.append({'role': 'message', 'name': input_element.get_attribute('name') or '', 'label': label_text, 'value': (message or '')[:200]})
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
                                ok = self._select_option_by_click(select, value=target_val, label=target_label)
                                if not ok:
                                    select.select_option(value=target_val)
                                    self._dispatch_select_events(select)
                            except Exception:
                                try:
                                    select.select_option(label=target_label or target_val)
                                    self._dispatch_select_events(select)
                                except Exception:
                                    select.select_option(index=1 if len(options) > 1 else 0)
                                    self._dispatch_select_events(select)
                            filled_count += 1
                            filled_field_patterns.append({'role': 'country', 'name': name or '', 'label': select_label, 'value': target_label or target_val or ''})
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
                        placeholder_exact = ('select', 'choose', '--', 'please select', 'select one', 'select...')
                        placeholder_phrases = ('choose a branch', 'choose branch', 'choose a ', 'select a ', 'select one', 'pick one', 'choose one', '-- select --', '-- choose --')
                        is_placeholder = (not first_val or first_val == '' or
                                          first_text in placeholder_exact or
                                          any(p in first_text for p in placeholder_phrases))
                        idx = 1 if (is_placeholder and len(options) > 1) else 0
                        opt = options[idx]
                        val = opt.get_attribute('value')
                        label = (opt.inner_text() or '').strip()
                        if target_opt_val:
                            val = target_opt_val
                            label = target_opt_val
                        if val is not None or label:
                            try:
                                ok = self._select_option_by_click(select, value=val, label=label, index=idx)
                                if not ok:
                                    select.select_option(value=val or label)
                                    self._dispatch_select_events(select)
                            except Exception:
                                try:
                                    select.select_option(label=label or val)
                                    self._dispatch_select_events(select)
                                except Exception:
                                    try:
                                        select.select_option(index=idx)
                                        self._dispatch_select_events(select)
                                    except Exception:
                                        pass
                        else:
                            try:
                                ok = self._select_option_by_click(select, index=idx)
                                if not ok:
                                    select.select_option(index=idx)
                                    self._dispatch_select_events(select)
                            except Exception:
                                pass
                        filled_count += 1
                        filled_field_patterns.append({'role': 'branch', 'name': name or '', 'label': select_label, 'value': label or val or str(idx)})
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
                    
                    # Only check when label clearly indicates opt-in / marketing / consent; do not blindly check (e.g. terms acceptance)
                    if any(kw in f"{name} {parent_text} {aria_label}" for kw in ['enquiry', 'sales', 'support', 'agree', 'consent', 'optin', 'marketing', 'newsletter']):
                        if not any(kw in f"{name} {parent_text} {aria_label}" for kw in ['terms', 'conditions', 'terms and conditions']):
                            try:
                                cb.check()
                                filled_count += 1
                                self.log('info', 'Checkbox Checked', f'Checkbox filled ({name})')
                            except Exception:
                                pass

            # Fill remaining required selects only (first real option). Include aria-required so "Branch" etc. are filled when only asterisk/aria marks them required.
            try:
                required_selects = form.query_selector_all('select[required], select[aria-required="true"]')
                for el in required_selects or []:
                    opts = el.query_selector_all('option')
                    if opts and len(opts) > 1:
                        first_text = (opts[0].inner_text() or '').strip().lower()
                        placeholder_ok = any(p in first_text for p in ('select', 'choose', '--', 'please select', 'choose a branch', 'choose branch', 'select one', 'pick one'))
                        # If first option is placeholder, pick index 1; else if first is real, pick 0
                        pick_idx = 1 if placeholder_ok else 0
                        try:
                            el.select_option(index=pick_idx)
                            self._dispatch_select_events(el)
                            filled_count += 1
                            self.log('info', 'Required Field', f'Select required: chose option index {pick_idx}')
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

            # Pre-submit pass: fill only fields we can match; select valid options for select/radio; do not type into unknown fields
            try:
                # Required radio groups: ensure one option selected (pick by preference or first)
                for el in (form.query_selector_all('input[type=radio]') or []):
                    try:
                        name = el.get_attribute('name')
                        if not name:
                            continue
                        group = form.query_selector_all(f'input[type=radio][name="{name}"]')
                        if not group or len(group) < 2:
                            continue
                        any_checked = any(e.evaluate('el => el.checked') for e in group)
                        if any_checked:
                            continue
                        preferred = ['email', 'phone', 'general', 'enquiry', 'inquiry', 'business', 'sales', 'support', 'other']
                        chosen = None
                        for opt in group:
                            val = (opt.get_attribute('value') or '').lower()
                            parent = (opt.evaluate("el => el.parentElement?.innerText || ''") or '').lower()
                            if any(p in val or p in parent for p in preferred):
                                chosen = opt
                                break
                        # Only select when we matched a preferred option; do not guess "first"
                        if chosen:
                            chosen.click()
                            filled_count += 1
                            self.log('info', 'Required Field', f'Pre-submit: selected radio "{name}"')
                    except Exception:
                        pass
                # Required checkboxes: only check when label clearly indicates opt-in/marketing; do not check terms/conditions
                for el in (form.query_selector_all('input[type=checkbox][required]') or []):
                    try:
                        if el.evaluate('el => el.checked'):
                            continue
                        name = (el.get_attribute('name') or '').lower()
                        aria = (el.get_attribute('aria-label') or '').lower()
                        parent_text = (el.evaluate("el => el.parentElement?.innerText || ''") or '').lower()
                        hint = f"{name} {aria} {parent_text}"
                        if any(kw in hint for kw in ['agree', 'consent', 'optin', 'marketing', 'newsletter']) and not any(kw in hint for kw in ['terms', 'conditions', 'terms and conditions']):
                            el.check()
                            filled_count += 1
                            self.log('info', 'Required Field', 'Pre-submit: checked required opt-in checkbox')
                    except Exception:
                        pass
                for sel in ['input[required]', 'textarea[required]', 'select[required]', 'select[aria-required="true"]']:
                    for el in (form.query_selector_all(sel) or []):
                        try:
                            tag = el.evaluate('el => el.tagName.toLowerCase()')
                            current = (el.evaluate('el => el.value') or '') if tag != 'select' else ''
                            if tag == 'select':
                                opts = el.query_selector_all('option')
                                if not opts or len(opts) < 1:
                                    continue
                                selected_val = el.evaluate('el => (el.options[el.selectedIndex] && el.options[el.selectedIndex].value) || ""')
                                if selected_val and str(selected_val).strip():
                                    continue
                            elif current and str(current).strip():
                                continue
                            name = (el.get_attribute('name') or '').lower()
                            elem_id = (el.get_attribute('id') or '').lower()
                            placeholder = (el.get_attribute('placeholder') or '').lower()
                            aria = (el.get_attribute('aria-label') or '').lower()
                            label_text = ''
                            try:
                                label_text = (el.evaluate('''el => {
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
                                    return (el.getAttribute('aria-label') || '').trim().toLowerCase();
                                }''') or '')
                            except Exception:
                                pass
                            field_hint = f"{name} {elem_id} {placeholder} {aria} {label_text}"
                            if tag == 'select':
                                opts = el.query_selector_all('option')
                                if opts and len(opts) >= 1:
                                    first_opt_text = (opts[0].inner_text() or '').strip().lower()
                                    is_ph = any(p in first_opt_text for p in ('select', 'choose', '--', 'please select', 'choose a branch', 'choose branch', 'select one', 'pick one'))
                                    pick_idx = 1 if (is_ph and len(opts) > 1) else 0
                                    el.select_option(index=pick_idx)
                                    self._dispatch_select_events(el)
                                    filled_count += 1
                                    self.log('info', 'Required Field', f'Pre-submit: filled required select (index {pick_idx})')
                            elif tag == 'textarea':
                                if any(kw in field_hint for kw in ['message', 'comment', 'inquiry', 'enquiry', 'body', 'details']):
                                    el.fill(message)
                                    el.dispatch_event('input')
                                    el.dispatch_event('change')
                                    filled_count += 1
                                    self.log('info', 'Required Field', 'Pre-submit: filled required message textarea')
                                else:
                                    el.fill('N/A')
                                    el.dispatch_event('input')
                                    el.dispatch_event('change')
                                    filled_count += 1
                                    self.log('info', 'Required Field', 'Pre-submit: filled required textarea with N/A')
                            else:
                                input_type = (el.get_attribute('type') or 'text').lower()
                                filled_this = False
                                if input_type == 'email' or 'email' in field_hint:
                                    el.fill(self.sender_data.get('sender_email') or 'contact@example.com')
                                    filled_this = True
                                elif any(kw in field_hint for kw in ['first name', 'first-name', 'fname', 'firstname', 'first_name']):
                                    el.fill(self.sender_data.get('sender_first_name') or self.company.get('contact_person', 'Business').split()[0])
                                    filled_this = True
                                elif any(kw in field_hint for kw in ['last name', 'last-name', 'lname', 'lastname', 'surname', 'last_name']):
                                    lname = self.sender_data.get('sender_last_name') or (self.company.get('contact_person', 'Contact').split()[-1] if len(self.company.get('contact_person', 'Contact').split()) > 1 else 'Contact')
                                    el.fill(lname)
                                    filled_this = True
                                elif any(kw in field_hint for kw in ['full name', 'your name', 'name', 'full-name', 'fullname']) and 'company' not in field_hint and 'first' not in field_hint and 'last' not in field_hint:
                                    el.fill(self.sender_data.get('sender_name') or self.company.get('contact_person', 'Business Contact'))
                                    filled_this = True
                                elif any(kw in field_hint for kw in ['company', 'organization', 'organisation', 'business-name', 'firm']) and 'email' not in field_hint:
                                    el.fill(self.sender_data.get('sender_company') or self.company.get('company_name', 'Your Company'))
                                    filled_this = True
                                elif any(kw in field_hint for kw in ['phone', 'tel', 'mobile', 'cell', 'telephone']) or input_type == 'tel':
                                    phone = self.sender_data.get('sender_phone') or self.company.get('phone') or self.company.get('phone_number')
                                    if phone:
                                        el.fill(phone)
                                        filled_this = True
                                elif any(kw in field_hint for kw in ['subject', 'topic', 'reason', 'inquiry_type']):
                                    el.fill(self.subject)
                                    filled_this = True
                                elif any(kw in field_hint for kw in ['country', 'nation', 'region', 'location']):
                                    el.fill(self.sender_data.get('sender_country') or 'United Kingdom')
                                    filled_this = True
                                else:
                                    # Unknown required text/textarea: use N/A so validation can pass
                                    if input_type != 'email':
                                        el.fill('N/A')
                                        filled_this = True
                                if filled_this:
                                    el.dispatch_event('input')
                                    el.dispatch_event('change')
                                    filled_count += 1
                                    self.log('info', 'Required Field', f'Pre-submit: filled required field ({field_hint[:50]})')
                        except Exception:
                            pass
            except Exception:
                pass

            # Take screenshot of the filled form (before submit)
            screenshot_url, screenshot_bytes = self.take_screenshot(f'filled_{location}')

            # Submit the form after screenshot
            if filled_count > 0:
                self.submit_form(form)
                self.page.wait_for_timeout(1000)
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
                                    if opts and len(opts) >= 1:
                                        first_opt_text = (opts[0].inner_text() or '').strip().lower()
                                        is_ph = any(p in first_opt_text for p in ('select', 'choose', '--', 'please select', 'choose a branch', 'choose branch', 'select one', 'pick one'))
                                        pick_idx = 1 if (is_ph and len(opts) > 1) else 0
                                        el.select_option(index=pick_idx)
                                        self._dispatch_select_events(el)
                                        filled_count += 1
                                elif tag == 'textarea':
                                    current = el.evaluate('el => el.value') or ''
                                    if not (current and str(current).strip()):
                                        if any(kw in field_hint for kw in ['message', 'comment', 'inquiry', 'enquiry', 'body', 'details']):
                                            el.fill(message)
                                        else:
                                            el.fill('N/A')
                                        el.dispatch_event('input')
                                        el.dispatch_event('change')
                                        filled_count += 1
                                elif el.get_attribute('type') in ('text', 'email', 'tel', None):
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
                                        elif any(kw in field_hint for kw in ['company', 'organization', 'organisation', 'business-name', 'firm']) and 'email' not in field_hint:
                                            el.fill(self.sender_data.get('sender_company') or self.company.get('company_name', 'Your Company'))
                                            el.dispatch_event('input')
                                            el.dispatch_event('change')
                                            filled_count += 1
                                        elif any(kw in field_hint for kw in ['phone', 'tel', 'mobile', 'cell', 'telephone']) or el.get_attribute('type') == 'tel':
                                            phone = self.sender_data.get('sender_phone') or self.company.get('phone') or self.company.get('phone_number')
                                            if phone:
                                                el.fill(phone)
                                                el.dispatch_event('input')
                                                el.dispatch_event('change')
                                                filled_count += 1
                                        elif any(kw in field_hint for kw in ['subject', 'topic', 'reason', 'inquiry_type']):
                                            el.fill(self.subject)
                                            el.dispatch_event('input')
                                            el.dispatch_event('change')
                                            filled_count += 1
                                        elif any(kw in field_hint for kw in ['country', 'nation', 'region', 'location']):
                                            el.fill(self.sender_data.get('sender_country') or 'United Kingdom')
                                            el.dispatch_event('input')
                                            el.dispatch_event('change')
                                            filled_count += 1
                                        elif any(kw in field_hint for kw in ['message', 'comment', 'inquiry', 'enquiry', 'details', 'body']):
                                            el.fill(message)
                                            el.dispatch_event('input')
                                            el.dispatch_event('change')
                                            filled_count += 1
                                        elif el.get_attribute('type') != 'email':
                                            el.fill('N/A')
                                            el.dispatch_event('input')
                                            el.dispatch_event('change')
                                            filled_count += 1
                            except Exception:
                                pass
                        self.submit_form(form)
                        self.page.wait_for_timeout(1000)
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
            message_content = self.replace_variables(self.message_body)
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
    <div class="content">
        <p>Hello,</p>
        
        <div class="message">
            {message_content.replace(chr(10), '<br>')}
        </div>
        
        <p>Best regards,<br>
        <strong>Campaign Team</strong></p>
        
        <div class="footer">
            <p>This is an automated campaign message.<br>
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
            
            cc_email = self.sender_data.get('cc_email') or None
            if cc_email and str(cc_email).strip():
                cc_email = str(cc_email).strip()
            
            # Use your existing email service
            success = send_email(
                to_email=email_address,
                subject=subject,
                html_content=html_content,
                text_content=text_content,
                cc_email=cc_email
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
