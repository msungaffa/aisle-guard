// 모든 소스가 설정을 읽는 한 곳: secrets.h(개인 값) → 아래 기본값
#pragma once
#if __has_include("secrets.h")
#include "secrets.h"
#else
#error "secrets.example.h를 secrets.h로 복사하세요"
#endif

#define FW_VERSION "0.1.0"

// 1이면 Edge Impulse 모델(firmware/libraries/aisle-guard-v2_inferencing), 0이면 검출 없음 스텁(배선 시험용)
#ifndef DETECTOR_EI
#define DETECTOR_EI 1
#endif
#define EI_HEADER <aisle-guard-v2_inferencing.h>
#ifndef MODEL_VERSION
#define MODEL_VERSION "ei1155430-d1"
#endif
#define EI_MIN_SCORE 0.3f   // 모델이 내보내는 최저 점수. 판정은 logic의 CONF_MIN(0.6)으로 다시 거른다

#ifndef DEVICE_ID
#define DEVICE_ID "aisle-cam-01"
#endif

#define LED_PIN 21               // XIAO ESP32S3 사용자 LED (LOW가 켜짐)
#define HEARTBEAT_MS 60000UL
#define WIFI_RETRY_MS 15000UL
#define HTTP_TIMEOUT_MS 8000
#define FRAME_LOG 1              // 1이면 프레임마다 한 줄 출력 (검증용)
