-- MOOSE MAN accounts. Run this once in the Supabase SQL editor.
--
-- Players sign up with a username + password. Supabase Auth needs an email,
-- so the game makes one from the username (<name>@players.moosemangame.com);
-- nothing is ever sent to it. Turn OFF "Confirm email" under
-- Authentication -> Sign In / Providers -> Email, or new accounts can't log in.
--
-- To make someone an admin (Table Editor works too):
--   update public.mooseman_profiles set is_admin = true where username = 'TheirName';

create table if not exists public.mooseman_profiles (
    id          uuid primary key references auth.users (id) on delete cascade,
    username    text not null unique,
    is_admin    boolean not null default false,
    created_at  timestamptz not null default now()
);

alter table public.mooseman_profiles enable row level security;

-- a player can read their own row (that's how the game learns is_admin) ...
drop policy if exists "read own mooseman profile" on public.mooseman_profiles;
create policy "read own mooseman profile" on public.mooseman_profiles
    for select using (auth.uid() = id);
-- ... and there are no insert/update/delete policies: nobody can make themselves
-- an admin from the game. Rows are created by the trigger below.

create or replace function public.mooseman_new_user()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
    -- only accounts made by Moose Man carry a username; other games' users are left alone
    if new.raw_user_meta_data ? 'mm_username' then
        insert into public.mooseman_profiles (id, username)
        values (new.id, new.raw_user_meta_data ->> 'mm_username')
        on conflict (id) do nothing;
    end if;
    return new;
end;
$$;

drop trigger if exists mooseman_on_auth_user_created on auth.users;
create trigger mooseman_on_auth_user_created
    after insert on auth.users
    for each row execute function public.mooseman_new_user();
