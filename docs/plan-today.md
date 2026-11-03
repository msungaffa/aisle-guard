# 오늘(2026-11-03) 16:30 제출까지 할 일 — 창 3개 동시 작업

**모든 창 공통: 아래 자기 목록을 순서대로 끝까지 진행한다. 사용자에게 허락을 묻지 않는다.**
사용자 손이 꼭 필요한 일(라벨 확인, Wi-Fi 끄기, 영상 촬영, 제출)만 한 줄로 요청하고, 기다리는 동안 다음 일을 한다.

## 공통 규칙
- 자기 담당 파일만 고치고 커밋한다. push 전에 `git pull --rebase`. main 직접 push.
- 보드(COM10) 업로드·`feed.py`는 ②만. ①은 컴파일까지만.
- README·HANDOFF·PRD 문서는 ③만. ①·②는 결과를 `docs/HISTORY.md` 맨 아래에 날짜·시각과 함께 덧붙인다(③이 반영).
- 작업 후: 단위시험 → 컴파일 → 커밋·push. 커밋 메시지 끝에 `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- 막히면 HISTORY에 원인을 적고 PRD "위험과 대응"의 대안으로 넘어간다. 16:00 이후에는 새 기능을 시작하지 않는다.

## ① 모델 (이 창) — 담당: EI, `tools/aisle.json`, `firmware/libraries/`, `firmware/aisle_cam/settings.h`, `detector_ei.cpp`
- [ ] 11:50 통로 crop 결정 → `tools/aisle.json` 커밋 (②의 feed.py가 씀)
- [ ] 12:00 `extract_frames.py videos --fps 3` → `ei_upload.py tools/frames`
- [ ] 12:40 라벨: `obstacle`(통로 바닥 상자·가방), `person`. 선반 위 상자는 라벨 없음
- [ ] 13:10 impulse 96×96 RGB + FOMO MobileNetV2 0.35 학습, 시험 세트 F1 확인(목표 obstacle 0.85)
- [ ] 13:30 Arduino 라이브러리 → `build.ps1 -InstallLib` → `firmware/libraries/`에 커밋, `DETECTOR_EI 1`, `MODEL_VERSION` → 컴파일 → CI 초록 확인 → ②에 알림(HISTORY)
- [ ] 이후: 오검출이 많으면 데이터 보강·재학습(15분 한도), 여유 있으면 CI `model-gate`

## ② 시연·검증 — 담당: 보드 COM10, `tools/demo.json`, `tools/logs/`, `tools/feed.py`·`verify.py`·`make_demo.py` 수정
- [ ] 12:30 `videos/C1~C5.mp4`를 프레임으로 보고 둔 시각·치운 시각·사람 구간 → `tools/demo.json`(HANDOFF "데이터 흐름"의 시연 순서) → `make_demo.py` → `videos/demo.mp4` + `demo_truth.json`
- [ ] 13:00 모델 전: 스텁 + `#FAKE`로 `feed.py`→`verify.py` 전체 흐름 연습
- [ ] 13:40 모델 커밋을 pull → 업로드 → `#AISLE`로 통로 다각형 설정 → 추론 시간 확인(500ms 이하)
- [ ] 15:00 PRD 검증 시나리오 1~6 실측(영상 구간으로 대응, 6번 Wi-Fi 끊기는 사용자에게 요청), `verify.py` 결과를 HISTORY에
- [ ] 15:40 시연 녹화 준비: 사용자에게 화면 녹화 + 보드 LED 촬영 요청, 시연용 명령 한 줄 정리

## ③ 문서·마무리 — 담당: README, HANDOFF, PRD 문서, `db/queries.sql`, 대시보드
- [ ] 12:30 `db/queries.sql`: 시간대별 경고 횟수, 평균·최대 방치 시간, 장치별 마지막 heartbeat, 오경보 표시 방법
- [ ] 13:30 README 다듬기(구성도, 조건별 구현, 판정 규칙, 실행법, 한계, 출처)
- [ ] 14:30 (여유) 대시보드 페이지: Supabase 조회는 anon이 못 하므로 읽기 전용 view+정책이 필요하면 schema에 추가하고 이유를 기록
- [ ] 15:30 security-review, code-review(low) → 고칠 것은 담당 창에 HISTORY로 전달하거나 문서만 직접
- [ ] 16:00 ①·②의 HISTORY 결과를 README 검증 표·PRD 결과 칸·HANDOFF에 반영, 제출물 점검(저장소 링크, 시연 영상, CI 배지)
- [ ] 16:20 최종 커밋·push, CI 초록 확인
- 제출(16:30)은 사용자가 한다
