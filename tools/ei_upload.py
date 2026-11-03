"""tools/frames/{training,testing}/*.jpg·png 를 Edge Impulse 프로젝트에 올린다.
--labels면 autolabel.py가 만든 박스를 같이 올리고, 아니면 라벨 없이 올려 Studio에서 단다
(obstacle = 통로 바닥의 상자·가방, person).

키: 저장소 루트 .env 의 EI_API_KEY (gitignore). 같은 파일을 두 번 올리면 EI가 거절한다(중복 방지 헤더).

사용: python tools/ei_upload.py tools/frames            # 올리기
      python tools/ei_upload.py tools/frames --labels   # 박스 라벨과 함께
      python tools/ei_upload.py tools/frames --dry-run  # 개수만 확인
"""
import argparse
import glob
import io
import json
import os
import sys

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
URL = "https://ingestion.edgeimpulse.com/api/{cat}/files"


def load_env():
    env = {}
    path = os.path.join(ROOT, ".env")
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.strip().split("=", 1)
                env[k] = v
    return env


def upload(key, cat, files, batch=20, labels=None):
    ok = fail = 0
    for i in range(0, len(files), batch):
        chunk = files[i:i + batch]
        handles = [("data", (os.path.basename(f), open(f, "rb"), "image/png" if f.endswith(".png") else "image/jpeg"))
                   for f in chunk]
        if labels:
            # 같은 요청에 bounding_boxes.labels를 넣으면 EI가 파일 이름으로 박스를 붙인다
            sub = {os.path.basename(f): labels.get(os.path.basename(f), []) for f in chunk}
            body = json.dumps({"version": 1, "type": "bounding-box-labels", "boundingBoxes": sub}).encode()
            handles.append(("data", ("bounding_boxes.labels", io.BytesIO(body), "application/json")))
        try:
            r = requests.post(URL.format(cat=cat), files=handles, timeout=120,
                              headers={"x-api-key": key, "x-disallow-duplicates": "1"})
        finally:
            for _, (_, fh, _) in handles:
                fh.close()
        if r.status_code != 200:
            print(f"  {cat} batch {i // batch}: HTTP {r.status_code} {r.text[:200]}")
            fail += len(chunk)
            continue
        body = r.json()
        for f in body.get("files", []):
            if f.get("success"):
                ok += 1
            else:
                fail += 1
                print(f"  {f.get('fileName')}: {f.get('error')}")
        print(f"  {cat}: {min(i + batch, len(files))}/{len(files)}")
    return ok, fail


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--labels", action="store_true", help="<cat>/bounding_boxes.labels(autolabel.py 결과)를 같이 올린다")
    args = ap.parse_args()
    key = os.environ.get("EI_API_KEY") or load_env().get("EI_API_KEY")
    if not key and not args.dry_run:
        sys.exit("EI_API_KEY 없음 (.env)")
    for cat in ("training", "testing"):
        files = sorted(glob.glob(os.path.join(args.folder, cat, "*.jpg")) + glob.glob(os.path.join(args.folder, cat, "*.png")))
        labels = None
        if args.labels:
            lp = os.path.join(args.folder, cat, "bounding_boxes.labels")
            labels = json.load(open(lp, encoding="utf-8"))["boundingBoxes"]
        print(f"{cat}: {len(files)} files" + (f", {sum(len(v) for v in labels.values())} boxes" if labels else ""))
        if files and not args.dry_run:
            ok, fail = upload(key, cat, files, labels=labels)
            print(f"{cat}: ok {ok}, failed {fail}")


if __name__ == "__main__":
    main()
