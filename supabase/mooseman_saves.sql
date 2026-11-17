-- MOOSE MAN cloud saves: your progress follows your account to every device.
-- Run this once in the Supabase SQL editor (after mooseman_accounts.sql).

create table if not exists public.mooseman_saves (
    user_id     uuid primary key default auth.uid() references auth.users (id) on delete cascade,
    data        jsonb not null default '{}'::jsonb,
    updated_at  timestamptz not null default now()
);

alter table public.mooseman_saves enable row level security;

-- each player can only see and change their own save
drop policy if exists "read own mooseman save" on public.mooseman_saves;
create policy "read own mooseman save" on public.mooseman_saves
    for select using (auth.uid() = user_id);

drop policy if exists "add own mooseman save" on public.mooseman_saves;
create policy "add own mooseman save" on public.mooseman_saves
    for insert with check (auth.uid() = user_id);

drop policy if exists "change own mooseman save" on public.mooseman_saves;
create policy "change own mooseman save" on public.mooseman_saves
    for update using (auth.uid() = user_id) with check (auth.uid() = user_id);
