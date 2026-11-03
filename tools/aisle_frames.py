"""영상 프레임을 모델 입력(96×96 RGB)으로 바꾸는 공통 함수. feed.py(시연)와 extract_frames.py(학습)가 같이 써서
학습 사진과 보드 입력이 같은 방식으로 잘리게 한다.

잘라낼 영역은 tools/aisle.json의 "crop": [x, y, w, h] (원본 영상 픽셀). 없으면 가운데 정사각형.
"""
import json
import os

import cv2

MODEL_SIZE = 96
CONFIG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "aisle.json")


def load_crop():
    if os.path.exists(CONFIG):
        with open(CONFIG, encoding="utf-8") as f:
            crop = json.load(f).get("crop")
        if crop:
            return tuple(int(v) for v in crop)
    return None


def crop_square(frame_bgr, crop=None):
    h, w = frame_bgr.shape[:2]
    if crop is None:
        side = min(w, h)
        crop = ((w - side) // 2, (h - side) // 2, side, side)
    x, y, cw, ch = crop
    x, y = max(0, x), max(0, y)
    return frame_bgr[y:y + ch, x:x + cw]


def to_model_rgb(frame_bgr, crop=None, size=MODEL_SIZE):
    """잘라서 size×size로 줄인 RGB uint8 배열"""
    sq = crop_square(frame_bgr, crop)
    small = cv2.resize(sq, (size, size), interpolation=cv2.INTER_AREA)
    return cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
