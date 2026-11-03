// 학습 사진 수집용 스케치. 시리얼로 'p'를 받으면 QVGA JPEG 한 장을 "JPG <hex>" 한 줄로 보낸다.
// PC 쪽은 tools/capture.py. 카메라 핀은 aisle_cam/camera.cpp와 같다(XIAO ESP32S3 Sense, PPE에서 실기 확인).
#include <Arduino.h>
#include <esp_camera.h>

static bool camera_begin() {
  camera_config_t c = {};
  c.pin_pwdn = -1;
  c.pin_reset = -1;
  c.pin_xclk = 10;
  c.pin_sccb_sda = 40;
  c.pin_sccb_scl = 39;
  c.pin_d7 = 48;
  c.pin_d6 = 11;
  c.pin_d5 = 12;
  c.pin_d4 = 14;
  c.pin_d3 = 16;
  c.pin_d2 = 18;
  c.pin_d1 = 17;
  c.pin_d0 = 15;
  c.pin_vsync = 38;
  c.pin_href = 47;
  c.pin_pclk = 13;
  c.xclk_freq_hz = 20000000;
  c.ledc_timer = LEDC_TIMER_0;
  c.ledc_channel = LEDC_CHANNEL_0;
  c.pixel_format = PIXFORMAT_JPEG;
  c.frame_size = FRAMESIZE_QVGA;  // aisle_cam의 감지 해상도와 같게
  c.jpeg_quality = 10;
  c.fb_count = 2;
  c.fb_location = CAMERA_FB_IN_PSRAM;
  c.grab_mode = CAMERA_GRAB_LATEST;
  esp_err_t err = esp_camera_init(&c);
  if (err != ESP_OK) {
    Serial.printf("[cam] init failed 0x%x\n", err);
    return false;
  }
  return true;
}

void setup() {
  Serial.begin(115200);
  delay(1500);
  Serial.println(camera_begin() ? "[cam] ready, send 'p'" : "[cam] FAILED");
}

void loop() {
  if (!Serial.available()) return;
  if (Serial.read() != 'p') return;
  // 오래된 프레임을 한 장 버려서 지금 장면을 찍는다
  camera_fb_t *fb = esp_camera_fb_get();
  if (fb) esp_camera_fb_return(fb);
  fb = esp_camera_fb_get();
  if (!fb) {
    Serial.println("[cam] capture failed");
    return;
  }
  Serial.print("JPG ");
  static const char hex[] = "0123456789abcdef";
  char buf[512];
  size_t n = 0;
  for (size_t i = 0; i < fb->len; i++) {
    buf[n++] = hex[fb->buf[i] >> 4];
    buf[n++] = hex[fb->buf[i] & 15];
    if (n == sizeof(buf)) {
      Serial.write((const uint8_t *)buf, n);
      n = 0;
    }
  }
  if (n) Serial.write((const uint8_t *)buf, n);
  Serial.println();
  esp_camera_fb_return(fb);
}
