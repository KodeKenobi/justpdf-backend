"""
Robustly fix detect_captcha in fast_campaign_processor.py
"""
import sys
import re

file_path = 'services/fast_campaign_processor.py'

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Define the new method
new_method = """    def detect_captcha(self, form) -> bool:
        \"\"\"Detect CAPTCHA (reCAPTCHA, hCaptcha, Turnstile, etc.) in form or context\"\"\"
        try:
            # 1. Check for known iframes in form
            if form.query_selector('iframe[src*="recaptcha"], iframe[title*="recaptcha"], iframe[src*="hcaptcha"], iframe[src*="turnstile"]'):
                self.log('warning', 'Captcha', 'Detected captcha iframe in form')
                return True
            
            # 2. Check for known badges/classes in form
            if form.query_selector('.grecaptcha-badge, .g-recaptcha, .h-captcha, .cf-turnstile, [data-sitekey]'):
                self.log('warning', 'Captcha', 'Detected captcha badge/data-sitekey in form')
                return True
            
            # 3. Check for generic captcha keywords in ids/names/classes (case-insensitive)
            captcha_selectors = [
                '[class*="captcha" i]',
                '[id*="captcha" i]',
                '[name*="captcha" i]',
                'img[src*="captcha" i]'
            ]
            for selector in captcha_selectors:
                el = form.query_selector(selector)
                if el and el.is_visible():
                    self.log('warning', 'Captcha', f'Detected probable captcha: {selector}')
                    return True
            
            # 4. Page-level check (sometimes they are outside the <form> tag)
            for sel in ['.grecaptcha-badge', 'iframe[src*="recaptcha"]', 'iframe[src*="hcaptcha"]', 'iframe[src*="turnstile"]']:
                el = self.page.query_selector(sel)
                if el and el.is_visible():
                    self.log('warning', 'Captcha', f'Detected page-level captcha: {sel}')
                    return True
            
            return False
        except Exception:
            return False"""

# Find the existing detect_captcha method using regex and replace it
# We want to match from 'def detect_captcha' until the next def or end of class
pattern = r'    def detect_captcha\(self, form\) -> bool:.*?\n(?=\s+def |\s+\Z)'
if re.search(pattern, content, re.DOTALL):
    new_content = re.sub(pattern, new_method + '\n\n', content, flags=re.DOTALL)
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(new_content)
    print("✓ Successfully replaced detect_captcha with robust version")
else:
    print("✗ Could not find detect_captcha method to replace")
