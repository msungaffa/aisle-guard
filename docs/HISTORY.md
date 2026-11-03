# HISTORY

## 2026-11-03 주제 결정과 시작
- 과제: ESP32 프로젝트, 주제 자유, 필수 조건 ① ESP32에 모델 탑재 ② 로그 DB 저장 ③ CI. 원래 5명 분량을 혼자, 16:30 마감.
- 사용자 배경: 자동차공학과, 품질관리 직무 지망 → 판정 기준·실측 검증·기록 관리를 보여 주는 주제로.
- 보드 확인(esptool): ESP32-S3 (QFN56) rev v0.2, PSRAM 8MB, 플래시 8MB, MAC 68:ee:8f:47:19:30, COM10 → PPE 때 쓰던 XIAO ESP32S3 Sense(OV3660 카메라 + PDM 마이크, 가속도계 없음).
- 후보: 진동 이상(가속도계 없음), 소리 이상(사용자가 어렵다고 판단), 외관 검사 → 사용자의 기획 페이지 https://msungaffa.github.io/physical-ai/ (AI 작업장 안전관리 시스템)의 PoC 2 "통로 장애물 감지"를 ESP32 버전으로 줄이기로 결정.
- 범위: 객체 추적 없이 통로 영역 + 시간 창(최근 N 프레임 중 K) + 방치 시간 T. 라벨은 물건을 `obstacle` 하나로 묶고 `person`을 따로 둠. 물건: 상자·가방·의자(의자는 클립 수 부족으로 뺌).
- DB는 서버 없이 ESP32 → Supabase REST. CI는 GitHub Actions(컴파일 + 판정 로직 단위시험, 여유 있으면 모델 게이트).
- PRD: https://claude.ai/artifact/7vguen5tdMA9Pb4VUPn3XW

## 2026-11-03 저장소와 사진 수집
- 저장소 생성, PPE 펌웨어 파일 복사. `capture_cam` 스케치(QVGA JPEG을 hex 한 줄로) + `tools/capture.py`(zero-touch `model/testing/capture.py` 방식, 가운데 240×240 자름 — `detector_ei.cpp`가 가운데 정사각형을 잘라 넣으므로 학습 입력과 맞춤).
- 업로드 후 시험 촬영 2장 정상.
- `build.ps1`에 스케치 선택 인자 추가하다 `param($Sketch)`와 `$sketch`가 같은 변수라 경로가 꼬일 뻔함 → `-Name`. bash heredoc 파이썬에서 `"C:\aisle_build"`의 `\a`가 벨 문자로 바뀌어 `C:isle_build`가 됨 → 정규식 교체로 고침.

## 2026-11-03 데이터 방식 변경: AI 영상 + 시리얼 프레임 전송
- 사용자: 집에서 실제 통로 시연이 어렵다 → 시연 영상을 잘 인식하게 만들기로.
- 유튜브 검색: 고정 CCTV에 물건이 오래 놓인 영상은 못 찾음(사고 모음은 장면이 몇 초마다 바뀜). AI 생성 영상으로 결정, 생성 가능 개수 5개.
- 방법 A 채택: PC가 영상 프레임을 USB 시리얼로 ESP32에 보냄. 이유: 학습 입력과 시연 입력이 같음, 반복 가능, 정답 시간을 알아 ±1초 검증 가능. 방법 B(보드 카메라로 화면 촬영)는 반사·줄무늬로 정확도 하락.
- 클립 5개라 학습/시연 분리 불가 → 클립마다 마지막 30%를 시험 세트로 두는 시간 분할 + 보고서에 한계 명시. 근거: 고정 카메라 현장 맞춤 학습(기획 페이지의 "현장 영상으로 다듬는다").
- 기준 사진: 선반에 상자가 많은 CAM 14 South Aisle 스타일 선택. 선반 상자 오인 대책: 다각형(사다리꼴) 통로 영역, 바닥 물건에만 라벨, 보내기 전 통로 부분만 자르기. 96×96에서 먼 물건은 작아서 프롬프트를 "카메라 가까이, 화면 아래쪽"으로 수정.

## 2026-11-03 연결과 영상 없이 할 수 있는 것
- 연결: GitHub(gh, 기존), Edge Impulse Public 프로젝트 `aisle-guard`(ID 1155404) 생성 — 비공개 자리 0/3이라 사용자가 Public 선택, labeling method를 bounding boxes로(키가 ingestion 권한이라 API로는 403, Studio 화면에서 바꿈). Supabase는 일시정지된 개인 프로젝트를 복구(사용자 선택), 다른 테이블(documents 등)은 건드리지 않음.
- `aisle_events` 마이그레이션 적용(첫 시도는 `drop policy if exists` 때문인지 확인 창이 자동 취소 → 빼고 재시도). anon 키 시험: insert 201, select 401, delete 401, 잘못된 event 400. advisor에 aisle_events 관련 경고 없음.
- 판정 로직 TDD: 시험 18개 먼저 쓰고 스텁으로 실패 확인(logic 38 FAILED, proto 23 FAILED) 후 구현 → ALL PASS. 설계 결정: 사람 근처(16px) obstacle은 Absent가 아니라 Skip(창에 안 넣음) — Absent로 치면 사람이 상자 옆을 지나가는 C2에서 해제가 잘못 나올 수 있어서. 방치 시작 = 점유가 된 창 안의 첫 "있음" 프레임 시각.
- 프레임 형식 `AGFR`+video_ms+len+RGB888(27,648B)+xor. USB CDC라 보율과 상관없이 빠르고, 보드가 늦으면 USB가 PC 쓰기를 막아 손실 없음.
- 업로더는 코어 0 FreeRTOS 태스크(TLS 핸드셰이크 1.5~2초가 판정 루프를 막지 않게). 코어 3.3.12의 `NetworkClientSecure::useBuiltinCACertBundle()`로 인증서 검사 유지(PRD 위험 표의 "검사 생략" 대안은 안 씀).
- 보드 배선 시험(`#FAKE 48 48 0.9`, 회색 프레임 2fps): 첫 실행 경고 10.0초·DB 201, 해제 명령이 안 먹음(프레임 찌꺼기 + 명령) → 수정. 두 번째 실행에서 포트 열 때 보드 리셋 → DTR/RTS 끔. 최종: 경고 v=10.0초, `#FAKE off` 15.0초 → 해제 v=17.0초, dwell 14.5초(−0.5초), 업로드 1.5~1.8초, DB 행 확인.
- 도구: extract_frames(한글 경로 imwrite 실패 → imencode), ei_upload(dry-run 확인, 실제 업로드는 영상 후), make_demo, verify(합성 로그로 자체 시험 PASS).
- CI: unit-test(g++ -Werror), firmware-build(arduino-cli + esp32 3.3.12, 코어 캐시, secrets.example.h 복사, `firmware/libraries` 있으면 사용).

## 2026-11-03 ② 시연·검증 (11:35)
- 클립(모두 10초·24fps·1280×720)을 crop 기준 0.125초 간격으로 봄. C1 상자 바닥 닿음 5.3초, C3 상자 들림 5.3초(든 채 7.4초까지 crop 안), C4 가방 바닥 5.9초. `videos/empty.jpg`는 사람 있는 CAM 14 사진, `ref.jpg`는 빈 통로지만 1376×768이라 안 씀 → `make_demo.py`에 `hold_first` 추가, 빈 통로는 C1·C5 첫 화면 정지.
- `tools/demo.json` → `videos/demo.mp4` 82.0초. 정답: 상자 둠 10.3초, 치움 42.3초(32초 방치), 가방 둠 65.9초(끝까지 16.1초).
- 스텁 + `#FAKE`를 정답 시각에 켜고 끈 리허설(`feed.py`, 2fps, `#AISLE 36 0 58 0 94 96 0 96`): 경고 v=21.0초(지연 10.7초), 해제 v=44.5초 dwell 31.5초(오차 −0.5초), 가방 경고 v=76.0초(지연 10.1초), 오경보 0, DB 201 5건, 프레임 손실 0. `verify.py` 둘 다 PASS.

## 2026-11-03 ③ 문서·마무리 (11:45)
- `db/queries.sql`: 시간대별 경고, 하루 단위 평균·최대 방치, 경고-해제 짝(시작 시각 ±2초), 장치별 마지막 heartbeat(3분 넘으면 offline), 오경보 비율, 모델 버전별 비교. 실제 DB에서 모두 실행 확인(해제 1건 14.5초, 해제 안 된 경고 2건 = 리허설 중 feed 중단).
- 오경보 표시: 원본 `aisle_events`는 장치가 쓰는 기록이라 고치지 않고 별도 표 `aisle_event_reviews(event_id, verdict, note)`. RLS 켬, anon·authenticated 권한 0 확인. MCP 마이그레이션은 권한 단계에서 막혀 사용자가 SQL 편집기에서 실행.
- 대시보드: Supabase 연결은 이 PC의 로컬 MCP라 웹 페이지가 실시간으로 읽을 수 없고, anon에 select를 열지 않기로 함 → DB 행을 JSON으로 받아 붙인 스냅숏(Dashboard 아티팩트). 실측 뒤 다시 받는다.

## 2026-11-03 ① 모델 (창 ①)
- crop: 1280×720에서 [440, 320, 400, 400](통로 바닥), 통로 다각형 96×96 `36 0 58 0 94 96 0 96` → `tools/aisle.json`.
- 프레임: 클립 5개 × 10초, 3fps → training 105 / testing 45(클립마다 마지막 30%).
- 라벨: 손 대신 `tools/autolabel.py`(고정 카메라 → 빈 통로와의 차이). 첫 시도는 상자 그림자 꼬리 때문에 상자가 세로로 길어져 person으로 분류, 사람이 상자 옆이면 한 덩어리 → 클립별로 물건이 혼자 보이는 프레임에서 위치를 잡고(그림자 줄 잘라냄) 그 자리가 기준 모습과 비슷하면 obstacle, 나머지 덩어리는 person(통로 밖 사람도 라벨). 150장 시트로 눈 확인. 박스: training obstacle 46 / person 113, testing 50개.
- EI: 기존 프로젝트(1155404)에 라벨 없이 먼저 올렸는데 키가 ingestion 권한이라 박스를 붙일 수 없음. admin 키 생성은 자동 권한 검사에서 거부, 샘플 삭제는 데이터 영구 삭제라 하지 않음 → 새 Public 프로젝트 `aisle-guard-v2`(1155430)에 박스와 함께 업로드. 옛 프로젝트는 사용자가 나중에 지워도 됨.
- 학습: 96×96 RGB, FOMO MobileNetV2 0.35, 60 cycles, lr 0.001, augmentation. 검증 F1 0.85(obstacle 0.89, person 0.83), 정밀도 0.93, 재현율 0.78. 시험 세트(float32) 정확도 71%, F1 0.78 — 물건 프레임은 대부분 100%, C5 끝(카메라 바로 앞 큰 사람)은 학습 구간에 없어서 놓침. 사람을 놓치는 건 경고를 만들지 않음.
- 배포: API로 Arduino int8 tflite 빌드(deploy v1) → `firmware/libraries/aisle-guard-v2_inferencing`(25MB, 1337 파일) 커밋, `build.ps1`도 `--libraries firmware/libraries` 사용(CI와 같게). `DETECTOR_EI 1`, `MODEL_VERSION "ei1155430-d1"`.
- model-gate(CI): 펌웨어 라이브러리 헤더의 int8 모델 바이트를 꺼내 LiteRT로 실행, `tests/model_gate/`(시험 45장, feed.py와 같은 자르기, 96×96 PNG)에서 obstacle 재현율 27/27(1.00), obstacle 없는 프레임 중 통로 안 오검출 1/18. 기준 0.9 미만이면 CI 실패.
- ②에게: 모델 커밋 `deb8980`. pull → `build.ps1 -Port COM10` → `#AISLE 36 0 58 0 94 96 0 96`. 추론 시간은 보드 `F ... inf=`로 확인.
- PC 시뮬레이션(`tools/simulate.py`: 펌웨어 int8 모델을 LiteRT로 + logic.cpp 규칙을 파이썬으로 옮김, 시간은 영상 시각, 보드 실측 대체 아님): demo.mp4 상자 경고 지연 10.2초·방치 오차 +0.5초, 가방 10.1초, 오경보 0. 시나리오1 10/10 경고(지연 10.2초, 오차 +0.5초; 마지막 1회는 영상 끝이라 해제 없음), 시나리오3(사람만) 오경보 0, 시나리오4(5초) 경고 0/5, 시나리오5(통로 밖) 오경보 0. 주의: 시나리오 반복은 같은 클립 구간이라 독립 시행이 아님 → 보고서 한계에 적기.

## 2026-11-03 ② 모델 보드 시험 (12:20)
- **①에게: 모델 그대로는 보드에서 `AllocateTensors() failed`로 추론 0회.** EI가 계산한 arena 185,036B가 esp-nn 작업 버퍼를 못 담는 것으로 보임. `tflite-model/tflite_learn_1155430_3.h`의 `tflite_learn_1155430_3_arena_size`를 320000으로 바꾸니 정상(추론 141ms, 목표 500ms 이하). ②는 라이브러리 파일을 로컬에서만 고쳐 시험 중 — ①이 이 값을 커밋해 줄 것(다시 받는 zip에서도 같은 수정 필요).
- 시연 영상(`demo.mp4`, 2fps, `#AISLE 36 0 58 0 94 96 0 96`): 상자 경고 지연 10.2초, 해제 dwell 33.0초(정답 32.0초, +1.0초 — 내려놓는 중 0.3초 일찍 잡고, C3에서 들고 가는 상자를 0.7초 더 잡음), 가방 경고 지연 10.6초, 오경보 0, DB 201 전부. `verify.py`는 오차를 로그 단위(0.1초)로 반올림해 비교하도록 고침(1.0000x > 1.0 때문에 FAIL로 나왔음).
- CI(94c9716, 모델 포함): unit-test, firmware-build, model-gate 모두 success.
