-- On Target: head-to-head records against other players.
-- Paste all of this into Supabase > SQL Editor > New query, then press Run.
-- Safe to run more than once. (Supabase may warn about "destructive operations": that's the
-- "drop ... if exists" lines, which only replace older copies of these same rules.)

-- One row per player per online match, from that player's side. Each player saves their own
-- result, so nobody can write into anyone else's record.
create table if not exists public.h2h_results (
  user_id uuid not null references public.profiles(id) on delete cascade,
  opp_id uuid not null references public.profiles(id) on delete cascade,
  match_key text not null check (char_length(match_key) between 3 and 40),
  kind text not null check (kind in ('live', 'turns')),
  my_pts int not null,
  opp_pts int not null,
  rounds int not null check (rounds between 1 and 10),
  created_at timestamptz not null default now(),
  primary key (user_id, match_key)
);
create index if not exists h2h_by_opp on public.h2h_results (user_id, opp_id, created_at desc);

alter table public.h2h_results enable row level security;
drop policy if exists "your own results" on public.h2h_results;
create policy "your own results" on public.h2h_results for select to authenticated using (user_id = (select auth.uid()));
grant select on public.h2h_results to authenticated;

create or replace function public.record_result(p_opp uuid, p_key text, p_kind text, p_my int, p_opp_pts int, p_rounds int)
returns text
language plpgsql security definer set search_path = public as $$
declare uid uuid := auth.uid();
begin
  if uid is null then raise exception 'Sign in first.'; end if;
  if p_opp = uid then raise exception 'You can''t play yourself.'; end if;
  if not exists (select 1 from profiles where id = uid) or not exists (select 1 from profiles where id = p_opp) then
    raise exception 'Both players need an account.';
  end if;
  if p_rounds < 1 or p_rounds > 10 or abs(p_my) > 30 * p_rounds or abs(p_opp_pts) > 30 * p_rounds then
    raise exception 'Score out of range.';
  end if;
  insert into h2h_results (user_id, opp_id, match_key, kind, my_pts, opp_pts, rounds)
    values (uid, p_opp, p_key, p_kind, p_my, p_opp_pts, p_rounds)
    on conflict (user_id, match_key) do nothing;
  return 'ok';
end $$;
revoke all on function public.record_result(uuid, text, text, int, int, int) from public, anon;
grant execute on function public.record_result(uuid, text, text, int, int, int) to authenticated;

-- Your record against everyone you've played, most recent first.
create or replace function public.my_rivals()
returns table (opp_id uuid, username text, badge text, played bigint, wins bigint, draws bigint, losses bigint,
               my_total bigint, opp_total bigint, last_played timestamptz)
language sql stable security definer set search_path = public as $$
  select r.opp_id, p.username, p.badge, count(*),
         count(*) filter (where r.my_pts > r.opp_pts), count(*) filter (where r.my_pts = r.opp_pts),
         count(*) filter (where r.my_pts < r.opp_pts), sum(r.my_pts), sum(r.opp_pts), max(r.created_at)
  from h2h_results r join profiles p on p.id = r.opp_id
  where r.user_id = auth.uid()
  group by r.opp_id, p.username, p.badge
  order by max(r.created_at) desc
  limit 100
$$;
grant execute on function public.my_rivals() to authenticated;
