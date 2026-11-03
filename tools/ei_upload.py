"""tools/frames/{training,testing}/*.jpg 를 Edge Impulse 프로젝트에 라벨 없이 올린다.
박스 라벨은 Studio의 Labeling queue / AI labeling에서 단다 (obstacle = 통로 바닥의 상자·가방, person).

키: 저장소 루트 .env 의 EI_API_KEY (gitignore). 같은 파일을 두 번 올리면 EI가 거절한다(중복 방지 헤더).

사용: python tools/ei_upload.py tools/frames            # 올리기
      python tools/ei_upload.py tools/frames --dry-run  # 개수만 확인
"""
import argparse
import glob
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


def upload(key, cat, files, batch=20):
    ok = fail = 0
    for i in range(0, len(files), batch):
        chunk = files[i:i + batch]
        handles = [("data", (os.path.basename(f), open(f, "rb"), "image/jpeg")) for f in chunk]
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
    args = ap.parse_args()
    key = os.environ.get("EI_API_KEY") or load_env().get("EI_API_KEY")
    if not key and not args.dry_run:
        sys.exit("EI_API_KEY 없음 (.env)")
    for cat in ("training", "testing"):
        files = sorted(glob.glob(os.path.join(args.folder, cat, "*.jpg")))
        print(f"{cat}: {len(files)} files")
        if files and not args.dry_run:
            ok, fail = upload(key, cat, files)
            print(f"{cat}: ok {ok}, failed {fail}")


if __name__ == "__main__":
    main()
