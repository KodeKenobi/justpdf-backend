import threading
import time
import random
from datetime import datetime, timedelta
import requests
import os
from PIL import Image
import io

class AutomatedImageTestService:
    def __init__(self, backend_url="http://localhost:5000", admin_email=None):
        self.backend_url = backend_url
        self.admin_email = admin_email or os.getenv("ADMIN_EMAIL")
        self.is_running = False
        self.thread = None
        self.stats = {
            "total_tests": 0,
            "failures": 0,
            "last_run": None,
            "next_run": None,
            "history": []
        }
        self.test_interval_hours = 3
        print(f"[IMAGE TEST SERVICE] Initialized with backend: {backend_url}")

    def start(self):
        if not self.is_running:
            self.is_running = True
            self.thread = threading.Thread(target=self._run_loop, daemon=True)
            self.thread.start()
            print("[IMAGE TEST SERVICE] Service started")

    def stop(self):
        self.is_running = False
        print("[IMAGE TEST SERVICE] Stopping service...")

    def _run_loop(self):
        while self.is_running:
            try:
                # Perform the test
                self.perform_test()
                
                # Schedule next run (3 hours +/- 15 mins randomness)
                random_offset = random.randint(-15, 15)
                wait_minutes = (self.test_interval_hours * 60) + random_offset
                
                self.stats["next_run"] = (datetime.now() + timedelta(minutes=wait_minutes)).isoformat()
                print(f"[IMAGE TEST SERVICE] Next test scheduled in {wait_minutes} minutes at {self.stats['next_run']}")
                
                # Sleep in small increments to respond to stop signal
                for _ in range(wait_minutes * 6): 
                    if not self.is_running:
                        break
                    time.sleep(10)
            except Exception as e:
                print(f"[IMAGE TEST SERVICE ERROR] Loop error: {e}")
                time.sleep(60)

    def perform_test(self):
        print(f"[IMAGE TEST SERVICE] Starting test at {datetime.now()}")
        self.stats["total_tests"] += 1
        self.stats["last_run"] = datetime.now().isoformat()
        
        success = False
        error_msg = ""
        
        try:
            # 1. Create a dummy image
            img = Image.new('RGB', (100, 100), color=(random.randint(0,255), random.randint(0,255), random.randint(0,255)))
            img_byte_arr = io.BytesIO()
            img.save(img_byte_arr, format='JPEG')
            img_byte_arr = img_byte_arr.getvalue()

            # 2. Call the conversion API
            files = {'file': ('test_image.jpg', img_byte_arr, 'image/jpeg')}
            data = {'target_format': 'png'}
            
            response = requests.post(
                f"{self.backend_url}/api/v1/convert/image",
                files=files,
                data=data,
                timeout=30
            )
            
            if response.status_code == 200:
                success = True
                print("[IMAGE TEST SERVICE] ✅ Test Successful")
            else:
                error_msg = f"API returned {response.status_code}: {response.text[:100]}"
                print(f"[IMAGE TEST SERVICE] ❌ Test Failed: {error_msg}")
        except Exception as e:
            error_msg = str(e)
            print(f"[IMAGE TEST SERVICE] ❌ Test Error: {error_msg}")

        # Update stats
        result = {
            "timestamp": datetime.now().isoformat(),
            "success": success,
            "error": error_msg if not success else None
        }
        self.stats["history"].insert(0, result)
        self.stats["history"] = self.stats["history"][:10] # Keep last 10
        
        if not success:
            self.stats["failures"] += 1
            self._send_alert(error_msg)
            
        return success

    def _send_alert(self, error_msg):
        if not self.admin_email:
            print("[IMAGE TEST SERVICE] No admin email configured, skipping alert")
            return
            
        try:
            from email_service import send_email
            subject = "🚨 trevnoctilla: Image Converter Test Failure"
            body = f"""
            <h3>Image Converter Test Failed</h3>
            <p>The automated image converter test failed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}.</p>
            <p><strong>Error:</strong> {error_msg}</p>
            <p>Please check the backend logs for more details.</p>
            <br>
            <p>---</p>
            <p>This is an automated message from your trevnoctilla monitoring service.</p>
            """
            send_email(self.admin_email, subject, body)
            print("[IMAGE TEST SERVICE] Alert email sent")
        except Exception as e:
            print(f"[IMAGE TEST SERVICE] Failed to send email alert: {e}")

# Global instance
image_test_service = AutomatedImageTestService()
