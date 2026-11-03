# aisle-guard HANDOFF

<!-- claude-setup-notify -->
> **새 PC면 세션 시작 전에 한 번 확인 — Claude 알림 훅**(1분 넘는 작업이 끝나거나 입력이 필요할 때, 그 VS Code 창이 **최소화돼 있으면** 윈도우 팝업 — 창을 보고 있으면 안 뜸, 누르면 그 창이 다시 뜸. 이미 설치한 PC도 `-Check` 가 `구버전` 이면 아래 2번으로 갱신). 이 PC에 없으면 먼저 설치한다.
> 1. 확인: `powershell -ExecutionPolicy Bypass -File C:\dev\claude-setup\install.ps1 -Check` → `OK`면 끝.
> 2. 폴더가 없거나 `없음/구버전`이면: (`gh auth login` 안 했으면 먼저) `git clone https://github.com/msungaffa/claude-setup C:\dev\claude-setup`(이미 있으면 `git -C C:\dev\claude-setup pull`) → `powershell -ExecutionPolicy Bypass -File C:\dev\claude-setup\install.ps1` → Claude Code·VS Code 다시 시작. 자세한 건 그 저장소 README(비공개).

다음 세션은 "남은 일" 절부터 이어간다. 작업 후에는 커밋 + 푸시.

## 구조
- 저장소: `C:\dev\aisle-guard` → `github.com/msungaffa/aisle-guard` (비공개)
- `firmware/aisle_cam/` 본 펌웨어. PPE(`C:\dev\ppe-edge-guard/firmware/ppe_cam`)에서 가져온 `camera.*`, `net.*`, `detector_ei.cpp`, `proto.*`, `secrets.example.h` (아직 이 프로젝트용으로 고치기 전)
- `firmware/capture_cam/` 보드 카메라 사진 수집 스케치(시리얼 `p` → `JPG <hex>`). 영상 방식으로 바꿔서 지금은 예비용
- `firmware/build.ps1` 컴파일·업로드(`-Name`으로 스케치 선택), `firmware/tests/run_tests.ps1` 호스트 g++ 단위시험 (둘 다 PPE에서 가져옴)
- `tools/capture.py` 보드 사진 수집(가운데 240×240 자름)
- 예정: `firmware/aisle_cam/logic.*`(판정), `tools/feed.py`(영상 프레임을 시리얼로 보냄), `db/schema.sql`, `.github/workflows/ci.yml`, `videos/`(gitignore)

### 데이터 흐름 (방법 A, 2026-11-03 결정)
- 집에서 실제 통로를 만들기 어려워 **AI 생성 창고 CCTV 영상**을 쓴다. 기준 사진 `ref.png`(CAM 14 South Aisle 스타일) + 클립 C1~C5.
  - C1 상자를 두고 감 · C2 상자 옆을 사람이 지나감 · C3 상자를 치움 · C4 가방을 두고 감 · C5 사람만 지나감 (C2·C3은 C1 마지막 화면에서 시작)
- PC(`tools/feed.py`)가 영상을 재생하며 통로 부분을 잘라 96×96으로 줄여 USB 시리얼로 ESP32에 보낸다 → ESP32가 FOMO 추론 + 판정 + LED + Supabase 기록. 모델은 ESP32 안에서 돈다(조건 ①).
- 학습: 5개 클립 프레임, 클립마다 마지막 30%는 EI 시험 세트. 클립이 5개뿐이라 시연과 학습이 같은 장면 → 보고서에 한계로 밝힌다.
- 시연 영상: 빈 통로(멈춤 5초) → C1 → 상자 방치(멈춤 12초) → C2 → C3 → 빈 통로 3초 → C5 → C4 → 가방 방치(멈춤 12초). 구간별 정답 시각으로 ±1초 검증.
- 라벨: `obstacle`(통로 바닥의 상자·가방만), `person`. **선반 위 상자는 라벨을 달지 않는다.**

## 현재 상태
- 2026-11-03 10:20 시작. PRD 작성, 저장소 생성, 사진 수집 스케치 보드에 올려 시험 촬영 확인(보드의 PPE 펌웨어는 덮어씀).
- 사용자가 AI로 C1~C5 영상 생성 중.

## 남은 일
- [ ] 사용자: `videos/`에 `ref.png`, `C1.mp4`~`C5.mp4` 넣기
- [ ] `logic.cpp` 판정 로직 (다각형 통로 영역, 시간 창 6/4, 해제 1, `DWELL_T` 10초, person 근처 제외) + 단위시험
- [ ] `tools/feed.py` 프레임 전송 + 펌웨어 시리얼 프레임 수신 → 추론
- [ ] 프레임 추출 → EI 프로젝트(`obstacle`/`person` FOMO) 업로드·라벨·학습 → Arduino zip 설치
- [ ] Supabase `aisle_events` 테이블(RLS insert-only) + ESP32 HTTPS 저장
- [ ] GitHub Actions: `unit-test`, `firmware-build`
- [ ] 시연 영상 이어 붙이기 + 정답 시간표, 검증 시나리오 실측, README 정리, 제출 (16:30)
- [ ] 제출 후: 보드에 PPE 펌웨어 다시 올리기

## 교훈
- PPE에서 이어진 것: 한글 사용자 폴더에서는 ESP32 링크와 MinGW가 깨진다 → 스크립트의 subst 우회 유지. EI SDK `ei_calloc`은 16바이트 정렬로 덮어써야 esp-nn에서 힙이 안 깨진다(`detector_ei.cpp`). `crop_and_interpolate_rgb888`은 dst에 먼저 잘라낸 크기로 쓰므로 버퍼를 모델 크기로 잡으면 넘친다.
- PowerShell 변수는 대소문자를 구분하지 않는다: `param($Sketch)`와 `$sketch`가 같은 변수라 `build.ps1` 인자를 `-Name`으로 지었다.
- bash에서 파이썬 heredoc으로 `"C:\a..."`를 쓰면 `\a`가 제어 문자로 바뀐다 → 경로 문자열은 Edit 도구로 고치거나 확인한다.
