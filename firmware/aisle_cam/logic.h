// 통로 방치 판정 규칙 (PRD "판정 로직"). Arduino에 의존하지 않아 PC에서 단위 시험한다.
#pragma once
#include <cstddef>
#include <cstdint>

constexpr int LABEL_OBSTACLE = 0;
constexpr int LABEL_PERSON = 1;
constexpr int AISLE_MAX_POINTS = 8;
constexpr int WIN_MAX = 16;

// 모델 출력 하나. x, y는 96×96 입력 화면의 중심점 좌표
struct Detection {
  int label;
  float x, y;
  float conf;
};

struct LogicConfig {
  int aisle_n = 0;  // 통로 다각형 꼭짓점 (시계·반시계 상관없음)
  float aisle_x[AISLE_MAX_POINTS] = {};
  float aisle_y[AISLE_MAX_POINTS] = {};
  float conf_min = 0.6f;       // CONF_MIN
  int win_n = 6;               // WIN_N
  int win_k = 4;               // WIN_K: 이 이상 "있음"이면 점유
  int clear_k = 1;             // CLEAR_K: 이 이하면 해제
  uint32_t dwell_ms = 10000;   // DWELL_T
  float person_radius = 16;    // 이 거리 안의 person 옆 obstacle은 보류. 0이면 끔
};

// Present: 통로 안 obstacle 있음 / Absent: 없음 / Skip: 사람 옆이라 판단 보류(창에 넣지 않음)
enum class FrameState { Absent, Present, Skip };
enum class EventKind { None, Warning, Cleared, Heartbeat };

bool logic_in_aisle(const LogicConfig &c, float x, float y);
FrameState logic_classify_frame(const LogicConfig &c, const Detection *d, int n);
// 통로 안 obstacle 중 가장 높은 신뢰도 (CONF_MIN 미만 포함, 없으면 0)
float logic_max_conf(const LogicConfig &c, const Detection *d, int n);

struct LogicEvent {
  EventKind kind = EventKind::None;
  uint32_t started_ms = 0;  // 점유가 시작된 프레임 시각 (첫 "있음")
  uint32_t ended_ms = 0;    // 해제 때 마지막 "있음" 프레임 시각
  uint32_t dwell_ms = 0;
  float max_conf = 0;       // 점유 동안 가장 높은 신뢰도
};

class AisleLogic {
 public:
  explicit AisleLogic(const LogicConfig &c);
  // 프레임마다 한 번. now_ms는 단조 증가 시각, conf는 그 프레임의 logic_max_conf
  LogicEvent update(FrameState s, uint32_t now_ms, float conf);
  int level() const;  // 0 정상, 1 관찰, 2 경고
  uint32_t started_ms() const { return start_ms_; }

 private:
  LogicConfig c_;
  bool win_present_[WIN_MAX] = {};
  uint32_t win_t_[WIN_MAX] = {};
  int win_len_ = 0, win_head_ = 0;
  bool occupied_ = false, warned_ = false;
  uint32_t start_ms_ = 0, last_present_ms_ = 0;
  float max_conf_ = 0;
};

// DB(aisle_events) 한 줄
struct EventRecord {
  char device_id[33] = "";
  EventKind kind = EventKind::None;
  char started_at[24] = "";  // ISO 8601 UTC, 비어 있으면 null
  char ended_at[24] = "";
  float dwell_s = 0;
  float max_conf = 0;
  char fw_version[16] = "";
  char model_version[24] = "";
};

// Supabase REST insert 본문. 버퍼가 모자라면 false
bool logic_event_json(const EventRecord &e, char *out, size_t n);

// 전송 못 한 이벤트 JSON을 최근 CAP건까지 보관 (가득 차면 가장 오래된 것을 버림)
class EventQueue {
 public:
  static constexpr int CAP = 20;
  static constexpr int LEN = 320;
  void push(const char *json);
  const char *front() const;
  void pop();
  bool empty() const { return n_ == 0; }
  int size() const { return n_; }
  int dropped() const { return dropped_; }

 private:
  char buf_[CAP][LEN] = {};
  int head_ = 0, n_ = 0, dropped_ = 0;
};
