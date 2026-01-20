"""
Automated Database Backup Service
Runs daily backups at 12am and 12pm, compresses them, and sends email notifications
"""
import os
import gzip
import shutil
import subprocess
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime, timedelta
import threading
import time
from pathlib import Path
from flask import Flask
from database import db

class BackupService:
    def __init__(self):
        self.backup_dir = Path("backups")
        self.backup_dir.mkdir(exist_ok=True)

        # Get database config from environment
        self.db_host = os.getenv('DB_HOST', 'localhost')
        self.db_name = os.getenv('DB_NAME', 'postgres')
        self.db_user = os.getenv('DB_USER', 'postgres')
        self.db_password = os.getenv('DB_PASSWORD', '')
        self.db_port = os.getenv('DB_PORT', '5432')

        # Email config
        self.smtp_server = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
        self.smtp_port = int(os.getenv('SMTP_PORT', '587'))
        self.smtp_username = os.getenv('SMTP_USERNAME', '')
        self.smtp_password = os.getenv('SMTP_PASSWORD', '')
        self.backup_notification_email = os.getenv('BACKUP_NOTIFICATION_EMAIL', 'admin@trevnoctilla.com')

    def create_backup(self):
        """Create a compressed database backup"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_filename = f"trevnoctilla_backup_{timestamp}.sql"
            compressed_filename = f"{backup_filename}.gz"

            backup_path = self.backup_dir / backup_filename
            compressed_path = self.backup_dir / compressed_filename

            print(f"[BACKUP] Creating backup: {backup_filename}")

            # Create pg_dump command
            dump_cmd = [
                'pg_dump',
                '--host', self.db_host,
                '--port', self.db_port,
                '--username', self.db_user,
                '--dbname', self.db_name,
                '--no-password',
                '--format', 'plain',
                '--file', str(backup_path),
                '--compress', '0'  # No compression in pg_dump, we'll compress later
            ]

            # Set PGPASSWORD environment variable
            env = os.environ.copy()
            env['PGPASSWORD'] = self.db_password

            # Run pg_dump
            result = subprocess.run(
                dump_cmd,
                env=env,
                capture_output=True,
                text=True
            )

            if result.returncode != 0:
                raise Exception(f"pg_dump failed: {result.stderr}")

            # Compress the backup
            print(f"[BACKUP] Compressing backup...")
            with open(backup_path, 'rb') as f_in:
                with gzip.open(compressed_path, 'wb', compresslevel=9) as f_out:
                    shutil.copyfileobj(f_in, f_out)

            # Remove uncompressed file
            backup_path.unlink()

            compressed_size = compressed_path.stat().st_size / (1024 * 1024)  # Size in MB
            print(".1f"
            return compressed_path, compressed_size

        except Exception as e:
            print(f"[BACKUP ERROR] Failed to create backup: {e}")
            raise

    def send_backup_email(self, backup_path: Path, backup_size: float, backup_time: datetime):
        """Send backup notification email with attachment"""
        try:
            # Create message
            msg = MIMEMultipart()
            msg['From'] = self.smtp_username
            msg['To'] = self.backup_notification_email
            msg['Subject'] = f'Trevnoctilla Database Backup - {backup_time.strftime("%Y-%m-%d %H:%M")}'

            # Email body
            body = f"""
Trevnoctilla Database Backup Completed

Backup Details:
- Date/Time: {backup_time.strftime("%Y-%m-%d %H:%M:%S")}
- File: {backup_path.name}
- Size: {backup_size:.1f} MB
- Location: {backup_path.absolute()}

This backup contains all database data including:
- User accounts and profiles
- Campaign data and analytics
- API keys and usage statistics
- All application data

Please store this backup securely.

Trevnoctilla Backup Service
            """

            msg.attach(MIMEText(body, 'plain'))

            # Attach backup file (if it's small enough)
            if backup_size < 25:  # Only attach if under 25MB
                with open(backup_path, 'rb') as attachment:
                    part = MIMEBase('application', 'octet-stream')
                    part.set_payload(attachment.read())
                    encoders.encode_base64(part)
                    part.add_header('Content-Disposition', f"attachment; filename= {backup_path.name}")
                    msg.attach(part)
            else:
                # For large backups, just notify about location
                body += f"\n\nNote: Backup file is {backup_size:.1f}MB and was not attached. Please download from server at: {backup_path}"

            # Send email
            server = smtplib.SMTP(self.smtp_server, self.smtp_port)
            server.starttls()
            server.login(self.smtp_username, self.smtp_password)
            text = msg.as_string()
            server.sendmail(self.smtp_username, self.backup_notification_email, text)
            server.quit()

            print(f"[BACKUP] Email sent to {self.backup_notification_email}")

        except Exception as e:
            print(f"[BACKUP ERROR] Failed to send email: {e}")
            raise

    def run_backup_cycle(self):
        """Run a complete backup cycle"""
        try:
            print("=" * 60)
            print("STARTING TREVNOCTILLA DATABASE BACKUP")
            print("=" * 60)

            backup_time = datetime.now()

            # Create backup
            backup_path, backup_size = self.create_backup()

            # Send email notification
            self.send_backup_email(backup_path, backup_size, backup_time)

            # Clean up old backups (keep last 30 days)
            self.cleanup_old_backups()

            print("=" * 60)
            print("BACKUP COMPLETED SUCCESSFULLY")
            print("=" * 60)

        except Exception as e:
            print(f"[BACKUP ERROR] Backup cycle failed: {e}")
            # Send failure notification
            try:
                self.send_failure_email(str(e), datetime.now())
            except:
                pass

    def cleanup_old_backups(self, days_to_keep=30):
        """Remove backups older than specified days"""
        try:
            cutoff_time = time.time() - (days_to_keep * 24 * 60 * 60)

            for backup_file in self.backup_dir.glob("*.gz"):
                if backup_file.stat().st_mtime < cutoff_time:
                    backup_file.unlink()
                    print(f"[BACKUP] Removed old backup: {backup_file.name}")

        except Exception as e:
            print(f"[BACKUP ERROR] Failed to cleanup old backups: {e}")

    def send_failure_email(self, error_message: str, failure_time: datetime):
        """Send failure notification email"""
        try:
            msg = MIMEMultipart()
            msg['From'] = self.smtp_username
            msg['To'] = self.backup_notification_email
            msg['Subject'] = f'❌ Trevnoctilla Backup FAILED - {failure_time.strftime("%Y-%m-%d %H:%M")}'

            body = f"""
❌ Trevnoctilla Database Backup FAILED

Failure Time: {failure_time.strftime("%Y-%m-%d %H:%M:%S")}
Error: {error_message}

Please check the server logs and investigate the issue.

Trevnoctilla Backup Service
            """

            msg.attach(MIMEText(body, 'plain'))

            server = smtplib.SMTP(self.smtp_server, self.smtp_port)
            server.starttls()
            server.login(self.smtp_username, self.smtp_password)
            server.sendmail(self.smtp_username, self.backup_notification_email, msg.as_string())
            server.quit()

            print(f"[BACKUP] Failure email sent to {self.backup_notification_email}")

        except Exception as e:
            print(f"[BACKUP ERROR] Failed to send failure email: {e}")

# Global backup service instance
backup_service = BackupService()

def schedule_daily_backups():
    """Schedule daily backups at 12am and 12pm"""
    def backup_worker():
        while True:
            now = datetime.now()

            # Calculate seconds until next backup (12am or 12pm)
            if now.hour < 12:
                # Next backup is 12pm today
                next_backup = now.replace(hour=12, minute=0, second=0, microsecond=0)
            else:
                # Next backup is 12am tomorrow
                next_backup = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)

            seconds_until_backup = (next_backup - now).total_seconds()

            print(f"[BACKUP] Next backup scheduled for {next_backup.strftime('%Y-%m-%d %H:%M:%S')} ({seconds_until_backup:.0f} seconds)")

            # Sleep until next backup
            time.sleep(seconds_until_backup)

            # Run backup
            try:
                backup_service.run_backup_cycle()
            except Exception as e:
                print(f"[BACKUP ERROR] Backup cycle failed: {e}")

            # Sleep a bit to avoid immediate retry on failure
            time.sleep(60)

    # Start backup worker in background thread
    backup_thread = threading.Thread(target=backup_worker, daemon=True)
    backup_thread.start()
    print("[BACKUP] Daily backup scheduler started")

# Manual backup function for admin use
def run_manual_backup():
    """Run a backup manually (for admin use)"""
    try:
        backup_service.run_backup_cycle()
        return True, "Backup completed successfully"
    except Exception as e:
        return False, str(e)