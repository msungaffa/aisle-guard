// 모델 없이 배선(시리얼 수신·판정·LED·DB)을 시험할 때 쓰는 검출기. 항상 검출 0개.
#include "settings.h"

#if !DETECTOR_EI

#include <Arduino.h>

#include "detector.h"

void detector_begin() { Serial.println("[det] stub detector (DETECTOR_EI=0): no detections"); }

int detector_run(const uint8_t *, Detection *, int, uint32_t *infer_ms) {
  *infer_ms = 0;
  return 0;
}

#endif  // !DETECTOR_EI
