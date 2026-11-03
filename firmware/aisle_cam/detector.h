// 검출 인터페이스. settings.h의 DETECTOR_EI로 detector_ei.cpp(Edge Impulse) / detector_stub.cpp 중 하나가 컴파일된다.
#pragma once
#include <cstdint>

#include "logic.h"

void detector_begin();
// rgb: 96×96 RGB888 (feed.py가 보낸 프레임). 검출을 out에 최대 max개 채우고 개수를 돌려준다. 실패하면 -1
int detector_run(const uint8_t *rgb, Detection *out, int max, uint32_t *infer_ms);
