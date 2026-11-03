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
