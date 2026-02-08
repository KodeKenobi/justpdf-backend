"""
Standalone worker script to process a single company.
Runs in a subprocess and can be forcefully killed if it exceeds timeout.

Usage:
    python process_single_company.py --input input.json --output output.json

Input JSON format:
{
    "campaign_id": 123,
    "company_id": 456,
    "company_data": {...},
    "message_template": "...",
    "subject": "...",
    "sender_data": {...},
    "timeout_sec": 60,
    "skip_submit": false
}

Output JSON format:
{
    "success": true/false,
    "method": "form_submitted" | "email_found" | "timeout" | "error",
    "error": "error message if any",
    "contact_info": {...},
    "fields_filled": 0,
    "screenshot_url": "...",
    "form_fields_detected": [...],
    "filled_field_patterns": [...]
}
"""

import sys
import json
import argparse
import os
from playwright.sync_api import sync_playwright

# Add parent directory to path so we can import services
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services.fast_campaign_processor import FastCampaignProcessor


def _timeout_handler(cid):
    print(f"ERROR: Absolute process timeout reached for company {cid}. Exiting.", file=sys.stderr)
    os._exit(1) # Force exit immediately


def process_single_company(input_data: dict) -> dict:
    """
    Process a single company and return the result.
    This function runs in a subprocess and can be killed.
    """
    result = {
        'success': False,
        'method': 'error',
        'error': None,
        'contact_info': None,
        'fields_filled': 0,
        'screenshot_url': None
    }
    
    try:
        campaign_id = input_data.get('campaign_id')
        company_id = input_data.get('company_id')
        company_data = input_data.get('company_data', {})
        message_template = input_data.get('message_template', '')
        subject = input_data.get('subject', 'Partnership Inquiry')
        sender_data = input_data.get('sender_data', {})
        timeout_sec = input_data.get('timeout_sec', 60)
        skip_submit = input_data.get('skip_submit', False)
        
        # Absolute safeguard: kill self if we exceed timeout + 10s grace
        import threading
        timer = threading.Timer(timeout_sec + 20, _timeout_handler, args=[company_id])
        timer.daemon = True
        timer.start()

        # Simple logger that prints to stderr (orchestrator can capture)
        def simple_logger(level, action, message):
            print(f"[{level}] {action}: {message}", file=sys.stderr)
        
        # Launch Playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--disable-dev-shm-usage',
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-web-security',
                    '--disable-features=IsolateOrigins,site-per-process'
                ]
            )
            
            context = browser.new_context(
                viewport={'width': 1280, 'height': 720},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                java_script_enabled=True,
                bypass_csp=True,
                ignore_https_errors=True
            )
            
            page = context.new_page()
            
            # LIGHTNING FAST: Block non-essential resources to slash load times
            def block_aggressively(route):
                if route.request.resource_type in ["image", "media", "font"]:
                    route.abort()
                else:
                    route.continue_()
            
            page.route("**/*", block_aggressively)
            
            try:
                # Create processor
                processor = FastCampaignProcessor(
                    page=page,
                    company_data=company_data,
                    message_template=message_template,
                    campaign_id=campaign_id,
                    company_id=company_id,
                    logger=simple_logger,
                    subject=subject,
                    sender_data=sender_data,
                    deadline_sec=timeout_sec,
                    skip_submit=skip_submit
                )
                
                # Process company
                result = processor.process_company()
                
            finally:
                # Clean up
                try:
                    page.close(timeout=5000)
                except Exception:
                    pass
                try:
                    context.close(timeout=5000)
                except Exception:
                    pass
                try:
                    browser.close()
                except Exception:
                    pass
    
    except Exception as e:
        result = {
            'success': False,
            'method': 'error',
            'error': str(e),
            'contact_info': None,
            'fields_filled': 0,
            'screenshot_url': None
        }
    
    # Ensure result is JSON serializable (bytes -> base64 string)
    if result and result.get('screenshot_bytes'):
        try:
            import base64
            if isinstance(result['screenshot_bytes'], bytes):
                result['screenshot_bytes'] = base64.b64encode(result['screenshot_bytes']).decode('utf-8')
        except Exception as e:
            print(f"ERROR: Failed to encode screenshot: {e}", file=sys.stderr)
            
    return result


def main():
    parser = argparse.ArgumentParser(description='Process a single company')
    parser.add_argument('--input', required=True, help='Input JSON file path')
    parser.add_argument('--output', required=True, help='Output JSON file path')
    args = parser.parse_args()
    
    # Read input
    try:
        with open(args.input, 'r', encoding='utf-8') as f:
            input_data = json.load(f)
    except Exception as e:
        result = {
            'success': False,
            'method': 'error',
            'error': f'Failed to read input: {e}',
            'contact_info': None,
            'fields_filled': 0,
            'screenshot_url': None
        }
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(result, f)
        sys.exit(1)
    
    # Process company
    result = process_single_company(input_data)
    
    # Write output
    try:
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2)
    except Exception as e:
        print(f"ERROR: Failed to write output: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Exit with appropriate code
    sys.exit(0 if result.get('success') else 1)


if __name__ == '__main__':
    main()
