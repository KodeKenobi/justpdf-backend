import os
import sys

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app
from database import db
from campaign_sequential import process_campaign_sequential

def test_manual(campaign_id):
    with app.app_context():
        print(f"--- STARTING MANUAL TEST FOR CAMPAIGN {campaign_id} ---")
        try:
            result = process_campaign_sequential(campaign_id, processing_limit=2)
            print(f"--- TEST FINISHED. RESULT: {result} ---")
        except Exception as e:
            print(f"--- TEST FAILED WITH ERROR: {e} ---")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    if len(sys.argv) > 1:
        test_manual(int(sys.argv[1]))
    else:
        print("Usage: py debug_sequential.py <campaign_id>")
