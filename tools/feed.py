"""시연 영상을 실제 시간으로 재생하며 프레임을 96×96 RGB로 줄여 USB 시리얼로 ESP32(aisle_cam)에 보낸다.
보드 출력은 PC 시각과 함께 화면과 로그 파일에 남긴다 (검증 때 정답 시간표와 비교).

사용:
  python tools/feed.py COM10 videos/demo.mp4                 # 2fps로 재생
  python tools/feed.py COM10 videos/C1.mp4 --fps 3 --loop
  python tools/feed.py COM10 --synthetic 40 --cmd "#FAKE 48 48 0.9" --cmd-at "15:#FAKE off"  # 영상 없이 배선 시험
  python tools/feed.py COM10 videos/demo.mp4 --cmd "#AISLE 20 10 76 10 90 96 6 96"

프레임 형식(firmware proto.h): "AGFR" + video_ms(u32 LE) + len(u16 LE) + RGB888 + xor(u8)
시리얼 포트는 한 프로그램만 열 수 있다. Arduino 시리얼 모니터는 닫고 실행한다.
"""
import argparse
import datetime
import os
import struct
import sys
import threading
import time

import numpy as np
import serial

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from aisle_frames import MODEL_SIZE, load_crop, to_model_rgb  # noqa: E402

FRAME_BYTES = MODEL_SIZE * MODEL_SIZE * 3
ready = threading.Event()


def packet(video_ms, rgb):
    payload = np.ascontiguousarray(rgb, dtype=np.uint8).tobytes()
    assert len(payload) == FRAME_BYTES
    x = np.bitwise_xor.reduce(np.frombuffer(payload, dtype=np.uint8))
    return b"AGFR" + struct.pack("<IH", video_ms & 0xFFFFFFFF, len(payload)) + payload + bytes([int(x)])


def reader(ser, log, stop, t0):
    buf = b""
    while not stop.is_set():
        try:
            chunk = ser.read(ser.in_waiting or 1)
        except serial.SerialException:
            break
        if not chunk:
            continue
        buf += chunk
        while b"\n" in buf:
            raw, buf = buf.split(b"\n", 1)
            text = raw.decode("utf-8", "replace").rstrip("\r")
            stamp = f"{time.time() - t0:8.2f}"
            line = f"{stamp} {text}"
            print(line, flush=True)
            if text.startswith("[cfg] aisle"):
                ready.set()
            log.write(line + "\n")
            log.flush()


def frames_from_video(path, fps, crop, loop):
    import cv2
    while True:
        cap = cv2.VideoCapture(path)
        if not cap.isOpened():
            sys.exit(f"cannot open {path}")
        src_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        step_ms = 1000.0 / fps
        next_ms = 0.0
        idx = 0
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            t_ms = idx * 1000.0 / src_fps
            idx += 1
            if t_ms + 1e-6 < next_ms:
                continue
            next_ms += step_ms
            yield int(t_ms), to_model_rgb(frame, crop)
        cap.release()
        if not loop:
            return


def frames_synthetic(n, fps):
    gray = np.full((MODEL_SIZE, MODEL_SIZE, 3), 128, dtype=np.uint8)
    for i in range(n):
        yield int(i * 1000 / fps), gray


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("port")
    ap.add_argument("video", nargs="?")
    ap.add_argument("--fps", type=float, default=2.0)
    ap.add_argument("--loop", action="store_true")
    ap.add_argument("--synthetic", type=int, default=0, help="영상 대신 회색 프레임 N장")
    ap.add_argument("--cmd", action="append", default=[], help="시작 전에 보낼 보드 명령 (여러 번 가능)")
    ap.add_argument("--cmd-at", action="append", default=[], help='"초:명령" 영상 시각에 보낼 명령 (예: "13:#FAKE off")')
    ap.add_argument("--after", type=float, default=3.0, help="끝난 뒤 보드 출력을 더 받을 초")
    ap.add_argument("--log", default=None, help="로그 파일 (기본 tools/logs/feed_<시각>.log)")
    args = ap.parse_args()
    if not args.video and not args.synthetic:
        ap.error("video 또는 --synthetic 이 필요하다")

    log_path = args.log or os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs",
                                        datetime.datetime.now().strftime("feed_%Y%m%d_%H%M%S.log"))
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    log = open(log_path, "w", encoding="utf-8")
    log.write(f"# feed {args.video or 'synthetic'} fps={args.fps} start={datetime.datetime.now().isoformat()}\n")

    # DTR/RTS를 내린 채 열어야 보드가 리셋되지 않는다
    ser = serial.Serial()
    ser.port, ser.baudrate, ser.timeout, ser.write_timeout = args.port, 115200, 0.1, 10
    ser.dtr = False
    ser.rts = False
    ser.open()
    t0 = time.time()
    stop = threading.Event()
    th = threading.Thread(target=reader, args=(ser, log, stop, t0), daemon=True)
    th.start()

    # 보드가 명령을 받을 수 있을 때까지 기다린다 (막 부팅했으면 Wi-Fi 연결에 최대 15초)
    deadline = time.time() + 30
    while not ready.is_set() and time.time() < deadline:
        ser.write(b"#AISLE?\n")
        ready.wait(1.0)
    if not ready.is_set():
        print("board did not answer #AISLE? (is aisle_cam running?)")

    for c in args.cmd:
        ser.write((c + "\n").encode())
        time.sleep(0.3)
    timed = sorted((float(a.split(":", 1)[0]), a.split(":", 1)[1]) for a in args.cmd_at)

    crop = load_crop()
    src = frames_synthetic(args.synthetic, args.fps) if args.synthetic else \
        frames_from_video(args.video, args.fps, crop, args.loop)
    sent = 0
    start = time.time()
    try:
        for video_ms, rgb in src:
            # 영상 시각에 맞춰 보낸다 (늦으면 바로)
            wait = start + video_ms / 1000.0 - time.time()
            if wait > 0:
                time.sleep(wait)
            while timed and timed[0][0] * 1000 <= video_ms:
                # 앞의 \n은 보드의 명령 줄 버퍼를 비운다
                ser.write(("\n" + timed.pop(0)[1] + "\n").encode())
            ser.write(packet(video_ms, rgb))
            sent += 1
            log.write(f"{time.time() - t0:8.2f} >> frame v={video_ms}\n")
    except KeyboardInterrupt:
        pass
    finally:
        time.sleep(args.after)
        stop.set()
        th.join(timeout=1)
        ser.close()
        log.close()
    print(f"sent {sent} frames in {time.time() - start:.1f}s, log: {log_path}")


if __name__ == "__main__":
    main()
