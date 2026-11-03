"""시연 영상 합치기 + 정답 시간표. tools/demo.json 설계대로 클립과 정지 화면을 이어 videos/demo.mp4를 만들고,
물건을 둔 시각·치운 시각을 영상 전체 기준 초로 바꿔 videos/demo_truth.json에 쓴다 (verify.py가 읽음).

demo.json 예:
{
  "segments": [
    {"image": "ref.png", "sec": 5},               # 정지 화면 5초
    {"clip": "C1.mp4"},                           # 클립 전체
    {"hold_last": "C1.mp4", "sec": 12},           # C1 마지막 화면을 12초 정지
    {"clip": "C2.mp4"}, ...
  ],
  "truth": [
    {"segment": 1, "at": 4.2, "event": "placed", "what": "box"},     # 1번 세그먼트 시작 후 4.2초에 상자를 내려놓음
    {"segment": 4, "at": 3.0, "event": "removed", "what": "box"},
    {"segment": 6, "at": 0.0, "event": "person_start"}, {"segment": 6, "at": 8.0, "event": "person_end"}
  ]
}
사용: python tools/make_demo.py            (videos/ 아래 파일을 읽는다)
"""
import json
import os
import sys

import cv2
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VID = os.path.join(ROOT, "videos")


def read_clip(name):
    cap = cv2.VideoCapture(os.path.join(VID, name))
    if not cap.isOpened():
        sys.exit(f"cannot open videos/{name}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    frames = []
    while True:
        ok, f = cap.read()
        if not ok:
            break
        frames.append(f)
    cap.release()
    return fps, frames


def read_image(name):
    data = np.fromfile(os.path.join(VID, name), dtype=np.uint8)
    img = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if img is None:
        sys.exit(f"cannot read videos/{name}")
    return img


def main():
    spec_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "demo.json")
    spec = json.load(open(spec_path, encoding="utf-8"))
    out_fps = spec.get("fps", 30)
    cache = {}
    starts, out_frames = [], []
    size = None
    for seg in spec["segments"]:
        starts.append(len(out_frames) / out_fps)
        if "clip" in seg:
            fps, frames = cache.setdefault(seg["clip"], read_clip(seg["clip"]))
            # 원본 fps가 달라도 시간이 맞게 다시 뽑는다
            n = int(round(len(frames) / fps * out_fps))
            out_frames += [frames[min(len(frames) - 1, int(i * fps / out_fps))] for i in range(n)]
        else:
            if "image" in seg:
                img = read_image(seg["image"])
            else:
                img = cache.setdefault(seg["hold_last"], read_clip(seg["hold_last"]))[1][-1]
            out_frames += [img] * int(round(seg["sec"] * out_fps))
        size = size or (out_frames[0].shape[1], out_frames[0].shape[0])

    out_path = os.path.join(VID, "demo.mp4")
    w = cv2.VideoWriter(out_path, cv2.VideoWriter_fourcc(*"mp4v"), out_fps, size)
    for f in out_frames:
        if (f.shape[1], f.shape[0]) != size:
            f = cv2.resize(f, size)
        w.write(f)
    w.release()

    truth = []
    for t in spec.get("truth", []):
        truth.append({**t, "t": round(starts[t["segment"]] + t["at"], 2)})
    json.dump({"duration": round(len(out_frames) / out_fps, 2), "segment_starts": [round(s, 2) for s in starts],
               "truth": truth}, open(os.path.join(VID, "demo_truth.json"), "w", encoding="utf-8"), indent=2,
              ensure_ascii=False)
    print(f"videos/demo.mp4 {len(out_frames) / out_fps:.1f}s, segments at {[round(s, 1) for s in starts]}")
    for t in truth:
        print(f"  {t['t']:7.2f}s {t['event']} {t.get('what', '')}")


if __name__ == "__main__":
    main()
