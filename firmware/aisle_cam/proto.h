// 통신 규칙만 모은 모듈 (Supabase 응답 분류, 시각 문자열, PC → 보드 프레임 형식).
// Arduino에 의존하지 않아 PC에서 단위 시험한다.
#pragma once
#include <cstddef>
#include <cstdint>
#include <ctime>

constexpr uint32_t PROTO_MAX_RETRIES = 3;           // 처음 1회 + 재시도 최대 3회
constexpr time_t PROTO_MIN_VALID_TIME = 1704067200; // 2024-01-01T00:00:00Z, 이전이면 NTP 미동기화로 본다
constexpr int PROTO_FRAME_W = 96;
constexpr int PROTO_FRAME_H = 96;
constexpr size_t PROTO_FRAME_BYTES = PROTO_FRAME_W * PROTO_FRAME_H * 3;  // RGB888

enum class SendAction { Success, Fatal, Retry };

// UTC ISO 8601 "YYYY-MM-DDTHH:MM:SSZ". t가 2024년 이전이면 false
bool proto_iso8601_utc(time_t t, char *out, size_t n);

// 2xx Success / 429·5xx·음수(HTTPClient 네트워크 오류) Retry / 그 밖 Fatal
SendAction proto_classify(int http_code);

// attempt 1~3 → 1000·2000·4000ms
uint32_t proto_retry_delay_ms(int attempt);

// tools/feed.py가 USB 시리얼로 보내는 프레임:
//   "AGFR" + video_ms(u32 LE) + len(u16 LE, = PROTO_FRAME_BYTES) + RGB888 payload + xor(payload)(u8)
class FrameParser {
 public:
  FrameParser(uint8_t *buf, size_t cap) : buf_(buf), cap_(cap) {}
  // 한 바이트씩 넣는다. 올바른 프레임이 완성된 바이트에서 true
  bool feed(uint8_t b);
  const uint8_t *pixels() const { return buf_; }
  uint32_t video_ms() const { return video_ms_; }
  int bad() const { return bad_; }  // 길이·체크섬이 틀려 버린 프레임 수

 private:
  enum class St { Magic, Header, Payload, Check };
  uint8_t *buf_;
  size_t cap_;
  St st_ = St::Magic;
  int magic_i_ = 0, hdr_i_ = 0;
  uint8_t hdr_[6] = {};
  size_t len_ = 0, got_ = 0;
  uint8_t x_ = 0;
  uint32_t video_ms_ = 0, pending_ms_ = 0;
  int bad_ = 0;
};
