# aisle-guard — 통로 장애물 방치 감지기

[![ci](https://github.com/msungaffa/aisle-guard/actions/workflows/ci.yml/badge.svg)](https://github.com/msungaffa/aisle-guard/actions/workflows/ci.yml)

통로에 물건(상자·가방)이 **10초 넘게** 놓여 있으면 ESP32가 LED로 경고하고, 이벤트를 Supabase에 기록한다.
사람은 장애물로 세지 않는다. 모델은 **보드 안에서만** 돈다.

- PRD: https://claude.ai/artifact/7vguen5tdMA9Pb4VUPn3XW
- 대시보드(DB 이벤트): https://claude.ai/artifact/Y96SJDB35Cw7M9EcPwVKvg

## 어떻게 동작하나

```
카메라 화면 ─▶ XIAO ESP32S3 Sense
                ① FOMO 모델 추론 (96×96, 약 160ms) → obstacle / person 위치
                ② 판정: 통로 안 물건이 10초 넘게 있으면 경고
                ③ LED: 관찰 1Hz 깜빡임 / 경고 5Hz 깜빡임
                ④ Supabase에 warning · cleared · heartbeat 기록 (끊기면 보관 후 재전송)
```

- 시연 영상은 AI로 만든 창고 CCTV 클립이다. 물건을 둔 시각·치운 시각을 알기 때문에 ±1초까지 검증할 수 있다.
- 입력은 두 가지이고, 펌웨어·모델·판정은 같다.
  - **USB 모드(수치 검증)**: PC가 영상 프레임을 보드로 보낸다. 매번 같은 입력이라 반복 시험에 쓴다.
  - **카메라 모드(시연)**: 보드 카메라가 노트북 화면을 직접 찍는다.

## 과제 조건

| 조건 | 구현 | 위치 |
|---|---|---|
| ① ESP32에 모델 탑재 | Edge Impulse FOMO(MobileNetV2 0.35, int8)를 Arduino 라이브러리로 넣음. 추론 157~163ms | `firmware/aisle_cam/detector_ei.cpp` |
| ② 로그 DB 저장 | ESP32가 Supabase REST로 바로 insert(중간 서버 없음). RLS로 insert만 허용 | `firmware/aisle_cam/uploader.cpp`, `db/` |
| ③ CI | push마다 판정 로직 단위시험 + 펌웨어 컴파일 + 모델 품질 검사(obstacle 재현율 0.9 미만이면 실패) | `.github/workflows/ci.yml` |

## 판정 규칙

1. 점수 0.6 이상인 `obstacle`이 통로 영역 안에 있으면 그 프레임은 "있음"이다. 사람 바로 옆의 물건은 보류한다.
2. 최근 6프레임 중 4프레임이 "있음"이면 점유로 본다.
3. 점유가 10초를 넘으면 경고(`warning`)를 보낸다. 물건을 치우면 해제(`cleared`)와 방치 시간을 보낸다.

규칙은 `firmware/aisle_cam/logic.cpp` 한 곳에만 있어 PC에서 단위시험을 돌린다.

## 모델

| 항목 | 값 |
|---|---|
| 구조 | 입력 96×96 RGB, FOMO MobileNetV2 0.35, int8 |
| 데이터 | 영상 프레임 105장 + 보드 카메라로 찍은 화면 369장(학습). 라벨 `obstacle`, `person` |
| 성능 | 검증 F1 0.87, 정밀도 0.92 |
| 버전 | `ei1155430-d2`. 첫 모델(d1)은 카메라 화면에서 물건을 절반도 못 찾아(재현율 0.44), 보드 카메라 화면을 더해 다시 학습함 → 카메라 시험 59/59 |

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
python tools/screen.py COM10 videos/demo.mp4         # 카메라 모드 시연
python tools/verify.py tools/logs/feed_<시각>.log    # 성공 기준 계산
```

DB는 `db/schema.sql`을 Supabase에서 한 번 실행하고, 비밀값은 `firmware/aisle_cam/secrets.h`(`secrets.example.h` 복사)에 넣는다. 로그 조회 SQL은 `db/queries.sql`에 있다.

작업 문서: `HANDOFF.md`(현재 상태), `docs/HISTORY.md`(날짜별 기록·측정 상세).
