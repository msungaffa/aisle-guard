# aisle-guard HANDOFF

<!-- claude-setup-notify -->
> **새 PC면 세션 시작 전에 한 번 확인 — Claude 알림 훅**(1분 넘는 작업이 끝나거나 입력이 필요할 때, 그 VS Code 창이 **최소화돼 있으면** 윈도우 팝업 — 창을 보고 있으면 안 뜸, 누르면 그 창이 다시 뜸. 이미 설치한 PC도 `-Check` 가 `구버전` 이면 아래 2번으로 갱신). 이 PC에 없으면 먼저 설치한다.
> 1. 확인: `powershell -ExecutionPolicy Bypass -File C:\dev\claude-setup\install.ps1 -Check` → `OK`면 끝.
> 2. 폴더가 없거나 `없음/구버전`이면: (`gh auth login` 안 했으면 먼저) `git clone https://github.com/msungaffa/claude-setup C:\dev\claude-setup`(이미 있으면 `git -C C:\dev\claude-setup pull`) → `powershell -ExecutionPolicy Bypass -File C:\dev\claude-setup\install.ps1` → Claude Code·VS Code 다시 시작. 자세한 건 그 저장소 README(비공개).

다음 세션은 "남은 일" 절부터 이어간다. 작업 후에는 커밋 + 푸시.

## 구조
- 저장소: `C:\dev\aisle-guard` → `github.com/msungaffa/aisle-guard` (비공개)
- `firmware/aisle_cam/` 본 펌웨어: `aisle_cam.ino`(시리얼 프레임 → 검출 → 판정 → LED → 이벤트), `logic.*`(판정·이벤트 JSON·20건 큐, Arduino 무관), `proto.*`(응답 분류·`AGFR` 프레임 파서), `detector_ei.cpp`/`detector_stub.cpp`(`settings.h`의 `DETECTOR_EI`로 선택), `uploader.*`(코어 0 태스크, Supabase REST, 내장 CA 번들), `net.*`(PPE Wi-Fi 재연결 수정판)
- 비밀값: `firmware/aisle_cam/secrets.h`(Wi-Fi, Supabase URL·publishable 키), 루트 `.env`(EI_API_KEY 업로드 전용, EI_PROJECT_ID, SUPABASE_*). 둘 다 gitignore
- 외부: Supabase 개인 프로젝트 `irnmlsgccbvbhsrdxaad`(도쿄, 다른 테이블은 무관 — 건드리지 않음), Edge Impulse Public 프로젝트 `aisle-guard` 1155404(bounding boxes)
- `firmware/capture_cam/` 보드 카메라 사진 수집 스케치(예비용)
- `firmware/build.ps1` 컴파일·업로드(`-Name`으로 스케치 선택), `firmware/tests/run_tests.ps1` 호스트 g++ 단위시험(test_logic, test_proto)
- `tools/`: `aisle_frames.py`(공통 자르기, `tools/aisle.json`의 crop), `feed.py`(시연 전송·로그 `tools/logs/`), `extract_frames.py`→`tools/frames/`, `ei_upload.py`, `make_demo.py`(`tools/demo.json` → `videos/demo.mp4`+`demo_truth.json`), `verify.py`(성공 기준 계산), `capture.py`(예비)
- `db/schema.sql`(적용됨), `.github/workflows/ci.yml`

### 데이터 흐름 (방법 A, 2026-11-03 결정)
- 집에서 실제 통로를 만들기 어려워 **AI 생성 창고 CCTV 영상**을 쓴다. 기준 사진 `ref.png`(CAM 14 South Aisle 스타일) + 클립 C1~C5.
  - C1 상자를 두고 감 · C2 상자 옆을 사람이 지나감 · C3 상자를 치움 · C4 가방을 두고 감 · C5 사람만 지나감 (C2·C3은 C1 마지막 화면에서 시작)
- PC(`tools/feed.py`)가 영상을 재생하며 통로 부분을 잘라 96×96으로 줄여 USB 시리얼로 ESP32에 보낸다 → ESP32가 FOMO 추론 + 판정 + LED + Supabase 기록. 모델은 ESP32 안에서 돈다(조건 ①).
- 학습: 5개 클립 프레임, 클립마다 마지막 30%는 EI 시험 세트. 클립이 5개뿐이라 시연과 학습이 같은 장면 → 보고서에 한계로 밝힌다.
- 시연 영상: 빈 통로(멈춤 5초) → C1 → 상자 방치(멈춤 12초) → C2 → C3 → 빈 통로 3초 → C5 → C4 → 가방 방치(멈춤 12초). 구간별 정답 시각으로 ±1초 검증.
- 라벨: `obstacle`(통로 바닥의 상자·가방만), `person`. **선반 위 상자는 라벨을 달지 않는다.**

## 현재 상태
- 2026-11-03 11:30: 영상 없이 할 수 있는 것 완료(`#FAKE` 배선 시험, 단위시험, CI).
- 13:40: 모델 `ei1155430-d1`(EI `aisle-guard-v2` 1155430, FOMO 0.35 int8, 검증 F1 0.85)을 펌웨어에 넣고 보드에서 추론 140~172ms. CI 3개(unit-test, firmware-build, model-gate) 초록. 보드 실측: 시연 영상 PASS(지연 10.2·10.6초, 방치 +1.0초, 오경보 0), PRD 시나리오 1·3·4·5 통과, 2는 +1.0초로 경계 통과, 6은 저절로 난 끊김 1회로 누락 0 확인. README 검증 표에 반영.
- ③ 문서: `db/queries.sql`, `aisle_event_reviews` 표, README, 대시보드 https://claude.ai/artifact/Y96SJDB35Cw7M9EcPwVKvg (DB 스냅숏, 16:00에 다시 받음).
- 14:10~14:50: 카메라 모드(`#CAM on`, `tools/screen.py`) 추가. 시연 = 카메라 모드, 정량 수치 = USB 모드. d1은 카메라 화면 obstacle 재현율 0.44.
- 15:23: 모델 `ei1155430-d2`(보드 카메라 화면 369장 추가 재학습, 검증 F1 0.87, arena 320000). PC: 카메라 시험 59/59, USB 27/27·오검출 0/18, simulate 방치 +0.0초. 보드 재확인은 ②.

## 남은 일
- [ ] ② d2 보드 재확인: USB 시연·시나리오 1 회귀, 카메라 모드 1회(conf_min 0.6 가능?), `inf=` → 결과가 오면 ③이 README 검증 표에 d2 행 추가
- [ ] ② 시연 녹화(카메라 모드 `screen.py` 또는 `feed.py --show` + 보드 LED 촬영, 사용자)
- [ ] ③ 15:30 security-review, code-review(low)
- [ ] ③ 16:00 대시보드 DB 다시 받기, 제출물 점검(저장소 링크, CI 초록, 시연 영상)
- [ ] 제출 (16:30, 사용자)
- [ ] Supabase 시험 행 `device_id='setup-test'`(id 1) 지우기 — 자동 삭제가 확인 창에서 취소됨. 조회·대시보드는 이 행을 뺀다
- [ ] 제출 후: EI 옛 프로젝트 `aisle-guard`(1155404) 지우기(선택), 보드에 PPE 펌웨어 다시 올리기

## 교훈
- EI가 계산한 tensor arena(185,036B)로는 ESP32-S3 esp-nn에서 `AllocateTensors()`가 실패한다 → `tflite-model/tflite_learn_*_arena_size`를 320000으로. **모델을 다시 내보내면 덮어써지므로 다시 고친다.** PC LiteRT(model-gate·시뮬레이터)로는 못 잡고 보드 실기에서만 보인다.
- 시리얼에 바이너리 프레임과 텍스트 명령을 섞으면 명령 줄 버퍼에 프레임 찌꺼기가 붙는다 → 프레임 완성 때 줄 버퍼를 비우고, PC는 명령 앞에 `
`을 붙인다.
- pyserial로 포트를 열 때 DTR/RTS를 내리지 않으면 ESP32-S3가 리셋된다 → `feed.py`는 `dtr=False, rts=False` 후 open, `#AISLE?` 응답을 기다린 뒤 보낸다.
- OpenCV `imwrite`/`imread`는 한글 경로에서 조용히 실패한다 → `imencode` 후 파이썬으로 쓴다.
- EI Keys 화면 기본 키는 ingestion 권한이라 프로젝트 설정 API가 403 → 설정은 Studio 화면에서.
- PPE에서 이어진 것: 한글 사용자 폴더에서는 ESP32 링크와 MinGW가 깨진다 → 스크립트의 subst 우회 유지. EI SDK `ei_calloc`은 16바이트 정렬로 덮어써야 esp-nn에서 힙이 안 깨진다(`detector_ei.cpp`). `crop_and_interpolate_rgb888`은 dst에 먼저 잘라낸 크기로 쓰므로 버퍼를 모델 크기로 잡으면 넘친다.
- PowerShell 변수는 대소문자를 구분하지 않는다: `param($Sketch)`와 `$sketch`가 같은 변수라 `build.ps1` 인자를 `-Name`으로 지었다.
- bash에서 파이썬 heredoc으로 `"C:\a..."`를 쓰면 `\a`가 제어 문자로 바뀐다 → 경로 문자열은 Edit 도구로 고치거나 확인한다.
