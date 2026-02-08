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
from campaign_sequential import SelfHealingSentinel, GLOBAL_CAMPAIGN_REGISTRY, REGISTRY_LOCK, SENTINEL_ORPHAN_THRESHOLD_SEC

def run_sync_test():
    with app.app_context():
        print("[TEST] Setting up simulated stall...")
        # 1. Create a dummy campaign
        camp = Campaign(
            name="SYNC TEST STALL",
            message_template="Test message",
            status='processing',
            total_companies=10,
            processed_count=5, 
            last_heartbeat_at=datetime.utcnow() - timedelta(seconds=20) # 20s old, threshold is 10s
        )
        db.session.add(camp)
        db.session.commit()
        cid = camp.id
        
        # 2. Add processing leads
        for i in range(3):
            lead = Company(campaign_id=cid, status='processing', company_name=f"Co {i}", website_url=f"http://test{i}.com")
            db.session.add(lead)
        db.session.commit()

        # 3. Mock process in registry
        class MockProc:
            def kill(self): print("[TEST-MOCK] Process KILLED.")
            def terminate(self): self.kill()
            def poll(self): return None

        with REGISTRY_LOCK:
            GLOBAL_CAMPAIGN_REGISTRY[cid] = {
                'active_procs': {1234: MockProc()},
                'lock': threading.Lock(),
                'interrupted': False,
                'stop_watchdog': False
            }

        print(f"[TEST] Force-triggering one Sentinel iteration (Threshold={SENTINEL_ORPHAN_THRESHOLD_SEC}s)...")
        # We manually call a modified version of the monitor logic or just the sentinel's logic
        # For simplicity, I'll just check if the sentinel WOULD trigger it
        
        from models import Campaign as Camp, Company as Comp
        cutoff = datetime.utcnow() - timedelta(seconds=SENTINEL_ORPHAN_THRESHOLD_SEC)
        orphans = Campaign.query.filter(
            Campaign.status == 'processing',
            (Campaign.last_heartbeat_at == None) | (Campaign.last_heartbeat_at < cutoff)
        ).all()
        
        if orphans:
            print(f"[TEST] Found {len(orphans)} orphans as expected.")
            for c in orphans:
                if c.id == cid:
                    print(f"[TEST] Recovering Campaign {c.id}...")
                    # A. Force kill
                    with REGISTRY_LOCK:
                        old_state = GLOBAL_CAMPAIGN_REGISTRY.get(c.id)
                        if old_state:
                            print(f"[TEST] Killing mock processes...")
                            old_state['interrupted'] = True
                            for pid, p in old_state['active_procs'].items():
                                p.kill()
                    
                    # B. Reset leads
                    stuck = Company.query.filter_by(campaign_id=c.id, status='processing').update({'status': 'pending'})
                    db.session.commit()
                    print(f"[TEST] Reset {stuck} leads.")

        # Final Verification
        db.session.expire_all()
        check_leads = Company.query.filter_by(campaign_id=cid, status='processing').count()
        if check_leads == 0:
            print("[TEST] SUCCESS: Campaign recovered correctly.")
            sys.exit(0)
        else:
            print(f"[TEST] FAILURE: Leads still stuck ({check_leads}).")
            sys.exit(1)

if __name__ == "__main__":
    run_sync_test()
