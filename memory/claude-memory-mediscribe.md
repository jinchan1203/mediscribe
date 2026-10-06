---
name: mediscribe-ymas-project
description: MediScribe 자율주행 의료 보조 로봇 — Y-MAS AI 대회(y-mas.ai) Physical AI 트랙 출전 프로젝트
metadata: 
  node_type: memory
  type: project
  originSessionId: 5a1cbfbd-7f59-41a9-bb3a-73dca69e1440
  modified: 2026-08-13T06:01:22.268Z
---

사용자(연세대, jinchan1203@yonsei.ac.kr)는 Y-MAS AI 대회(https://y-mas.ai) Physical AI 부문에 'MediScribe'로 출전 중 (2026년 8월 기준).

**프로젝트**: 회진 동행 자율주행 로봇. 의사-환자 대화 수음 → 화자분리 → SBAR 형식 환자용 요약 → 의사 1-tap 검수 → 감열 프린터(A6) 또는 QR/카카오톡으로 환자에게 즉석 전달.

**기술 스택**: Jetson Orin NX 16GB (전부 on-device), NVIDIA Riva ASR(한국어) + pyannote.audio 화자분리, NeMo + TensorRT-LLM으로 Llama 3.1 8B LoRA fine-tune (INT4), ChromaDB RAG(KIMS·식약처 약품 DB), ROS2 Humble + Nav2 + LiDAR + RealSense D435, ReSpeaker 6-Mic, 4WD 메카넘 휠 베이스(50x50cm).

**목표**: end-to-end 지연 5초(요약 3초+출력 2초), Riva vs Whisper Large-v3 한국어 의학용어(메트포르민, eGFR, ARB 등) 인식률 비교, 가짜 회진 50건 기반 요약 품질 평가, IEC 62304 human-in-the-loop 준수.

**하드웨어 (2026-08-13 브링업 완료)**: Yahboom Jetson Orin NX Super 16GB 킷 (모듈 16GB 확인). 사전 설치 이미지로 부팅 성공 — **JetPack 6.2 (L4T R36.4.3), 재플래싱 불필요**. 256GB NVMe(K-RICARD), 루트 파티션 100GiB 확장 완료(233G 중 117G 여유). RTL8822CE WiFi + 안테나 장착. 영상 출력은 DisplayPort(HDMI 아님). USB-C 포트는 recovery 전용. FC REC/GND 핀은 보드 뒷면 실크 표기 있음.

**소프트웨어**: Yahboom 이미지에 ROS2 Humble, CUDA 12.6, TensorRT 10.7, PyTorch 2.10(GPU 확인), Docker, ollama(qwen3:8b 등 4모델) 사전 설치. jtop 설치함. 데모 정리로 여유 144G 확보. 첫 SBAR 벤치마크(2026-08-13): qwen3:8b 12.8 tok/s·품질 양호, qwen3.5:2b 23.8 tok/s·환각 심각 → 검수 필요성 실증. 결과는 Jetson `~/mediscribe/benchmarks/`에 저장.

**접속**: 맥북에서 `ssh jetson` (~/.ssh/config: HostName `yahboom.local` mDNS + HostKeyAlias jetson → IP 바뀌어도 동작, 키 등록돼 비번 불필요). 2026-09-11 기준 IP 172.20.10.3, WiFi MAC 84:fc:14:0c:44:ce (예전 dc:4a:9e…에서 바뀜 → IP 찾을 땐 MAC 말고 mDNS/hostname 사용). macOS ping은 -W가 ms 단위라 스캔 시 `-t 2` 사용 (폰 핫스팟 172.20.10.x 대역, 맥북과 같은 핫스팟), 비밀번호 `yahboom`. IP는 핫스팟 재시작 시 바뀔 수 있음. 홈에 Yahboom 데모 40GB(workspaces 15G, .cache 7.5G 등) 있음 — 공간 부족 시 정리 후보. Docker 사전 설치(open-webui, label-studio, ros-melodic 이미지는 불필요).

**Day 2 (2026-09-01)**: 사용자가 Jetson에서 직접 VS Code + Claude Code로 작업하길 원함. Jetson에 Claude Code CLI 2.1.252(~/.local/bin), Firefox(snap), 한국어 입력(ibus-hangul, gsettings로 us+hangul 등록, 언어팩) 설치 완료. 핸드오프: `~/mediscribe/CLAUDE.md`(프로젝트 전체 맥락) + 맥북 세션 기록·메모리를 `~/.claude/projects/-home-jetson-mediscribe/`에 배치. 맥북 바탕화면 `mediscribe-handoff/`에 동일 사본. WiFi는 안테나 장착 시 신호 100%, 미장착 시 SSH 끊김 반복. ReSpeaker는 Day 2 시점 아직 미연결(micro-USB 케이블 문제).

**차량 (2026-09-07)**: Arduino Mega 2560이 맥북 `/dev/cu.usbmodem1101`에 연결. 드라이버 3개(IN1/IN2 2선식): 조향 D2/D3, 좌구동 D4/D5, 우구동 D6/D7, 5V/GND 공급. 앞바퀴 조향 방식(메카넘 아님). 기존 펌웨어 "MEDISCRIBE CAR v2"(115200, `S 0 0.000 0 ms` 상태줄)는 소스 없음·명령 불명. 팀원(nam-yunsang 맥, Arduino IDE 2.3.8)이 핀 테스트: L/R 전진 OK, 우측 후진 OK, **좌측 후진 안 움직임(드라이버#2 D5 배선 의심)**, 조향 양방향 OK. 맥북에 arduino-cli 1.5.1(~/.local/bin) + avr 코어 설치. 새 펌웨어 v3 `~/mediscribe-car/firmware/mediscribe_car_v3/` 컴파일 완료(미업로드), 파이썬 `~/mediscribe-car/car.py`(Car 클래스), `teleop.py`(WASD). 사용자는 ROS2 없이 파이썬만으로 조종 원함.
**차량 v3 완료 (2026-09-07)**: v3 펌웨어 업로드 성공, 6방향(좌우 전후진, 조향 좌우) 전부 검증 완료, 극성 반전 불필요. 텔레옵 `~/mediscribe-car/teleop.py` (SPEED 180, STEER 255/200ms) 동작 확인. 접촉 불량이 IN2 쪽 선(D3 흰색, D7 보라)에서 반복 발생 → 고정(테이프/납땜) 권고. 모터 배터리 스위치 꺼져 있으면 아무것도 안 돎(첫 테스트 실패 원인). Jetson에서 쓸 땐 포트가 /dev/ttyACM0.

**SLAM 매핑 (2026-09-11)**: 사용자 지시로 맥북 세션이 SSH로 Jetson을 직접 조작(Jetson Claude 세션 369cbec4는 별개; 그쪽 성과는 `~/mediscribe/CLAUDE.md`에 상세). Jetson 스택은 ROS2 없이 `~/mediscribe/sw/2.0/`(Pickr2 순수 파이썬: GraphSLAM/ScanMatcher/OccupancyGrid, `hal/lidar_stl27l.py`, `hal/arduino_v3.py`, `scripts/teleop_joy.py`). 내가 만든 것: `sw/2.0/scripts/mapping_joy.py` — 조이스틱(F710 xpad js0) + STL-27L + GraphSLAM, 엔코더 없어서 **라이다 오도메(매 스캔 scan-to-map 정합)** 를 odom 으로 넣음, 15cm 이내 차체 반사 필터, HTTP :8765 로 /state·/map.png·브라우저 페이지 서비스, out/joymap_<ts>.npz/png/log 저장. 맥 뷰어 `~/mediscribe-car/mapview.py`(matplotlib, AppleGothic, /state·/map.png 폴링). 실측: 10Hz, 처리 ~70ms(--decim 3; decim 2면 75~105ms). 원격 프로세스 kill 시 `pgrep -f` 자기매칭 함정 → 문자열 쪼개기(`P=mapping_; P="${P}joy.py"`). 맥의 `~/mediscribe-car` 사본을 Jetson `~/mediscribe/car-mac/`에 복사함(v3 펌웨어 소스 포함).
**첫 지도 + 자율주행 착수 (2026-09-11 저녁)**: 매핑 결과 `~/mediscribe/sw/2.0/out/joymap_20260911_194852.npz/.png` (복도+교차로, KF 116, 30m 맵, 루프클로저 OFF). 교훈: 엔코더 없는 차에서 원본 GraphSLAM 루프클로저(accept 0.55/gap 8)는 회전 직후 오탐으로 지도를 부채꼴로 망침 → mapping_joy.py 기본 루프 OFF, 등속 예측은 정지 시 끄고 이동 시 절반만(안 그러면 헤딩이 시계방향으로 계속 드리프트), 정합 신뢰도(점당 필드값) <0.12 스캔은 지도 제외. **라이다 오프셋 확정: `config.ANGLE_OFFSET_DEG = 94.5`** (직진 2.6m 궤적 vs 헤딩 δ=-109°로 계산; 방법: off' = off − δ). 자율주행 `sw/2.0/scripts/nav_drive.py`(저장맵 정합 측위 + heading_sweep/local_search 초기·복구, Costmap+A*, 전방주시 헤딩오차→요레이트 서보로 조향 펄스, 정면 거리 감속/정지, HTTP :8766 /state /map.png POST /goal /stop /go /init). 맥 뷰어 `mapview.py --nav` 클릭=목표, 우클릭=초기위치, s/g. 차 치수 미확인(기본 radius 0.22, halfw 0.20). 배선: 드라이버#3 신호선(D6 연보라, D7 보라) 접촉 불량 하루 3회 → 새 점퍼선+글루건 권고.
(9/11 20:20) 오프셋 94.5° 물리 검증 완료: 사람이 차 정면 1m에 서면 로봇프레임 0~+5°에 잡힘. 매핑 종료 위치 근처는 지도가 불일치(직진 구간 스킵 447회)라 nav 초기 측위가 1.9m 떨어진 곳(conf 0.26)을 택함 — 복도 자기유사성 주의. nav_drive에 RB 수동 오버라이드/B 자율정지/Back 종료, /scan?sector=10 진단, /conf 진단 추가. nav 기본 min_conf 0.18.
