#!/usr/bin/env python3
"""
Test Supabase Storage upload only (no Playwright). Uses same env as app:
SUPABASE_DATABASE_URL, SUPABASE_SERVICE_ROLE_KEY. Optional: SUPABASE_SCREENSHOT_BUCKET.

Loads .env from this directory if python-dotenv is installed. Run from backend dir:

  cd trevnoctilla-backend
  py test_supabase_upload.py

Exits 0 if upload and public URL work. Prints the URL so you can open it in a browser.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from dotenv import load_dotenv
    backend_dir = os.path.dirname(os.path.abspath(__file__))
    load_dotenv(os.path.join(backend_dir, ".env"))
    load_dotenv(os.path.join(os.path.dirname(backend_dir), ".env"))  # repo root (NEXT_PUBLIC_*)
except ImportError:
    pass

# Minimal 1x1 PNG bytes
MINI_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)


def main():
    url = (os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL") or "").strip()
    db_url = os.getenv("SUPABASE_DATABASE_URL", "").strip()
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not key:
        print("ERROR: Set SUPABASE_SERVICE_ROLE_KEY in trevnoctilla-backend/.env")
        sys.exit(1)
    if not url and not db_url:
        print("ERROR: Set SUPABASE_URL or NEXT_PUBLIC_SUPABASE_URL or SUPABASE_DATABASE_URL in trevnoctilla-backend/.env")
        sys.exit(1)

    from utils.supabase_storage import upload_screenshot, _get_supabase_url

    url_derived = _get_supabase_url()
    print(f"Derived Supabase API URL: {url_derived or '(empty - upload will fail)'}")
    if not url_derived:
        print("ERROR: Could not derive Supabase URL from SUPABASE_DATABASE_URL (check pooler/db host format)")
        sys.exit(1)

    print("Uploading tiny test PNG to Supabase Storage ...")
    public_url = upload_screenshot(MINI_PNG, campaign_id=0, company_id=0)
    if not public_url:
        print("FAIL: upload_screenshot returned None")
        sys.exit(1)
    print("PASS: Upload OK")
    print("Public URL (open in browser):", public_url)
    sys.exit(0)


if __name__ == "__main__":
    main()
