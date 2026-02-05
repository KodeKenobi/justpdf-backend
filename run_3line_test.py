#!/usr/bin/env python3
"""
Run campaign processor for 3lineelectrical.co.uk only (no frontend).
Creates a campaign with one company, runs sequential processor, prints result and logs.

  cd trevnoctilla-backend
  py run_3line_test.py
"""
import os
import sys
import json
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
except ImportError:
    pass

def _ts():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

def main():
    from app import app
    from models import Campaign, Company, db
    from campaign_sequential import process_campaign_sequential

    url = "https://www.3lineelectrical.co.uk/"
    company_name = "3 Line Electrical Wholesale Ltd"
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
            session_id="mimic-3line-test",
            name=f"3line test {datetime.now().strftime('%Y-%m-%d %H:%M')}",
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
        print(f"[{_ts()}] Created campaign {cid}, company {coid}: {company_name} | {url}")
        print(f"[{_ts()}] Running sequential processor (watch for Strategy 0/2, form wait, no_contact)...\n")
        result = process_campaign_sequential(cid)
        if "error" in result:
            print(f"[{_ts()}] Processor error: {result['error']}")
            sys.exit(1)
        company = Company.query.get(coid)
        print(f"\n[{_ts()}] --- Result for 3lineelectrical.co.uk ---")
        print(f"[{_ts()}]   status:         {company.status}")
        print(f"[{_ts()}]   contact_method: {getattr(company, 'contact_method', '—')}")
        print(f"[{_ts()}]   fields_filled:   {getattr(company, 'fields_filled', 0)}")
        print(f"[{_ts()}]   error_message:  {getattr(company, 'error_message', '—') or '—'}")
        print(f"[{_ts()}]   screenshot_url:  {getattr(company, 'screenshot_url', '—') or '—'}")
        print(f"[{_ts()}]   processed_at:   {getattr(company, 'processed_at', '—')}")
        print(f"[{_ts()}] --- Done ---")


if __name__ == "__main__":
    main()
