"""학습용 프레임 추출: videos/C1.mp4~C5.mp4 → tools/frames/{training,testing}/<클립>_<번호>.jpg

- feed.py와 같은 영역(tools/aisle.json의 crop, 없으면 가운데 정사각형)을 잘라 --size×--size로 저장한다.
  Edge Impulse가 96×96으로 줄이므로 보드 입력과 같은 그림이 된다 (라벨 달기 편하게 기본 288).
- 클립마다 마지막 --test-ratio(기본 0.3) 구간은 testing으로 보낸다 (HANDOFF "데이터 흐름").

사용: python tools/extract_frames.py videos/C1.mp4 videos/C2.mp4 ... --fps 3
      python tools/extract_frames.py videos --fps 3        # 폴더면 C*.mp4 전부
다음: python tools/ei_upload.py tools/frames
"""
import argparse
import glob
import os
import shutil
import sys

import cv2

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from aisle_frames import crop_square, load_crop  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames")


def extract(path, fps, size, test_ratio, crop, out):
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        sys.exit(f"cannot open {path}")
    src_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    dur_ms = total * 1000.0 / src_fps
    test_from = dur_ms * (1 - test_ratio)
    name = os.path.splitext(os.path.basename(path))[0]
    step, next_ms, idx, n = 1000.0 / fps, 0.0, 0, {"training": 0, "testing": 0}
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        t = idx * 1000.0 / src_fps
        idx += 1
        if t + 1e-6 < next_ms:
            continue
        next_ms += step
        cat = "testing" if t >= test_from else "training"
        img = cv2.resize(crop_square(frame, crop), (size, size), interpolation=cv2.INTER_AREA)
        # imwrite는 한글 경로에서 조용히 실패한다 → 인코딩 후 직접 쓴다
        ok, jpg = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 92])
        with open(os.path.join(out, cat, f"{name}_{int(t):06d}.jpg"), "wb") as f:
            f.write(jpg.tobytes())
        n[cat] += 1
    cap.release()
    print(f"{name}: {dur_ms / 1000:.1f}s -> training {n['training']}, testing {n['testing']}")
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("inputs", nargs="+")
    ap.add_argument("--fps", type=float, default=3.0)
    ap.add_argument("--size", type=int, default=288)
    ap.add_argument("--test-ratio", type=float, default=0.3)
    ap.add_argument("--out", default=OUT)
    args = ap.parse_args()

    paths = []
    for p in args.inputs:
        paths += sorted(glob.glob(os.path.join(p, "C*.mp4"))) if os.path.isdir(p) else [p]
    if not paths:
        sys.exit("no videos")
    if os.path.isdir(args.out):
        shutil.rmtree(args.out)
    for cat in ("training", "testing"):
        os.makedirs(os.path.join(args.out, cat))
    crop = load_crop()
    print(f"crop={crop or 'center square'} fps={args.fps} size={args.size}")
    tot = {"training": 0, "testing": 0}
    for p in paths:
        for k, v in extract(p, args.fps, args.size, args.test_ratio, crop, args.out).items():
            tot[k] += v
    print(f"total training {tot['training']}, testing {tot['testing']} -> {args.out}")


if __name__ == "__main__":
    main()
