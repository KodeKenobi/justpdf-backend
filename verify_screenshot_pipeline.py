#!/usr/bin/env python3
"""
Verify screenshot pipeline locally: capture -> bytes -> Supabase upload -> URL.
Run from backend dir. Requires SUPABASE_DATABASE_URL and SUPABASE_SERVICE_ROLE_KEY
(e.g. from .env or Railway; script loads .env if python-dotenv is installed).

  cd trevnoctilla-backend
  # Windows:
  set SUPABASE_DATABASE_URL=postgresql://...
  set SUPABASE_SERVICE_ROLE_KEY=...
  py verify_screenshot_pipeline.py

  # Or with .env in backend dir (pip install python-dotenv):
  py verify_screenshot_pipeline.py

Exits 0 only if: (1) screenshot bytes captured, (2) upload returns a URL you can open in browser.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Optional: load .env so you don't have to export vars
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
except ImportError:
    pass

def main():
    db_url = os.getenv("SUPABASE_DATABASE_URL", "").strip()
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not db_url or not key:
        print("ERROR: Set SUPABASE_DATABASE_URL and SUPABASE_SERVICE_ROLE_KEY")
        sys.exit(1)

    from playwright.sync_api import sync_playwright
    from services.fast_campaign_processor import FastCampaignProcessor
    from utils.supabase_storage import upload_screenshot

    test_url = os.getenv("TEST_URL", "https://www.2020innovation.com")
    campaign_id = 999
    company_id = 999

    def log(level, action, message):
        print(f"[{level}] {action}: {message}")

    print("=== Screenshot pipeline verification ===\n")
    print(f"1. Opening {test_url} ...")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-setuid-sandbox"])
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        page = context.new_page()

        try:
            page.goto(test_url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(3000)
        except Exception as e:
            print(f"   FAIL: Could not load page: {e}")
            browser.close()
            sys.exit(1)

        company_data = {
            "id": company_id,
            "website_url": test_url,
            "company_name": "Verify Test",
            "contact_email": "",
            "phone": "",
            "contact_person": "",
        }
        processor = FastCampaignProcessor(
            page=page,
            company_data=company_data,
            message_template="Test",
            campaign_id=campaign_id,
            company_id=company_id,
            logger=log,
        )

        print("2. Running process_company() (discovery + form fill + screenshot) ...")
        result = processor.process_company()

        screenshot_bytes = result.get("screenshot_bytes")
        if not screenshot_bytes:
            print("   No bytes from process_company; taking page screenshot to verify upload path...")
            _, screenshot_bytes = processor.take_screenshot("verify_test")
            if not screenshot_bytes:
                print("   FAIL: take_screenshot() returned no bytes")
                browser.close()
                sys.exit(1)
            print(f"   OK: take_screenshot() returned {len(screenshot_bytes)} bytes")
        else:
            print(f"   OK: screenshot_bytes from process_company ({len(screenshot_bytes)} bytes)")

        browser.close()

    if not screenshot_bytes:
        print("   FAIL: No screenshot bytes to upload")
        sys.exit(1)

    print("3. Uploading to Supabase ...")
    try:
        url = upload_screenshot(screenshot_bytes or b"", campaign_id, company_id)
    except Exception as e:
        print(f"   FAIL: upload_screenshot raised: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    if not url:
        print("   FAIL: upload_screenshot returned None")
        sys.exit(1)

    print(f"   OK: URL = {url}")
    print("\n=== PASS: Screenshot pipeline works ===")
    print("Open this URL in a browser to confirm the image loads:")
    print(url)
    sys.exit(0)


if __name__ == "__main__":
    main()
