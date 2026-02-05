# Logging in as enterprise when testing locally

The app decides you are "enterprise" using **backend** user data:

- **role** = `admin` → frontend redirects you to `/enterprise`
- **subscription_tier** = `enterprise` and **monthly_call_limit** = `-1` → same

That data comes from the **same database your local backend uses** (NextAuth calls `/auth/login`; profile and get-token use that DB). If your local DB has that user as `role='user'` and `subscription_tier='free'`, you will never be treated as enterprise.

## Fix: set your test user to enterprise in the local DB

From `trevnoctilla-backend` (with the same `.env` as when you run the backend):

```bash
# Use default email (tshepomtshali89@gmail.com)
python set_enterprise_user.py

# Or specify email
python set_enterprise_user.py your@email.com
```

This sets that user to `role=admin`, `subscription_tier=enterprise`, `monthly_call_limit=-1`. Then log in again (or refresh after login) so the frontend gets the updated user; you should be redirected to the enterprise dashboard.

## Checklist when enterprise login fails locally

1. **Backend and DB** – You’re running the backend locally and it’s using the DB you expect (check `DATABASE_URL` / `SUPABASE_DATABASE_URL` in `trevnoctilla-backend/.env`).
2. **Frontend backend URL** – In the Next.js app, `BACKEND_URL` should point at your local backend when testing (e.g. `BACKEND_URL=http://localhost:5000` in `.env.local`).
3. **User row** – The user you log in with exists in that DB and has been set to enterprise (run `set_enterprise_user.py` as above).
4. **Fresh login** – After changing the user in the DB, log out and log in again (or at least wait for profile/context to refresh) so the UI sees the new role/tier.
