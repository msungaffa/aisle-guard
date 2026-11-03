#include "proto.h"

bool proto_iso8601_utc(time_t t, char *out, size_t n) {
  if (t < PROTO_MIN_VALID_TIME) return false;
  struct tm *tm = std::gmtime(&t);  // 단일 스레드에서만 호출
  if (!tm) return false;
  return std::strftime(out, n, "%Y-%m-%dT%H:%M:%SZ", tm) > 0;
}

SendAction proto_classify(int http_code) {
  if (http_code >= 200 && http_code <= 299) return SendAction::Success;
  if (http_code < 0) return SendAction::Retry;  // HTTPClient 연결 실패·타임아웃 등
  if (http_code == 429 || (http_code >= 500 && http_code <= 599)) return SendAction::Retry;
  return SendAction::Fatal;  // 4xx(키·RLS·형식 오류) 및 예상 밖 코드: 재시도하지 않음
}

uint32_t proto_retry_delay_ms(int attempt) {
  if (attempt < 1) attempt = 1;
  if (attempt > 3) attempt = 3;
  return 1000u << (attempt - 1);
}

static const uint8_t MAGIC[4] = {'A', 'G', 'F', 'R'};

bool FrameParser::feed(uint8_t b) {
  switch (st_) {
    case St::Magic:
      if (b == MAGIC[magic_i_]) {
        if (++magic_i_ == 4) { st_ = St::Header; hdr_i_ = 0; magic_i_ = 0; }
      } else {
        magic_i_ = (b == MAGIC[0]) ? 1 : 0;
      }
      return false;
    case St::Header:
      hdr_[hdr_i_++] = b;
      if (hdr_i_ == 6) {
        pending_ms_ = (uint32_t)hdr_[0] | ((uint32_t)hdr_[1] << 8) | ((uint32_t)hdr_[2] << 16) |
                      ((uint32_t)hdr_[3] << 24);
        len_ = (size_t)hdr_[4] | ((size_t)hdr_[5] << 8);
        got_ = 0;
        x_ = 0;
        // 길이가 다르면 버리고 다시 magic을 찾는다
        if (len_ != PROTO_FRAME_BYTES || len_ > cap_) { bad_++; st_ = St::Magic; }
        else st_ = St::Payload;
      }
      return false;
    case St::Payload:
      buf_[got_++] = b;
      x_ ^= b;
      if (got_ == len_) st_ = St::Check;
      return false;
    case St::Check:
      st_ = St::Magic;
      if (b != x_) { bad_++; return false; }
      video_ms_ = pending_ms_;
      return true;
  }
  return false;
}
