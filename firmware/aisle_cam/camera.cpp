// 카메라 핀은 capture_cam과 같다 (XIAO ESP32S3 Sense, PPE에서 실기 확인)
#include "camera.h"

#include <Arduino.h>
#include <esp_camera.h>

#include "proto.h"

static const int CAM_W = 320, CAM_H = 240;
static int crop_x = 40, crop_y = 0, crop_side = 240;

bool camera_begin() {
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
  c.pixel_format = PIXFORMAT_RGB565;
  c.frame_size = FRAMESIZE_QVGA;
  c.fb_count = 2;
  c.fb_location = CAMERA_FB_IN_PSRAM;
  c.grab_mode = CAMERA_GRAB_LATEST;
  esp_err_t err = esp_camera_init(&c);
  if (err != ESP_OK) {
    Serial.printf("[cam] init failed 0x%x\n", err);
    return false;
  }
  camera_set_ae(-1);  // 노트북 화면을 찍으면 가운데가 하얗게 날아가 검출이 0이 됨 → 한 단계 어둡게
  return true;
}

void camera_set_ae(int level) {
  sensor_t *s = esp_camera_sensor_get();
  if (s) s->set_ae_level(s, constrain(level, -2, 2));
}

void camera_set_crop(int x, int y, int side) {
  side = constrain(side, PROTO_FRAME_W, CAM_H);
  crop_x = constrain(x, 0, CAM_W - side);
  crop_y = constrain(y, 0, CAM_H - side);
  crop_side = side;
}

void camera_get_crop(int *x, int *y, int *side) {
  *x = crop_x;
  *y = crop_y;
  *side = crop_side;
}

bool camera_grab96(uint8_t *rgb) {
  camera_fb_t *fb = esp_camera_fb_get();
  if (!fb) return false;
  if (fb->format != PIXFORMAT_RGB565 || (int)fb->width != CAM_W || (int)fb->height != CAM_H) {
    esp_camera_fb_return(fb);
    return false;
  }
  const uint8_t *src = fb->buf;
  // 출력 한 칸 = 원본 블록 평균 (INTER_AREA와 비슷하게, feed.py 쪽 줄이기와 맞춤)
  for (int oy = 0; oy < PROTO_FRAME_H; oy++) {
    int y0 = crop_y + oy * crop_side / PROTO_FRAME_H, y1 = crop_y + (oy + 1) * crop_side / PROTO_FRAME_H;
    for (int ox = 0; ox < PROTO_FRAME_W; ox++) {
      int x0 = crop_x + ox * crop_side / PROTO_FRAME_W, x1 = crop_x + (ox + 1) * crop_side / PROTO_FRAME_W;
      uint32_t r = 0, g = 0, b = 0, n = 0;
      for (int y = y0; y < y1; y++) {
        const uint8_t *p = src + (y * CAM_W + x0) * 2;
        for (int x = x0; x < x1; x++, p += 2) {
          uint16_t v = (uint16_t)(p[0] << 8 | p[1]);  // esp32-camera RGB565는 상위 바이트가 먼저
          r += (v >> 11) << 3;
          g += ((v >> 5) & 0x3F) << 2;
          b += (v & 0x1F) << 3;
          n++;
        }
      }
      uint8_t *o = rgb + (oy * PROTO_FRAME_W + ox) * 3;
      o[0] = r / n;
      o[1] = g / n;
      o[2] = b / n;
    }
  }
  esp_camera_fb_return(fb);
  return true;
}
