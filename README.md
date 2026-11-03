# aisle-guard — 통로 장애물 방치 감지기

[![ci](https://github.com/msungaffa/aisle-guard/actions/workflows/ci.yml/badge.svg)](https://github.com/msungaffa/aisle-guard/actions/workflows/ci.yml)

통로에 물건(상자·가방)이 **10초 넘게** 놓여 있으면 ESP32가 LED로 경고하고, 이벤트를 Supabase에 기록합니다.
사람은 장애물로 세지 않습니다. 모델은 **보드 안에서만** 돌아갑니다.

- 시연 영상(화면 녹화 + 보드 LED): https://drive.google.com/file/d/1YHrJpq66roO4Dqs8m1JyYQ0wWA_3UZJz/view?usp=sharing
- PRD: https://claude.ai/artifact/7vguen5tdMA9Pb4VUPn3XW
- 대시보드(DB 이벤트): https://claude.ai/artifact/Y96SJDB35Cw7M9EcPwVKvg
- 한 장 요약(아키텍처 그림 + README): https://msungaffa.github.io/aisle-guard/

## 어떻게 동작하나

```
카메라 화면 ─▶ XIAO ESP32S3 Sense
                ① FOMO 모델 추론 (96×96, 약 160ms) → obstacle / person 위치
                ② 판정: 통로 안 물건이 10초 넘게 있으면 경고
                ③ LED: 관찰 1Hz 깜빡임 / 경고 5Hz 깜빡임
                ④ Supabase에 warning · cleared · heartbeat 기록 (끊기면 보관 후 재전송)
```

- 시연 영상은 AI로 만든 창고 CCTV 클립입니다. 물건을 둔 시각·치운 시각을 알기 때문에 ±1초까지 검증할 수 있습니다.
- 입력은 두 가지이고, 펌웨어·모델·판정은 같습니다.
  - **USB 모드(수치 검증)**: PC가 영상 프레임을 보드로 보냅니다. 매번 같은 입력이라 반복 시험에 씁니다.
  - **카메라 모드(시연)**: 보드 카메라가 노트북 화면을 직접 찍습니다.

## 전체 구현 아키텍처

```
 [PC]                                   [XIAO ESP32S3 Sense]                         [클라우드]
 videos/*.mp4                          ┌──────────────────────────────────┐
   │                                   │ 입력                              │
   ├─ tools/feed.py ── USB 96×96 ────▶ │  시리얼 프레임 수신 (USB 모드)    │
   │                                   │  camera.cpp: OV2640 (카메라 모드) │
   └─ tools/screen.py ─ 노트북 화면 ─▶ │         │                         │
        ▲     (보드 카메라가 찍음)      │         ▼                         │
        │                              │ detector_ei.cpp: FOMO int8 추론   │
        │                              │         │ 중심점·점수             │
        │                              │         ▼                         │
        │   F/V 로그 줄 (시리얼)        │ logic.cpp: 통로·사람·시간 창 판정 │
        └──────────────────────────────│         │ level 0/1/2, 이벤트     │
 tools/verify.py: 로그 ↔ 정답 비교      │    ┌────┴─────┐                   │
                                       │    ▼          ▼                   │
                                       │ LED(GPIO21)  EventQueue(20칸)     │
                                       │              │                    │      Supabase
                                       │ net.cpp: Wi-Fi·NTP                │   ┌──────────────┐
                                       │ uploader.cpp: HTTPS POST ─────────┼──▶│ aisle_events │
                                       └──────────────────────────────────┘   │ (RLS insert) │
                                                                              └──────┬───────┘
 Edge Impulse (aisle-guard-v2) ─ 학습·배포 ─▶ Arduino 라이브러리                       │
 GitHub Actions: unit-test · firmware-build · model-gate               db/queries.sql, 대시보드
```

| 층 | 구성 요소 | 역할 |
|---|---|---|
| 입력 | `tools/feed.py`, `camera.cpp`, `tools/screen.py` | USB로 영상 프레임 전송, 또는 보드 카메라로 화면 촬영 |
| 추론 | `detector_ei.cpp` (`detector_stub.cpp`는 모델 없는 배선 시험용) | Edge Impulse FOMO로 obstacle·person 중심점과 점수 산출 |
| 판정 | `logic.cpp`, `logic.h` (`LogicConfig`) | 점수·통로·사람·시간 창 규칙으로 단계와 이벤트 결정. Arduino 비의존 |
| 표시 | `aisle_cam.ino`의 `led_loop` | 단계를 LED 깜빡임 속도로 표시 |
| 전송 | `net.cpp`, `uploader.cpp`, `EventQueue` | Wi-Fi·NTP 시각, 이벤트를 큐에 두고 Supabase REST로 insert, 실패 시 재전송 |
| 저장·조회 | `db/schema.sql`, `db/queries.sql`, 대시보드 | `aisle_events` 표(RLS insert만), 시간대별 경고·방치 시간·장치 상태 조회 |
| 모델 | Edge Impulse `aisle-guard-v2`, `tools/autolabel.py`, `tools/cam_label.py` | 자동 라벨 초안 → 학습 → Arduino 라이브러리 배포 |
| 검증 | `tools/verify.py`, `tools/simulate.py`, `tools/model_gate.py` | 보드 로그를 정답과 비교, PC 시뮬레이션, 모델 재현율 검사 |
| CI | `.github/workflows/ci.yml` | 판정 단위시험 + 펌웨어 컴파일 + model-gate |

## 과제 조건

| 조건 | 구현 | 위치 |
|---|---|---|
| ① ESP32에 모델 탑재 | Edge Impulse FOMO(MobileNetV2 0.35, int8)를 Arduino 라이브러리로 탑재. 추론 157~163ms | `firmware/aisle_cam/detector_ei.cpp` |
| ② 로그 DB 저장 | ESP32가 Supabase REST로 직접 insert(중간 서버 없음). RLS로 insert만 허용 | `firmware/aisle_cam/uploader.cpp`, `db/` |
| ③ CI | push마다 판정 로직 단위시험 + 펌웨어 컴파일 + 모델 품질 검사(obstacle 재현율 0.9 미만이면 실패) | `.github/workflows/ci.yml` |

## 시연 프로그램: ESP32가 보는 화면을 같이 보기

`tools/screen.py`는 노트북 한 화면에 영상과 보드 상태를 나란히 띄웁니다. `camera_demo.bat`을 더블클릭해도 실행됩니다.

```
┌──────────────────────────────┬──────────────────────────┐
│                              │ ESP32 camera             │
│   통로 영상 (640×640)        │ CLEAR / OBJECT IN AISLE  │  ← 보드 판정 단계
│                              │ / WARNING: OBSTACLE      │
│                              │ obstacle=1 person=0      │  ← 이번 프레임 검출 수
│   ← 보드 카메라가            │ inference 160ms          │  ← 보드 추론 시간
│     이 칸만 찍음             │ video 23.5s              │
│                              │ ┌──────────────────────┐ │
│                              │ │ board sees (96×96)   │ │  ← 보드가 실제로 본 그림
│                              │ │ + 빨간 통로 영역 선  │ │
│                              │ └──────────────────────┘ │
└──────────────────────────────┴──────────────────────────┘
```

| 부분 | 하는 일 |
|---|---|
| 왼쪽 영상 칸 | 시연 영상의 통로 부분을 크게 재생. 보드 카메라는 이 칸만 찍도록 배치 |
| 보드 → PC (시리얼) | 프레임마다 판정 단계·검출 수·추론 시간을 한 줄씩 전송. `#VIEW on`이면 모델에 들어간 96×96 그림도 `V <hex>` 줄로 전송 |
| 오른쪽 칸 | 그 줄을 읽어 상태를 글자로 표시하고, 96×96 그림을 확대해 통로 영역과 함께 표시 |
| 조준 단계 | 실행하면 상자가 있는 장면에서 정지. "board sees"를 보며 카메라 위치를 맞추고 스페이스를 누르면 재생·판정 시작 |
| 카메라 조정 키 | `-`/`=` 노출, `m`/`f` 좌우·상하 반전. 보드에 `#CAMAE`, `#CAMMIRROR` 명령으로 전송 |
| 기록 | 보드 로그를 저장해 `verify.py`로 정답 시각과 비교. 보드 화면도 장면별로 저장해 재학습 데이터로 사용 |

"board sees" 화면 덕분에 모델이 무엇을 보고 판정했는지 바로 확인할 수 있습니다. 검은 테가 보이거나 좌우가 뒤집혀 있으면 그 자리에서 고칩니다.

## 판정 로직 (`firmware/aisle_cam/logic.cpp`)

모델은 프레임마다 물체의 **중심점과 점수**만 냅니다. 이것을 경고로 바꾸는 규칙은 다음과 같습니다.

| 단계 | 규칙 | 이유 |
|---|---|---|
| 1. 점수 거르기 | 점수 0.6 미만인 검출은 제외 | 흐린 화면의 약한 오검출 제거 |
| 2. 통로 안인가 | `obstacle` 중심점이 통로 다각형 안에 있어야 함. 선반 위 상자는 제외 | 통로를 막는 물건만 대상 |
| 3. 사람 옆은 보류 | `person` 중심 16px 안의 obstacle은 "보류"로 두고 세지 않음 | 사람(옷·가방)을 물건으로 잘못 본 경우 대비 |
| 4. 시간 창 | 최근 6프레임 중 4프레임 이상 "있음"이면 점유, 1프레임 이하면 해제 | 한두 프레임 놓치거나 튀어도 흔들리지 않게 |
| 5. 단계 | 0 정상 → 1 관찰(점유 시작, LED 1Hz) → 2 경고(점유 10초, LED 5Hz, `warning` 기록) | 잠깐 둔 물건은 경고하지 않음 |
| 6. 해제 | 점유가 끝나면 `cleared`와 방치 시간(첫 "있음" ~ 마지막 "있음") 기록 | DB에서 방치 시간 통계 |

모든 수치(0.6, 6/4/1, 10초)는 `LogicConfig` 한 곳에 있습니다. 규칙이 Arduino에 기대지 않아 PC에서 단위시험(`firmware/tests/test_logic.cpp`)을 돌리고, CI도 같은 시험을 돌립니다.

### LED 경고 (`aisle_cam.ino`의 `led_loop`)

LED는 프레임마다 반응하지 않고 판정 단계(`AisleLogic::level()`)만 봅니다. 판정과 표시가 나뉘어 있어 LED 쪽은 단계를 깜빡임 속도로 바꾸기만 합니다.

| 단계 | 언제 | LED |
|---|---|---|
| 0 정상 | 점유 아님 | 꺼짐 |
| 1 관찰 | 점유 시작 ~ 10초 전 | 1Hz로 천천히 깜빡임 (0.5초 켜짐 / 0.5초 꺼짐) |
| 2 경고 | 점유 10초 이상 | 5Hz로 빠르게 깜빡임 (0.1초씩), `warning` 기록 |

- 깜빡임은 `millis()`를 나눈 값의 홀짝으로 정해 따로 타이머가 없습니다. 매 `loop()`마다 다시 계산합니다.
- XIAO ESP32S3 사용자 LED(GPIO 21)는 LOW일 때 켜집니다.
- 판정과 LED는 보드 안에서만 돌기 때문에 Wi-Fi가 끊겨도 경고는 계속됩니다. DB 기록은 큐에 두었다가 다시 연결되면 보냅니다.

예: 상자를 15초 두었다 치우면 다음과 같이 진행됩니다.
1. 6프레임 창에 "있음"이 4개 쌓이면(약 2초) 점유가 시작되고 1Hz로 깜빡입니다. 방치 시간은 첫 "있음" 프레임부터 셉니다.
2. 10초가 되면 5Hz로 바뀌고 `warning`을 기록합니다.
3. 상자를 치워 창의 "있음"이 1개 이하가 되면 LED가 꺼지고 `cleared`(방치 약 15초)를 기록합니다.

## 모델

| 항목 | 값 |
|---|---|
| 구조 | 입력 96×96 RGB, FOMO MobileNetV2 0.35, int8 |
| 데이터 | 영상 프레임 105장 + 보드 카메라로 찍은 화면 369장(학습). 라벨 `obstacle`, `person` |
| 성능 | 검증 F1 0.87, 정밀도 0.92 |
| 버전 | `ei1155430-d2`. 첫 모델(d1)은 카메라 화면에서 물건을 절반도 못 찾아(재현율 0.44), 보드 카메라 화면을 더해 재학습 → 카메라 시험 59/59 |

## 정확도를 높인 과정

| 문제 | 원인 찾기 | 개선 | 결과 |
|---|---|---|---|
| 라벨을 손으로 붙이기엔 시간 부족 | 카메라가 고정이라 빈 통로와 다른 부분이 곧 물체 | `autolabel.py`: 빈 통로와의 차이로 박스 초안 → 150장 시트로 눈 확인 | USB 시험 obstacle 27/27 |
| 카메라 모드에서 물건을 절반도 못 찾음 (d1 재현율 0.44) | 영상을 PC에서 흐리게·어둡게·비스듬히 바꿔 같은 모델로 시험 → 흐림·밝기는 괜찮고 **검은 테와 기울어짐**이 문제 | 카메라 자르기(`#CAMCROP`)로 화면을 꽉 차게, "board sees"로 조준 | 검은 테 없이 촬영 |
| 화면이 하얗게 날아가 검출 0 | 저장한 보드 화면 확인 | 노출 조절 `#CAMAE` 추가 | 검출 회복 |
| 보드 카메라 좌우 반전 | 보드 화면과 영상 비교 | 반전 명령 `#CAMMIRROR` 추가 | 영상과 같은 방향 |
| 화면 재촬영 시 점수가 여전히 흔들림(0.3~0.9) | 학습 데이터가 깨끗한 영상 프레임뿐 | **보드가 실제로 찍은 화면 369장을 학습에 추가**. 화면 시각에 맞는 영상 프레임을 찾아(ECC 정렬) 박스를 옮겨 라벨 | d2: 카메라 시험 **59/59**, 오검출 0/33, 점수 기준 0.6 그대로 PASS |
| 방치 시간이 매번 +1.0초 | 내려놓는 순간과 들고 가는 순간까지 물건으로 인식 | d2 재학습 | 시나리오 1에서 **오차 0.0초** ×10 |
| 시연 중 보드 재부팅 | 백트레이스 해석: 시각 맞추기(SNTP)와 업로드가 겹칠 때 충돌 | 시각을 맞추면 SNTP를 멈추고 그 뒤에만 업로드 | 재부팅 0 |

모델을 바꿀 때마다 CI의 model-gate가 펌웨어에 든 모델을 시험 프레임에 돌려, 재현율이 0.9 아래로 떨어지면 막습니다.

## 검증 결과

| 시나리오 | 기준 | 결과 |
|---|---|---|
| 물건을 15초 두고 치움 ×10 | 9/10 이상 경고 | **10/10**, 경고까지 9.7~10.2초 |
| 그때의 방치 시간 | 실제와 ±1초 | **10회 모두 오차 0.0초** (d2) |
| 사람이 지나감 ×10 | 경고 0 | **0/10** |
| 물건을 5초만 둠 ×5 | 경고 0 | **0/5** |
| 물건을 통로 밖에 둠 ×5 | 경고 0 | **0/5** |
| 경고 중 Wi-Fi 끊김 | 기록 누락 0 | **누락 0** (1회) |
| 시연 영상(USB·카메라 모드) | 경고 12초 이내, 방치 ±1초, 오경보 0 | **PASS** (경고까지 10.2~10.7초, 오경보 0) |

## 실행

```powershell
powershell -File firmware/tests/run_tests.ps1        # 판정 로직 단위시험
powershell -File firmware/build.ps1 -Port COM10      # 컴파일 + 업로드
python tools/feed.py COM10 videos/demo.mp4           # USB 모드 시연
python tools/screen.py COM10 videos/demo.mp4         # 카메라 모드 시연 (camera_demo.bat 더블클릭과 같음)
python tools/verify.py tools/logs/feed_<시각>.log    # 성공 기준 계산
```

DB는 `db/schema.sql`을 Supabase에서 한 번 실행하고, 비밀값은 `firmware/aisle_cam/secrets.h`(`secrets.example.h` 복사)에 넣습니다. 로그 조회 SQL은 `db/queries.sql`에 있습니다.

작업 문서: `HANDOFF.md`(현재 상태), `docs/HISTORY.md`(날짜별 기록·측정 상세).
