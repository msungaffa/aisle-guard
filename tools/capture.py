"""학습 사진 수집. 보드에 firmware/capture_cam을 올린 뒤 실행한다.

일정 간격으로 보드에 'p'를 보내 QVGA JPEG을 받고, 가운데 240x240을 잘라 저장한다.
(aisle_cam의 detector_ei.cpp도 가운데 정사각형을 잘라 모델에 넣으므로, 학습 사진과 실제 입력이 같아진다.)

사용: python tools/capture.py COM10 --label obstacle --every 1.5 --max 80
      장면 라벨(obstacle / person / mixed / empty)은 폴더 이름일 뿐이고, 박스 라벨은 Edge Impulse에서 단다.
저장: tools/captures/<label>/<시각>_<번호>.jpg  (git에 안 올라감)

시리얼 포트는 한 프로그램만 열 수 있다. Arduino 시리얼 모니터는 닫고 실행한다.
"""
import argparse
import io
import os
import time

import serial
from PIL import Image


def grab(s):
    s.reset_input_buffer()
    s.write(b"p")
    deadline = time.time() + 5
    while time.time() < deadline:
        line = s.readline().decode("ascii", "ignore").strip()
        if line.startswith("JPG "):
            try:
                return Image.open(io.BytesIO(bytes.fromhex(line[4:]))).convert("RGB")
            except ValueError:
                return None  # 줄이 잘렸다
    return None


def center_square(img):
    w, h = img.size
    side = min(w, h)
    x0, y0 = (w - side) // 2, (h - side) // 2
    return img.crop((x0, y0, x0 + side, y0 + side))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("port")
    ap.add_argument("--label", required=True)
    ap.add_argument("--every", type=float, default=1.5, help="몇 초마다 한 장")
    ap.add_argument("--max", type=int, default=0, help="0이면 Ctrl+C까지")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "captures"))
    a = ap.parse_args()
    out = os.path.join(a.out, a.label)
    os.makedirs(out, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    n = 0
    with serial.Serial(a.port, 115200, timeout=2) as s:
        time.sleep(2)  # 포트를 열면 보드가 재시작할 수 있다
        print(f"{a.port} 연결 - {a.every}초마다 한 장, Ctrl+C로 끝. 저장 위치 {out}")
        try:
            while not a.max or n < a.max:
                t0 = time.time()
                img = grab(s)
                if img is None:
                    print("\n  받기 실패, 다시 시도")
                    continue
                center_square(img).save(os.path.join(out, f"{stamp}_{n:04d}.jpg"), quality=95)
                n += 1
                print(f"\r  {n}장 (물건을 옮기세요)", end="", flush=True)
                time.sleep(max(0.0, a.every - (time.time() - t0)))
        except KeyboardInterrupt:
            pass
    print(f"\n{n}장 저장: {out}")


if __name__ == "__main__":
    main()
