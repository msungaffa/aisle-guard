"""카메라 모드 점검: screen.py가 저장한 보드 화면(tools/logs/<log>_views/v*.png, 96×96)을 PC에서 다시 본다.

1. 각 화면에 펌웨어와 같은 int8 모델(LiteRT)을 돌려 obstacle·person 칸을 표시
2. 기준 화면(영상의 빈 통로, aisle.json crop)에 ECC 정렬로 호모그래피를 구해
   기준 통로 다각형을 보드 화면 좌표로 옮기고, 보드에 넣을 "#AISLE ..." 명령을 제안
3. 결과를 시트 한 장(<views>_check.png)으로 저장: 화면 | 모델 출력 + 현재 다각형(초록) + 제안 다각형(주황)

카메라 시야와 화면 통로 칸이 어긋나 선반 상자가 다각형 안에 들어오는지 보드 없이 확인하기 위한 것.
매칭이 실패하면(점이 모자라거나 다각형이 화면 밖) 제안 없이 검출만 보여 준다.

사용: python tools/view_check.py tools/logs/screen_xxx_views [--ref-video videos/demo.mp4 --ref-sec 1]
"""
import argparse
import glob
import json
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from aisle_frames import crop_square, load_crop  # noqa: E402
from model_gate import labels_order, load_model_bytes  # noqa: E402
from simulate import fomo_detections  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UP = 4  # 그림 배율 (96 → 384)


def read_png(path):
    return cv2.imdecode(np.fromfile(path, np.uint8), cv2.IMREAD_COLOR)


def ref_frame(video, sec):
    cap = cv2.VideoCapture(video)
    cap.set(cv2.CAP_PROP_POS_MSEC, sec * 1000)
    ok, frame = cap.read()
    if not ok:
        sys.exit(f"cannot read {video} at {sec}s")
    return cv2.resize(crop_square(frame, load_crop()), (96 * UP, 96 * UP), interpolation=cv2.INTER_AREA)


def estimate_poly(ref_big, view_big, poly):
    """기준 화면 → 보드 화면 호모그래피(ECC, 작은 그림에서 큰 그림 순)로 다각형을 옮긴다. 실패하면 (None, 이유)"""
    def gray(img, size):
        g = cv2.cvtColor(cv2.resize(img, (size, size), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY)
        return cv2.GaussianBlur(g, (5, 5), 0).astype(np.float32)

    H = np.eye(3, dtype=np.float32)
    crit = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 200, 1e-5)
    score, prev = 0.0, None
    for size in (48, 96):
        if prev is not None:
            s = size / prev
            H = (np.diag([s, s, 1]) @ H @ np.diag([1 / s, 1 / s, 1])).astype(np.float32)
        try:
            score, H = cv2.findTransformECC(gray(ref_big, size), gray(view_big, size), H, cv2.MOTION_HOMOGRAPHY,
                                            crit, None, 5)
        except cv2.error:
            return None, "ECC did not converge"
        prev = size
    # findTransformECC(template=기준, input=보드 화면): view(H·x) ≈ ref(x), 즉 H는 기준 좌표 → 보드 화면 좌표
    pts = cv2.perspectiveTransform(np.float32(poly)[None], H)[0]
    if score < 0.6:
        return None, f"ECC corr {score:.2f} < 0.6"
    if not cv2.isContourConvex(pts.astype(np.float32)) or (pts < -20).any() or (pts > 116).any():
        return None, f"ECC corr {score:.2f}, polygon off screen"
    return np.clip(np.round(pts), 0, 96).astype(int).tolist(), f"ECC corr {score:.2f}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("views")
    ap.add_argument("--ref-video", default=os.path.join(ROOT, "videos", "demo.mp4"))
    ap.add_argument("--ref-sec", type=float, default=1.0, help="빈 통로가 보이는 시각")
    ap.add_argument("--min-score", type=float, default=0.3)
    ap.add_argument("--conf-min", type=float, default=0.6)
    args = ap.parse_args()
    try:
        from ai_edge_litert.interpreter import Interpreter
    except ImportError:
        from tflite_runtime.interpreter import Interpreter

    files = sorted(glob.glob(os.path.join(args.views, "*.png")))
    if not files:
        sys.exit(f"no png in {args.views}")
    _, model = load_model_bytes()
    cats = labels_order()
    it = Interpreter(model_content=model)
    it.allocate_tensors()
    inp, outp = it.get_input_details()[0], it.get_output_details()[0]
    in_scale, in_zero = inp["quantization"]
    out_scale, out_zero = outp["quantization"]
    aisle = json.load(open(os.path.join(ROOT, "tools", "aisle.json"), encoding="utf-8"))["aisle_96"]
    poly = list(zip(aisle[0::2], aisle[1::2]))
    ref = ref_frame(args.ref_video, args.ref_sec) if os.path.exists(args.ref_video) else None

    tiles, proposals = [], []
    for f in files:
        bgr = read_png(f)
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        it.set_tensor(inp["index"], np.round(rgb / in_scale + in_zero).clip(-128, 127).astype(inp["dtype"])[None])
        it.invoke()
        out = (it.get_tensor(outp["index"])[0].astype(np.float32) - out_zero) * out_scale
        dets = fomo_detections(out, cats, args.min_score)
        big = cv2.resize(bgr, (96 * UP, 96 * UP), interpolation=cv2.INTER_NEAREST)
        new_poly, why = estimate_poly(ref, big, poly) if ref is not None else (None, "no ref video")
        if new_poly:
            proposals.append(new_poly)
        draw = big.copy()
        cv2.polylines(draw, [np.int32([[x * UP, y * UP] for x, y in poly])], True, (0, 200, 0), 2)
        if new_poly:
            cv2.polylines(draw, [np.int32([[x * UP, y * UP] for x, y in new_poly])], True, (0, 140, 255), 2)
        for lab, x, y, c in dets:
            col = (0, 0, 255) if lab == "obstacle" else (255, 160, 0)
            cv2.circle(draw, (int(x * UP), int(y * UP)), 10 if c >= args.conf_min else 5, col, 2)
            cv2.putText(draw, f"{lab[0]}{c:.2f}", (int(x * UP) + 12, int(y * UP)), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                        col, 1)
        cv2.putText(draw, f"{os.path.basename(f)} {why}", (6, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        tiles.append(draw)
        obs = [f"{x:.0f},{y:.0f}:{c:.2f}" for lab, x, y, c in dets if lab == "obstacle"]
        print(f"{os.path.basename(f)}  obstacle {obs}  match {why}")

    cols = 4
    while len(tiles) % cols:
        tiles.append(np.zeros_like(tiles[0]))
    sheet = np.vstack([np.hstack(tiles[i:i + cols]) for i in range(0, len(tiles), cols)])
    out_path = args.views.rstrip("/\\") + "_check.png"
    cv2.imencode(".png", sheet)[1].tofile(out_path)
    print(f"sheet: {out_path}")
    if proposals:
        med = np.median(np.array(proposals), axis=0).round().astype(int)
        print(f"proposed ({len(proposals)}/{len(files)} views matched): #AISLE " +
              " ".join(f"{x} {y}" for x, y in med))
    else:
        print("no polygon proposal (matching failed on every view) — aim by eye with the sheet")


if __name__ == "__main__":
    main()
