"""CI 모델 정확도 게이트 (PRD "model-gate"). 펌웨어에 들어간 바로 그 int8 모델을
firmware/libraries/*_inferencing의 헤더에서 꺼내 PC(LiteRT)로 돌리고, 시험 프레임에서 obstacle 재현율을 잰다.

- 시험 세트: tests/model_gate/*.png (96×96, 클립마다 마지막 30% 구간, 학습에 안 쓴 프레임) + labels.json
- obstacle 박스 하나는 FOMO 칸(8px) 중 박스 안 칸의 obstacle 점수가 --thr(0.5) 이상이면 찾은 것
- 오검출: obstacle 라벨이 없는 프레임에서 통로 다각형 안에 obstacle 칸이 나오면 1
- 재현율이 --min-recall(0.9) 미만이면 종료 코드 1
- --testset tests/model_gate_cam: 카메라 모드 보드 화면(screen.py 6·7회차, tools/cam_label.py 라벨) 53장

사용: python tools/model_gate.py                 # 검사
      python tools/model_gate.py --make-testset  # tools/frames/testing 라벨로 시험 세트 만들기 (videos/ 필요)
"""
import argparse
import glob
import json
import os
import re
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTSET = os.path.join(ROOT, "tests", "model_gate")


def load_model_bytes():
    hdrs = glob.glob(os.path.join(ROOT, "firmware", "libraries", "*_inferencing", "src", "tflite-model",
                                  "tflite_learn_*.h"))
    if not hdrs:
        sys.exit("model header not found under firmware/libraries")
    text = open(hdrs[0], encoding="utf-8", errors="ignore").read()
    body = text[text.index("{", text.index("MODEL_SECTION(")):]
    body = body[1:body.index("}")]
    data = bytes(int(v, 16) for v in re.findall(r"0x([0-9a-fA-F]{2})", body))
    return os.path.basename(hdrs[0]), data


def labels_order():
    meta = glob.glob(os.path.join(ROOT, "firmware", "libraries", "*_inferencing", "src", "model-parameters",
                                  "model_variables.h"))[0]
    text = open(meta, encoding="utf-8", errors="ignore").read()
    m = re.search(r"ei_classifier_inferencing_categories\w*\[\]\s*=\s*\{([^}]*)\}", text)
    return [s.strip().strip('"') for s in m.group(1).split(",") if s.strip()]


def in_poly(poly, x, y):
    inside = False
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def make_testset():
    import cv2
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    from aisle_frames import load_crop, to_model_rgb
    src = os.path.join(ROOT, "tools", "frames", "testing")
    labels = json.load(open(os.path.join(src, "bounding_boxes.labels"), encoding="utf-8"))["boundingBoxes"]
    os.makedirs(TESTSET, exist_ok=True)
    crop, out, caps = load_crop(), {}, {}
    for name, boxes in sorted(labels.items()):
        clip, ms = name[:-4].split("_")
        cap = caps.setdefault(clip, cv2.VideoCapture(os.path.join(ROOT, "videos", clip + ".mp4")))
        cap.set(cv2.CAP_PROP_POS_MSEC, int(ms))
        ok, frame = cap.read()
        rgb = to_model_rgb(frame, crop)
        png = name[:-4] + ".png"
        ok, enc = cv2.imencode(".png", cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
        open(os.path.join(TESTSET, png), "wb").write(enc.tobytes())
        s = 96 / 288
        out[png] = [{"label": b["label"], "x": b["x"] * s, "y": b["y"] * s, "w": b["width"] * s, "h": b["height"] * s}
                    for b in boxes]
    json.dump(out, open(os.path.join(TESTSET, "labels.json"), "w", encoding="utf-8"), indent=1)
    print(f"{len(out)} frames -> {TESTSET}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--make-testset", action="store_true")
    ap.add_argument("--thr", type=float, default=0.5)
    ap.add_argument("--min-recall", type=float, default=0.9)
    ap.add_argument("--testset", default=TESTSET, help="tests/model_gate(USB 프레임) 또는 tests/model_gate_cam(보드 카메라 화면)")
    args = ap.parse_args()
    testset = os.path.join(ROOT, args.testset) if not os.path.isabs(args.testset) else args.testset
    if args.make_testset:
        make_testset()
        return

    from PIL import Image
    try:
        from ai_edge_litert.interpreter import Interpreter
    except ImportError:
        from tflite_runtime.interpreter import Interpreter

    name, model = load_model_bytes()
    cats = labels_order()
    it = Interpreter(model_content=model)
    it.allocate_tensors()
    inp, outp = it.get_input_details()[0], it.get_output_details()[0]
    in_scale, in_zero = inp["quantization"]
    out_scale, out_zero = outp["quantization"]
    aisle = json.load(open(os.path.join(ROOT, "tools", "aisle.json"), encoding="utf-8"))["aisle_96"]
    poly = list(zip(aisle[0::2], aisle[1::2]))
    labels = json.load(open(os.path.join(testset, "labels.json"), encoding="utf-8"))
    obs_ch = 1 + cats.index("obstacle")  # 0번 채널은 background

    found = total = false_frames = empty_frames = 0
    misses = []
    for png, boxes in sorted(labels.items()):
        img = np.asarray(Image.open(os.path.join(testset, png)).convert("RGB"), dtype=np.float32) / 255.0
        q = np.round(img / in_scale + in_zero).clip(-128, 127).astype(inp["dtype"])
        it.set_tensor(inp["index"], q[None])
        it.invoke()
        out = (it.get_tensor(outp["index"])[0].astype(np.float32) - out_zero) * out_scale  # (12, 12, C)
        grid = out.shape[0]
        cell = 96 / grid
        hot = [((gx + 0.5) * cell, (gy + 0.5) * cell) for gy in range(grid) for gx in range(grid)
               if out[gy, gx, obs_ch] >= args.thr]
        obs = [b for b in boxes if b["label"] == "obstacle"]
        for b in obs:
            total += 1
            hit = any(b["x"] <= x <= b["x"] + b["w"] and b["y"] <= y <= b["y"] + b["h"] for x, y in hot)
            found += hit
            if not hit:
                misses.append(png)
        if not obs:
            empty_frames += 1
            if any(in_poly(poly, x, y) for x, y in hot):
                false_frames += 1
    recall = found / total if total else 1.0
    print(f"model {name}, labels {cats}, thr {args.thr}, testset {os.path.basename(testset)}")
    print(f"obstacle recall {found}/{total} = {recall:.3f} (gate {args.min_recall})")
    print(f"frames without obstacle that fire in aisle: {false_frames}/{empty_frames}")
    if misses:
        print("missed: " + ", ".join(misses))
    sys.exit(0 if recall >= args.min_recall else 1)


if __name__ == "__main__":
    main()
