# aisle-guard

통로에 물건(상자·가방)이 정해진 시간 넘게 놓여 있으면 ESP32가 경고하고 이벤트를 Supabase에 기록한다. 사람은 장애물로 세지 않는다.
개인 과제(마감 2026-11-03 16:30). 조건: ① ESP32에 모델 탑재 ② 로그 DB 저장 ③ CI. PRD: https://claude.ai/artifact/7vguen5tdMA9Pb4VUPn3XW

## 문서 역할
| 파일 | 내용 | 읽는 법 |
|---|---|---|
| `CLAUDE.md` | 항상 지킬 규칙 | 자동 |
| `HANDOFF.md` | 구조, 현재 상태, **남은 일**, 교훈 | 세션 시작 때 `grep -n "^## " HANDOFF.md` 후 "남은 일" 절만 |
| `docs/HISTORY.md` | 날짜별 기록·원인·측정 | 통째로 읽지 말고 grep |

HANDOFF에서 작업별로 읽을 절:
| 작업 | 읽을 절 |
|---|---|
| 펌웨어·판정 로직 | 구조, 교훈 |
| 모델·데이터 | 구조의 "데이터 흐름" |
| DB·CI | 구조 |

## 빌드·시험 (저장소 루트에서)
- 펌웨어 컴파일: `powershell -File firmware/build.ps1` (기본 `aisle_cam`)
- 업로드: `powershell -File firmware/build.ps1 -Port COM10`, 사진 수집 스케치는 `-Name capture_cam`
- EI 라이브러리 설치: `powershell -File firmware/build.ps1 -InstallLib <zip>`
- 판정 로직 단위시험: `powershell -File firmware/tests/run_tests.ps1`
- 파이썬 도구는 conda `ztmc` 환경: `C:\miniforge3\envs\ztmc\python.exe tools/<script>.py` (한글 출력이 깨지면 `PYTHONIOENCODING=utf-8`)
- 보드: XIAO ESP32S3 Sense, FQBN `esp32:esp32:XIAO_ESP32S3:PSRAM=opi`, 이 PC에서는 COM10

## 지킬 것
- 판정 규칙은 Arduino에 기대지 않는 `logic.cpp`에만 둔다. 고치면 `firmware/tests/`에 시험을 먼저 쓴다.
- 비밀값은 `firmware/aisle_cam/secrets.h`(gitignore). `secrets.example.h`만 커밋한다.
- `videos/`, `tools/captures/`, EI zip은 커밋하지 않는다(용량·저작권).
- `.ps1` 주석은 영어로 쓴다(PowerShell 5.1이 BOM 없는 UTF-8 한글을 깨뜨림).
- 한글 사용자 폴더 문제: 빌드·시험 스크립트의 subst 우회를 지우지 않는다. 작업 경로는 `C:\dev` 아래.
- 작업 후 순서: 단위시험 통과 → 컴파일 확인 → HANDOFF "남은 일" 갱신 → 상세는 `docs/HISTORY.md` 맨 아래 → 커밋 + push (main 직접, 개인 저장소).
