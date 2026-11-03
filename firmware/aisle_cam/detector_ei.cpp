// Edge Impulse FOMO (obstacle / person). settings.h의 DETECTOR_EI=1일 때만 컴파일된다.
// feed.py가 이미 96×96 RGB888로 줄여 보내므로 변환 없이 그대로 넣는다.
#include "settings.h"

#if DETECTOR_EI

#include <Arduino.h>
#include <esp_heap_caps.h>

#include EI_HEADER
#include "edge-impulse-sdk/classifier/postprocessing/ei_postprocessing_thresholds.h"

#include "detector.h"
#include "proto.h"

static_assert(EI_CLASSIFIER_INPUT_WIDTH == PROTO_FRAME_W && EI_CLASSIFIER_INPUT_HEIGHT == PROTO_FRAME_H,
              "model input must be 96x96 (feed.py size)");

static const uint8_t *cur = nullptr;

// EI SDK(espressif 포팅) 기본 ei_calloc은 IDF 5.x(코어 3.x)에서 정렬 없는 heap_caps_calloc이라 esp-nn에서 힙이 깨진다
// (zero-touch·PPE 교훈, espressif/esp-nn#7). SDK의 weak 정의를 16바이트 정렬 할당으로 덮어쓴다.
void *ei_malloc(size_t size) { return heap_caps_aligned_alloc(16, size, MALLOC_CAP_8BIT); }
void *ei_calloc(size_t nitems, size_t size) {
  return heap_caps_aligned_calloc(16, nitems, size, MALLOC_CAP_8BIT);
}
void ei_free(void *ptr) { heap_caps_free(ptr); }

static int get_signal_data(size_t offset, size_t length, float *out) {
  const uint8_t *p = cur + offset * 3;
  for (size_t i = 0; i < length; i++, p += 3) out[i] = (float)((p[0] << 16) | (p[1] << 8) | p[2]);
  return 0;
}

void detector_begin() {
  EI_IMPULSE_ERROR r = set_threshold_postprocessing(&ei_default_impulse.impulse->postprocessing_blocks[0],
                                                    "min_score", EI_MIN_SCORE);
  if (r != EI_IMPULSE_OK) Serial.printf("[det] set min_score failed (%d), model default used\n", (int)r);
  Serial.printf("[det] edge impulse %dx%d, labels=%d, min_score=%.2f, model=%s\n", EI_CLASSIFIER_INPUT_WIDTH,
                EI_CLASSIFIER_INPUT_HEIGHT, EI_CLASSIFIER_LABEL_COUNT, (double)EI_MIN_SCORE, MODEL_VERSION);
}

int detector_run(const uint8_t *rgb, Detection *out, int max, uint32_t *infer_ms) {
  cur = rgb;
  ei::signal_t signal;
  signal.total_length = EI_CLASSIFIER_INPUT_WIDTH * EI_CLASSIFIER_INPUT_HEIGHT;
  signal.get_data = &get_signal_data;
  ei_impulse_result_t result = {};
  uint32_t t0 = millis();
  if (run_classifier(&signal, &result, false) != EI_IMPULSE_OK) return -1;
  *infer_ms = millis() - t0;

  int n = 0;
  for (uint32_t i = 0; i < result.bounding_boxes_count && n < max; i++) {
    const auto &bb = result.bounding_boxes[i];
    if (bb.value <= 0) continue;
    int label;
    if (strcmp(bb.label, "obstacle") == 0) label = LABEL_OBSTACLE;
    else if (strcmp(bb.label, "person") == 0) label = LABEL_PERSON;
    else continue;
    out[n++] = {label, bb.x + bb.width / 2.0f, bb.y + bb.height / 2.0f, bb.value};
  }
  return n;
}

#endif  // DETECTOR_EI
