"""시나리오 5용 정지 화면: C1 마지막 화면의 상자를 잘라 통로 다각형 오른쪽 바깥 바닥(96 좌표 약 83,45)에 붙인다.
빈 바탕은 C1 첫 화면. 결과: videos/outside_box.png (tools/scenario5.json이 씀)
사용: python tools/make_outside.py
"""
import os

import cv2

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VID = os.path.join(ROOT, "videos")


def main():
    cap = cv2.VideoCapture(os.path.join(VID, "C1.mp4"))
    frames = []
    while True:
        ok, f = cap.read()
        if not ok:
            break
        frames.append(f)
    empty, last = frames[0], frames[-1]
    box = last[546:656, 593:707]  # C1 마지막 화면의 상자 (1280x720 좌표)
    w = 60
    h = int(box.shape[0] * w / box.shape[1])
    small = cv2.resize(box, (w, h), interpolation=cv2.INTER_AREA)
    cx, bottom = 788, 528  # 오른쪽 노란 선과 다각형 바깥, 선반 앞 바닥
    img = empty.copy()
    img[bottom - h:bottom, cx - w // 2:cx - w // 2 + w] = small
    # 한글 경로에서도 되도록 imencode 후 쓴다
    cv2.imencode(".png", img)[1].tofile(os.path.join(VID, "outside_box.png"))
    print("videos/outside_box.png")


if __name__ == "__main__":
    main()
