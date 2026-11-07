-- On Target: leaderboards.
-- Paste all of this into Supabase > SQL Editor > New query, then press Run.
-- Safe to run more than once. (Supabase may warn about "destructive operations": that's the
-- "drop ... if exists" lines, which only replace older copies of these same rules.)

-- One row per player, per board, per day: their best that day (the daily challenge keeps the first go only).
--   game: 'daily' (Hit the Target daily), 'solo5' (Hit the Target solo, 5 rounds),
--         'hl_easy' / 'hl_hard' (Higher or Lower streaks)
create table if not exists public.scores (
  user_id uuid not null references public.profiles(id) on delete cascade,
  game text not null check (game in ('daily', 'solo5', 'hl_easy', 'hl_hard')),
  day date not null,
  score int not null,
  detail jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  primary key (user_id, game, day),
  constraint detail_size check (pg_column_size(detail) < 8192)
);
create index if not exists scores_board on public.scores (game, day, score desc);

alter table public.scores enable row level security;
drop policy if exists "scores are public" on public.scores;
create policy "scores are public" on public.scores for select using (true);
grant select on public.scores to anon, authenticated;
-- No insert/update grants: scores only arrive through submit_score below, which checks them.

-- UK date: "today" on the leaderboards runs midnight to midnight UK time.
create or replace function public.uk_today() returns date
language sql stable as $$ select (now() at time zone 'Europe/London')::date $$;

create or replace function public.submit_score(p_game text, p_score int, p_day date default null, p_detail jsonb default '{}'::jsonb)
returns text
language plpgsql security definer set search_path = public as $$
declare
  uid uuid := auth.uid();
  d date := coalesce(p_day, public.uk_today());
begin
  if uid is null then raise exception 'Sign in first.'; end if;
  if not exists (select 1 from profiles where id = uid) then raise exception 'Pick a username first.'; end if;
  if p_game not in ('daily', 'solo5', 'hl_easy', 'hl_hard') then raise exception 'Unknown game.'; end if;
  -- Possible scores: 5 rounds of -20..30 for Hit the Target; streaks for Higher or Lower.
  if p_game in ('daily', 'solo5') and (p_score < -100 or p_score > 150) then raise exception 'Score out of range.'; end if;
  if p_game in ('hl_easy', 'hl_hard') and (p_score < 0 or p_score > 1000) then raise exception 'Score out of range.'; end if;
  if p_game = 'daily' then
    -- The daily is numbered by the player's own date, so allow a day either side for time zones.
    if d < public.uk_today() - 1 or d > public.uk_today() + 1 then raise exception 'That daily has closed.'; end if;
    insert into scores (user_id, game, day, score, detail) values (uid, p_game, d, p_score, p_detail)
      on conflict (user_id, game, day) do nothing;
  else
    d := public.uk_today();
    insert into scores (user_id, game, day, score, detail) values (uid, p_game, d, p_score, p_detail)
      on conflict (user_id, game, day) do update
        set score = excluded.score, detail = excluded.detail, created_at = now()
        where excluded.score > scores.score;
  end if;
  return 'ok';
end $$;
revoke all on function public.submit_score(text, int, date, jsonb) from public, anon;
grant execute on function public.submit_score(text, int, date, jsonb) to authenticated;

-- A board: top 50, plus your own row if you're further down.
--   p_period: 'today' or 'all'. p_day: which daily (defaults to UK today).
--   All-time: the daily board adds up every daily score (so turning up every day counts);
--   the others show each player's best ever.
create or replace function public.leaderboard(p_game text, p_period text, p_day date default null)
returns table (rank bigint, username text, badge text, score bigint, games bigint, is_me boolean)
language sql stable security definer set search_path = public as $$
  with rows as (
    select s.user_id,
           case when p_game = 'daily' and p_period = 'all' then sum(s.score) else max(s.score) end as score,
           count(*) as games,
           min(s.created_at) as first_at
    from scores s
    where s.game = p_game
      and (p_period = 'all' or s.day = coalesce(p_day, public.uk_today()))
    group by s.user_id
  ), ranked as (
    select rank() over (order by r.score desc) as rank, p.username, p.badge, r.score, r.games,
           (r.user_id = auth.uid()) as is_me,
           row_number() over (order by r.score desc, r.first_at) as pos
    from rows r join profiles p on p.id = r.user_id
  )
  select rank, username, badge, score, games, is_me from ranked
  where pos <= 50 or is_me
  order by pos
$$;
grant execute on function public.leaderboard(text, text, date) to anon, authenticated;
