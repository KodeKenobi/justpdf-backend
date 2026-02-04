-- Guest sessions: map stable cookie id -> backend session_id for campaign list recovery
-- Run this in Supabase SQL Editor (Dashboard -> SQL Editor)
--
-- Next.js needs: SUPABASE_SERVICE_ROLE_KEY in .env.local (same project Supabase;
-- get from Supabase Dashboard -> Settings -> API -> service_role secret)

create table if not exists public.guest_sessions (
  stable_id text primary key,
  session_id text not null,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

alter table public.guest_sessions enable row level security;

create policy "Allow service role full access"
  on public.guest_sessions
  for all
  using (true)
  with check (true);

-- Optional: index for lookups by session_id if you ever need reverse lookup
create index if not exists idx_guest_sessions_session_id on public.guest_sessions(session_id);

comment on table public.guest_sessions is 'Maps guest_stable_id (cookie) to backend session_id for campaign list recovery when localStorage is cleared';
