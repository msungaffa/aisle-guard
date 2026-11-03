# aisle-guard — 통로 장애물 방치 감지기

[![ci](https://github.com/msungaffa/aisle-guard/actions/workflows/ci.yml/badge.svg)](https://github.com/msungaffa/aisle-guard/actions/workflows/ci.yml)

XIAO ESP32S3 Sense 안에서 Edge Impulse FOMO 모델이 통로에 놓인 물건(`obstacle`: 상자·가방)과 사람(`person`)을 찾는다.
물건이 정해진 시간(`DWELL_T`, 시연 10초) 넘게 통로에 있으면 LED로 경고하고 이벤트를 Supabase에 기록한다.
사람은 장애물로 세지 않는다.

- PRD: https://claude.ai/artifact/7vguen5tdMA9Pb4VUPn3XW
- 대시보드(DB 이벤트 스냅숏): https://claude.ai/artifact/Y96SJDB35Cw7M9EcPwVKvg
- 과제 조건: ① ESP32에 모델 탑재 ② 로그 DB 저장 ③ CI → 아래 "조건별 구현"
- 작업 문서: `CLAUDE.md`(규칙), `HANDOFF.md`(현재 상태·남은 일), `docs/HISTORY.md`(날짜별 기록)

## 구성

```
[학습]  videos/C1~C5.mp4 ─ extract_frames.py ─▶ 96×96 프레임 ─ ei_upload.py ─▶ Edge Impulse
                                                  (클립마다 마지막 30%는 시험 세트)     │ FOMO MobileNetV2 0.35 학습
                                                                                        ▼
                                                              Arduino 라이브러리 (firmware/libraries/)
[시연]                                                                                  │ 펌웨어에 포함
videos/demo.mp4 ─ feed.py (통로 부분 잘라 96×96 RGB, 2fps 실제 시간) ─ USB 시리얼 ─▶ ESP32-S3
                                                                                        │ ① FOMO 추론 → obstacle/person 중심점
                                                                                        │ ② logic.cpp 판정 (통로 다각형, 6프레임 중 4, 10초)
                                                                                        │ ③ LED (관찰 1Hz / 경고 5Hz)
                                                                                        └ ④ 코어 0 태스크 ─ HTTPS ─▶ Supabase aisle_events
                                                                                             (끊기면 20건 보관 후 재전송)
[CI]    push·PR ─▶ GitHub Actions: unit-test (logic·proto, g++) + firmware-build (arduino-cli, esp32 3.3.12)
```

집에서 실제 통로를 만들기 어려워 AI로 만든 창고 CCTV 영상(클립 5개)을 쓰고, PC가 프레임을 보드로 보낸다.
학습 입력과 시연 입력은 같은 코드(`tools/aisle_frames.py`, crop은 `tools/aisle.json`)로 잘린다.
영상의 정답 시각(물건을 둔 시각·치운 시각)을 알기 때문에 ±1초 검증을 할 수 있다. 모델은 보드 안에서만 돈다.

## 조건별 구현

| 조건 | 구현 | 확인 방법 | 위치 |
|---|---|---|---|
| ① ESP32에 모델 | Edge Impulse FOMO(MobileNetV2 0.35), 입력 96×96 RGB. Arduino 라이브러리로 펌웨어에 포함되고, 추론은 보드에서 한다 | 시리얼 로그의 프레임별 추론 시간, 보드 LED | `firmware/aisle_cam/detector_ei.cpp`, `firmware/libraries/` |
| ② 로그 DB | ESP32가 Supabase REST로 직접 insert(중간 서버 없음). `warning`·`cleared`·1분 `heartbeat`. 끊기면 20건 보관 후 재전송. TLS 인증서 검사 켬. RLS로 anon 키는 insert만 가능 | `db/queries.sql`(경고 횟수, 방치 시간, 장치 상태, 오경보 비율) | `uploader.cpp`, `db/schema.sql` |
| ③ CI | push·PR마다 판정 로직 단위시험(호스트 g++, `-Werror`)과 펌웨어 컴파일 | 위 ci 배지 | `.github/workflows/ci.yml`, `firmware/tests/` |

## 판정 규칙 (`firmware/aisle_cam/logic.cpp`)

1. 프레임 판정: 신뢰도 0.6 이상인 `obstacle` 중심점이 통로 다각형 안에 있으면 "있음"이다. `person` 반경 16px 안의 obstacle은 사람을 잘못 본 것일 수 있어 "보류"로 두고 시간 창에 넣지 않는다.
2. 시간 창: 최근 6프레임 중 4프레임 이상이 "있음"이면 점유로 본다. 1프레임 이하로 줄면 해제한다.
3. 단계: 0 정상 → 1 관찰(점유 시작) → 2 경고(점유 10초 이상, `warning` 기록) → 해제 시 `cleared`와 방치 시간을 기록한다.

판정 규칙은 Arduino에 기대지 않는 `logic.cpp`에만 있어 PC에서 단위시험을 돌린다(`firmware/tests/test_logic.cpp`).

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

DB 설정: `db/schema.sql`을 Supabase SQL 편집기에서 한 번 실행한다. 비밀값은 `firmware/aisle_cam/secrets.h`(`secrets.example.h`를 복사)에 넣는다.

## 로그 조회 (`db/queries.sql`)

| # | 조회 | 쓰임 |
|---|---|---|
| 0 | `aisle_event_reviews` 표 만들기 | 경고 한 건마다 `true_alarm`/`false_alarm`을 사람이 표시. 원본 `aisle_events`는 고치지 않는다 |
| 1 | 시간대별 경고 횟수 (최근 7일, KST) | 언제 통로가 자주 막히는지 |
| 2 | 하루 단위 해제 건수, 평균·최대 방치 시간 | 방치가 얼마나 오래 가는지 |
| 3 | 경고-해제 짝, 아직 해제 안 된 경고 | 지금 막힌 통로 |
| 4 | 장치별 마지막 heartbeat, 3분 넘게 없으면 offline | 장치 고장·끊김 |
| 5 | 오경보 비율 | 모델 품질 |
| 6 | 모델 버전별 경고 수·평균 신뢰도 | 모델을 바꾼 뒤 비교 |

## 검증 결과

| # | 시나리오 | 기준 | 결과 |
|---|---|---|---|
| 0 | 배선 시험: 가짜 obstacle 15초 (모델 없이, 보드) | 10초 경고, 해제, DB 기록 | 경고 10.0초, 해제 방치 14.5초(실제 15.0초, −0.5초), DB 201 |
| 0' | 시연 영상 리허설: 정답 시각에 `#FAKE`를 켜고 끔 (모델 없이) | 경고 지연 T+2초 이내, 방치 ±1초, 오경보 0 | 경고 지연 10.7초·10.1초, 방치 31.5초(정답 32초, −0.5초), 오경보 0, DB 5건, 프레임 손실 0 |
| 1 | 학습한 물건을 통로에 15초 넘게 두고 치움 | 경고 9/10 이상 | 실측 중 |
| 2 | 시나리오 1의 방치 시간 | DB `dwell_s`와 정답 차이 ±1초 | 실측 중 |
| 3 | 사람이 통로를 걸어서 지나감 | 경고 0 | 실측 중 |
| 4 | 물건을 5초만 두고 치움 | 관찰(1단계)만, 경고 0 | 실측 중 |
| 5 | 물건을 통로 밖에 15초 둠 | 경고 0 | 실측 중 |
| 6 | 경고 중 Wi-Fi 끊었다 다시 연결 | LED 유지, 재연결 후 기록 누락 0 | 실측 중 |

시나리오는 PRD "검증 계획"과 같다. 실물 대신 영상 구간으로 재현하므로 횟수는 PRD보다 적을 수 있고, 실제 횟수는 결과 칸에 적는다.

## 한계

- 실제 카메라가 아니라 AI로 만든 영상을 PC가 USB로 보낸다. 보드의 카메라·조명·렌즈 왜곡은 시험하지 않았다.
- 클립이 5개뿐이라 학습과 시연이 같은 장면이다(클립마다 시간으로 나눠 마지막 30%를 시험 세트로 둠). 처음 보는 장면·물건에 대한 성능은 이 결과로 말할 수 없다.
- 같은 영상을 반복 재생하는 시험이라 시나리오별 반복은 서로 독립된 시험이 아니다.
- FOMO는 상자 크기가 아니라 중심점만 낸다. 물건이 통로 경계에 걸치면 중심점 위치에 따라 안/밖이 갈린다.
- 사람 바로 옆(16px 안)의 물건은 보류하므로, 사람이 물건 옆에 오래 서 있으면 그동안 경고가 늦어진다.
- 방치 시간은 첫 "있음" 프레임부터 마지막 "있음" 프레임까지라 실제보다 최대 1프레임(2fps에서 0.5초) 짧게 나온다.
- 펌웨어에 든 anon(publishable) 키는 보드에서 꺼낼 수 있다. RLS로 insert만 되지만, 키를 얻은 사람이 가짜 행을 넣을 수는 있다. 장치별 인증은 하지 않았다.
- 시각은 NTP로 맞춘 UTC다. NTP가 맞기 전의 이벤트는 시각이 비어 `created_at`(DB 도착 시각)으로 본다.

## 출처

- 펌웨어 빌드 스크립트·Wi-Fi·EI 추론 틀: 팀 프로젝트 ppe-edge-guard의 내 담당 부분(firmware)에서 가져와 고침.
- 영상: AI 생성 창고 CCTV 스타일 클립(저작권 때문에 저장소에 넣지 않음).
- 모델 학습: Edge Impulse Public 프로젝트 `aisle-guard`(1155404).
