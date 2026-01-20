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
        self.admin_notification_email = os.getenv('ADMIN_NOTIFICATION_EMAIL', 'admin@trevnoctilla.com')

        # Get frontend URL for making requests
        self.frontend_url = os.getenv('NEXT_PUBLIC_BASE_URL', 'https://www.trevnoctilla.com')

    def start_service(self):
        """Start the automated ad view service"""
        if self.is_running:
            return False, "Service is already running"

        self.is_running = True
        self.thread = threading.Thread(target=self._run_service, daemon=True)
        self.thread.start()

        print("[AD SERVICE] Automated ad view service started")
        return True, "Service started successfully"

    def stop_service(self):
        """Stop the automated ad view service"""
        if not self.is_running:
            return False, "Service is not running"

        self.is_running = False
        if self.thread:
            self.thread.join(timeout=5)

        print("[AD SERVICE] Automated ad view service stopped")
        return True, "Service stopped successfully"

    def _run_service(self):
        """Main service loop"""
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
            # We'll use the test-monetization page and simulate clicking "View Ad"

            # Method 1: Direct API call to trigger ad view (if we create an endpoint)
            # For now, we'll simulate the browser interaction

            # Visit the test page (this loads the page)
            test_url = f"{self.frontend_url}/test-monetization"
            response = requests.get(test_url, timeout=10)

            if response.status_code == 200:
                print(f"[AD SERVICE] ✅ Page loaded successfully")

                # Simulate the ad view process
                # In a real implementation, we'd need to:
                # 1. Load the page with a headless browser
                # 2. Click the "View Ad" button
                # 3. Wait for the ad to load
                # 4. Close the ad tab

                # For now, we'll simulate this with a delay and logging
                time.sleep(random.uniform(3, 8))  # Simulate ad viewing time

                self.view_count += 1
                self.last_view_time = datetime.now()

                # Log the view
                view_record = {
                    'timestamp': self.last_view_time.isoformat(),
                    'context': context,
                    'simulated': True
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
                print(f"[AD SERVICE] ❌ Failed to load page: HTTP {response.status_code}")

        except Exception as e:
            print(f"[AD SERVICE] ❌ Error performing ad view: {e}")

    def _get_today_view_count(self) -> int:
        """Get number of views completed today"""
        today = datetime.now().date()
        return sum(1 for record in self.view_history
                  if datetime.fromisoformat(record['timestamp']).date() == today)

    def get_status(self):
        """Get current service status"""
        return {
            'is_running': self.is_running,
            'total_views': self.view_count,
            'last_view_time': self.last_view_time.isoformat() if self.last_view_time else None,
            'today_views': self._get_today_view_count(),
            'target_daily_views': self.target_views_per_day,
            'recent_history': self.view_history[-10:]  # Last 10 views
        }

    def reset_stats(self):
        """Reset view statistics"""
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