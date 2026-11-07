-- On Target, Phase 1: accounts.
-- Paste all of this into Supabase > SQL Editor > New query, then press Run.
-- Safe to run more than once.

-- One row per player. Only the username and badge are public; the email stays in Supabase's own auth tables.
create table if not exists public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  username text not null,
  badge text not null default '⚽',
  searchable boolean not null default true,
  created_at timestamptz not null default now(),
  username_changed_at timestamptz not null default now(),
  constraint username_format check (username ~ '^[A-Za-z0-9_]{3,15}$'),
  constraint badge_size check (char_length(badge) between 1 and 8)
);
create unique index if not exists profiles_username_lower on public.profiles (lower(username));

-- Each player's saved stats (solo bests, daily streak, Higher or Lower bests) as one JSON blob.
create table if not exists public.player_stats (
  user_id uuid primary key references public.profiles(id) on delete cascade,
  data jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now(),
  constraint stats_size check (pg_column_size(data) < 65536)
);

-- Usernames: no offensive words, and a change at most once every 30 days.
create or replace function public.username_ok(u text) returns boolean
language sql immutable as $$
  select not exists (
    select 1 from unnest(array['fuck','shit','cunt','nigg','fag','bitch','whore','slut','rape','nazi','hitler',
                               'retard','twat','wank','pussy','porn','penis','vagina','admin','ontarget']) w
    where position(w in lower(replace(u, '_', ''))) > 0)
$$;

create or replace function public.profiles_guard() returns trigger
language plpgsql as $$
begin
  if not public.username_ok(new.username) then
    raise exception 'That username isn''t allowed. Try another.';
  end if;
  if tg_op = 'INSERT' then
    new.created_at := now();
    new.username_changed_at := now();
    return new;
  end if;
  new.id := old.id;
  new.created_at := old.created_at;
  if lower(new.username) <> lower(old.username) then
    if old.username_changed_at > now() - interval '30 days' then
      raise exception 'You can change your username once every 30 days.';
    end if;
    new.username_changed_at := now();
  else
    new.username_changed_at := old.username_changed_at;
  end if;
  return new;
end $$;

drop trigger if exists profiles_guard on public.profiles;
create trigger profiles_guard before insert or update on public.profiles
  for each row execute function public.profiles_guard();

create or replace function public.stats_touch() returns trigger
language plpgsql as $$ begin new.updated_at := now(); return new; end $$;
drop trigger if exists stats_touch on public.player_stats;
create trigger stats_touch before insert or update on public.player_stats
  for each row execute function public.stats_touch();

-- Security rules: anyone can see usernames and badges; only you can change your own profile and stats.
alter table public.profiles enable row level security;
alter table public.player_stats enable row level security;

drop policy if exists "profiles are public" on public.profiles;
create policy "profiles are public" on public.profiles for select using (true);
drop policy if exists "make your own profile" on public.profiles;
create policy "make your own profile" on public.profiles for insert to authenticated
  with check (id = (select auth.uid()));
drop policy if exists "edit your own profile" on public.profiles;
create policy "edit your own profile" on public.profiles for update to authenticated
  using (id = (select auth.uid())) with check (id = (select auth.uid()));

drop policy if exists "your own stats" on public.player_stats;
create policy "your own stats" on public.player_stats for all to authenticated
  using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));

grant select on public.profiles to anon, authenticated;
grant insert, update on public.profiles to authenticated;
grant select, insert, update on public.player_stats to authenticated;

-- Tiny table the weekly keep-alive job reads, so the free project never pauses for inactivity.
create table if not exists public.heartbeat (id int primary key, note text);
insert into public.heartbeat values (1, 'keep-alive') on conflict (id) do nothing;
alter table public.heartbeat enable row level security;
drop policy if exists "heartbeat is public" on public.heartbeat;
create policy "heartbeat is public" on public.heartbeat for select using (true);
grant select on public.heartbeat to anon, authenticated;
