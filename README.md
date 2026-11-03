# aisle-guard — 통로 장애물 방치 감지기

[![ci](https://github.com/msungaffa/aisle-guard/actions/workflows/ci.yml/badge.svg)](https://github.com/msungaffa/aisle-guard/actions/workflows/ci.yml)

XIAO ESP32S3 Sense 안에서 Edge Impulse FOMO 모델이 통로에 놓인 물건(`obstacle`: 상자·가방)과 사람(`person`)을 찾고,
물건이 정해진 시간(`DWELL_T`, 시연 10초) 넘게 통로에 있으면 LED로 경고하고 이벤트를 Supabase에 기록한다.
사람은 장애물로 세지 않는다.

- PRD: https://claude.ai/artifact/7vguen5tdMA9Pb4VUPn3XW
- 과제 조건: ① ESP32에 모델 탑재 ② 로그 DB 저장 ③ CI → 아래 "조건별 구현"
- 작업 문서: `CLAUDE.md`(규칙), `HANDOFF.md`(현재 상태·남은 일), `docs/HISTORY.md`(기록)

## 구성

```
videos/demo.mp4 ──(tools/feed.py: 통로 부분 잘라 96×96 RGB, 실제 시간으로 재생)──USB 시리얼──▶ ESP32-S3
                                                                                      │ FOMO 추론 (obstacle/person 중심점)
                                                                                      │ logic.cpp 판정 (통로 다각형, 6프레임 중 4, 10초)
                                                                                      │ LED (관찰 1Hz / 경고 5Hz)
                                                                                      └─ HTTPS ──▶ Supabase aisle_events
GitHub Actions: unit-test (logic·proto g++) + firmware-build (arduino-cli, esp32 3.3.12)
```

집에서 실제 통로를 만들기 어려워 AI 생성 창고 CCTV 영상(클립 5개)을 쓰고, PC가 프레임을 보드로 보낸다.
학습 입력과 시연 입력이 같은 방식으로 잘리고(`tools/aisle_frames.py`), 영상의 정답 시각을 알기 때문에 ±1초 검증이 된다.
모델은 보드 안에서만 돈다.

## 조건별 구현

| 조건 | 구현 | 위치 |
|---|---|---|
| ① ESP32에 모델 | Edge Impulse FOMO(MobileNetV2 0.35) 96×96, Arduino 라이브러리로 펌웨어에 포함 | `firmware/aisle_cam/detector_ei.cpp` |
| ② 로그 DB | ESP32 → Supabase REST 직접 insert (서버 없음). 경고·해제·1분 heartbeat. 끊기면 20건 보관 후 재전송. TLS 인증서 검사 켬. RLS로 anon은 insert만 | `uploader.cpp`, `db/schema.sql` |
| ③ CI | push·PR마다 판정 로직 단위시험 + 펌웨어 컴파일 | `.github/workflows/ci.yml` |

## 판정 규칙 (`firmware/aisle_cam/logic.cpp`)

1. 프레임 판정: 신뢰도 ≥ 0.6인 `obstacle` 중심점이 통로 다각형 안에 있으면 "있음". `person` 반경 16px 안의 obstacle은 사람을 잘못 본 것일 수 있어 "보류"(창에 넣지 않음).
2. 시간 창: 최근 6프레임 중 4프레임 이상 "있음"이면 점유. 1프레임 이하로 줄면 해제.
3. 단계: 0 정상 → 1 관찰(점유 시작) → 2 경고(점유 10초 이상, `warning` 기록) → 해제 시 `cleared`와 방치 시간 기록.

## 실행

```powershell
# 단위시험, 컴파일, 업로드 (보드 COM10)
powershell -File firmware/tests/run_tests.ps1
powershell -File firmware/build.ps1 -Port COM10
# 모델 라이브러리 설치 후 모델로 빌드: settings.h의 DETECTOR_EI를 1로
powershell -File firmware/build.ps1 -InstallLib <ei-...-arduino-x.zip>

# 파이썬 도구 (conda ztmc 환경)
python tools/extract_frames.py videos --fps 3          # 학습 프레임 (클립별 마지막 30%는 testing)
python tools/ei_upload.py tools/frames                 # Edge Impulse 업로드 (.env의 EI_API_KEY)
python tools/make_demo.py                              # tools/demo.json → videos/demo.mp4 + 정답 시간표
python tools/feed.py COM10 videos/demo.mp4             # 시연: 프레임 전송 + 보드 로그 저장
python tools/verify.py tools/logs/feed_<시각>.log      # PRD 성공 기준 계산
```

보드 시리얼 명령: `#AISLE x1 y1 x2 y2 ...`(통로 다각형, 96×96 좌표, 보드에 저장), `#AISLE?`, `#FAKE x y conf` / `#FAKE off`(모델 없이 배선 시험).

## 검증 결과

| # | 시나리오 | 기준 | 결과 |
|---|---|---|---|
| 0 | 배선 시험: 가짜 obstacle 15초 (모델 없이) | 10초 경고, 해제, DB 기록 | 경고 10.0초, 해제 방치 14.5초(실제 15.0초, −0.5초), DB 201 |

모델·시연 영상 결과는 실측 후 채운다.

## 한계

- 클립이 5개뿐이라 학습과 시연이 같은 장면이다(클립마다 시간으로 나눠 마지막 30%를 시험 세트로 둠). 처음 보는 장면·물건 성능은 이 결과로 말할 수 없다.
- 방치 시간은 첫 "있음" 프레임부터 마지막 "있음" 프레임까지라 실제보다 최대 1프레임(2fps에서 0.5초) 짧게 나온다.

## 출처

- 펌웨어 빌드 스크립트·Wi-Fi·EI 추론 틀: 팀 프로젝트 ppe-edge-guard의 내 담당 부분(firmware)에서 가져와 고침.
