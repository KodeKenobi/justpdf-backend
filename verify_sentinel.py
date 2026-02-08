import os
import sys
import time
import threading
from datetime import datetime, timedelta

# Mock/Setup for testing sentinel in isolation
sys.path.append(os.getcwd())

from app import app
from database import db
from models import Campaign, Company
from campaign_sequential import SelfHealingSentinel, GLOBAL_CAMPAIGN_REGISTRY

def run_test():
    with app.app_context():
        print("[TEST] Setting up simulated stall...")
        # 1. Create a dummy campaign
        camp = Campaign(
            name="TEST STALL CAMPAIGN",
            message_template="Test message",
            status='processing',
            total_companies=10,
            processed_count=5, # Stuck at 5
            last_heartbeat_at=datetime.utcnow() # Heartbeat is fresh, but progress is stuck
        )
        db.session.add(camp)
        db.session.commit()
        
        cid = camp.id
        public_id = camp.public_id
        print(f"[TEST] Created Campaign ID: {cid} (Public: {public_id})")

        # 2. Add some pending/processing leads
        for i in range(3):
            lead = Company(
                campaign_id=cid, 
                status='processing', 
                company_name=f"Test Co {i}",
                website_url=f"http://test{i}.com"
            )
            db.session.add(lead)
        db.session.commit()
        
        print(f"[TEST] Added 3 'processing' leads.")

        # 3. Simulate a "ghost" entry in the registry to test FORCE KILL
        class MockProc:
            def __init__(self, pid): self.pid = pid
            def poll(self): return None # Still running
            def kill(self): print(f"[TEST-MOCK] Process {self.pid} KILLED by Sentinel.")
            def terminate(self): self.kill()

        from campaign_sequential import REGISTRY_LOCK
        with REGISTRY_LOCK:
            GLOBAL_CAMPAIGN_REGISTRY[cid] = {
                'active_procs': {9999: MockProc(9999)},
                'lock': threading.Lock(),
                'interrupted': False,
                'stop_watchdog': False
            }
        print("[TEST] Injected mock process 9999 into registry for force-kill test.")

        # Start Sentinel
        SelfHealingSentinel.start()
        print(f"[TEST] Waiting for Sentinel (Threshold 10s, Scan 10s)...")

        # Watch for progress
        start_time = time.time()
        recovered = False
        while time.time() - start_time < 60:
            db.session.expire_all()
            check_camp = Campaign.query.get(cid)
            stuck_leads = Company.query.filter_by(campaign_id=cid, status='processing').count()
            
            if stuck_leads == 0:
                print(f"[TEST] SUCCESS: Sentinel detected stall and reset leads.")
                recovered = True
                break
            
            print(f"--- {int(time.time() - start_time)}s elapsed | Stuck Leads: {stuck_leads} | Status: {check_camp.status}")
            time.sleep(5)

        if not recovered:
            print("[TEST] FAILURE: Sentinel did not recover the campaign.")
            sys.exit(1)
        else:
            print("[TEST] Verification Complete.")
            sys.exit(0)

if __name__ == "__main__":
    run_test()
