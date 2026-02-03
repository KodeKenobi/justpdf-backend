"""
Supabase Storage utility for uploading campaign screenshots.
Uses only Railway env vars: SUPABASE_DATABASE_URL, SUPABASE_SERVICE_ROLE_KEY.
"""
import os
import re
from supabase import create_client, Client
from datetime import datetime

def _get_supabase_url() -> str:
    """Derive API URL from SUPABASE_DATABASE_URL (only existing backend vars)."""
    db_url = os.getenv("SUPABASE_DATABASE_URL", "")
    # e.g. postgresql://...@db.XXXXX.supabase.co:5432/... -> https://XXXXX.supabase.co
    m = re.search(r"@(?:db\.)?([a-z0-9-]+)\.supabase\.co", db_url)
    if m:
        return f"https://{m.group(1)}.supabase.co"
    return ""

def _get_supabase_client() -> Client:
    url = _get_supabase_url()
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not key:
        raise ValueError("SUPABASE_DATABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set")
    return create_client(url, key)

# Lazy init so env is available at runtime
_supabase: Client = None

def _client() -> Client:
    global _supabase
    if _supabase is None:
        _supabase = _get_supabase_client()
    return _supabase

# Storage bucket name
SCREENSHOT_BUCKET = 'campaign-screenshots'

def upload_screenshot(screenshot_bytes: bytes, campaign_id: int, company_id: int) -> str:
    """
    Upload screenshot to Supabase Storage (all campaign screenshots live in Supabase only).
    
    Args:
        screenshot_bytes: Screenshot image as bytes (PNG from processor)
        campaign_id: Campaign ID
        company_id: Company ID
    
    Returns:
        Public URL of uploaded screenshot, or None on failure
    """
    try:
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        filename = f"campaign_{campaign_id}/company_{company_id}_{timestamp}.png"
        
        print(f"[INFO] Uploading screenshot to Supabase: {filename} ({len(screenshot_bytes)} bytes)")
        
        client = _client()
        response = client.storage.from_(SCREENSHOT_BUCKET).upload(
            filename,
            screenshot_bytes,
            file_options={
                'content-type': 'image/png',
                'cache-control': '3600',
                'upsert': 'true'
            }
        )
        
        print(f"[DEBUG] Upload response: {response}")
        
        # Get public URL
        public_url = client.storage.from_(SCREENSHOT_BUCKET).get_public_url(filename)
        
        print(f"[OK] Screenshot uploaded to Supabase: {filename}")
        print(f"[OK] Public URL: {public_url}")
        return public_url
        
    except Exception as e:
        print(f"[ERROR] Failed to upload screenshot to Supabase: {e}")
        import traceback
        traceback.print_exc()
        return None

def delete_screenshot(screenshot_url: str) -> bool:
    """
    Delete screenshot from Supabase Storage
    
    Args:
        screenshot_url: Public URL of screenshot
    
    Returns:
        True if deleted successfully
    """
    try:
        # Extract filename from URL
        filename = screenshot_url.split(f'{SCREENSHOT_BUCKET}/')[-1]
        
        # Delete from Supabase Storage
        _client().storage.from_(SCREENSHOT_BUCKET).remove([filename])
        
        print(f"[OK] Screenshot deleted from Supabase: {filename}")
        return True
        
    except Exception as e:
        print(f"[ERROR] Failed to delete screenshot from Supabase: {e}")
        return False
