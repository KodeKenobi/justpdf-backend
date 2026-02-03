#!/usr/bin/env python3
"""Test ONLY screenshot capture path - no Supabase. Run from backend dir: py test_screenshot_capture.py"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from playwright.sync_api import sync_playwright
from services.fast_campaign_processor import FastCampaignProcessor

def log(level, action, message):
    print(f"[{level}] {action}: {message}")

def main():
    url = "https://www.2020innovation.com"
    company_data = {
        "id": 1,
        "website_url": url,
        "company_name": "Test",
        "contact_email": "",
        "phone": "",
        "contact_person": "",
    }
    print("1. Launch browser, goto", url)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-setuid-sandbox"])
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        page = context.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(3000)

        processor = FastCampaignProcessor(
            page=page,
            company_data=company_data,
            message_template="Hello",
            campaign_id=1,
            company_id=1,
            logger=log,
        )
        print("2. Call process_company()...")
        result = processor.process_company()
        browser.close()

    print("3. Result keys:", list(result.keys()))
    print("   success:", result.get("success"))
    print("   method:", result.get("method"))
    sb = result.get("screenshot_bytes")
    print("   screenshot_bytes: present=%s type=%s len=%s" % (sb is not None, type(sb).__name__, len(sb) if sb else 0))
    print("   screenshot_url (path):", result.get("screenshot_url"))

    if not sb:
        print("\n>>> FAIL: No screenshot_bytes in result - fix processor/take_screenshot")
        sys.exit(1)
    print("\n>>> PASS: Processor returns screenshot_bytes. Issue is likely Supabase upload or bucket.")
    sys.exit(0)

if __name__ == "__main__":
    main()
