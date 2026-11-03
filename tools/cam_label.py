"""카메라 모드 재학습 데이터: screen.py가 저장한 보드 화면(96×96, tools/logs/<log>_views/v<재생 ms>.png)에
깨끗한 클립 프레임의 라벨(tools/frames/*/bounding_boxes.labels, autolabel.py 결과)을 옮겨 단다.

1. 재생 ms - 지연(--lat) → demo.json 구간 → (클립, 클립 ms) → 가장 가까운 라벨 프레임(±200ms)
2. 그 깨끗한 프레임 → 보드 화면 호모그래피(ECC, view_check.py와 같은 방식). 상관 0.6 미만이면 버린다
3. 박스 네 꼭짓점을 옮겨 감싸는 사각형 → 96×96 좌표
결과: tools/cam_frames/{training,testing}/<run>_<ms>.png + bounding_boxes.labels (EI 형식, ei_upload.py --labels로 올림)
      tools/cam_frames/sheet_<n>.jpg (눈 확인용)

사용: python tools/cam_label.py tools/logs/cam_demo6_views tools/logs/cam_demo7_views --test tools/logs/cam_record3_views
"""
import argparse
import glob
import json
import os
import re

import cv2
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRAMES = os.path.join(ROOT, "tools", "frames")
OUT = os.path.join(ROOT, "tools", "cam_frames")
CLIP_MS = 10000


def load_labels():
    """{(클립, ms): (이미지 경로, [박스])}"""
    out = {}
    for split in ("training", "testing"):
        path = os.path.join(FRAMES, split, "bounding_boxes.labels")
        if not os.path.exists(path):
            continue
        boxes = json.load(open(path, encoding="utf-8"))["boundingBoxes"]
        for name, bb in boxes.items():
            m = re.match(r"(C\d)_(\d+)\.", name)
            if m:
                out[(m[1], int(m[2]))] = (os.path.join(FRAMES, split, name), bb)
    return out


def demo_to_clip(t_ms, spec, starts):
    """demo.mp4 시각 → (클립, 클립 ms)"""
    i = max(k for k, s in enumerate(starts) if s * 1000 <= t_ms)
    seg, off = spec["segments"][i], t_ms - starts[i] * 1000
    if "clip" in seg:
        return seg["clip"][:2], seg.get("from", 0) * 1000 + off
    if "hold_first" in seg:
        return seg["hold_first"][:2], 0
    if "hold_last" in seg:
        return seg["hold_last"][:2], CLIP_MS
    return None, None


def gray(img, size):
    g = cv2.cvtColor(cv2.resize(img, (size, size), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY)
    return cv2.GaussianBlur(g, (5, 5), 0).astype(np.float32)


def homography(ref, view):
    """깨끗한 프레임 좌표(96) → 보드 화면 좌표(96). 실패하면 (None, 상관)"""
    H = np.eye(3, dtype=np.float32)
    crit = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 200, 1e-5)
    score, prev = 0.0, None
    for size in (48, 96):
        if prev is not None:
            s = size / prev
            H = (np.diag([s, s, 1]) @ H @ np.diag([1 / s, 1 / s, 1])).astype(np.float32)
        try:
            score, H = cv2.findTransformECC(gray(ref, size), gray(view, size), H, cv2.MOTION_HOMOGRAPHY, crit, None, 5)
        except cv2.error:
            return None, 0.0
        prev = size
    return (H if score >= 0.6 else None), score


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("views", nargs="+", help="학습용 보드 화면 폴더")
    ap.add_argument("--test", nargs="*", default=[], help="시험 세트로 둘 보드 화면 폴더")
    ap.add_argument("--lat", type=int, default=400, help="화면·카메라 지연 ms (보드 화면은 이만큼 늦은 장면)")
    args = ap.parse_args()

    spec = json.load(open(os.path.join(ROOT, "tools", "demo.json"), encoding="utf-8"))
    starts = json.load(open(os.path.join(ROOT, "videos", "demo_truth.json"), encoding="utf-8"))["segment_starts"]
    labels = load_labels()
    keys_by_clip = {}
    for c, ms in labels:
        keys_by_clip.setdefault(c, []).append(ms)

    stats = {"ok": 0, "no_label": 0, "ecc": 0}
    sheet = []
    for split, dirs in (("training", args.views), ("testing", args.test)):
        out_dir = os.path.join(OUT, split)
        os.makedirs(out_dir, exist_ok=True)
        result = {}
        for d in dirs:
            run = os.path.basename(os.path.normpath(d)).replace("_views", "")
            for path in sorted(glob.glob(os.path.join(d, "v*.png"))):
                t = int(re.search(r"v(\d+)\.png$", path)[1]) - args.lat
                if t < 0:
                    continue
                clip, cms = demo_to_clip(t, spec, starts)
                near = min(keys_by_clip.get(clip, []), key=lambda k: abs(k - cms), default=None)
                if near is None or abs(near - cms) > 200:
                    stats["no_label"] += 1
                    continue
                ref_path, boxes = labels[(clip, near)]
                ref = cv2.imdecode(np.fromfile(ref_path, np.uint8), cv2.IMREAD_COLOR)
                view = cv2.imdecode(np.fromfile(path, np.uint8), cv2.IMREAD_COLOR)
                s = 96.0 / ref.shape[1]
                H, score = homography(cv2.resize(ref, (96, 96), interpolation=cv2.INTER_AREA), view)
                if H is None:
                    stats["ecc"] += 1
                    continue
                out_boxes = []
                for b in boxes:
                    x, y, w, h = (b[k] * s for k in ("x", "y", "width", "height"))
                    pts = cv2.perspectiveTransform(np.float32([[x, y], [x + w, y], [x + w, y + h], [x, y + h]])[None], H)[0]
                    x0, y0 = np.clip(pts.min(0), 0, 96)
                    x1, y1 = np.clip(pts.max(0), 0, 96)
                    if x1 - x0 >= 3 and y1 - y0 >= 3:
                        out_boxes.append({"label": b["label"], "x": int(round(x0)), "y": int(round(y0)),
                                          "width": int(round(x1 - x0)), "height": int(round(y1 - y0))})
                name = f"{run}_{t + args.lat:06d}.png"
                cv2.imencode(".png", view)[1].tofile(os.path.join(out_dir, name))
                result[name] = out_boxes
                stats["ok"] += 1
                if len(sheet) < 400 and stats["ok"] % 4 == 0:
                    big = cv2.resize(view, (192, 192), interpolation=cv2.INTER_NEAREST)
                    for b in out_boxes:
                        color = (0, 0, 255) if b["label"] == "obstacle" else (0, 255, 0)
                        cv2.rectangle(big, (b["x"] * 2, b["y"] * 2), ((b["x"] + b["width"]) * 2,
                                                                      (b["y"] + b["height"]) * 2), color, 2)
                    cv2.putText(big, f"{name[-10:-4]} {score:.2f}", (3, 14), 0, 0.4, (0, 255, 255), 1)
                    sheet.append(big)
        json.dump({"version": 1, "type": "bounding-box-labels", "boundingBoxes": result},
                  open(os.path.join(out_dir, "bounding_boxes.labels"), "w", encoding="utf-8"))
        print(f"{split}: {len(result)} images")
    for n in range(0, len(sheet), 48):
        part = sheet[n:n + 48]
        while len(part) % 8:
            part.append(np.zeros_like(sheet[0]))
        cv2.imwrite(os.path.join(OUT, f"sheet_{n // 48}.jpg"),
                    np.vstack([np.hstack(part[i:i + 8]) for i in range(0, len(part), 8)]))
    print(stats)


if __name__ == "__main__":
    main()
