#include "uploader.h"

#include <Arduino.h>
#include <HTTPClient.h>
#include <NetworkClientSecure.h>

#include "logic.h"
#include "net.h"
#include "proto.h"
#include "settings.h"

static EventQueue queue;
static SemaphoreHandle_t lock;
static char sending[EventQueue::LEN];

static int post_once(const char *json) {
  NetworkClientSecure client;
  client.useBuiltinCACertBundle();  // 인증서 검사를 끄지 않는다
  HTTPClient http;
  char url[128];
  snprintf(url, sizeof url, "%s/rest/v1/aisle_events", SUPABASE_URL);
  if (!http.begin(client, url)) return HTTPC_ERROR_CONNECTION_REFUSED;
  http.setConnectTimeout(HTTP_TIMEOUT_MS);
  http.setTimeout(HTTP_TIMEOUT_MS);
  http.addHeader("Content-Type", "application/json");
  http.addHeader("apikey", SUPABASE_ANON_KEY);
  http.addHeader("Prefer", "return=minimal");
  int code = http.POST((uint8_t *)json, strlen(json));
  if (code >= 400) Serial.printf("[up] code=%d body=%s\n", code, http.getString().c_str());
  http.end();
  return code;
}

static void task(void *) {
  for (;;) {
    bool have = false;
    // SNTP가 도는 동안 보내면 DNS 콜백 경합으로 lwIP assert가 난다 (net.cpp)
    if (net_connected() && net_time_done()) {
      xSemaphoreTake(lock, portMAX_DELAY);
      if (!queue.empty()) {
        strncpy(sending, queue.front(), sizeof sending);
        have = true;
      }
      xSemaphoreGive(lock);
    }
    if (!have) {
      vTaskDelay(pdMS_TO_TICKS(200));
      continue;
    }

    SendAction action = SendAction::Retry;
    for (uint32_t attempt = 0; attempt <= PROTO_MAX_RETRIES; attempt++) {
      uint32_t t0 = millis();
      int code = post_once(sending);
      action = proto_classify(code);
      Serial.printf("[up] code=%d %lums try=%lu\n", code, (unsigned long)(millis() - t0),
                    (unsigned long)attempt + 1);
      if (action != SendAction::Retry || !net_connected()) break;
      vTaskDelay(pdMS_TO_TICKS(proto_retry_delay_ms(attempt + 1)));
    }
    // 성공이나 다시 보내도 안 되는 오류(키·형식)는 큐에서 뺀다. 네트워크 문제면 남겨 두고 재연결 후 다시 보낸다
    if (action != SendAction::Retry) {
      xSemaphoreTake(lock, portMAX_DELAY);
      if (!queue.empty() && strcmp(queue.front(), sending) == 0) queue.pop();
      xSemaphoreGive(lock);
      if (action == SendAction::Fatal) Serial.printf("[up] dropped: %s\n", sending);
    } else {
      vTaskDelay(pdMS_TO_TICKS(5000));
    }
  }
}

void uploader_begin() {
  lock = xSemaphoreCreateMutex();
  xTaskCreatePinnedToCore(task, "uploader", 12288, nullptr, 1, nullptr, 0);
}

void uploader_enqueue(const char *json) {
  xSemaphoreTake(lock, portMAX_DELAY);
  int before = queue.dropped();
  queue.push(json);
  int dropped = queue.dropped() - before;
  int n = queue.size();
  xSemaphoreGive(lock);
  Serial.printf("[up] queued (%d pending)%s\n", n, dropped ? " - oldest dropped" : "");
}

int uploader_pending() {
  xSemaphoreTake(lock, portMAX_DELAY);
  int n = queue.size();
  xSemaphoreGive(lock);
  return n;
}
