#!/usr/bin/env python3
"""
Reproduce processing for ONE company and print full traceback on failure.
Use this to see exactly what's failing (e.g. after check-campaign-failures.js).

  cd trevnoctilla-backend
  py run_one_company.py <campaign_id> <company_id>

Example (after "node check-campaign-failures.js 5" shows company id 123):
  py run_one_company.py 5 123

Loads .env if python-dotenv is installed. Requires Supabase/DB and Playwright.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
except ImportError:
    pass

def main():
    if len(sys.argv) < 3:
        print("Usage: py run_one_company.py <campaign_id> <company_id>")
        print("Example: py run_one_company.py 5 123")
        sys.exit(1)
    campaign_id = int(sys.argv[1])
    company_id = int(sys.argv[2])

    from app import app
    from models import Campaign, Company
    from database import db
    from services.fast_campaign_processor import FastCampaignProcessor
    from playwright.sync_api import sync_playwright

    with app.app_context():
        campaign = Campaign.query.get(campaign_id)
        company = Company.query.get(company_id)
        if not campaign:
            print(f"Campaign {campaign_id} not found")
            sys.exit(1)
        if not company or company.campaign_id != campaign_id:
            print(f"Company {company_id} not found or not in campaign {campaign_id}")
            sys.exit(1)

        message_template_str = campaign.message_template or ""
        subject_str = "Partnership Inquiry"
        sender_data = {}
        try:
            import json
            if isinstance(campaign.message_template, str) and campaign.message_template.strip().startswith("{"):
                parsed = json.loads(campaign.message_template)
                if isinstance(parsed, dict):
                    sender_data = parsed
                    message_template_str = parsed.get("message", message_template_str)
                    subject_str = parsed.get("subject", subject_str)
        except Exception:
            pass

        def log(level, action, message):
            print(f"[{level}] {action}: {message}")

        print(f"--- Processing company {company_id}: {company.company_name} | {company.website_url} ---\n")

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-setuid-sandbox"])
            context = browser.new_context()
            page = context.new_page()
            page.set_default_timeout(25000)
            page.set_default_navigation_timeout(30000)
            try:
                processor = FastCampaignProcessor(
                    page=page,
                    company_data=company.to_dict(),
                    message_template=message_template_str,
                    campaign_id=campaign_id,
                    company_id=company.id,
                    logger=log,
                    subject=subject_str,
                    sender_data=sender_data,
                )
                result = processor.process_company()
                print("\n--- Result ---")
                print("success:", result.get("success"))
                print("method:", result.get("method"))
                if result.get("error"):
                    print("error:", result.get("error"))
                if not result.get("success"):
                    sys.exit(1)
            except Exception as e:
                print("\n--- FAILED (full traceback below) ---")
                import traceback
                traceback.print_exc()
                sys.exit(1)
            finally:
                browser.close()


if __name__ == "__main__":
    main()
