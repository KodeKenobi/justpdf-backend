#!/usr/bin/env python3
"""
Run campaign processor for 7core.co.uk only (no frontend).
Creates a campaign with one company, runs sequential processor, prints result.

  cd trevnoctilla-backend
  py run_7core_test.py
"""
import os
import sys
import json
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
except ImportError:
    pass

def main():
    from app import app
    from models import Campaign, Company, db
    from campaign_sequential import process_campaign_sequential

    url = "https://www.7core.co.uk/"
    company_name = "7 Core Electrical Wholesale Ltd"
    message_template = json.dumps({
        "message": "Hello, we would like to discuss a partnership opportunity. Please get in touch.",
        "subject": "Partnership Inquiry",
        "sender_name": "Test User",
        "sender_email": "test@trevnoctilla.com",
        "sender_company": "Trevnoctilla",
        "sender_first_name": "Test",
        "sender_last_name": "User",
        "sender_phone": "+44 555 123 4567",
        "sender_country": "United Kingdom",
    })

    with app.app_context():
        campaign = Campaign(
            user_id=None,
            session_id="mimic-7core-test",
            name=f"7core test {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            message_template=message_template,
            status="draft",
            total_companies=1,
        )
        db.session.add(campaign)
        db.session.flush()
        company = Company(
            campaign_id=campaign.id,
            company_name=company_name,
            website_url=url,
            status="pending",
        )
        db.session.add(company)
        db.session.commit()
        cid = campaign.id
        coid = company.id
        print(f"Created campaign {cid}, company {coid}: {company_name} | {url}")
        print("Running sequential processor...\n")
        result = process_campaign_sequential(cid)
        if "error" in result:
            print(f"Processor error: {result['error']}")
            sys.exit(1)
        company = Company.query.get(coid)
        print("\n--- Result for 7core.co.uk ---")
        print(f"  status:        {company.status}")
        print(f"  contact_method: {getattr(company, 'contact_method', '—')}")
        print(f"  fields_filled: {getattr(company, 'fields_filled', 0)}")
        print(f"  error_message: {getattr(company, 'error_message', '—') or '—'}")
        print(f"  screenshot_url: {getattr(company, 'screenshot_url', '—') or '—'}")
        print(f"  processed_at:  {getattr(company, 'processed_at', '—')}")
        print("--- Done ---")


if __name__ == "__main__":
    main()
