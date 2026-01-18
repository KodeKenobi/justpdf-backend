"""
Supabase Storage utility for uploading campaign screenshots
"""
import os
from supabase import create_client, Client
from datetime import datetime

# Supabase credentials
SUPABASE_URL = os.getenv('SUPABASE_URL', 'https://pqdxqvxyrahvongbhtdb.supabase.co')
SUPABASE_KEY = os.getenv('SUPABASE_KEY', 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InBxZHhxdnh5cmFodm9uZ2JodGRiIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTczMTk0NzE5MiwiZXhwIjoyMDQ3NTIzMTkyfQ.5WnRaHqAl0EcNzwMuY_dFYMaW5F8xfv6bj31gPGdgLs')

# Initialize Supabase client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Storage bucket name
SCREENSHOT_BUCKET = 'campaign-screenshots'

def upload_screenshot(screenshot_bytes: bytes, campaign_id: int, company_id: int) -> str:
    """
    Upload screenshot to Supabase Storage
    
    Args:
        screenshot_bytes: Screenshot image as bytes
        campaign_id: Campaign ID
        company_id: Company ID
    
    Returns:
        Public URL of uploaded screenshot
    """
    try:
        # Generate unique filename
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        filename = f"campaign_{campaign_id}/company_{company_id}_{timestamp}.jpg"
        
        print(f"[INFO] Attempting to upload screenshot: {filename} ({len(screenshot_bytes)} bytes)")
        
        # Upload to Supabase Storage
        response = supabase.storage.from_(SCREENSHOT_BUCKET).upload(
            filename,
            screenshot_bytes,
            {
                'content-type': 'image/jpeg',
                'cache-control': '3600',
                'upsert': 'true'  # Overwrite if exists
            }
        )
        
        print(f"[DEBUG] Upload response: {response}")
        
        # Get public URL
        public_url = supabase.storage.from_(SCREENSHOT_BUCKET).get_public_url(filename)
        
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
        supabase.storage.from_(SCREENSHOT_BUCKET).remove([filename])
        
        print(f"[OK] Screenshot deleted from Supabase: {filename}")
        return True
        
    except Exception as e:
        print(f"[ERROR] Failed to delete screenshot from Supabase: {e}")
        return False
