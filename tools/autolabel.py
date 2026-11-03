"""고정 카메라라 빈 통로 화면과의 차이로 물체 박스를 찾아 Edge Impulse 라벨 초안을 만든다.

- 클립마다 빈 통로 기준 화면을 쓴다 (클립에 따라 처음/끝 프레임, 기본은 C1 첫 프레임).
- 놓인 물건: 클립마다 물건이 혼자 보이는 프레임(STATIC)에서 위치를 잡고, 그 자리가 그 모습과 비슷하면 obstacle.
- 사람: 물건 자리를 뺀 나머지 차이 덩어리 중 중심이 통로 다각형 안인 것. 들고 가는 상자는 사람에 포함된다.
- 결과: tools/frames/<cat>/bounding_boxes.labels (EI 형식) + tools/frames/labels_sheet_<n>.jpg (눈 확인용)

사용: python tools/autolabel.py            → 확인 후 python tools/ei_upload.py tools/frames --labels
"""
import glob
import json
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from aisle_frames import crop_square, load_crop  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRAMES = os.path.join(ROOT, "tools", "frames")
# 클립별 빈 통로 기준: (클립, 프레임 번호). -1은 마지막 프레임
BACKGROUND = {"C1": ("C1", 0), "C2": ("C1", 0), "C3": ("C3", -1), "C4": ("C4", 0), "C5": ("C1", 0)}
# 놓인 물건이 혼자 보이는 프레임 (그 자리를 obstacle 위치로 쓴다)
STATIC = {"C1": ("C1", -1), "C2": ("C2", -1), "C3": ("C3", 0), "C4": ("C4", -1)}
DIFF_T = 40
MIN_AREA = 0.004   # 화면 넓이 대비
PERSON_MIN = 0.012  # 사람 덩어리 최소 넓이 (다리 그림자 조각 제외)
SAME_T = 35        # 물건 자리가 기준 모습과 이 값보다 비슷하면(평균 차이) 물건이 있다
AISLE = None       # aisle.json의 aisle_96 (다각형)


def read_frame(clip, idx, crop, size):
    cap = cv2.VideoCapture(os.path.join(ROOT, "videos", clip + ".mp4"))
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.set(cv2.CAP_PROP_POS_FRAMES, n - 1 if idx < 0 else idx)
    ok, f = cap.read()
    cap.release()
    return cv2.resize(crop_square(f, crop), (size, size), interpolation=cv2.INTER_AREA)


def diff_mask(img, bg):
    d = cv2.absdiff(cv2.GaussianBlur(img, (5, 5), 0), cv2.GaussianBlur(bg, (5, 5), 0)).max(axis=2)
    m = (d > DIFF_T).astype(np.uint8) * 255
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    return cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))


def in_aisle(x, y, size):
    if not AISLE:
        return True
    poly = (np.array(AISLE, np.float32).reshape(-1, 2) * size / 96.0)
    return cv2.pointPolygonTest(poly, (float(x), float(y)), False) >= 0


def static_box(img, bg):
    """혼자 있는 물건의 박스. 그림자 꼬리는 가로 폭이 최대의 50% 미만인 줄을 잘라 없앤다"""
    m = diff_mask(img, bg)
    size = m.shape[0]
    best = None
    for c in cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0]:
        x, y, w, h = cv2.boundingRect(c)
        if w * h < MIN_AREA * size * size or not in_aisle(x + w / 2, y + h / 2, size) or y < size * 0.3:
            continue
        if best is None or w * h > best[2] * best[3]:
            best = (x, y, w, h)
    if best is None:
        return None
    x, y, w, h = best
    rows = (m[y:y + h, x:x + w] > 0).sum(axis=1)
    keep = np.where(rows >= 0.5 * rows.max())[0]
    # 윗면은 폭이 좁아 잘리므로 위로 10px 넓힌다
    top = max(0, y + int(keep[0]) - 10)
    return (x, top, w, y + int(keep[-1]) + 1 - top)


def boxes_for(img, bg, static, static_img):
    out = []
    m = diff_mask(img, bg)
    size = m.shape[0]
    if static:
        x, y, w, h = static
        same = cv2.absdiff(img[y:y + h, x:x + w], static_img[y:y + h, x:x + w]).mean()
        if same < SAME_T:
            out.append({"label": "obstacle", "x": x, "y": y, "width": w, "height": h})
        # 물건 자리(조금 넓혀서)는 사람 찾기에서 뺀다
        m[max(0, y - 16):y + h + 12, max(0, x - 6):x + w + 6] = 0
    for c in cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0]:
        x, y, bw, bh = cv2.boundingRect(c)
        # 사람은 통로 밖이어도 라벨을 단다 (안 달면 모델이 사람을 배경으로 배운다)
        if bw < 0.07 * size or bw * bh < PERSON_MIN * size * size:
            continue
        out.append({"label": "person", "x": int(x), "y": int(y), "width": int(bw), "height": int(bh)})
    return out


def main():
    global AISLE
    crop = load_crop()
    cfg = json.load(open(os.path.join(ROOT, "tools", "aisle.json"), encoding="utf-8"))
    AISLE = cfg.get("aisle_96")
    bgs, statics = {}, {}
    sheets, tiles = 0, []
    for cat in ("training", "testing"):
        labels = {}
        for path in sorted(glob.glob(os.path.join(FRAMES, cat, "*.jpg"))):
            name = os.path.basename(path)
            clip = name.split("_")[0]
            img = cv2.imdecode(np.fromfile(path, np.uint8), cv2.IMREAD_COLOR)
            size = img.shape[0]
            key = BACKGROUND.get(clip, ("C1", 0))
            if key not in bgs:
                bgs[key] = read_frame(key[0], key[1], crop, size)
            if clip in STATIC and clip not in statics:
                simg = read_frame(*STATIC[clip], crop, size)
                statics[clip] = (static_box(simg, bgs[key]), simg)
                print(f"{clip}: static object box {statics[clip][0]}")
            st, simg = statics.get(clip, (None, None))
            bxs = boxes_for(img, bgs[key], st, simg)
            labels[name] = bxs
            vis = img.copy()
            for b in bxs:
                col = (0, 0, 255) if b["label"] == "obstacle" else (0, 255, 0)
                cv2.rectangle(vis, (b["x"], b["y"]), (b["x"] + b["width"], b["y"] + b["height"]), col, 2)
            cv2.putText(vis, f"{cat[:2]} {name[:-4]}", (3, 14), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 0), 1)
            tiles.append(cv2.resize(vis, (192, 192)))
        with open(os.path.join(FRAMES, cat, "bounding_boxes.labels"), "w", encoding="utf-8") as f:
            json.dump({"version": 1, "type": "bounding-box-labels", "boundingBoxes": labels}, f)
        n_obs = sum(b["label"] == "obstacle" for v in labels.values() for b in v)
        n_per = sum(b["label"] == "person" for v in labels.values() for b in v)
        print(f"{cat}: {len(labels)} images, obstacle {n_obs}, person {n_per}")
    # 눈 확인용 시트 (10열)
    for i in range(0, len(tiles), 50):
        chunk = tiles[i:i + 50]
        while len(chunk) % 10:
            chunk.append(np.zeros_like(tiles[0]))
        sheet = np.vstack([np.hstack(chunk[r:r + 10]) for r in range(0, len(chunk), 10)])
        ok, jpg = cv2.imencode(".jpg", sheet, [cv2.IMWRITE_JPEG_QUALITY, 80])
        open(os.path.join(FRAMES, f"labels_sheet_{sheets}.jpg"), "wb").write(jpg.tobytes())
        sheets += 1
    print(f"sheets: {sheets} in {FRAMES}")


if __name__ == "__main__":
    main()
