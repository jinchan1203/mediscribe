# Jetson 쪽 파일 위치 (실물은 Jetson에 있음 — 여기는 사본/기록)

- 실제 프로젝트 폴더: `jetson@yahboom:~/mediscribe/` (핸드오프 `CLAUDE.md`, benchmarks/, audio/, python/, tools/, docs/DEMO.md)
- 자율주행 스택(ROS2 없음, Pickr2 기반 순수 파이썬): `~/mediscribe/sw/2.0/` — `pickr/` 라이브러리, `scripts/`
- 이 폴더의 `scripts/`: 맥북 세션이 만든 3개 (Jetson `sw/2.0/scripts/`에 동일하게 배치됨)
  - `mapping_joy.py` — 조이스틱 + STL-27L + GraphSLAM 매핑, HTTP :8765 실시간 뷰
  - `nav_drive.py`  — 저장 지도 위 자율주행(측위+A*+조향 서보), HTTP :8766, 조이스틱 RB 수동 오버라이드
  - `mapstate.py`   — 매핑 상태 한 줄 요약
- 지도: Jetson `~/mediscribe/sw/2.0/out/joymap_20260911_194852.npz` (+.png/.log/.json). PNG 사본은 ../maps/
- `CLAUDE-jetson-2026-09-11.md`: Jetson Claude 세션이 유지한 프로젝트 문서(9/11 시점 전문) — Riva/ASR/검수서버/메모리 계획 등 음성 파이프라인 내용 포함
- 접속: 맥북에서 `ssh jetson` (핫스팟 CHAN, mDNS yahboom.local, 비번 yahboom)
