"""보드 없이 PC에서 시연을 미리 돌려 보는 시뮬레이터.
펌웨어와 같은 int8 모델(LiteRT) + logic.cpp와 같은 판정 규칙(파이썬 옮김)으로 영상을 처리하고,
보드와 같은 형식("OBSTACLE WARNING dwell=.. max_conf=.. v=..")의 로그를 써서 verify.py로 바로 채점한다.
시간은 영상 시각(v)을 쓴다. 보드 실측의 대체가 아니라 사전 점검용이다.

사용: python tools/simulate.py videos/demo.mp4 [--fps 2] [--log tools/logs/sim_demo.log]
      python tools/verify.py tools/logs/sim_demo.log
"""
import argparse
import json
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from aisle_frames import load_crop, to_model_rgb  # noqa: E402
from model_gate import in_poly, labels_order, load_model_bytes  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Logic:
    """firmware/aisle_cam/logic.cpp와 같은 규칙"""

    def __init__(self, poly, conf_min=0.6, win_n=6, win_k=4, clear_k=1, dwell_ms=10000, person_radius=16):
        self.poly, self.conf_min, self.win_n, self.win_k = poly, conf_min, win_n, win_k
        self.clear_k, self.dwell_ms, self.r = clear_k, dwell_ms, person_radius
        self.win = []  # (present, t)
        self.occupied = self.warned = False
        self.start = self.last_present = 0
        self.max_conf = 0.0

    def classify(self, dets):
        held = False
        for lab, x, y, c in dets:
            if lab != "obstacle" or c < self.conf_min or not in_poly(self.poly, x, y):
                continue
            near = self.r > 0 and any(l2 == "person" and c2 >= self.conf_min and (x2 - x) ** 2 + (y2 - y) ** 2 <= self.r ** 2
                                      for l2, x2, y2, c2 in dets)
            if near:
                held = True
            else:
                return "P"
        return "S" if held else "-"

    def update(self, st, t, conf):
        ev = None
        if st != "S":
            self.win.append((st == "P", t))
            self.win = self.win[-self.win_n:]
            if st == "P":
                self.last_present = t
            pres = [tt for p, tt in self.win if p]
            if not self.occupied and len(pres) >= self.win_k:
                self.occupied, self.warned, self.start, self.max_conf = True, False, pres[0], 0.0
            elif self.occupied and len(pres) <= self.clear_k:
                if self.warned:
                    ev = ("CLEARED", self.last_present - self.start)
                self.occupied = self.warned = False
                return ev
        if self.occupied:
            if st == "P":
                self.max_conf = max(self.max_conf, conf)
            if not self.warned and t - self.start >= self.dwell_ms:
                self.warned = True
                ev = ("WARNING", t - self.start)
        return ev

    def level(self):
        return 0 if not self.occupied else (2 if self.warned else 1)


def fomo_detections(out, cats, thr):
    """EI FOMO 후처리처럼 점수가 thr 이상인 이웃 칸을 묶어 중심점 하나로"""
    grid = out.shape[0]
    cell = 96 / grid
    dets = []
    for ci, lab in enumerate(cats):
        ch = out[:, :, ci + 1]
        seen = np.zeros_like(ch, dtype=bool)
        for gy in range(grid):
            for gx in range(grid):
                if ch[gy, gx] < thr or seen[gy, gx]:
                    continue
                stack, cells = [(gy, gx)], []
                seen[gy, gx] = True
                while stack:
                    y, x = stack.pop()
                    cells.append((y, x))
                    for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        ny, nx = y + dy, x + dx
                        if 0 <= ny < grid and 0 <= nx < grid and not seen[ny, nx] and ch[ny, nx] >= thr:
                            seen[ny, nx] = True
                            stack.append((ny, nx))
                ys = [c[0] for c in cells]
                xs = [c[1] for c in cells]
                cx = (min(xs) + max(xs) + 1) / 2 * cell
                cy = (min(ys) + max(ys) + 1) / 2 * cell
                dets.append((lab, cx, cy, float(max(ch[y, x] for y, x in cells))))
    return dets


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--fps", type=float, default=2.0)
    ap.add_argument("--min-score", type=float, default=0.3, help="settings.h EI_MIN_SCORE")
    ap.add_argument("--log", default=None)
    args = ap.parse_args()
    try:
        from ai_edge_litert.interpreter import Interpreter
    except ImportError:
        from tflite_runtime.interpreter import Interpreter

    _, model = load_model_bytes()
    cats = labels_order()
    it = Interpreter(model_content=model)
    it.allocate_tensors()
    inp, outp = it.get_input_details()[0], it.get_output_details()[0]
    in_scale, in_zero = inp["quantization"]
    out_scale, out_zero = outp["quantization"]
    aisle = json.load(open(os.path.join(ROOT, "tools", "aisle.json"), encoding="utf-8"))["aisle_96"]
    logic = Logic(list(zip(aisle[0::2], aisle[1::2])))

    name = os.path.splitext(os.path.basename(args.video))[0]
    log_path = args.log or os.path.join(ROOT, "tools", "logs", f"sim_{name}.log")
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    log = open(log_path, "w", encoding="utf-8")
    cap = cv2.VideoCapture(args.video)
    src_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    crop, step, next_ms, idx = load_crop(), 1000.0 / args.fps, 0.0, 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        t = idx * 1000.0 / src_fps
        idx += 1
        if t + 1e-6 < next_ms:
            continue
        next_ms += step
        rgb = to_model_rgb(frame, crop).astype(np.float32) / 255.0
        it.set_tensor(inp["index"], np.round(rgb / in_scale + in_zero).clip(-128, 127).astype(inp["dtype"])[None])
        it.invoke()
        out = (it.get_tensor(outp["index"])[0].astype(np.float32) - out_zero) * out_scale
        dets = fomo_detections(out, cats, args.min_score)
        st = logic.classify(dets)
        conf = max([c for l, x, y, c in dets if l == "obstacle" and in_poly(logic.poly, x, y)], default=0.0)
        ev = logic.update(st, int(t), conf)
        obs = sum(d[0] == "obstacle" for d in dets)
        log.write(f"{t / 1000:8.2f} F v={int(t)} obs={obs} per={len(dets) - obs} st={st} lvl={logic.level()} "
                  f"conf={conf:.2f}\n")
        if ev:
            line = f"OBSTACLE {ev[0]} dwell={ev[1] / 1000:.1f}s max_conf={logic.max_conf:.2f} v={int(t)}"
            log.write(f"{t / 1000:8.2f} {line}\n")
            print(f"{t / 1000:7.1f}s {line}")
    log.close()
    print(f"log: {log_path}")


if __name__ == "__main__":
    main()
