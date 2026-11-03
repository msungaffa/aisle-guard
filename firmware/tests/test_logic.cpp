// logic 모듈 단위 시험 (PC g++). 실행: powershell -File firmware/tests/run_tests.ps1
#include <cstdio>
#include <cstring>
#include <string>

#include "logic.h"

static int failures = 0;
#define CHECK(cond)                                                    \
  do {                                                                 \
    if (!(cond)) {                                                     \
      std::printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #cond);      \
      failures++;                                                      \
    }                                                                  \
  } while (0)

// 시험용 통로: 96×96 화면 가운데 세로 띠 (x 30~66, y 10~90) 사각형
static LogicConfig cfg() {
  LogicConfig c;
  c.aisle_n = 4;
  c.aisle_x[0] = 30; c.aisle_y[0] = 10;
  c.aisle_x[1] = 66; c.aisle_y[1] = 10;
  c.aisle_x[2] = 66; c.aisle_y[2] = 90;
  c.aisle_x[3] = 30; c.aisle_y[3] = 90;
  return c;  // 나머지는 기본값: CONF_MIN 0.6, 6/4, 해제 1, 10초, 사람 반경 16
}

static Detection obs(float x, float y, float conf = 0.9f) { return {LABEL_OBSTACLE, x, y, conf}; }
static Detection per(float x, float y, float conf = 0.9f) { return {LABEL_PERSON, x, y, conf}; }

static void test_defaults_match_prd() {
  LogicConfig c;
  CHECK(c.conf_min == 0.6f);
  CHECK(c.win_n == 6);
  CHECK(c.win_k == 4);
  CHECK(c.clear_k == 1);
  CHECK(c.dwell_ms == 10000u);
}

static void test_point_in_aisle() {
  LogicConfig c = cfg();
  CHECK(logic_in_aisle(c, 48, 50));
  CHECK(!logic_in_aisle(c, 10, 50));   // 왼쪽 밖
  CHECK(!logic_in_aisle(c, 80, 50));   // 오른쪽 밖
  CHECK(!logic_in_aisle(c, 48, 95));   // 아래 밖
  // 사다리꼴(원근)도 된다
  LogicConfig t = c;
  t.aisle_x[0] = 40; t.aisle_x[1] = 56;  // 위쪽이 좁다
  CHECK(logic_in_aisle(t, 48, 12));
  CHECK(!logic_in_aisle(t, 33, 12));
  CHECK(logic_in_aisle(t, 33, 88));
}

static void test_frame_outside_aisle_not_counted() {
  LogicConfig c = cfg();
  Detection d[] = {obs(10, 50)};
  CHECK(logic_classify_frame(c, d, 1) == FrameState::Absent);
}

static void test_frame_obstacle_in_aisle_present() {
  LogicConfig c = cfg();
  Detection d[] = {obs(48, 50)};
  CHECK(logic_classify_frame(c, d, 1) == FrameState::Present);
}

static void test_frame_person_not_counted() {
  LogicConfig c = cfg();
  Detection d[] = {per(48, 50)};
  CHECK(logic_classify_frame(c, d, 1) == FrameState::Absent);
}

static void test_frame_low_conf_dropped() {
  LogicConfig c = cfg();
  Detection d[] = {obs(48, 50, 0.59f)};
  CHECK(logic_classify_frame(c, d, 1) == FrameState::Absent);
  Detection e[] = {obs(48, 50, 0.6f)};
  CHECK(logic_classify_frame(c, e, 1) == FrameState::Present);
}

static void test_frame_obstacle_near_person_skipped() {
  // 사람 근처의 obstacle은 사람을 잘못 본 것일 수 있어 판단을 보류한다(창에 넣지 않음)
  LogicConfig c = cfg();
  Detection d[] = {obs(48, 50), per(52, 54)};
  CHECK(logic_classify_frame(c, d, 2) == FrameState::Skip);
  // 사람과 멀리 떨어진 obstacle이 하나라도 있으면 있음
  Detection e[] = {obs(48, 50), per(52, 54), obs(40, 85)};
  CHECK(logic_classify_frame(c, e, 3) == FrameState::Present);
  // 반경 0이면 규칙을 끈다
  c.person_radius = 0;
  CHECK(logic_classify_frame(c, d, 2) == FrameState::Present);
}

static void test_frame_max_conf() {
  LogicConfig c = cfg();
  Detection d[] = {obs(48, 50, 0.7f), obs(40, 30, 0.95f), obs(10, 10, 0.99f)};
  CHECK(logic_max_conf(c, d, 3) == 0.95f);  // 통로 밖은 빼고
}

// 프레임을 500ms(2fps) 간격으로 넣는 도우미
struct Run {
  AisleLogic lg;
  uint32_t t = 0;
  int warnings = 0, clears = 0;
  LogicEvent last{};
  explicit Run(const LogicConfig &c) : lg(c) {}
  void feed(FrameState s, int frames, float conf = 0.9f) {
    for (int i = 0; i < frames; i++) {
      LogicEvent e = lg.update(s, t, conf);
      if (e.kind == EventKind::Warning) { warnings++; last = e; }
      if (e.kind == EventKind::Cleared) { clears++; last = e; }
      t += 500;
    }
  }
};

static void test_single_frame_not_occupied() {
  Run r(cfg());
  r.feed(FrameState::Absent, 6);
  r.feed(FrameState::Present, 1);
  r.feed(FrameState::Absent, 6);
  CHECK(r.lg.level() == 0);
  CHECK(r.warnings == 0);
  CHECK(r.clears == 0);
}

static void test_levels_by_dwell() {
  Run r(cfg());
  r.feed(FrameState::Absent, 6);
  r.feed(FrameState::Present, 4);
  CHECK(r.lg.level() == 1);  // 4/6 → 점유, 아직 10초 미만
  r.feed(FrameState::Present, 16);  // 마지막 프레임이 시작 후 9.5초
  CHECK(r.lg.level() == 1);
  CHECK(r.warnings == 0);
  r.feed(FrameState::Present, 1);   // 시작 후 10초
  CHECK(r.lg.level() == 2);
  CHECK(r.warnings == 1);
  CHECK(r.last.dwell_ms == 10000u);
  r.feed(FrameState::Present, 10);
  CHECK(r.warnings == 1);  // 경고는 한 번만
}

static void test_short_stay_no_warning() {
  // 시나리오 4: 5초만 두고 치움 → Level 1만, 경고·해제 기록 없음
  Run r(cfg());
  r.feed(FrameState::Absent, 6);
  r.feed(FrameState::Present, 10);
  CHECK(r.lg.level() == 1);
  r.feed(FrameState::Absent, 6);
  CHECK(r.lg.level() == 0);
  CHECK(r.warnings == 0);
  CHECK(r.clears == 0);
}

static void test_clear_reports_dwell() {
  // 15초 두고 치움: 방치 시간이 실제와 ±1프레임(500ms) 안에서 맞는다
  Run r(cfg());
  r.feed(FrameState::Absent, 6);
  uint32_t placed = r.t;
  r.feed(FrameState::Present, 30);
  uint32_t removed = r.t;
  r.feed(FrameState::Absent, 6);
  CHECK(r.lg.level() == 0);
  CHECK(r.warnings == 1);
  CHECK(r.clears == 1);
  uint32_t truth = removed - placed;
  uint32_t got = r.last.dwell_ms;
  CHECK(got + 500 >= truth && got <= truth + 500);
  CHECK(r.last.started_ms == placed);
}

static void test_flicker_tolerated() {
  // 한두 프레임 놓쳐도 점유가 이어지고 시작 시각이 바뀌지 않는다
  Run r(cfg());
  r.feed(FrameState::Absent, 6);
  uint32_t placed = r.t;
  for (int i = 0; i < 8; i++) {
    r.feed(FrameState::Present, 2);
    r.feed(FrameState::Absent, 1);
  }
  r.feed(FrameState::Present, 2);
  CHECK(r.lg.level() == 2);
  CHECK(r.warnings == 1);
  CHECK(r.last.started_ms == placed);
}

static void test_person_walk_no_warning() {
  // 사람이 3초 지나감: person만 보이는 프레임은 Absent
  LogicConfig c = cfg();
  Run r(c);
  Detection d[] = {per(48, 50)};
  r.feed(FrameState::Absent, 6);
  r.feed(logic_classify_frame(c, d, 1), 6);
  r.feed(FrameState::Absent, 6);
  CHECK(r.warnings == 0);
  CHECK(r.lg.level() == 0);
}

static void test_skip_holds_state() {
  // 경고 중 사람이 상자 옆을 지나가도(Skip) 해제되지 않는다
  Run r(cfg());
  r.feed(FrameState::Absent, 6);
  r.feed(FrameState::Present, 24);
  CHECK(r.lg.level() == 2);
  r.feed(FrameState::Skip, 8);
  CHECK(r.lg.level() == 2);
  CHECK(r.clears == 0);
  r.feed(FrameState::Present, 2);
  r.feed(FrameState::Absent, 6);
  CHECK(r.clears == 1);
}

static void test_skip_only_never_occupies() {
  Run r(cfg());
  r.feed(FrameState::Skip, 40);
  CHECK(r.lg.level() == 0);
  CHECK(r.warnings == 0);
}

static void test_event_json() {
  EventRecord e;
  std::strcpy(e.device_id, "aisle-cam-01");
  e.kind = EventKind::Cleared;
  std::strcpy(e.started_at, "2026-11-03T05:00:00Z");
  std::strcpy(e.ended_at, "2026-11-03T05:00:15Z");
  e.dwell_s = 15.5f;
  e.max_conf = 0.93f;
  std::strcpy(e.fw_version, "0.1.0");
  std::strcpy(e.model_version, "ei-3");
  char buf[512];
  CHECK(logic_event_json(e, buf, sizeof buf));
  CHECK(std::string(buf) ==
        "{\"device_id\":\"aisle-cam-01\",\"event\":\"cleared\","
        "\"started_at\":\"2026-11-03T05:00:00Z\",\"ended_at\":\"2026-11-03T05:00:15Z\","
        "\"dwell_s\":15.50,\"max_conf\":0.930,\"fw_version\":\"0.1.0\",\"model_version\":\"ei-3\"}");

  // warning: ended_at은 null, 시각을 모르면(NTP 전) started_at도 null
  e.kind = EventKind::Warning;
  e.ended_at[0] = '\0';
  e.started_at[0] = '\0';
  e.dwell_s = 10.0f;
  CHECK(logic_event_json(e, buf, sizeof buf));
  CHECK(std::string(buf).find("\"event\":\"warning\"") != std::string::npos);
  CHECK(std::string(buf).find("\"started_at\":null,\"ended_at\":null") != std::string::npos);

  // heartbeat
  e.kind = EventKind::Heartbeat;
  CHECK(logic_event_json(e, buf, sizeof buf));
  CHECK(std::string(buf).find("\"event\":\"heartbeat\"") != std::string::npos);

  // 버퍼가 작으면 false
  char small[16];
  CHECK(!logic_event_json(e, small, sizeof small));
}

static void test_queue_keeps_latest_20() {
  EventQueue q;
  CHECK(q.empty());
  for (int i = 0; i < 25; i++) {
    char s[16];
    std::snprintf(s, sizeof s, "{\"n\":%d}", i);
    q.push(s);
  }
  CHECK(q.size() == EventQueue::CAP);
  CHECK(EventQueue::CAP == 20);
  CHECK(q.dropped() == 5);
  CHECK(std::string(q.front()) == "{\"n\":5}");  // 가장 오래된 5개를 버림
  q.pop();
  CHECK(std::string(q.front()) == "{\"n\":6}");
  CHECK(q.size() == 19);
  while (!q.empty()) q.pop();
  CHECK(q.size() == 0);
}

int main() {
  test_defaults_match_prd();
  test_point_in_aisle();
  test_frame_outside_aisle_not_counted();
  test_frame_obstacle_in_aisle_present();
  test_frame_person_not_counted();
  test_frame_low_conf_dropped();
  test_frame_obstacle_near_person_skipped();
  test_frame_max_conf();
  test_single_frame_not_occupied();
  test_levels_by_dwell();
  test_short_stay_no_warning();
  test_clear_reports_dwell();
  test_flicker_tolerated();
  test_person_walk_no_warning();
  test_skip_holds_state();
  test_skip_only_never_occupies();
  test_event_json();
  test_queue_keeps_latest_20();
  if (failures == 0) std::printf("logic: ALL PASS\n");
  else std::printf("logic: %d FAILED\n", failures);
  return failures == 0 ? 0 : 1;
}
