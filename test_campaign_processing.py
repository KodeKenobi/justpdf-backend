"""
Test script to diagnose campaign processing issues
"""
import os
import sys

# Set up Flask app context
os.environ['FLASK_APP'] = 'app.py'

print("=" * 60)
print("TESTING CAMPAIGN PROCESSING")
print("=" * 60)

# Test 1: Import campaign_sequential
print("\n[TEST 1] Importing campaign_sequential...")
try:
    from campaign_sequential import process_campaign_sequential
    print("✓ Import successful")
except Exception as e:
    print(f"✗ Import failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 2: Import dependencies
print("\n[TEST 2] Importing dependencies...")
try:
    from websocket_manager import ws_manager
    print("✓ websocket_manager imported")
except Exception as e:
    print(f"✗ websocket_manager failed: {e}")

try:
    from utils.supabase_storage import upload_screenshot
    print("✓ supabase_storage imported")
except Exception as e:
    print(f"✗ supabase_storage failed: {e}")

# Test 3: Import FastCampaignProcessor
print("\n[TEST 3] Importing FastCampaignProcessor...")
try:
    from services.fast_campaign_processor import FastCampaignProcessor
    print("✓ FastCampaignProcessor imported")
    
    # Check if detect_captcha method exists
    if hasattr(FastCampaignProcessor, 'detect_captcha'):
        print("✓ detect_captcha method exists")
    else:
        print("✗ detect_captcha method MISSING!")
except Exception as e:
    print(f"✗ FastCampaignProcessor import failed: {e}")
    import traceback
    traceback.print_exc()

# Test 4: Check worker script exists
print("\n[TEST 4] Checking worker script...")
worker_script = os.path.join(os.path.dirname(__file__), 'process_single_company.py')
if os.path.exists(worker_script):
    print(f"✓ Worker script exists: {worker_script}")
else:
    print(f"✗ Worker script NOT FOUND: {worker_script}")

# Test 5: Test subprocess spawn
print("\n[TEST 5] Testing subprocess spawn...")
import subprocess
import tempfile
import json

try:
    # Create test input
    test_input = {
        "campaign_id": 999,
        "company_id": 999,
        "company_data": {"website_url": "https://example.com", "company_name": "Test"},
        "message_template": "Test message",
        "subject": "Test",
        "sender_data": {},
        "timeout_sec": 5,
        "skip_submit": True
    }
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        input_path = f.name
        json.dump(test_input, f)
    
    output_path = input_path.replace('.json', '_output.json')
    
    # Try to spawn worker
    print(f"  Spawning: py {worker_script} --input {input_path} --output {output_path}")
    proc = subprocess.Popen(
        ['py', worker_script, '--input', input_path, '--output', output_path],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=os.path.dirname(__file__)
    )
    
    print(f"  Worker PID: {proc.pid}")
    print("  Waiting 3 seconds...")
    
    try:
        stdout, stderr = proc.communicate(timeout=3)
        print(f"  Exit code: {proc.returncode}")
        if stderr:
            print(f"  Stderr: {stderr.decode('utf-8', errors='ignore')[:200]}")
    except subprocess.TimeoutExpired:
        print("  Worker still running after 3s (expected for real processing)")
        proc.kill()
        proc.wait()
    
    # Cleanup
    try:
        os.remove(input_path)
        if os.path.exists(output_path):
            os.remove(output_path)
    except:
        pass
    
    print("✓ Subprocess spawn works")
    
except Exception as e:
    print(f"✗ Subprocess test failed: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)
print("TEST COMPLETE")
print("=" * 60)
