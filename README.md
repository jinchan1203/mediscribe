# MediScribe — 개발 기록 (맥북 세션 정리, 2026-08-13 ~ 2026-09-11)

Y-MAS AI 대회 Physical AI 부문 출전작. 병동 회진 동행 자율주행 로봇 + 의사-환자 대화 → 환자용 SBAR 요약 → 의사 1-tap 검수 → 즉석 출력.
이 폴더는 **맥북 쪽 Claude Code 세션**에서 한 작업의 정리본이다. Jetson 쪽 음성 파이프라인(Riva·검수서버 등)은 `jetson/CLAUDE-jetson-2026-09-11.md` 참조.

## 폴더
| 경로 | 내용 |
|---|---|
| `car/` | 아두이노 v3 펌웨어 소스, 파이썬 조종(`car.py`), 키보드/게임패드 텔레옵, **맥북 실시간 지도 뷰어 `mapview.py`** |
| `jetson/scripts/` | Jetson에 올린 매핑(`mapping_joy.py`)·자율주행(`nav_drive.py`) 스크립트 사본 |
| `jetson/` | Jetson 파일 위치 안내, Jetson Claude 세션 문서 전문 |
| `maps/` | 첫 지도 PNG (npz 원본은 Jetson) |
| `memory/` | 맥북 Claude 메모리(프로젝트 맥락 요약) |

## 하드웨어 (확정 사항)
- **Jetson**: Yahboom Orin NX Super 16GB, JetPack 6.2 (L4T R36.4.3), MAXN_SUPER. 영상 출력 **DisplayPort**, USB-C는 recovery 전용. 256GB NVMe(루트 233G로 확장).
  - 사전 설치: ROS2 Humble, CUDA 12.6, TensorRT 10.7, PyTorch 2.10, Docker, ollama. 추가: jtop, Claude Code CLI, Firefox, 한글 입력(ibus-hangul).
  - **우분투 24.04 업그레이드 제안 절대 수락 금지.**
- **WiFi**: USB 동글(wlx84fc140c44ce) 사용, 내장 RTL8822CE 비활성. 핫스팟 `CHAN`(비번 11111111)에서 맥북과 SSH. 학교 WiFi는 기기 간 차단.
- **차량**: 대호토이즈 벤츠 1/5 스케일, 앞바퀴 조향(DC모터, 각도 센서 없음, 스프링 복귀 없음) + 좌/우 뒷바퀴 구동. 엔코더 없음.
- **Arduino Mega 2560** (`/dev/ttyACM0`, 맥에선 `/dev/cu.usbmodem1101`), 모터 드라이버 3개(IN1/IN2 2선식):

  | 드라이버 | 역할 | IN1(PWM) | IN2 | 점퍼선 색 |
  |---|---|---|---|---|
  | #1 | 조향 | D2 | D3 | 검정 / 흰색 |
  | #2 | 좌측 구동 | D4 | D5 | 노랑 / 청록 |
  | #3 | 우측 구동 | D6 | D7 | 연보라 / 보라 |

  ⚠ **접촉 불량 반복**(9/7 2회, 9/11 3회, 전부 IN2쪽·드라이버#3). 새 점퍼선 교체 + 글루건 고정 필요. 배터리 스위치 OFF면 아무것도 안 돎.
- **라이다**: LDROBOT STL-27L (0.03~25m, 10Hz, 0.167°, 2160점/회전) — PL2303 USB-TTL → `/dev/ttyUSB0`, 921600bps. 드라이버 `sw/2.0/pickr/hal/lidar_stl27l.py`.
  - **장착 오프셋 확정: `pickr/config.py` `ANGLE_OFFSET_DEG = 94.5`, `LIDAR_FLIP = +1`** (직진 2.6m 궤적 vs 헤딩 δ=−109° → off' = off − δ; 사람이 정면 1m에 서면 0~+5°에 잡히는 것으로 물리 검증).
- **조이스틱**: Logitech F710, 뒷면 스위치 **X**(XInput, xpad 모듈) → `/dev/input/js0`. (맥에서는 D 모드 필요)
- **마이크**: ReSpeaker Mic Array v3.0(XMOS) — Jetson USB-A, `ArrayUAC10`.

## 아두이노 펌웨어 v3 프로토콜 (`car/firmware/mediscribe_car_v3/`) — 115200bps, 줄바꿈 종료
| 명령 | 뜻 |
|---|---|
| `V <l> <r>` | 좌/우 구동 PWM −255..255 |
| `D <pwm>` | 양쪽 구동 동일 |
| `S <pwm> [ms]` | 조향 펄스 (+ = 오른쪽), ms 후 자동 정지(최대 1500) |
| `X` | 전부 정지 |
| `T L\|R\|S <1\|-1> [pwm] [ms]` | 단일 모터 시험 펄스 |
| `C L\|R\|S 0\|1` | 극성 반전 플래그 (현재 전부 0 = 반전 불필요) |
| `?` | 도움말 |
| (수신) `ST l r s ms` | 100ms 상태, `WD STOP` = 0.5초 명령 끊겨 자동 정지, `OK`/`ERR` |
안전: 구동 명령 0.5초 끊기면 워치독 정지. 모터 기동 하한 ≈ 90 PWM.

## 소프트웨어 사용법
### 맥북에서 차 조종 (아두이노를 맥에 연결)
```bash
cd car && python3 teleop.py          # W/S/A/D, space 정지, q 종료 (속도 180, 조향 255)
python3 joy_teleop.py                # F710 (D 모드): 왼스틱 전후진, 오른스틱 조향, B 정지, BACK 종료
```
### Jetson에서 매핑 (조이스틱, 맥북 뷰어)
```bash
# Jetson
cd ~/mediscribe/sw/2.0 && python3 scripts/mapping_joy.py --max 160 --decim 3   # RB+RT/LT, 왼스틱 조향, B=저장 종료
# 맥북
cd car && python3 mapview.py         # http://yahboom.local:8765 도 가능. q 닫기, f 따라가기
```
결과: `out/joymap_<ts>.npz/.png/.log/.json`. 루프 닫힘은 기본 OFF(`--loops` 로 켜되 accept 0.75/gap 20).
### Jetson에서 자율주행
```bash
# Jetson
python3 scripts/nav_drive.py --map out/joymap_20260911_194852.npz [--init X Y DEG] [--pwm 130]
# 맥북
python3 mapview.py --nav             # 왼클릭=목표, 우클릭=현재위치 재설정, s 정지, g 재개
```
조이스틱: **RB 잡으면 수동**(측위는 계속), **B** 자율 정지(목표 해제), **Back** 종료. 상태: drive/blocked/lost/arrived/noplan/manual.

## 핵심 결과·교훈
1. **SBAR 요약 벤치마크(8/13)**: qwen3:8b 12.8 tok/s 품질 양호 / qwen3.5:2b 23.8 tok/s 환각 심각 → "요약 3초"는 일괄 생성으로 불가 → 증분 요약 구조 + 의사 검수 필수의 실증 데이터.
2. **엔코더 없는 차의 SLAM**: 오도메 대신 **라이다 오도메(매 스캔 scan-to-map 정합)** 사용. 원본 GraphSLAM의 루프 닫힘(accept 0.55/gap 8)은 회전 직후 오탐으로 지도를 부채꼴로 망침 → 루프 OFF. 등속 예측은 정지 시 끄고 이동 시 절반만(안 그러면 헤딩이 계속 드리프트). 정합 신뢰도(점당 필드값) < 0.12 스캔은 지도 제외. 15cm 이내 차체 반사 제거.
3. **첫 지도(9/11)**: 복도+교차로, 116 키프레임, `maps/joymap_20260911_194852.png`. 마지막 직진 구간에서 스캔 447개 스킵 → 지도 끝부분과 최종 포즈 불일치. 복도는 자기유사성이 커서 초기 측위가 1.9m 어긋난 후보를 택함 → 매핑 시작점(지도 중앙)에서 nav를 시작하는 것이 안전.
4. **자율주행 제어 설계**: 조향 각도 센서가 없어 **요레이트 서보**(전방 주시점 헤딩오차 → 목표 요레이트, 측위 Δθ로 잰 실제 요레이트와 비교해 좌/우 255 펄스). 실주행 테스트는 미완.
5. **원격 프로세스 관리 함정**: `pgrep -f "패턴"`이 자기 SSH 셸에 매칭돼 셸을 죽임 → 문자열 쪼개기(`P=mapping_; P="${P}joy.py"`).

## 다음 할 일
- [ ] 드라이버 신호선 6가닥 새 점퍼선 교체 + 글루건 고정
- [ ] 차 치수(폭·길이·축간거리) 실측 → `nav_drive.py --radius/--halfw`, `config.py` 반영
- [ ] 매핑 시작점에서 `nav_drive.py` 시작 → RB 수동으로 측위 검증 → 2~3m 목표 자율주행 → 조향 이득(`--k-e`, `--rate-thr`, `--pulse-ms`) 튜닝
- [ ] 필요 시 재매핑(천천히, 신뢰도 0.2 이상 유지) 또는 루프 닫힘 ON(accept 0.75) 시험
- [ ] Jetson 음성 파이프라인(Riva·live_sbar·검수서버)과 주행 모드 전환(`tools/mode.sh`) 통합 시연
