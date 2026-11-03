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
[카메라 시연] 노트북 화면의 demo.mp4 ─ 보드 카메라 (#CAM on, QVGA → 96×96) ─▶ 같은 ①~④
[CI]    push·PR ─▶ GitHub Actions: unit-test (logic·proto, g++) + firmware-build (arduino-cli, esp32 3.3.12)
                                  + model-gate (펌웨어 int8 모델, 시험 프레임 obstacle 재현율 ≥ 0.9)
```

집에서 실제 통로를 만들기 어려워 AI로 만든 창고 CCTV 영상(클립 5개)을 쓰고, PC가 프레임을 보드로 보낸다.
학습 입력과 시연 입력은 같은 코드(`tools/aisle_frames.py`, crop은 `tools/aisle.json`)로 잘린다.
영상의 정답 시각(물건을 둔 시각·치운 시각)을 알기 때문에 ±1초 검증을 할 수 있다. 모델은 보드 안에서만 돈다.

입력은 두 가지이고 펌웨어·모델·판정은 같다.
- **USB 모드(정량 검증)**: 같은 프레임이 매번 똑같이 들어가 ±1초 오차와 10회 반복을 잴 수 있다. 아래 검증 표의 수치는 모두 이 모드다.
- **카메라 모드(동작 시연)**: 보드 카메라가 노트북 화면의 영상을 찍어 판정한다(`#CAM on`, `tools/screen.py`). 지난 팀 프로젝트(ppe-edge-guard)에서 화면 재촬영은 5개 중 4개만 인식하고 점수가 0.4~0.7로 흔들렸고, 이번에도 처음 모델(d1)은 카메라 화면에서 obstacle 재현율 0.44였다. 그래서 보드가 찍은 화면 369장을 더해 다시 학습했다(d2).

## 모델

| 항목 | 값 |
|---|---|
| 프로젝트 | Edge Impulse Public `aisle-guard-v2` (1155430), Arduino 라이브러리 deploy v2 → `MODEL_VERSION "ei1155430-d2"` (d1: USB 프레임만으로 학습한 첫 모델) |
| 구조 | 96×96 RGB, FOMO MobileNetV2 0.35, int8, 60 cycles |
| 데이터 | USB 프레임: 클립 5개 × 10초를 3fps로, 학습 105장 / 시험 45장(클립마다 마지막 30%). 보드 카메라 화면(d2에서 추가): 카메라 모드 6·7회차와 녹화 2·3회차 369장 학습 / 92장 시험(5장마다 1장) |
| 라벨 | USB 프레임은 `tools/autolabel.py`: 고정 카메라라 빈 통로와의 차이로 박스 초안 → 150장 시트로 눈 확인. 카메라 화면은 `tools/cam_label.py`: 화면 시각 근처 demo.mp4 프레임을 ECC로 맞춰 박스를 옮김(상관 0.75 미만 버림). 선반 위 상자는 라벨 없음 |
| 검증 세트 | d2 F1 0.87, 정밀도 0.92 (d1 F1 0.85: obstacle 0.89, person 0.83) |
| 시험 세트 (d1) | 정확도 71%, F1 0.78. 물건 프레임은 대부분 맞힘. C5 끝의 카메라 바로 앞 큰 사람은 학습 구간에 없어 놓침(사람을 놓쳐도 경고는 생기지 않음) |
| model-gate (CI) | USB 시험 45장 obstacle 재현율 27/27, obstacle 없는 프레임의 통로 안 오검출 d1 1/18 → d2 0/18. 카메라 시험 92장(`tests/model_gate_cam`) d1 26/59 (0.44) → d2 59/59, 오검출 0/33. 카메라 시험은 학습과 같은 회차의 이웃 프레임이라 1.00은 낙관적인 값 |
| PC 시뮬레이션 (d2) | `simulate.py` 시연 영상: 지연 9.7·10.1초, 방치 +0.0초(d1 +0.5초), 오경보 0. 시나리오 1/3/4/5 회귀 없음 |
| 보드 | 추론 140~172ms (목표 500ms 이하). tensor arena는 EI 계산값 185,036B로는 `AllocateTensors()`가 실패해 320,000B로 늘림 |


## 조건별 구현

| 조건 | 구현 | 확인 방법 | 위치 |
|---|---|---|---|
| ① ESP32에 모델 | Edge Impulse FOMO(MobileNetV2 0.35, int8), 입력 96×96 RGB. Arduino 라이브러리로 펌웨어에 포함되고, 추론은 보드에서 한다(140~172ms) | 시리얼 로그 `F ... inf=`, 보드 LED, 아래 "모델" | `firmware/aisle_cam/detector_ei.cpp`, `firmware/libraries/` |
| ② 로그 DB | ESP32가 Supabase REST로 직접 insert(중간 서버 없음). `warning`·`cleared`·1분 `heartbeat`. 끊기면 20건 보관 후 재전송. TLS 인증서 검사 켬. RLS로 anon 키는 insert만 가능 | `db/queries.sql`(경고 횟수, 방치 시간, 장치 상태, 오경보 비율) | `uploader.cpp`, `db/schema.sql` |
| ③ CI | push·PR마다 세 작업: 판정 로직 단위시험(호스트 g++, `-Werror`), 모델을 넣은 펌웨어 컴파일, model-gate(펌웨어에 든 int8 모델을 PC에서 돌려 obstacle 재현율 0.9 미만이면 실패) | 위 ci 배지 | `.github/workflows/ci.yml`, `firmware/tests/`, `tools/model_gate.py` |

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

보드 시리얼 명령: `#AISLE x1 y1 x2 y2 ...`(통로 다각형, 96×96 좌표, 보드에 저장), `#AISLE?`, `#FAKE x y conf` / `#FAKE off`(모델 없이 배선 시험), `#CAM on|off`(카메라 모드), `#CAMCROP x y side`, `#CAMAE n`(노출), `#CAMMIRROR h v`, `#CONF c`(판정 점수 기준, 저장 안 함), `#VIEW on|off`(보드가 본 96×96을 PC로).

카메라 시연: `python tools/screen.py COM10 videos/demo.mp4` — 통로 부분을 크게 띄우고 보드 판정·보드 화면을 옆에 보여 준다. 스페이스로 재생 시작.

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
| D | 시연 영상 `demo.mp4` (모델, 보드, 2fps) | 경고 지연 T+2초 이내, 방치 ±1초, 오경보 0 | 상자 지연 10.2초, 방치 33.0초(정답 32.0초, +1.0초), 가방 지연 10.6초, 오경보 0, DB 201 전부. `verify.py` PASS |
| 0' | 시연 영상 리허설: 정답 시각에 `#FAKE`를 켜고 끔 (모델 없이) | 경고 지연 T+2초 이내, 방치 ±1초, 오경보 0 | 경고 지연 10.7초·10.1초, 방치 31.5초(정답 32초, −0.5초), 오경보 0, DB 5건, 프레임 손실 0 |
| 1 | 학습한 물건을 통로에 15초 두고 치움 (`scenario1.mp4` ×10) | 경고 9/10 이상, 지연 T+2초 이내 | **통과** 경고 10/10, 지연 9.7~10.2초 |
| 2 | 시나리오 1의 방치 시간 | DB `dwell_s`와 정답 차이 ±1초 | **경계에서 통과** 9회 모두 +1.0초(15.0 → 16.0초). 10번째는 영상이 해제 전에 끝남 |
| 3 | 사람이 통로를 걸어서 지나감 (`scenario3.mp4` ×10) | 경고 0/10 | **통과** 0/10 |
| 4 | 물건을 5초만 두고 치움 (`scenario4.mp4` ×5) | 경고 0/5 | **통과** 0/5 |
| 5 | 물건을 통로 밖에 15초 둠 (`scenario5.mp4` ×5) | 경고 0/5 | **통과** 0/5. 단 모델이 합성 상자를 검출하지 않아, `#FAKE 83 45 0.9`(통로 밖)로 다시: 검출 176프레임 모두 무시, 경고 0 |
| 6 | 경고 중 Wi-Fi 끊었다 다시 연결 | LED 유지, 재연결 후 기록 누락 0 | **1회만 확인** 공유기를 끌 수 없어 계획(2회)대로는 못 함. 시연 중 약한 신호(RSSI −80)로 저절로 20초 끊긴 사이 경고 발생 → LED 판정 계속, 재연결 후 경고·해제·heartbeat 전송, 누락 0 |

위 보드 결과는 모두 USB 모드, `ei1155430-d1`, 보드 COM10, 2fps 기준이다. d2는 PC 시뮬레이션에서 같은 시나리오 회귀가 없었고(위 "모델"), 보드 재확인 결과는 아래 카메라 모드 표 다음에 적는다.

카메라 모드(d1, 손에 들고 노트북 화면을 찍음): 6회차 상자·가방 `verify.py` PASS(지연 10.8·11.2초, 방치 +0.5초, 오경보 0, 판정 점수 기준 0.4), 7회차 지연 13.3·12.7초, 방치 −2.5초로 FAIL. 회차마다 1~3초씩 달라져 카메라 모드는 동작 시연으로만 쓰고 수치는 USB 모드로 보고한다. 시나리오는 PRD "검증 계획"과 같고, 실물 대신 영상 구간(`tools/scenario*.json` → `make_demo.py`)으로 재현했다.

방치 시간이 매번 +1.0초인 이유: 내려놓는 중에 0.3초 일찍 잡고, 들고 가는 상자를 0.7초 더 잡는다. 들고 지나가는 상자도 통로를 막는 것이라 틀렸다고 보기는 어렵지만, ±1초 기준에는 여유가 없다.

## 한계

- 실제 통로가 아니라 AI로 만든 영상이다. 정량 검증은 PC가 USB로 보낸 프레임으로 했고, 보드 카메라는 노트북 화면을 다시 찍는 시연에서만 썼다. 실제 조명·거리·렌즈 왜곡에 대한 성능은 알 수 없다.
- 카메라 화면 학습 데이터의 person 박스는 autolabel 박스를 옮긴 것이라 일부 어긋나 있다. person은 "물건 옆 사람이면 보류"에만 쓰여 경고에 주는 영향은 작다.
- 클립이 5개뿐이라 학습과 시연이 같은 장면이다(클립마다 시간으로 나눠 마지막 30%를 시험 세트로 둠). 처음 보는 장면·물건에 대한 성능은 이 결과로 말할 수 없다.
- 같은 클립 구간을 반복하는 시험이라 시나리오별 10회·5회는 서로 독립된 시험이 아니다.
- Wi-Fi 끊김(시나리오 6)은 계획한 2회가 아니라 저절로 일어난 1회만 확인했다.
- 통로 밖 시험(시나리오 5)의 합성 상자는 모델이 검출하지 못해, 통로 다각형 판정은 가짜 검출(`#FAKE`)로 확인했다.
- FOMO는 상자 크기가 아니라 중심점만 낸다. 물건이 통로 경계에 걸치면 중심점 위치에 따라 안/밖이 갈린다.
- 사람 바로 옆(16px 안)의 물건은 보류하므로, 사람이 물건 옆에 오래 서 있으면 그동안 경고가 늦어진다.
- 방치 시간은 첫 "있음" 프레임부터 마지막 "있음" 프레임까지라 0.5초(2fps 한 프레임) 단위로 어긋난다. 가짜 검출로는 0.5초 짧게, 모델로는 물건을 내려놓고 드는 순간까지 잡아 1.0초 길게 나왔다.
- 펌웨어에 든 anon(publishable) 키는 보드에서 꺼낼 수 있다. RLS로 insert만 되지만, 키를 얻은 사람이 가짜 행을 넣을 수는 있다. 장치별 인증은 하지 않았다.
- 보내지 못한 이벤트는 20건까지만 보관하고, heartbeat도 같은 칸을 쓴다. Wi-Fi가 20분 넘게 끊기면 오래된 경고·해제가 heartbeat에 밀려 지워진다. 응답이 8초를 넘으면 다시 보내므로, 서버가 이미 받았다면 같은 행이 두 번 들어갈 수 있다.
- `#AISLE`·`#CONF`·`#CAM on` 명령은 판정을 처음 상태로 되돌린다. 경고 중에 보내면 그 경고의 `cleared`가 기록되지 않는다(조회 3에서 계속 open).
- 시각은 NTP로 맞춘 UTC다. 부팅 후 30초 안에 맞추지 못하면 다시 시도하지 않는다. NTP가 맞기 전의 이벤트는 시각이 비어 `created_at`(DB 도착 시각)으로 본다.

## 출처

- 펌웨어 빌드 스크립트·Wi-Fi·EI 추론 틀: 팀 프로젝트 ppe-edge-guard의 내 담당 부분(firmware)에서 가져와 고침.
- 영상: AI 생성 창고 CCTV 스타일 클립(저작권 때문에 저장소에 넣지 않음).
- 모델 학습: Edge Impulse Public 프로젝트 `aisle-guard-v2`(1155430). 처음 만든 `aisle-guard`(1155404)는 업로드 키 권한 문제로 박스를 붙이지 못해 쓰지 않음.
