#include "logic.h"

#include <cstdio>
#include <cstring>

bool logic_in_aisle(const LogicConfig &c, float x, float y) {
  // 반직선 교차 수 (짝수면 밖)
  bool in = false;
  for (int i = 0, j = c.aisle_n - 1; i < c.aisle_n; j = i++) {
    float xi = c.aisle_x[i], yi = c.aisle_y[i], xj = c.aisle_x[j], yj = c.aisle_y[j];
    if ((yi > y) != (yj > y) && x < (xj - xi) * (y - yi) / (yj - yi) + xi) in = !in;
  }
  return in;
}

static bool counted_obstacle(const LogicConfig &c, const Detection &d) {
  return d.label == LABEL_OBSTACLE && d.conf >= c.conf_min && logic_in_aisle(c, d.x, d.y);
}

static bool near_person(const LogicConfig &c, const Detection &o, const Detection *d, int n) {
  if (c.person_radius <= 0) return false;
  float r2 = c.person_radius * c.person_radius;
  for (int i = 0; i < n; i++) {
    if (d[i].label != LABEL_PERSON || d[i].conf < c.conf_min) continue;
    float dx = d[i].x - o.x, dy = d[i].y - o.y;
    if (dx * dx + dy * dy <= r2) return true;
  }
  return false;
}

FrameState logic_classify_frame(const LogicConfig &c, const Detection *d, int n) {
  bool held = false;
  for (int i = 0; i < n; i++) {
    if (!counted_obstacle(c, d[i])) continue;
    if (near_person(c, d[i], d, n)) held = true;
    else return FrameState::Present;
  }
  return held ? FrameState::Skip : FrameState::Absent;
}

float logic_max_conf(const LogicConfig &c, const Detection *d, int n) {
  float m = 0;
  for (int i = 0; i < n; i++)
    if (d[i].label == LABEL_OBSTACLE && logic_in_aisle(c, d[i].x, d[i].y) && d[i].conf > m) m = d[i].conf;
  return m;
}

AisleLogic::AisleLogic(const LogicConfig &c) : c_(c) {
  if (c_.win_n > WIN_MAX) c_.win_n = WIN_MAX;
  if (c_.win_n < 1) c_.win_n = 1;
}

int AisleLogic::level() const {
  if (!occupied_) return 0;
  return warned_ ? 2 : 1;
}

LogicEvent AisleLogic::update(FrameState s, uint32_t now_ms, float conf) {
  LogicEvent ev;
  if (s != FrameState::Skip) {
    // 창에 넣기 (가득 차면 가장 오래된 것을 덮어씀)
    int idx = (win_head_ + win_len_) % c_.win_n;
    if (win_len_ == c_.win_n) {
      idx = win_head_;
      win_head_ = (win_head_ + 1) % c_.win_n;
    } else {
      win_len_++;
    }
    win_present_[idx] = (s == FrameState::Present);
    win_t_[idx] = now_ms;
    if (s == FrameState::Present) last_present_ms_ = now_ms;

    int count = 0;
    uint32_t first_t = 0;
    bool have_first = false;
    for (int k = 0; k < win_len_; k++) {
      int i = (win_head_ + k) % c_.win_n;
      if (!win_present_[i]) continue;
      count++;
      if (!have_first) { first_t = win_t_[i]; have_first = true; }
    }

    if (!occupied_ && count >= c_.win_k) {
      occupied_ = true;
      warned_ = false;
      start_ms_ = first_t;
      max_conf_ = 0;
    } else if (occupied_ && count <= c_.clear_k) {
      if (warned_) {
        ev.kind = EventKind::Cleared;
        ev.started_ms = start_ms_;
        ev.ended_ms = last_present_ms_;
        ev.dwell_ms = last_present_ms_ - start_ms_;
        ev.max_conf = max_conf_;
      }
      occupied_ = false;
      warned_ = false;
      return ev;
    }
  }

  if (occupied_) {
    if (s == FrameState::Present && conf > max_conf_) max_conf_ = conf;
    if (!warned_ && now_ms - start_ms_ >= c_.dwell_ms) {
      warned_ = true;
      ev.kind = EventKind::Warning;
      ev.started_ms = start_ms_;
      ev.dwell_ms = now_ms - start_ms_;
      ev.max_conf = max_conf_;
    }
  }
  return ev;
}

static const char *kind_name(EventKind k) {
  switch (k) {
    case EventKind::Warning: return "warning";
    case EventKind::Cleared: return "cleared";
    case EventKind::Heartbeat: return "heartbeat";
    default: return nullptr;
  }
}

static int put_time(char *out, size_t n, const char *key, const char *iso) {
  if (iso[0]) return std::snprintf(out, n, "\"%s\":\"%s\",", key, iso);
  return std::snprintf(out, n, "\"%s\":null,", key);
}

bool logic_event_json(const EventRecord &e, char *out, size_t n) {
  const char *kind = kind_name(e.kind);
  if (!kind || !out || n == 0) return false;
  size_t used = 0;
  int w = std::snprintf(out, n, "{\"device_id\":\"%s\",\"event\":\"%s\",", e.device_id, kind);
  if (w < 0 || (size_t)w >= n) return false;
  used += w;
  w = put_time(out + used, n - used, "started_at", e.started_at);
  if (w < 0 || (size_t)w >= n - used) return false;
  used += w;
  w = put_time(out + used, n - used, "ended_at", e.ended_at);
  if (w < 0 || (size_t)w >= n - used) return false;
  used += w;
  w = std::snprintf(out + used, n - used,
                    "\"dwell_s\":%.2f,\"max_conf\":%.3f,\"fw_version\":\"%s\",\"model_version\":\"%s\"}",
                    (double)e.dwell_s, (double)e.max_conf, e.fw_version, e.model_version);
  return w >= 0 && (size_t)w < n - used;
}

void EventQueue::push(const char *json) {
  if (n_ == CAP) {
    head_ = (head_ + 1) % CAP;
    n_--;
    dropped_++;
  }
  int idx = (head_ + n_) % CAP;
  std::strncpy(buf_[idx], json, LEN - 1);
  buf_[idx][LEN - 1] = '\0';
  n_++;
}

const char *EventQueue::front() const { return n_ ? buf_[head_] : ""; }

void EventQueue::pop() {
  if (!n_) return;
  head_ = (head_ + 1) % CAP;
  n_--;
}
