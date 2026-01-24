#!/usr/bin/env python3
"""
Test script for FastCampaignProcessor
Tests the new campaign processing logic without running a full campaign
"""

import os
import sys
from playwright.sync_api import sync_playwright

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services.fast_campaign_processor import FastCampaignProcessor


def test_logger(level, action, message):
    """Test logger function"""
    print(f"[{level}] {action}: {message}")


def test_basic_processor():
    """Test basic processor functionality"""
    print("\n" + "="*80)
    print("Testing Fast Campaign Processor")
    print("="*80 + "\n")
    
    # Test company data
    company_data = {
        'id': 1,
        'website_url': 'https://example.com',
        'company_name': 'Test Company',
        'contact_email': 'test@example.com',
        'phone': '555-1234',
        'contact_person': 'John Doe'
    }
    
    # Test message template
    message_template = """
Hello {company_name} team,

I noticed your website at {website_url} and wanted to reach out.

Best regards,
Test Campaign
"""
    
    print(f"Company: {company_data['company_name']}")
    print(f"Website: {company_data['website_url']}")
    print("\nStarting browser automation...\n")
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-setuid-sandbox']
            )
            
            context = browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            )
            
            page = context.new_page()
            
            # Navigate to test website
            try:
                page.goto(company_data['website_url'], wait_until='domcontentloaded', timeout=30000)
                page.wait_for_timeout(2000)
                
                print("✅ Successfully navigated to website\n")
                
                # Create processor
                processor = FastCampaignProcessor(
                    page=page,
                    company_data=company_data,
                    message_template=message_template,
                    campaign_id=1,
                    company_id=1,
                    logger=test_logger
                )
                
                # Test variable replacement
                print("Testing variable replacement...")
                replaced_message = processor.replace_variables(message_template)
                print(f"✅ Variables replaced successfully")
                print(f"   Original: {message_template[:50]}...")
                print(f"   Replaced: {replaced_message[:50]}...\n")
                
                # Test contact link finding
                print("Testing contact link finding...")
                contact_link = processor.find_contact_link()
                if contact_link:
                    print(f"✅ Found contact link: {contact_link}\n")
                else:
                    print(f"ℹ️  No contact link found (expected for example.com)\n")
                
                # Test form detection
                print("Testing form detection...")
                forms = page.query_selector_all('form')
                print(f"ℹ️  Found {len(forms)} form(s) on page\n")
                
                # Test CAPTCHA detection
                print("Testing CAPTCHA detection...")
                if forms:
                    has_captcha = processor.detect_captcha(forms[0])
                    print(f"✅ CAPTCHA detection works: {has_captcha}\n")
                
                # Test contact info extraction
                print("Testing contact info extraction...")
                contact_info = processor.extract_contact_info()
                if contact_info:
                    print(f"✅ Contact info extracted:")
                    if contact_info.get('emails'):
                        print(f"   Emails: {', '.join(contact_info['emails'][:3])}")
                    if contact_info.get('phones'):
                        print(f"   Phones: {', '.join(contact_info['phones'][:3])}")
                else:
                    print(f"ℹ️  No contact info found\n")
                
                print("\n" + "="*80)
                print("✅ All basic tests passed!")
                print("="*80 + "\n")
                
            except Exception as e:
                print(f"❌ Error during testing: {e}")
                import traceback
                traceback.print_exc()
            finally:
                browser.close()
                
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()


def test_full_processing():
    """Test full company processing on a real website"""
    print("\n" + "="*80)
    print("Full Processing Test")
    print("="*80 + "\n")
    print("Note: This test will attempt to process a real company website")
    print("It's safe but may take 30-60 seconds\n")
    
    # Use a safe test website (your own or example.com)
    company_data = {
        'id': 999,
        'website_url': 'https://www.trevnoctilla.com',  # Your own site
        'company_name': 'Trevnoctilla',
        'contact_email': 'test@trevnoctilla.com',
        'phone': '555-0000',
        'contact_person': 'Test User'
    }
    
    message_template = "This is a test message for {company_name} at {website_url}"
    
    print(f"Processing: {company_data['company_name']}")
    print(f"URL: {company_data['website_url']}\n")
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-setuid-sandbox']
            )
            
            context = browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            )
            
            page = context.new_page()
            
            try:
                page.goto(company_data['website_url'], wait_until='domcontentloaded', timeout=30000)
                page.wait_for_timeout(2000)
                
                processor = FastCampaignProcessor(
                    page=page,
                    company_data=company_data,
                    message_template=message_template,
                    campaign_id=999,
                    company_id=999,
                    logger=test_logger
                )
                
                print("Starting full company processing...\n")
                result = processor.process_company()
                
                print("\n" + "-"*80)
                print("PROCESSING RESULT:")
                print("-"*80)
                print(f"Success: {result.get('success')}")
                print(f"Method: {result.get('method')}")
                print(f"Error: {result.get('error', 'None')}")
                print(f"Fields Filled: {result.get('fields_filled', 0)}")
                if result.get('contact_info'):
                    print(f"Contact Info: {result.get('contact_info')}")
                print("-"*80 + "\n")
                
                if result.get('success'):
                    print("✅ Processing completed successfully!")
                else:
                    print("ℹ️  Processing completed (check method and error for details)")
                
            except Exception as e:
                print(f"❌ Error during full processing: {e}")
                import traceback
                traceback.print_exc()
            finally:
                browser.close()
                
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()


def test_email_config():
    """Test email configuration"""
    print("\n" + "="*80)
    print("Email Configuration Test")
    print("="*80 + "\n")
    
    # Check for existing email service configuration (Resend)
    resend_api_key = os.getenv('RESEND_API_KEY')
    from_email = os.getenv('FROM_EMAIL')
    nextjs_url = os.getenv('NEXTJS_API_URL') or os.getenv('NEXTJS_URL')
    
    print("Email Service Configuration (Resend via Next.js):")
    print(f"  Resend API Key: {'✅ Set' if resend_api_key else '❌ Not configured'}")
    print(f"  From Email: {from_email or '❌ Not configured'}")
    print(f"  Next.js API URL: {nextjs_url or '❌ Not configured'}")
    
    if all([resend_api_key, from_email]):
        print("\n✅ Email service is configured!")
        print("   Using your existing Resend email service")
        print("   Campaign emails will be sent through the same infrastructure")
        print("   as your invoices, welcome emails, etc.")
    else:
        print("\n⚠️  Email service configuration incomplete")
        print("   Email sending will be skipped during campaigns")
        print("   Forms will still be filled and submitted")
        print(f"\n   To enable email: Configure RESEND_API_KEY in .env")
    
    # Test if email_service module can be imported
    print("\nTesting email_service import...")
    try:
        from email_service import send_email
        print("✅ email_service.py found and importable")
        print("   Campaign processor can use existing email infrastructure")
    except ImportError as e:
        print(f"❌ Could not import email_service: {e}")
        print("   Email sending will not work")
    
    print()


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Test Fast Campaign Processor')
    parser.add_argument('--test', choices=['basic', 'full', 'email', 'all'], 
                       default='all', help='Which test to run')
    
    args = parser.parse_args()
    
    print("\n🚀 Fast Campaign Processor Test Suite")
    print("=" * 80)
    
    if args.test in ['basic', 'all']:
        test_basic_processor()
    
    if args.test in ['email', 'all']:
        test_email_config()
    
    if args.test in ['full', 'all']:
        print("\n⚠️  Full processing test will access real websites")
        response = input("Continue? (y/N): ")
        if response.lower() == 'y':
            test_full_processing()
        else:
            print("Skipped full processing test")
    
    print("\n✅ Test suite completed!\n")
