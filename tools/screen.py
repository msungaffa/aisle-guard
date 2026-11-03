"""카메라 모드 시연: 노트북 화면에 통로 부분(tools/aisle.json의 crop)을 크게 띄우고, 보드(aisle_cam)가
자기 카메라로 그 화면을 찍어 판정한다. 오른쪽 칸에 보드 판정과 보드가 본 96×96 화면을 보여 준다.
오른쪽 칸 글자가 카메라에 찍히지 않게 카메라는 왼쪽 영상 칸만 보도록 놓는다.

순서: 실행 → 상자가 있는 장면(--aim-at)이 멈춘 채로 보드 화면(오른쪽 아래)을 보며 카메라 위치를 맞춤 → 스페이스 → 재생 시작과 함께
보드에 "#CAM on"(판정 초기화, v=0) → 끝나면 "#CAM off". q로 중단.
보드 로그는 feed.py와 같은 형식이라 verify.py로 정답과 비교할 수 있다(화면·카메라 지연이 더해진다).

사용:
  python tools/screen.py COM10 videos/demo.mp4
  python tools/screen.py COM10 videos/demo.mp4 --size 640 --camcrop "40 0 240"
"""
import argparse
import datetime
import json
import os
import sys
import threading
import time

import cv2
import numpy as np
import serial

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import feed  # noqa: E402
from aisle_frames import CONFIG, crop_square, load_crop  # noqa: E402

PANEL_W = 340
CROP = None
# 카메라 모드 판정 영역: 기본은 USB 검증과 같은 aisle.json 값 (좁히면 가장자리 물건을 놓친다는 사용자 피드백)
CAM_AISLE = None
AISLE_PTS = None


def compose(frame, size, video_s, playing):
    left = cv2.resize(crop_square(frame, CROP), (size, size), interpolation=cv2.INTER_AREA)
    panel = np.zeros((size, PANEL_W, 3), np.uint8)
    st = feed.status
    text, color = feed.LEVEL_TEXT.get(st["lvl"], feed.LEVEL_TEXT[2])
    cv2.putText(panel, "ESP32 camera", (12, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (230, 230, 230), 2)
    cv2.putText(panel, text, (12, 72), cv2.FONT_HERSHEY_SIMPLEX, 0.75, color, 2)
    cv2.putText(panel, f"obstacle={st['obs']} person={st['per']}", (12, 104), cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                (230, 230, 230), 1)
    cv2.putText(panel, f"inference {st['inf']}ms", (12, 128), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (230, 230, 230), 1)
    cv2.putText(panel, f"exposure {st.get('ae', -1):+d}  (- / = keys)", (12, 176), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                (180, 180, 180), 1)
    cv2.putText(panel, f"video {video_s:5.1f}s" if playing else "aim camera, SPACE to start", (12, 152),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 200, 255) if not playing else (230, 230, 230), 1)
    if st["event"] and time.time() - st["event_t"] < 4:
        cv2.putText(panel, st["event"].replace("OBSTACLE ", ""), (12, 204), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
    view = st.get("view")
    if view is not None:
        v = cv2.resize(cv2.cvtColor(view, cv2.COLOR_RGB2BGR), (288, 288), interpolation=cv2.INTER_NEAREST)
        if AISLE_PTS is not None:  # 조준 기준: 노란 선을 이 사다리꼴 안쪽에 맞춘다
            cv2.polylines(v, [AISLE_PTS], True, (0, 0, 255), 2)
        y0 = size - 288 - 10
        if y0 > 215:
            panel[y0:y0 + 288, 26:26 + 288] = v
            cv2.putText(panel, "board sees (96x96)", (26, y0 - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (180, 180, 180), 1)
    return np.hstack([left, panel])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("port")
    ap.add_argument("video")
    ap.add_argument("--size", type=int, default=640, help="영상 칸 한 변 픽셀")
    ap.add_argument("--aisle", default=CAM_AISLE, help="카메라 모드 판정 영역 (96 좌표, 기본 aisle.json, 끝나면 aisle.json 값으로 되돌림)")
    ap.add_argument("--camcrop", default=None, help='보드 카메라 자르기 "x y side" (QVGA 좌표)')
    ap.add_argument("--conf", type=float, default=0.4,
                    help="카메라 모드 판정 점수 기준 (화면 재촬영이라 점수가 낮게 흔들림, 끝나면 0.6으로 되돌림)")
    ap.add_argument("--ae", type=int, default=-1, help="카메라 자동 노출 목표 -2~2 (창에서 - / = 로 바꿈)")
    ap.add_argument("--aim-at", type=float, default=20.0, help="조준할 때 멈춰 보여 줄 영상 시각(초, 상자가 있는 장면)")
    ap.add_argument("--no-view", action="store_true", help="보드 화면을 받지 않는다 (시리얼 부하 줄이기)")
    ap.add_argument("--log", default=None)
    args = ap.parse_args()

    global CROP
    CROP = load_crop()
    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        sys.exit(f"cannot open {args.video}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    frames = []
    while True:
        ok, f = cap.read()
        if not ok:
            break
        frames.append(f)

    log_path = args.log or os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs",
                                        datetime.datetime.now().strftime("screen_%Y%m%d_%H%M%S.log"))
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    log = open(log_path, "w", encoding="utf-8")
    log.write(f"# screen {args.video} camera mode start={datetime.datetime.now().isoformat()}\n")

    ser = serial.Serial()
    ser.port, ser.baudrate, ser.timeout, ser.write_timeout = args.port, 115200, 0.1, 10
    ser.dtr = False
    ser.rts = False
    ser.open()
    t0 = time.time()
    stop = threading.Event()
    th = threading.Thread(target=feed.reader, args=(ser, log, stop, t0), daemon=True)
    th.start()
    deadline = time.time() + 30
    while not feed.ready.is_set() and time.time() < deadline:
        ser.write(b"#AISLE?\n")
        feed.ready.wait(1.0)

    def cmd(c):
        ser.write(("\n" + c + "\n").encode())
        time.sleep(0.2)

    global AISLE_PTS
    if not args.aisle:
        args.aisle = " ".join(str(a) for a in json.load(open(CONFIG, encoding="utf-8"))["aisle_96"])
    v = [float(t) for t in args.aisle.split()]
    AISLE_PTS = (np.array(v, dtype=np.float32).reshape(-1, 2) * 3).astype(np.int32)  # 288/96
    cmd("#AISLE " + args.aisle)
    cmd(f"#CONF {args.conf}")
    if args.camcrop:
        cmd("#CAMCROP " + args.camcrop)
    feed.status["ae"] = args.ae
    cmd(f"#CAMAE {args.ae}")
    cmd("#VIEW off" if args.no_view else "#VIEW on")
    cmd("#CAM on")  # 조준하는 동안에도 보드 화면이 보이게 켠다

    viewer = feed.Viewer()
    try:
        # 조준: 상자가 있는 장면을 멈춰 두고, obstacle 수를 보며 위치·노출을 맞춘다
        aim = frames[min(len(frames) - 1, int(args.aim_at * fps))]

        def set_ae(d):
            feed.status["ae"] = max(-2, min(2, feed.status["ae"] + d))
            cmd(f"#CAMAE {feed.status['ae']}")

        viewer.draw(cv2.cvtColor(compose(aim, args.size, 0, False), cv2.COLOR_BGR2RGB))
        viewer.root.bind("-", lambda e: set_ae(-1))
        viewer.root.bind("=", lambda e: set_ae(1))
        while viewer.alive and not viewer.space:
            viewer.draw(cv2.cvtColor(compose(aim, args.size, 0, False), cv2.COLOR_BGR2RGB))
            time.sleep(0.03)
        if not viewer.alive:
            return
        cmd("#CAM on")  # 판정 초기화, v=0
        log.write(f"{time.time() - t0:8.2f} >> play start\n")
        start = time.time()
        # 보드가 본 화면을 새로 올 때마다 저장한다 (카메라가 화면을 제대로 봤는지 확인, 카메라 재학습 데이터 후보)
        view_dir = os.path.splitext(log_path)[0] + "_views"
        os.makedirs(view_dir, exist_ok=True)
        last_view = None
        while viewer.alive:
            t = time.time() - start
            i = int(t * fps)
            if i >= len(frames):
                break
            viewer.draw(cv2.cvtColor(compose(frames[i], args.size, t, True), cv2.COLOR_BGR2RGB))
            view = feed.status.get("view")
            if view is not None and view is not last_view:
                last_view = view
                cv2.imencode(".png", cv2.cvtColor(view, cv2.COLOR_RGB2BGR))[1].tofile(
                    os.path.join(view_dir, f"v{int(t * 1000):06d}.png"))
        time.sleep(3)
    finally:
        try:
            cmd("#CAM off")
            cmd("#VIEW off")
            aisle = json.load(open(CONFIG, encoding="utf-8")).get("aisle_96")
            cmd("#CONF 0.6")  # logic.h 기본값 (USB 검증 기준)
            if aisle:  # USB 검증용 원래 영역으로 되돌린다
                cmd("#AISLE " + " ".join(str(a) for a in aisle))
        except serial.SerialException:
            pass
        stop.set()
        th.join(timeout=1)
        ser.close()
        log.close()
    print(f"log: {log_path}")


if __name__ == "__main__":
    main()
