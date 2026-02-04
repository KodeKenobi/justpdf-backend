#!/usr/bin/env python3
"""
Backend-only test: read first 5 companies from main-leads.csv, create campaign,
run sequential processor, print results. No frontend.

  cd trevnoctilla-backend
  py run_main_leads_test.py

CSV path: project root main-leads.csv (col0=company_name, col1=website_url).
"""
import os
import sys
import csv
import json
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
except ImportError:
    pass

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAIN_LEADS_CSV = os.path.join(PROJECT_ROOT, "main-leads.csv")
MAX_COMPANIES = 5


def load_first_n_companies(csv_path, n=5):
    """Parse CSV; return list of dicts with company_name, website_url. No header row expected."""
    rows = []
    with open(csv_path, "r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        for row in reader:
            if len(row) < 2:
                continue
            name = (row[0] or "").strip()
            url = (row[1] or "").strip()
            if not url:
                continue
            if not url.startswith("http"):
                url = "https://" + url
            rows.append({"company_name": name or url, "website_url": url})
            if len(rows) >= n:
                break
    return rows


def main():
    from app import app
    from models import Campaign, Company, db
    from campaign_sequential import process_campaign_sequential

    if not os.path.isfile(MAIN_LEADS_CSV):
        print(f"CSV not found: {MAIN_LEADS_CSV}")
        sys.exit(1)

    companies_data = load_first_n_companies(MAIN_LEADS_CSV, MAX_COMPANIES)
    if not companies_data:
        print("No valid rows in CSV (need at least company name and website URL in cols 0 and 1).")
        sys.exit(1)

    message_template = json.dumps({
        "message": "Hello, we would like to discuss a partnership opportunity. Please get in touch.",
        "subject": "Partnership Inquiry",
        "sender_name": "Main Leads Test",
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
            session_id="main-leads-test",
            name=f"Main leads test {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            message_template=message_template,
            status="draft",
            total_companies=len(companies_data),
        )
        db.session.add(campaign)
        db.session.flush()
        for company_data in companies_data:
            company = Company(
                campaign_id=campaign.id,
                company_name=company_data["company_name"],
                website_url=company_data["website_url"],
                status="pending",
            )
            db.session.add(company)
        db.session.commit()
        cid = campaign.id
        print(f"Created campaign {cid} with {len(companies_data)} companies from main-leads.csv")
        for c in companies_data:
            print(f"  - {c['company_name']} | {c['website_url']}")
        print("\nRunning sequential processor...\n")

        result = process_campaign_sequential(cid)
        if "error" in result:
            print(f"Processor error: {result['error']}")
            sys.exit(1)

        print("\n--- Results ---")
        companies = Company.query.filter_by(campaign_id=cid).order_by(Company.id).all()
        for co in companies:
            print(
                f"  {co.company_name or co.website_url}: {co.status} | "
                f"contact_method={getattr(co, 'contact_method', '—') or '—'} | "
                f"fields_filled={getattr(co, 'fields_filled', 0)} | "
                f"error={getattr(co, 'error_message', None) or '—'}"
            )
        print("--- Done ---")


if __name__ == "__main__":
    main()
