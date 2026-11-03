// aisle-guard: PC(tools/feed.py)가 USB 시리얼로 보내는 96×96 프레임 → FOMO 검출 → 통로 방치 판정 → LED → Supabase 기록
// 시리얼 명령 (줄 단위, '#'로 시작):
//   #AISLE x1 y1 x2 y2 x3 y3 ...   통로 다각형(96×96 좌표, 3~8점). 보드에 저장된다
//   #AISLE?                         지금 통로 출력
//   #FAKE x y conf | #FAKE off      스텁 검출기에 가짜 obstacle (모델 없이 배선 시험)
//   #CAM on | #CAM off              카메라 모드: 보드 카메라로 2fps 촬영해 같은 검출·판정 (v는 #CAM on부터 ms)
//   #CAMCROP x y side               카메라에서 잘라낼 정사각형 (QVGA 320×240 좌표, 기본 40 0 240)
//   #CAMAE n                        카메라 자동 노출 목표 -2~2 (화면을 찍을 때 하얗게 날아가면 낮춘다, 기본 -1)
//   #CAMMIRROR h v                  카메라 좌우(h)·상하(v) 반전 0/1
//   #CONF c                        판정 점수 기준 conf_min (저장 안 함, 기본 0.6. 카메라 모드는 screen.py가 0.4로)
//   #VIEW on | #VIEW off           카메라 모드에서 보드가 본 96×96을 "V <hex>" 줄로 보낸다 (조준용, tools/screen.py)
#include <Arduino.h>
#include <Preferences.h>
#include <esp_heap_caps.h>
#include <time.h>

#include "camera.h"
#include "detector.h"
#include "logic.h"
#include "net.h"
#include "proto.h"
#include "settings.h"
#include "uploader.h"

static uint8_t *frame_buf;
static FrameParser *parser;
static LogicConfig cfg;
static AisleLogic *logic_;
static Preferences prefs;
static char line[160];
static size_t line_n = 0;
static uint32_t last_heartbeat_ms = 0;
static uint32_t frames = 0;

Detection g_fake = {LABEL_OBSTACLE, 48, 48, 0.9f};
bool g_fake_on = false;

static bool cam_ready = false, cam_on = false, view_on = false;
static uint32_t cam_t0 = 0, cam_next = 0;
static const uint32_t CAM_PERIOD_MS = 500;  // feed.py 기본 2fps와 같게

static void set_default_aisle() {
  float xs[] = {0, 96, 96, 0}, ys[] = {0, 0, 96, 96};
  cfg.aisle_n = 4;
  for (int i = 0; i < 4; i++) { cfg.aisle_x[i] = xs[i]; cfg.aisle_y[i] = ys[i]; }
}

static void print_aisle() {
  Serial.print("[cfg] aisle");
  for (int i = 0; i < cfg.aisle_n; i++) Serial.printf(" %.0f,%.0f", (double)cfg.aisle_x[i], (double)cfg.aisle_y[i]);
  Serial.println();
}

static void load_aisle() {
  set_default_aisle();
  prefs.begin("aisle", true);
  int n = prefs.getInt("n", 0);
  if (n >= 3 && n <= AISLE_MAX_POINTS) {
    prefs.getBytes("x", cfg.aisle_x, sizeof(float) * n);
    prefs.getBytes("y", cfg.aisle_y, sizeof(float) * n);
    cfg.aisle_n = n;
  }
  prefs.end();
}

static void save_aisle() {
  prefs.begin("aisle", false);
  prefs.putInt("n", cfg.aisle_n);
  prefs.putBytes("x", cfg.aisle_x, sizeof(float) * cfg.aisle_n);
  prefs.putBytes("y", cfg.aisle_y, sizeof(float) * cfg.aisle_n);
  prefs.end();
}

static void handle_command(char *s) {
  if (strcmp(s, "#AISLE?") == 0) { print_aisle(); return; }
  if (strncmp(s, "#AISLE ", 7) == 0) {
    float v[AISLE_MAX_POINTS * 2];
    int n = 0;
    for (char *tok = strtok(s + 7, " ,"); tok && n < AISLE_MAX_POINTS * 2; tok = strtok(nullptr, " ,"))
      v[n++] = atof(tok);
    if (n < 6 || n % 2) { Serial.println("[cfg] need 3~8 points: #AISLE x1 y1 x2 y2 x3 y3 ..."); return; }
    cfg.aisle_n = n / 2;
    for (int i = 0; i < cfg.aisle_n; i++) { cfg.aisle_x[i] = v[2 * i]; cfg.aisle_y[i] = v[2 * i + 1]; }
    save_aisle();
    delete logic_;
    logic_ = new AisleLogic(cfg);
    print_aisle();
    return;
  }
  if (strcmp(s, "#CAM on") == 0) {
    if (!cam_ready) cam_ready = camera_begin();
    if (!cam_ready) { Serial.println("[cam] not available"); return; }
    cam_on = true;
    cam_t0 = cam_next = millis();
    delete logic_;  // 새 시연을 처음 상태에서 시작
    logic_ = new AisleLogic(cfg);
    int x, y, side;
    camera_get_crop(&x, &y, &side);
    Serial.printf("[cam] on crop=%d,%d,%d\n", x, y, side);
    return;
  }
  if (strcmp(s, "#CAM off") == 0) { cam_on = false; Serial.println("[cam] off"); return; }
  if (strncmp(s, "#CAMCROP ", 9) == 0) {
    int x, y, side;
    if (sscanf(s + 9, "%d %d %d", &x, &y, &side) == 3) camera_set_crop(x, y, side);
    camera_get_crop(&x, &y, &side);
    Serial.printf("[cam] crop=%d,%d,%d\n", x, y, side);
    return;
  }
  if (strncmp(s, "#CONF ", 6) == 0) {  // 판정 점수 기준 (저장 안 함, 부팅하면 0.6)
    float c = atof(s + 6);
    if (c > 0 && c < 1) {
      cfg.conf_min = c;
      delete logic_;
      logic_ = new AisleLogic(cfg);
    }
    Serial.printf("[cfg] conf_min=%.2f\n", (double)cfg.conf_min);
    return;
  }
  if (strncmp(s, "#CAMMIRROR ", 11) == 0) {
    int h = 0, v = 0;
    sscanf(s + 11, "%d %d", &h, &v);
    if (!cam_ready) cam_ready = camera_begin();
    if (cam_ready) camera_set_mirror(h, v);
    Serial.printf("[cam] mirror h=%d v=%d\n", h, v);
    return;
  }
  if (strncmp(s, "#CAMAE ", 7) == 0) {
    if (!cam_ready) cam_ready = camera_begin();
    if (cam_ready) camera_set_ae(atoi(s + 7));
    Serial.printf("[cam] ae=%d\n", atoi(s + 7));
    return;
  }
  if (strcmp(s, "#VIEW on") == 0) { view_on = true; Serial.println("[cam] view on"); return; }
  if (strcmp(s, "#VIEW off") == 0) { view_on = false; Serial.println("[cam] view off"); return; }
  if (strcmp(s, "#FAKE off") == 0) { g_fake_on = false; Serial.println("[cfg] fake off"); return; }
  if (strncmp(s, "#FAKE ", 6) == 0) {
    float x, y, c;
    if (sscanf(s + 6, "%f %f %f", &x, &y, &c) == 3) {
      g_fake = {LABEL_OBSTACLE, x, y, c};
      g_fake_on = true;
      Serial.printf("[cfg] fake obstacle %.0f,%.0f conf=%.2f\n", (double)x, (double)y, (double)c);
    }
    return;
  }
}

// 지금으로부터 ago_ms 전의 UTC 시각. NTP 전이면 빈 문자열
static void iso_ago(uint32_t ago_ms, char *out, size_t n) {
  out[0] = '\0';
  time_t now = time(nullptr);
  if (now < PROTO_MIN_VALID_TIME) return;
  if (!proto_iso8601_utc(now - (time_t)((ago_ms + 500) / 1000), out, n)) out[0] = '\0';
}

static void send_event(EventKind kind, const LogicEvent *ev) {
  EventRecord r;
  strncpy(r.device_id, DEVICE_ID, sizeof r.device_id - 1);
  r.kind = kind;
  strncpy(r.fw_version, FW_VERSION, sizeof r.fw_version - 1);
  strncpy(r.model_version, MODEL_VERSION, sizeof r.model_version - 1);
  if (ev) {
    uint32_t now = millis();
    iso_ago(now - ev->started_ms, r.started_at, sizeof r.started_at);
    if (kind == EventKind::Cleared) iso_ago(now - ev->ended_ms, r.ended_at, sizeof r.ended_at);
    r.dwell_s = ev->dwell_ms / 1000.0f;
    r.max_conf = ev->max_conf;
  }
  char json[EventQueue::LEN];
  if (logic_event_json(r, json, sizeof json)) uploader_enqueue(json);
  else Serial.println("[up] event json too long");
}

static void on_frame(uint32_t video_ms) {
  Detection det[16];
  uint32_t infer_ms = 0;
  int n = detector_run(frame_buf, det, 16, &infer_ms);
  if (n < 0) { Serial.println("[det] inference failed"); return; }
  if (g_fake_on && n < 16) det[n++] = g_fake;

  FrameState st = logic_classify_frame(cfg, det, n);
  float conf = logic_max_conf(cfg, det, n);
  LogicEvent ev = logic_->update(st, millis(), conf);
  frames++;

#if FRAME_LOG
  int obs = 0, per = 0;
  for (int i = 0; i < n; i++) (det[i].label == LABEL_OBSTACLE ? obs : per)++;
  Serial.printf("F v=%lu obs=%d per=%d st=%c lvl=%d conf=%.2f inf=%lums\n", (unsigned long)video_ms, obs, per,
                st == FrameState::Present ? 'P' : st == FrameState::Skip ? 'S' : '-', logic_->level(),
                (double)conf, (unsigned long)infer_ms);
#endif
  if (ev.kind == EventKind::Warning) {
    Serial.printf("OBSTACLE WARNING dwell=%.1fs max_conf=%.2f v=%lu\n", ev.dwell_ms / 1000.0, (double)ev.max_conf,
                  (unsigned long)video_ms);
    send_event(EventKind::Warning, &ev);
  } else if (ev.kind == EventKind::Cleared) {
    Serial.printf("OBSTACLE CLEARED dwell=%.1fs max_conf=%.2f v=%lu\n", ev.dwell_ms / 1000.0, (double)ev.max_conf,
                  (unsigned long)video_ms);
    send_event(EventKind::Cleared, &ev);
  }
}

// 보드가 본 96×96 RGB를 한 줄 hex로 (PC 조준 화면용)
static void send_view() {
  static const char hex[] = "0123456789abcdef";
  char buf[512];
  size_t n = 0;
  Serial.print("V ");
  for (size_t i = 0; i < PROTO_FRAME_BYTES; i++) {
    buf[n++] = hex[frame_buf[i] >> 4];
    buf[n++] = hex[frame_buf[i] & 15];
    if (n == sizeof buf) {
      Serial.write((const uint8_t *)buf, n);
      n = 0;
    }
  }
  if (n) Serial.write((const uint8_t *)buf, n);
  Serial.println();
}

static void led_loop() {
  int lvl = logic_->level();
  bool on = false;
  if (lvl == 1) on = (millis() / 500) % 2;       // 1Hz 천천히
  else if (lvl == 2) on = (millis() / 100) % 2;  // 5Hz 빠르게
  digitalWrite(LED_PIN, on ? LOW : HIGH);
}

void setup() {
  Serial.setRxBufferSize(PROTO_FRAME_BYTES + 1024);
  Serial.begin(115200);
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, HIGH);
  delay(1500);
  Serial.printf("\n[boot] aisle-guard fw=%s model=%s device=%s\n", FW_VERSION, MODEL_VERSION, DEVICE_ID);

  frame_buf = (uint8_t *)heap_caps_malloc(PROTO_FRAME_BYTES, MALLOC_CAP_SPIRAM);
  if (!frame_buf) frame_buf = (uint8_t *)malloc(PROTO_FRAME_BYTES);
  parser = new FrameParser(frame_buf, PROTO_FRAME_BYTES);
  load_aisle();
  logic_ = new AisleLogic(cfg);
  print_aisle();
  Serial.printf("[cfg] conf_min=%.2f win=%d/%d clear=%d dwell=%lums person_r=%.0f\n", (double)cfg.conf_min,
                cfg.win_k, cfg.win_n, cfg.clear_k, (unsigned long)cfg.dwell_ms, (double)cfg.person_radius);

  detector_begin();
  net_begin();
  uploader_begin();
  last_heartbeat_ms = millis();
  Serial.println("[boot] ready");
}

void loop() {
  while (Serial.available()) {
    uint8_t b = (uint8_t)Serial.read();
    if (parser->feed(b)) {
      on_frame(parser->video_ms());
      line_n = 0;  // 프레임 바이너리는 명령 줄이 아니다
      continue;
    }
    if (b == '\n' || b == '\r') {
      line[line_n] = '\0';
      if (line_n > 0 && line[0] == '#') handle_command(line);
      line_n = 0;
    } else if (line_n < sizeof line - 1) {
      line[line_n++] = (char)b;
    } else {
      line_n = 0;
    }
  }
  if (cam_on && (int32_t)(millis() - cam_next) >= 0) {
    cam_next += CAM_PERIOD_MS;
    if ((int32_t)(millis() - cam_next) > 0) cam_next = millis() + CAM_PERIOD_MS;  // 밀리면 따라잡지 않는다
    if (camera_grab96(frame_buf)) {
      if (view_on) send_view();
      on_frame(millis() - cam_t0);
    } else {
      Serial.println("[cam] grab failed");
    }
  }
  net_loop();
  led_loop();
  if (millis() - last_heartbeat_ms >= HEARTBEAT_MS) {
    last_heartbeat_ms = millis();
    Serial.printf("[hb] frames=%lu bad=%d pending=%d wifi=%d\n", (unsigned long)frames, parser->bad(),
                  uploader_pending(), net_connected());
    send_event(EventKind::Heartbeat, nullptr);
  }
}
