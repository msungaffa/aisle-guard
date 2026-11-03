-- aisle_events 품질 지표 조회 (Supabase SQL 편집기에서 실행, 시간은 Asia/Seoul)
-- 이벤트 모양 (logic.cpp / aisle_cam.ino):
--   warning   : 점유가 DWELL_T(10초)를 넘은 순간 1건. started_at = 점유 시작, dwell_s ≈ 10
--   cleared   : 경고 뒤 해제될 때 1건. started_at 같음, ended_at = 해제, dwell_s = 전체 방치 시간
--   heartbeat : 1분마다 1건 (장치 살아 있음)
-- 같은 방치의 warning과 cleared는 (device_id, started_at)으로 묶인다. 시계 오차로 1초 안쪽이 다를 수 있어 ±2초로 맞춘다.
-- 시험 행은 device_id = 'setup-test'라 모든 조회에서 뺀다.

-- 0) 오경보 표시용 표 (한 번만 실행). anon에는 권한을 주지 않는다 — 사람이 SQL 편집기에서만 표시한다.
--    aisle_events는 장치가 쓰는 원본이라 고치지 않고, 판정은 따로 둔다.
create table if not exists public.aisle_event_reviews (
  event_id    bigint primary key references public.aisle_events (id) on delete cascade,
  verdict     text not null check (verdict in ('true_alarm', 'false_alarm')),
  note        text,
  reviewed_at timestamptz not null default now()
);
alter table public.aisle_event_reviews enable row level security;
revoke all on public.aisle_event_reviews from anon, authenticated;

-- 오경보 표시 예: 시연 정답(demo_truth.json)에 없는 경고, 또는 사람을 상자로 본 경고
-- insert into public.aisle_event_reviews (event_id, verdict, note)
-- values (42, 'false_alarm', '사람이 서 있던 구간')
-- on conflict (event_id) do update set verdict = excluded.verdict, note = excluded.note, reviewed_at = now();

-- 1) 시간대별 경고 횟수 (최근 7일, 한 시간 단위)
select date_trunc('hour', coalesce(started_at, created_at) at time zone 'Asia/Seoul') as hour_kst,
       device_id,
       count(*) as warnings
from public.aisle_events
where event = 'warning'
  and device_id <> 'setup-test'
  and created_at > now() - interval '7 days'
group by 1, 2
order by 1 desc, 2;

-- 2) 하루 단위 방치 시간: 해제 건수, 평균·최대 방치(초)
select date_trunc('day', ended_at at time zone 'Asia/Seoul')::date as day_kst,
       device_id,
       count(*)                      as cleared,
       round(avg(dwell_s)::numeric, 1) as avg_dwell_s,
       round(max(dwell_s)::numeric, 1) as max_dwell_s
from public.aisle_events
where event = 'cleared'
  and device_id <> 'setup-test'
group by 1, 2
order by 1 desc, 2;

-- 3) 경고-해제 짝: 아직 해제되지 않은 경고(진행 중)와 각 방치 시간
select w.id as warning_id, w.device_id,
       w.started_at at time zone 'Asia/Seoul' as started_kst,
       c.ended_at   at time zone 'Asia/Seoul' as cleared_kst,
       c.dwell_s,
       case when c.id is null then 'open' else 'cleared' end as state
from public.aisle_events w
left join lateral (
  select c.* from public.aisle_events c
  where c.event = 'cleared'
    and c.device_id = w.device_id
    and abs(extract(epoch from c.started_at - w.started_at)) <= 2
  order by c.id
  limit 1
) c on true
where w.event = 'warning'
  and w.device_id <> 'setup-test'
order by w.id desc
limit 50;

-- 4) 장치별 마지막 heartbeat와 끊김 여부 (heartbeat 1분 간격, 3분 넘게 없으면 offline)
select device_id,
       max(created_at) at time zone 'Asia/Seoul' as last_seen_kst,
       (select model_version from public.aisle_events e2
        where e2.device_id = e.device_id order by id desc limit 1) as model_version,
       case when max(created_at) < now() - interval '3 minutes' then 'offline' else 'online' end as status
from public.aisle_events e
where event = 'heartbeat'
  and device_id <> 'setup-test'
group by device_id
order by last_seen_kst desc;

-- 5) 오경보 비율: 표시한 경고 중 false_alarm 비율, 아직 표시 안 한 경고 수
select count(*) filter (where r.verdict = 'false_alarm') as false_alarms,
       count(*) filter (where r.verdict = 'true_alarm')  as true_alarms,
       count(*) filter (where r.event_id is null)       as unreviewed,
       round(100.0 * count(*) filter (where r.verdict = 'false_alarm')
             / nullif(count(r.event_id), 0), 1)          as false_alarm_pct
from public.aisle_events w
left join public.aisle_event_reviews r on r.event_id = w.id
where w.event = 'warning'
  and w.device_id <> 'setup-test';

-- 6) 모델 버전별 경고 수·평균 신뢰도 (모델을 바꾼 뒤 비교용)
select model_version,
       count(*) as warnings,
       round(avg(max_conf)::numeric, 3) as avg_max_conf
from public.aisle_events
where event = 'warning'
  and device_id <> 'setup-test'
group by model_version
order by model_version;
