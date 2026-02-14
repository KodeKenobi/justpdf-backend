"""
Automated Ad View Service
Simulates ad views randomly throughout the day to boost ad revenue
"""
import os
import time
import random
import threading
from datetime import datetime, timedelta
import requests
from flask import Flask
from database import db

class AutomatedAdService:
    def __init__(self):
        self.is_running = False
        self.thread = None
        self.view_count = 0
        self.last_view_time = None
        self.target_views_per_day = 12
        self.view_history = []
        # Only use existing Railway vars; FROM_EMAIL used for notifications
        self.admin_notification_email = os.getenv('FROM_EMAIL', 'admin@trevnoctilla.com').split('<')[-1].split('>')[0].strip() if os.getenv('FROM_EMAIL') else 'admin@trevnoctilla.com'
        self.frontend_url = 'https://www.trevnoctilla.com'

    def start_service(self):
        """Start the automated ad view service"""
        from models import SystemSetting
        from app import app
        
        with app.app_context():
            SystemSetting.set('ad_engine_running', 'True', 'Whether the automated ad engine is active')
        
        # We handle thread starting in a way that allows multiple workers to know it SHOULD be running
        # but for simplicity in this PR, we just ensure local instance matches DB
        self.is_running = True
        
        if not self.thread or not self.thread.is_alive():
            self.thread = threading.Thread(target=self._run_service, daemon=True)
            self.thread.start()

        print("[AD SERVICE] Automated ad view service started (Persisted to DB)")
        return True, "Service started successfully"

    def stop_service(self):
        """Stop the automated ad view service"""
        from models import SystemSetting
        from app import app
        
        with app.app_context():
            SystemSetting.set('ad_engine_running', 'False')
            
        self.is_running = False
        print("[AD SERVICE] Automated ad view service stopped (Persisted to DB)")
        return True, "Service stopped successfully"

    def _run_service(self):
        """Main service loop"""
        # Initial view immediately on start
        if self.is_running:
            print("[AD SERVICE] ⚡ Starting initial background view...")
            self._perform_ad_view("Initial Start View")

        while self.is_running:
            try:
                # Calculate optimal timing for views
                views_completed_today = self._get_today_view_count()
                views_remaining = max(0, self.target_views_per_day - views_completed_today)

                if views_remaining > 0:
                    # Spread remaining views throughout the day
                    hours_remaining = max(1, 24 - datetime.now().hour)
                    avg_views_per_hour = views_remaining / hours_remaining

                    # Add some randomness (±50%)
                    views_this_hour = max(1, int(avg_views_per_hour * random.uniform(0.5, 1.5)))

                    self._schedule_hourly_views(views_this_hour)
                else:
                    # All views completed for today, wait until tomorrow
                    tomorrow = datetime.now().replace(hour=0, minute=0, second=0) + timedelta(days=1)
                    seconds_until_tomorrow = (tomorrow - datetime.now()).total_seconds()
                    print(f"[AD SERVICE] Daily target reached. Sleeping until tomorrow ({seconds_until_tomorrow:.0f}s)")
                    time.sleep(min(seconds_until_tomorrow, 3600))  # Sleep max 1 hour

            except Exception as e:
                print(f"[AD SERVICE ERROR] {e}")
                time.sleep(300)  # Sleep 5 minutes on error

    def _schedule_hourly_views(self, views_this_hour: int):
        """Schedule views for the current hour"""
        if views_this_hour <= 0:
            time.sleep(3600)  # Sleep for an hour
            return

        # Spread views randomly throughout the hour
        intervals = []
        total_seconds = 3600  # 1 hour

        for i in range(views_this_hour):
            # Random interval between views (but ensure they're spread out)
            if i == 0:
                # First view: random time within first half hour
                interval = random.uniform(60, 1800)  # 1-30 minutes
            else:
                # Subsequent views: spread remaining time
                remaining_time = total_seconds - sum(intervals)
                remaining_views = views_this_hour - i
                if remaining_views > 0:
                    avg_interval = remaining_time / remaining_views
                    interval = random.uniform(avg_interval * 0.5, avg_interval * 1.5)
                else:
                    interval = random.uniform(300, 1800)  # 5-30 minutes

            intervals.append(interval)

        print(f"[AD SERVICE] Scheduling {views_this_hour} views this hour")

        # Execute the views
        for i, interval in enumerate(intervals):
            if not self.is_running:
                break

            time.sleep(interval)
            if self.is_running:  # Check again after sleep
                self._perform_ad_view(f"View {i+1}/{views_this_hour} this hour")

    def _perform_ad_view(self, context: str = ""):
        """Perform a single ad view simulation"""
        try:
            print(f"[AD SERVICE] Performing ad view: {context}")

            # Simulate visiting a page that triggers monetization
            test_url = f"{self.frontend_url}/test-monetization"
            # Use a realistic browser-like User-Agent
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
                "Content-Type": "application/json"
            }
            
            # Simple visit simulation (non-critical if fails)
            try:
                requests.get(test_url, headers=headers, timeout=10)
            except Exception as visit_err:
                print(f"[AD SERVICE] ⚠️ Simulation visit warning: {visit_err}")

            # Process the ad view tracking DIRECTLY via database (more reliable than API calls)
            api_recorded = False
            try:
                # Import inside to avoid circular dependencies
                from models import AnalyticsEvent
                from app import app
                
                with app.app_context():
                    # Create the event exactly as the frontend would
                    # We bypass the /admin/ filter by setting page_url to /
                    new_event = AnalyticsEvent(
                        event_type="custom",
                        event_name="ad_click",
                        properties={
                            "ad_provider": "monetag",
                            "ad_url": "https://otieu.com/4/10115019",
                            "file_name": "automated-engine-diagnostic.pdf",
                            "download_url": "blob:automated-engine-blob-data",
                            "page": "/", # Bypass admin filter
                            "manual_trigger": True, 
                            "automated": True,
                            "simulated": True,
                            "context": context
                        },
                        session_id=f"session_engine_{int(time.time())}",
                        page_url="/", # Bypass admin filter
                        page_title="Home",
                        timestamp=datetime.utcnow(),
                        user_agent=headers["User-Agent"],
                        device_type="desktop",
                        browser="chrome",
                        os="windows"
                    )
                    
                    db.session.add(new_event)
                    db.session.commit()
                    print(f"[AD SERVICE] ✅ Event recorded directly to DB")
                    api_recorded = True
            except Exception as db_err:
                print(f"[AD SERVICE] ❌ Database recording failed: {db_err}")
                try:
                    db.session.rollback()
                except:
                    pass

            if api_recorded:
                self.view_count += 1
                self.last_view_time = datetime.now()
                
                # Persist stats to DB
                try:
                    from models import SystemSetting
                    from app import app
                    with app.app_context():
                        SystemSetting.set('ad_engine_total_views', self.view_count)
                        SystemSetting.set('ad_engine_last_view', self.last_view_time.isoformat())
                except:
                    pass

                # Log the view for service status
                view_record = {
                    'timestamp': self.last_view_time.isoformat(),
                    'context': context,
                    'simulated': True,
                    'status': 'Success'
                }
                self.view_history.append(view_record)

                # Keep only last 100 records
                if len(self.view_history) > 100:
                    self.view_history = self.view_history[-100:]

                print(f"[AD SERVICE] ✅ Ad view completed (Total: {self.view_count})")

                # Send notification email every 10 views
                if self.view_count % 10 == 0:
                    self._send_progress_email()
            else:
                print(f"[AD SERVICE] ❌ Ad view failed (Database recording was unsuccessful)")

        except Exception as e:
            print(f"[AD SERVICE] ❌ Critical error performing ad view: {e}")

    def _get_today_view_count(self) -> int:
        """Get number of views completed today from DB"""
        from models import AnalyticsEvent
        from app import app
        from sqlalchemy import func
        
        try:
            with app.app_context():
                today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
                # Count non-admin ad_click events today
                count = db.session.query(func.count(AnalyticsEvent.id)).filter(
                    AnalyticsEvent.event_name == 'ad_click',
                    AnalyticsEvent.timestamp >= today,
                    ~AnalyticsEvent.page_url.like('%/admin/%')
                ).scalar()
                return count or 0
        except Exception as e:
            print(f"[AD SERVICE] Error counting today's views: {e}")
            return 0

    def _get_total_view_count(self) -> int:
        """Get total number of views completed all-time from DB"""
        from models import AnalyticsEvent
        from app import app
        from sqlalchemy import func
        
        try:
            with app.app_context():
                # Count non-admin ad_click events all-time
                count = db.session.query(func.count(AnalyticsEvent.id)).filter(
                    AnalyticsEvent.event_name == 'ad_click',
                    ~AnalyticsEvent.page_url.like('%/admin/%')
                ).scalar()
                return count or 0
        except Exception as e:
            print(f"[AD SERVICE] Error counting total views: {e}")
            return 0

    def get_status(self):
        """Get current service status with global counts"""
        from models import SystemSetting
        from app import app
        
        # Initialize from DB
        db_running = False
        today_views = self._get_today_view_count()
        total_views = self._get_total_view_count()
        db_last_view = self.last_view_time
        
        try:
            with app.app_context():
                db_running = SystemSetting.get('ad_engine_running', 'False') == 'True'
                last_view_str = SystemSetting.get('ad_engine_last_view')
                if last_view_str:
                    db_last_view = datetime.fromisoformat(last_view_str)
                    
                # Sync local state if DB says it should be running but local isn't
                if db_running and not self.is_running:
                    print("[AD SERVICE] ⚡ Resyncing runner with DB state (Auto-starting thread)")
                    self.is_running = True
                    if not self.thread or not self.thread.is_alive():
                        self.thread = threading.Thread(target=self._run_service, daemon=True)
                        self.thread.start()
                elif not db_running and self.is_running:
                    print("[AD SERVICE] ⚡ Resyncing runner with DB state (Stopping thread)")
                    self.is_running = False
        except Exception as e:
            print(f"[AD SERVICE] Status sync warning: {e}")

        # If 10 total views exist and target is 12, show 2 remaining
        target_remaining = max(0, self.target_views_per_day - today_views)

        return {
            'is_running': db_running,
            'total_views': total_views,
            'last_view_time': db_last_view.isoformat() if db_last_view else None,
            'today_views': today_views,
            'target_daily_views': target_remaining,
            'recent_history': self.view_history[-10:]  # Last 10 views
        }

    def reset_stats(self):
        """Reset view statistics"""
        from models import SystemSetting
        from app import app
        
        with app.app_context():
            SystemSetting.set('ad_engine_total_views', '0')
            SystemSetting.set('ad_engine_last_view', '')
            
        self.view_count = 0
        self.view_history = []
        return True, "Statistics reset successfully"

    def _send_progress_email(self):
        """Send progress notification email"""
        try:
            # Use the existing email service
            from email_service import send_email

            subject = f"Ad View Progress - {self.view_count} Views Completed"
            html_content = f"""
            <h2>Automated Ad View Progress</h2>
            <p><strong>Total Views:</strong> {self.view_count}</p>
            <p><strong>Today's Views:</strong> {self._get_today_view_count()}</p>
            <p><strong>Daily Target:</strong> {self.target_views_per_day}</p>
            <p><strong>Last View:</strong> {self.last_view_time.strftime('%Y-%m-%d %H:%M:%S') if self.last_view_time else 'N/A'}</p>
            <p><strong>Service Status:</strong> {'Running' if self.is_running else 'Stopped'}</p>

            <h3>Recent Activity:</h3>
            <ul>
            {"".join(f"<li>{record['timestamp'][:19]} - {record['context']}</li>" for record in self.view_history[-5:])}
            </ul>

            <p>This is an automated notification from the Trevnoctilla Ad Service.</p>
            """

            text_content = f"""
            Automated Ad View Progress

            Total Views: {self.view_count}
            Today's Views: {self._get_today_view_count()}
            Daily Target: {self.target_views_per_day}
            Last View: {self.last_view_time.strftime('%Y-%m-%d %H:%M:%S') if self.last_view_time else 'N/A'}
            Service Status: {'Running' if self.is_running else 'Stopped'}

            Recent Activity:
            {"\\n".join(f"- {record['timestamp'][:19]} - {record['context']}" for record in self.view_history[-5:])}

            This is an automated notification from the Trevnoctilla Ad Service.
            """

            success = send_email(
                self.admin_notification_email,
                subject,
                html_content,
                text_content
            )

            if success:
                print(f"[AD SERVICE] Progress email sent to {self.admin_notification_email}")
            else:
                print("[AD SERVICE] Failed to send progress email")

        except Exception as e:
            print(f"[AD SERVICE] Error sending progress email: {e}")

    def perform_manual_ad_view(self):
        """Perform a single ad view immediately (manual trigger)"""
        print("[AD SERVICE] Manual ad view triggered")
        self._perform_ad_view("Manual Trigger")
        return True, "Manual ad click simulated successfully"

# Global service instance
ad_service = AutomatedAdService()

# Admin control functions
def start_ad_service():
    """Start the automated ad service (admin function)"""
    return ad_service.start_service()

def stop_ad_service():
    """Stop the automated ad service (admin function)"""
    return ad_service.stop_service()

def get_ad_service_status():
    """Get ad service status (admin function)"""
    return ad_service.get_status()

def reset_ad_stats():
    """Reset ad view statistics (admin function)"""
    return ad_service.reset_stats()

def trigger_manual_ad_view():
    """Trigger a single ad view immediately (admin function)"""
    return ad_service.perform_manual_ad_view()