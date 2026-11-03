// proto 모듈 단위 시험 (PC g++). 실행: powershell -File firmware/tests/run_tests.ps1
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

#include "proto.h"

static int failures = 0;
#define CHECK(cond)                                                    \
  do {                                                                 \
    if (!(cond)) {                                                     \
      std::printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #cond);      \
      failures++;                                                      \
    }                                                                  \
  } while (0)

static void test_iso8601() {
  char buf[32];
  CHECK(proto_iso8601_utc(1793597472, buf, sizeof buf));
  CHECK(std::strcmp(buf, "2026-11-02T05:31:12Z") == 0);
  CHECK(proto_iso8601_utc(1704067200, buf, sizeof buf));
  CHECK(std::strcmp(buf, "2024-01-01T00:00:00Z") == 0);
  CHECK(!proto_iso8601_utc(0, buf, sizeof buf));
  CHECK(!proto_iso8601_utc(1704067199, buf, sizeof buf));
}

static void test_classify() {
  CHECK(proto_classify(201) == SendAction::Success);  // Supabase insert
  CHECK(proto_classify(200) == SendAction::Success);
  CHECK(proto_classify(204) == SendAction::Success);
  CHECK(proto_classify(400) == SendAction::Fatal);    // 컬럼·형식 오류
  CHECK(proto_classify(401) == SendAction::Fatal);    // 키 오류
  CHECK(proto_classify(403) == SendAction::Fatal);    // RLS 거부
  CHECK(proto_classify(429) == SendAction::Retry);
  CHECK(proto_classify(503) == SendAction::Retry);
  CHECK(proto_classify(500) == SendAction::Retry);
  CHECK(proto_classify(-1) == SendAction::Retry);     // HTTPC_ERROR_CONNECTION_REFUSED
  CHECK(proto_classify(-11) == SendAction::Retry);    // HTTPC_ERROR_READ_TIMEOUT
  CHECK(proto_classify(302) == SendAction::Fatal);
}

// feed.py와 같은 형식: "AGFR" + video_ms(u32 LE) + len(u16 LE) + payload + xor(u8)
static std::vector<uint8_t> packet(uint32_t video_ms, const std::vector<uint8_t> &payload, int corrupt = 0) {
  std::vector<uint8_t> p = {'A', 'G', 'F', 'R'};
  for (int i = 0; i < 4; i++) p.push_back((video_ms >> (8 * i)) & 0xFF);
  p.push_back(payload.size() & 0xFF);
  p.push_back((payload.size() >> 8) & 0xFF);
  uint8_t x = 0;
  for (uint8_t b : payload) { p.push_back(b); x ^= b; }
  p.push_back(x ^ corrupt);
  return p;
}

static std::vector<uint8_t> pixels(uint8_t seed) {
  std::vector<uint8_t> v(PROTO_FRAME_BYTES);
  for (size_t i = 0; i < v.size(); i++) v[i] = (uint8_t)(i * 7 + seed);
  return v;
}

static int feed_all(FrameParser &fp, const std::vector<uint8_t> &bytes) {
  int frames = 0;
  for (uint8_t b : bytes) frames += fp.feed(b) ? 1 : 0;
  return frames;
}

static void test_frame_parse() {
  static uint8_t buf[PROTO_FRAME_BYTES];
  FrameParser fp(buf, sizeof buf);
  auto px = pixels(3);
  CHECK(feed_all(fp, packet(123456, px)) == 1);
  CHECK(fp.video_ms() == 123456u);
  CHECK(std::memcmp(fp.pixels(), px.data(), px.size()) == 0);
  CHECK(fp.bad() == 0);
}

static void test_frame_resync_after_garbage() {
  static uint8_t buf[PROTO_FRAME_BYTES];
  FrameParser fp(buf, sizeof buf);
  std::vector<uint8_t> bytes = {'x', 'A', 'G', 'q', 'A'};  // 로그 찌꺼기, 부분 magic
  auto p = packet(7, pixels(1));
  bytes.insert(bytes.end(), p.begin(), p.end());
  CHECK(feed_all(fp, bytes) == 1);
  CHECK(fp.video_ms() == 7u);
}

static void test_frame_bad_checksum_dropped() {
  static uint8_t buf[PROTO_FRAME_BYTES];
  FrameParser fp(buf, sizeof buf);
  auto bad = packet(1, pixels(1), 0x5A);
  auto good = packet(2, pixels(2));
  CHECK(feed_all(fp, bad) == 0);
  CHECK(fp.bad() == 1);
  CHECK(feed_all(fp, good) == 1);
  CHECK(fp.video_ms() == 2u);
}

static void test_frame_wrong_length_dropped() {
  static uint8_t buf[PROTO_FRAME_BYTES];
  FrameParser fp(buf, sizeof buf);
  std::vector<uint8_t> small(100, 9);
  CHECK(feed_all(fp, packet(1, small)) == 0);
  CHECK(fp.bad() == 1);
  CHECK(feed_all(fp, packet(3, pixels(3))) == 1);
  CHECK(fp.video_ms() == 3u);
}

int main() {
  test_iso8601();
  test_classify();
  test_frame_parse();
  test_frame_resync_after_garbage();
  test_frame_bad_checksum_dropped();
  test_frame_wrong_length_dropped();
  if (failures == 0) std::printf("proto: ALL PASS\n");
  else std::printf("proto: %d FAILED\n", failures);
  return failures == 0 ? 0 : 1;
}
