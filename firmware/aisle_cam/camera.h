// 보드 카메라 입력 (카메라 모드). QVGA RGB565에서 정사각형을 잘라 96×96 RGB888로 줄인다.
// USB 프레임(feed.py)과 같은 크기·형식이라 같은 검출·판정으로 넘긴다.
#pragma once
#include <stdint.h>

bool camera_begin();
// 자동 노출 목표 (-2 어둡게 ~ 2 밝게)
void camera_set_ae(int level);
// 좌우·상하 반전 (손에 든 방향에 맞춘다)
void camera_set_mirror(bool h, bool v);
// 잘라낼 정사각형 (QVGA 320×240 좌표). 기본은 가운데 240×240
void camera_set_crop(int x, int y, int side);
void camera_get_crop(int *x, int *y, int *side);
// 한 장 찍어 rgb(96*96*3)에 쓴다. 실패하면 false
bool camera_grab96(uint8_t *rgb);
