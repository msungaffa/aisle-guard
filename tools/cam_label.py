"""카메라 모드 재학습 데이터: screen.py가 저장한 보드 화면(<log>_views/v<재생 ms>.png, 96×96)에 박스 라벨을 단다.

보드 화면 하나마다
1. 파일 이름 ms 근처(-1.2초 ~ +0.3초, 0.1초 간격)의 demo.mp4 시각을 demo.json 구간으로 클립 프레임에 대응시키고
2. 그 깨끗한 프레임(aisle.json crop, 96×96)을 ECC(호모그래피)로 보드 화면에 맞춰 상관이 가장 높은 시각을 고른다
   (좌우 반전된 회차가 있어 뒤집은 화면도 시도, 뒤집힌 쪽이 맞으면 바로잡은 화면을 저장)
3. 그 프레임의 autolabel 박스를 호모그래피로 옮겨 보드 화면 좌표 박스로 쓴다
상관이 --min-corr 미만이면 버린다. 결과: <out>/{training,testing}/*.png + bounding_boxes.labels, 눈 확인 시트.

사용: python tools/cam_label.py tools/logs/cam_demo6_views tools/logs/cam_demo7_views --out tools/frames_cam
      python tools/ei_upload.py tools/frames_cam --labels
"""
import argparse
import glob
import json
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import autolabel  # noqa: E402
from aisle_frames import crop_square, load_crop  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SIZE = 288  # autolabel이 학습 프레임에서 쓰던 크기


class Demo:
    """demo.json 구간 → 클립 프레임(288)과 autolabel 박스, 시각별 캐시"""

    def __init__(self):
        spec = json.load(open(os.path.join(ROOT, "tools", "demo.json"), encoding="utf-8"))
        self.fps = spec["fps"]
        self.segs, t = [], 0.0
        self.clips = {}
        for seg in spec["segments"]:
            name = (seg.get("clip") or seg.get("hold_first") or seg.get("hold_last"))[:-4]
            frames = self.load(name)
            if "clip" in seg:
                dur, idx = len(frames) / self.fps, None
            else:
                dur, idx = seg["sec"], 0 if "hold_first" in seg else len(frames) - 1
            self.segs.append((t, t + dur, name, idx))
            t += dur
        self.crop = load_crop()
        cfg = json.load(open(os.path.join(ROOT, "tools", "aisle.json"), encoding="utf-8"))
        autolabel.AISLE = cfg.get("aisle_96")
        self.bgs, self.statics, self.cache = {}, {}, {}

    def load(self, name):
        if name not in self.clips:
            cap, out = cv2.VideoCapture(os.path.join(ROOT, "videos", name + ".mp4")), []
            while True:
                ok, f = cap.read()
                if not ok:
                    break
                out.append(f)
            self.clips[name] = out
        return self.clips[name]

    def at(self, t):
        """demo 시각 t초의 (96 BGR, 288 박스들) 또는 None"""
        key = round(t, 1)
        if key in self.cache:
            return self.cache[key]
        res = None
        for a, b, name, idx in self.segs:
            if a <= t < b:
                frames = self.clips[name]
                i = idx if idx is not None else min(len(frames) - 1, int((t - a) * self.fps))
                img = cv2.resize(crop_square(frames[i], self.crop), (SIZE, SIZE), interpolation=cv2.INTER_AREA)
                bkey = autolabel.BACKGROUND.get(name, ("C1", 0))
                if bkey not in self.bgs:
                    self.bgs[bkey] = autolabel.read_frame(bkey[0], bkey[1], self.crop, SIZE)
                if name in autolabel.STATIC and name not in self.statics:
                    simg = autolabel.read_frame(*autolabel.STATIC[name], self.crop, SIZE)
                    self.statics[name] = (autolabel.static_box(simg, self.bgs[bkey]), simg)
                st, simg = self.statics.get(name, (None, None))
                boxes = autolabel.boxes_for(img, self.bgs[bkey], st, simg)
                res = (cv2.resize(img, (96, 96), interpolation=cv2.INTER_AREA), boxes)
                break
        self.cache[key] = res
        return res


def gray(img):
    return cv2.GaussianBlur(cv2.equalizeHist(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)), (5, 5), 0).astype(np.float32)


def ecc(ref, view):
    H = np.eye(3, dtype=np.float32)
    try:
        score, H = cv2.findTransformECC(gray(ref), gray(view), H, cv2.MOTION_HOMOGRAPHY,
                                        (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 100, 1e-4), None, 5)
    except cv2.error:
        return -1.0, None
    return score, H


def warp_box(b, H):
    s = 96 / SIZE
    x, y, w, h = b["x"] * s, b["y"] * s, b["width"] * s, b["height"] * s
    pts = cv2.perspectiveTransform(np.float32([[x, y], [x + w, y], [x + w, y + h], [x, y + h]])[None], H)[0]
    x0, y0 = np.clip(pts.min(axis=0), 0, 96)
    x1, y1 = np.clip(pts.max(axis=0), 0, 96)
    if (x1 - x0) < 3 or (y1 - y0) < 3:
        return None
    return {"label": b["label"], "x": int(x0), "y": int(y0), "width": int(round(x1 - x0)), "height": int(round(y1 - y0))}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("views", nargs="+")
    ap.add_argument("--out", default=os.path.join(ROOT, "tools", "frames_cam"))
    ap.add_argument("--min-corr", type=float, default=0.75)
    ap.add_argument("--test-every", type=int, default=5, help="n장마다 1장은 testing")
    args = ap.parse_args()
    demo = Demo()
    labels = {"training": {}, "testing": {}}
    tiles, kept, dropped, n = [], 0, 0, 0
    for vdir in args.views:
        run = os.path.basename(vdir.rstrip("/\\")).replace("_views", "")
        for f in sorted(glob.glob(os.path.join(vdir, "v*.png"))):
            view = cv2.imdecode(np.fromfile(f, np.uint8), cv2.IMREAD_COLOR)
            ms = int(os.path.basename(f)[1:-4])
            best = (-1.0, None, None, None)
            for flip in (False, True):
                v = cv2.flip(view, 1) if flip else view
                for dt in np.arange(-1.2, 0.31, 0.1):
                    fr = demo.at(ms / 1000 + dt)
                    if fr is None:
                        continue
                    score, H = ecc(fr[0], v)
                    if score > best[0]:
                        best = (score, H, fr[1], v)
            score, H, boxes, v = best
            if score < args.min_corr:
                dropped += 1
                continue
            out = [wb for wb in (warp_box(b, H) for b in boxes) if wb]
            # 아래 절반에만 있는 person 박스는 대부분 그림자·다리 조각(손떨림으로 어긋남) → 물건 옆 가짜 사람을 배우지 않게 뺀다
            out = [b for b in out if b["label"] != "person" or b["y"] < 48]
            cat = "testing" if n % args.test_every == args.test_every - 1 else "training"
            n += 1
            name = f"{run}_{ms:06d}.png"
            os.makedirs(os.path.join(args.out, cat), exist_ok=True)
            cv2.imencode(".png", v)[1].tofile(os.path.join(args.out, cat, name))
            labels[cat][name] = out
            kept += 1
            vis = cv2.resize(v, (192, 192), interpolation=cv2.INTER_NEAREST)
            for b in out:
                col = (0, 0, 255) if b["label"] == "obstacle" else (0, 255, 0)
                cv2.rectangle(vis, (b["x"] * 2, b["y"] * 2), ((b["x"] + b["width"]) * 2, (b["y"] + b["height"]) * 2),
                              col, 2)
            cv2.putText(vis, f"{run[-1]} {ms / 1000:.1f} {score:.2f}", (3, 14), cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                        (255, 255, 0), 1)
            tiles.append(vis)
    for cat, lab in labels.items():
        if lab:
            json.dump({"version": 1, "type": "bounding-box-labels", "boundingBoxes": lab},
                      open(os.path.join(args.out, cat, "bounding_boxes.labels"), "w", encoding="utf-8"))
        n_obs = sum(b["label"] == "obstacle" for v in lab.values() for b in v)
        n_per = sum(b["label"] == "person" for v in lab.values() for b in v)
        print(f"{cat}: {len(lab)} images, obstacle {n_obs}, person {n_per}")
    print(f"kept {kept}, dropped {dropped} (ECC corr < {args.min_corr})")
    for i in range(0, len(tiles), 60):
        chunk = tiles[i:i + 60]
        while len(chunk) % 10:
            chunk.append(np.zeros_like(tiles[0]))
        sheet = np.vstack([np.hstack(chunk[r:r + 10]) for r in range(0, len(chunk), 10)])
        cv2.imencode(".jpg", sheet, [cv2.IMWRITE_JPEG_QUALITY, 80])[1].tofile(
            os.path.join(args.out, f"sheet_{i // 60}.jpg"))


if __name__ == "__main__":
    main()
