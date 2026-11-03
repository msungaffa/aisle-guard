# aisle-guard — 통로 장애물 방치 감지기

XIAO ESP32S3 Sense 카메라가 통로에 놓인 물건(상자·가방·의자)을 Edge Impulse FOMO 모델로 찾아,
정해진 시간 넘게 방치되면 LED로 경고하고 이벤트를 Supabase에 기록한다. 사람은 장애물로 세지 않는다.

- PRD: https://claude.ai/artifact/7vguen5tdMA9Pb4VUPn3XW
- 작업 문서: `CLAUDE.md`(규칙), `HANDOFF.md`(현재 상태·남은 일), `docs/HISTORY.md`(기록)
- 과제 조건: ① ESP32에 모델 탑재 ② 로그 DB 저장 ③ CI
- 재사용: 팀 프로젝트 ppe-edge-guard(카메라·Wi-Fi·EI 감지·빌드 스크립트), zero-touch-media(사진 수집)

## 사진 수집
```powershell
powershell -File firmware/build.ps1 -Name capture_cam -Port COM10
python tools/capture.py COM10 --label obstacle --every 1.5 --max 80
```
