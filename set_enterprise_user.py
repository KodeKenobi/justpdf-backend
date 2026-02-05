#!/usr/bin/env python3
"""
Set an existing user to enterprise for local testing.
The app treats you as enterprise when the backend user has:
  - role='admin' (frontend redirects admin -> /enterprise), and/or
  - subscription_tier='enterprise' and monthly_call_limit=-1.

Run from trevnoctilla-backend with the same .env as your running backend
(so it uses the same database).

Usage:
  python set_enterprise_user.py
  python set_enterprise_user.py someone@example.com
"""
import sys
import os

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

# Default: same email as scripts/mimic-user-process-10.js
DEFAULT_EMAIL = "tshepomtshali89@gmail.com"


def set_enterprise_user(email: str) -> bool:
    from flask import Flask
    from database import db, init_db
    from models import User

    app = Flask(__name__)
    init_db(app)

    with app.app_context():
        try:
            db.create_all()
            email_clean = email.strip().lower()
            user = User.query.filter_by(email=email_clean).first()
            if not user:
                # Case-insensitive fallback
                for u in User.query.all():
                    if u.email.lower().strip() == email_clean:
                        user = u
                        break
            if not user:
                print(f"[ERROR] User not found: {email}")
                print("  Existing emails:", [u.email for u in User.query.all()])
                return False

            old_role = user.role
            old_tier = user.subscription_tier
            old_limit = user.monthly_call_limit

            user.role = "admin"
            user.subscription_tier = "enterprise"
            user.monthly_call_limit = -1
            user.is_active = True
            db.session.commit()

            print(f"[OK] User set to enterprise: {user.email}")
            print(f"     role: {old_role} -> {user.role}")
            print(f"     subscription_tier: {old_tier} -> {user.subscription_tier}")
            print(f"     monthly_call_limit: {old_limit} -> {user.monthly_call_limit}")
            print("  Log in again (or refresh after login) to see enterprise dashboard.")
            return True
        except Exception as e:
            db.session.rollback()
            print(f"[ERROR] {e}")
            import traceback
            traceback.print_exc()
            return False


if __name__ == "__main__":
    email = (sys.argv[1] if len(sys.argv) > 1 else os.getenv("ENTERPRISE_TEST_EMAIL", DEFAULT_EMAIL))
    ok = set_enterprise_user(email)
    sys.exit(0 if ok else 1)
