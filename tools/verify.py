"""feed.py 로그와 정답 시간표(videos/demo_truth.json)를 맞춰 PRD 성공 기준을 계산한다.

- 방치 구간: placed → removed 쌍 (같은 what). 경고가 placed + DWELL_T + 2초 안에 나오면 검출 성공
- 경고 지연: 경고 시각(영상 v) - placed
- 방치 시간 오차: 보드의 cleared dwell - (removed - placed)
- 오경보: 어떤 방치 구간에도 속하지 않는 경고 (예: 사람만 지나갈 때)

사용: python tools/verify.py tools/logs/feed_xxx.log [--truth videos/demo_truth.json] [--dwell 10]
"""
import argparse
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EV = re.compile(r"OBSTACLE (WARNING|CLEARED) dwell=([\d.]+)s max_conf=([\d.]+) v=(\d+)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("log")
    ap.add_argument("--truth", default=os.path.join(ROOT, "videos", "demo_truth.json"))
    ap.add_argument("--dwell", type=float, default=10.0)
    args = ap.parse_args()

    events = []
    for line in open(args.log, encoding="utf-8"):
        m = EV.search(line)
        if m:
            events.append({"kind": m[1].lower(), "dwell": float(m[2]), "conf": float(m[3]), "v": int(m[4]) / 1000})
    truth = json.load(open(args.truth, encoding="utf-8"))["truth"]

    stays, open_ = [], {}
    for t in sorted(truth, key=lambda x: x["t"]):
        if t["event"] == "placed":
            open_[t.get("what", "")] = t["t"]
        elif t["event"] == "removed" and t.get("what", "") in open_:
            stays.append({"what": t.get("what", ""), "placed": open_.pop(t.get("what", "")), "removed": t["t"]})
    for what, placed in open_.items():
        stays.append({"what": what, "placed": placed, "removed": None})

    used = set()
    rows = []
    for s in stays:
        end = s["removed"] if s["removed"] is not None else float("inf")
        long_enough = end - s["placed"] >= args.dwell
        warn = next((i for i, e in enumerate(events) if e["kind"] == "warning" and i not in used
                     and s["placed"] <= e["v"] <= end + 2), None)
        clr = next((i for i, e in enumerate(events) if e["kind"] == "cleared" and i not in used
                    and warn is not None and e["v"] >= events[warn]["v"]), None)
        for i in (warn, clr):
            if i is not None:
                used.add(i)
        latency = events[warn]["v"] - s["placed"] if warn is not None else None
        ok_detect = (warn is not None and latency <= args.dwell + 2) if long_enough else warn is None
        dwell_err = None
        if clr is not None and s["removed"] is not None:
            dwell_err = events[clr]["dwell"] - (s["removed"] - s["placed"])
        rows.append((s, long_enough, latency, ok_detect, dwell_err))

    false_alarms = [e for i, e in enumerate(events) if e["kind"] == "warning" and i not in used]
    print(f"{'what':8} {'placed':>7} {'removed':>7} {'expect':>7} {'latency':>8} {'dwell err':>9}  result")
    for s, long_enough, latency, ok, err in rows:
        rem = f"{s['removed']:.1f}" if s["removed"] is not None else "-"
        lat = f"{latency:.1f}s" if latency is not None else "-"
        e = f"{err:+.1f}s" if err is not None else "-"
        print(f"{s['what']:8} {s['placed']:7.1f} {rem:>7} {'warn' if long_enough else 'none':>7} {lat:>8} {e:>9}  "
              f"{'PASS' if ok and (err is None or round(abs(err), 1) <= 1.0) else 'FAIL'}")
    print(f"false alarms: {len(false_alarms)}" + "".join(f"\n  warning at v={e['v']:.1f}s" for e in false_alarms))


if __name__ == "__main__":
    main()
