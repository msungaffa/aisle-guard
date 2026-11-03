-- aisle_events: ESP32가 Supabase REST(/rest/v1/aisle_events)로 한 줄씩 넣는 이벤트 로그
-- anon 키에는 insert만 허용한다(읽기·수정·삭제 불가). 조회는 대시보드(SQL 편집기)나 service_role로 한다.

create table if not exists public.aisle_events (
  id            bigint generated always as identity primary key,
  device_id     text        not null,
  event         text        not null check (event in ('warning', 'cleared', 'heartbeat')),
  started_at    timestamptz,
  ended_at      timestamptz,
  dwell_s       real        check (dwell_s is null or dwell_s >= 0),
  max_conf      real        check (max_conf is null or (max_conf >= 0 and max_conf <= 1)),
  fw_version    text,
  model_version text,
  created_at    timestamptz not null default now()
);

create index if not exists aisle_events_created_at_idx on public.aisle_events (created_at desc);

alter table public.aisle_events enable row level security;

revoke all on public.aisle_events from anon, authenticated;
grant insert on public.aisle_events to anon;

create policy "anon can insert events" on public.aisle_events
  for insert to anon
  with check (true);
