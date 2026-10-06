# MediScribe — 프로젝트 컨텍스트 (Claude Code 핸드오프)

이 문서는 맥북에서 진행한 Claude Code 세션(2026-08-13 Day 1)의 맥락을 Jetson 위 Claude Code로 넘기기 위한 것이다. 새 세션은 이 파일을 먼저 읽고 이어서 작업한다.

## 프로젝트
Y-MAS AI 대회(https://y-mas.ai) Physical AI 부문 출전작 **MediScribe**: 회진 동행 자율주행 의료 보조 로봇.
파이프라인: 의사-환자 대화 수음 → ASR(NVIDIA Riva) → 화자분리(pyannote) → LLM SBAR 환자용 요약 → 의사 1-tap 검수(IEC 62304 human-in-the-loop, 미검수 출력 차단) → 감열 프린터(A6) / QR·카카오톡 전달. 모든 추론은 Jetson on-device(외부 클라우드 전송 없음).
목표: end-to-end 5초(요약 3초+출력 2초), Riva vs Whisper 한국어 의학용어 인식률 비교, 가짜 회진 50건 SBAR 품질 평가.
스택: Jetson Orin NX 16GB, Riva ASR, pyannote.audio, NeMo+TensorRT-LLM(Llama 3.1 8B LoRA, INT4), ChromaDB RAG(KIMS·식약처 약품), ROS2 Humble+Nav2+LiDAR+RealSense D435, ReSpeaker Mic Array v3.0, 4WD 메카넘 베이스.

## 사용자
연세대 학생(jinchan1203@yonsei.ac.kr). 하드웨어/리눅스 초심자 — 설명은 한국어로, 단계별로 구체적으로. 명령은 복붙 가능하게.

## 이 장비 (Jetson) 상태 — 2026-08-13 기준
- Yahboom Jetson Orin NX Super 킷, 모듈 16GB, JetPack 6.2 (L4T R36.4.3), MAXN_SUPER 모드, 커널 5.15.148-tegra
- 계정 jetson / 비밀번호 yahboom, hostname yahboom
- 사전 설치: ROS2 Humble, CUDA 12.6, TensorRT 10.7, PyTorch 2.10(GPU OK), Docker 27.5, ollama 0.18 (qwen3:8b, qwen3.5:2b, qwen3.5:0.8b, qwen2.5vl:3b), VS Code, Chromium, jtop
- 디스크: 256GB NVMe, 루트 파티션 233G로 확장 완료, 여유 ~144G
- 하드웨어 주의: 영상 출력은 DisplayPort(HDMI 아님). USB-C는 recovery 전용. 뒷면 FC REC/GND 핀. WiFi RTL8822CE + 안테나 2개(Main/Aux).
- 네트워크: 폰 핫스팟(172.20.10.x)에서 맥북과 SSH. 학교 WiFi는 기기간 통신 차단 가능성. 대용량 다운로드는 유선랜 권장. **우분투 24.04 업그레이드 제안 절대 수락 금지.**
- 남은 정리: `docker rmi ghcr.io/open-webui/open-webui:main heartexlabs/label-studio:latest yahboomtechnology/ros-melodic:usb_cam` (9GB, 불필요)

## Day 1 핵심 결과: SBAR 요약 베이스라인 (benchmarks/ 폴더)
가짜 회진 대화(당뇨, 메트포르민 증량, ~400토큰) → ollama API(think=false):
| 모델 | 속도 | 총시간 | 품질 |
|---|---|---|---|
| qwen3:8b | 12.8 tok/s | 36.2s (311tok) | 양호 — 형식 준수, 용어 풀이 정확 |
| qwen3.5:2b | 23.8 tok/s | 26.7s (348tok) | 불량 — 환각 다수(수치 해석 반대, 증상 날조) |
시사점: (1) "요약 3초"는 일괄 생성으로 불가 → 회진 중 실시간 증분 요약 구조 필요 (2) 2B 환각 = 의사 검수 필요성의 실증 데이터.
ollama 팁: CLI `ollama run`은 SSH 비대화형에서 멈춘 적 있음 → `curl localhost:11434/api/generate` API 사용.

## Riva ASR 조사 결과 (2026-09-01) — 다운로드 전 필독
**버전 고정 필수: `riva_quickstart_arm64:2.19.0`**
- Riva 2.24.0에서 **Jetson Orin 지원 공식 중단** (이후 Jetson Thor 전용). 2.24/2.26을 받으면 이 장비에서 안 돌아감.
- 2.19.0 = JetPack 6.x + Jetson Orin 조합의 마지막 지원 버전. 우리 장비(Orin NX 16GB, JetPack 6.2)에 맞음.
- 한국어 ko-KR는 2.19 기본 Conformer ASR에 포함. `config.sh`에서 `asr_acoustic_model` / `asr_language_code=ko-KR` 지정.
- ⚠️ 릴리즈 노트: 한국어 **Citrinet**은 타 언어 대비 throughput 낮고 latency 높음 → 5초 목표상 **Conformer 사용**.
- 디스크 ~32GB 필요 (여유 141GB, OK). Riva embedded(ARM64)는 public beta.

**JetPack 6.2에서 2.19 구동 시 알려진 함정 3가지** (NVIDIA 포럼 해결 사례):
1. Docker 27.5.x 필요 (iptables 지원) — 현재 27.5.0 이미 충족
2. `mkdir model_repository/models` 수동 생성 필요
3. `riva_start.sh`에서 `--gpus` → `--runtime=nvidia` 로 수정 필요

**다운로드 명령** (NGC API key 등록 후):
```
ngc registry resource download-version nvidia/riva/riva_quickstart_arm64:2.19.0
```

## 환경 상태 업데이트 (2026-09-01)
- NGC CLI 3.64.0 설치됨: `~/mediscribe/tools/ngc-cli` (PATH는 ~/.bashrc에 등록)
- 네트워크: **학교 WiFi `Yonsei` 사용 중** (172.24.120.x/21, DNS 165.132.5.21). 다운로드 실측 **1.9 MB/s** → 32GB면 약 4.7시간. 유선랜(eno1) 미연결 상태이며 꽂으면 훨씬 빠름.
- 이 Jetson 세션은 SSH가 아닌 **로컬 세션**(모니터 직결)이라 WiFi 변경해도 작업 안 끊김.
- ollama 모델 2개 추가됨(문서 미기록분): `phi4-mini:3.8b`, `llama3.2:3b`
- 오디오 도구 준비 완료: arecord/aplay/sox, python pyaudio·sounddevice·soundfile·numpy·scipy. **pyusb는 미설치**(ReSpeaker DOA 제어에 필요).
- ReSpeaker: **micro-USB 케이블이 없어 연결 보류**. 케이블 확보 시 재개. Jetson USB-C는 recovery 전용이므로 USB-A 포트 사용할 것.

## Day 2 핵심 결과: 3초 목표 달성 경로 확정 (2026-09-01)
상세: `benchmarks/2026-09-01-latency-breakdown.md`, 코드: `python/`

**측정으로 확정된 사실**
- TTFT는 모델 크기와 무관하게 ~1.0~1.5초로 일정. 병목은 프롬프트 읽기가 아니라 **토큰 생성**이다. 줄여야 할 것은 출력 길이.
- **일괄 생성으로 3초는 물리적으로 불가능.** 가장 빠른 llama3.2:3b도 3초에 67토큰뿐이고 쓸만한 SBAR는 150토큰 이상 필요.
- **냉시작 최대 12.9초**(qwen3:8b). ollama 기본값은 5분 유휴 시 언로드 → 회진 중 환자가 바뀔 때 13초를 날린다. **`keep_alive=-1` 적용 완료(9/7, `live_sbar.py` 워밍업 호출)**.

**증분 누적 구조로 3초 달성 (`python/incremental_v2.py`)**
회진 중 대화를 조각내어 사실을 뽑아 누적하고, 종료 시점엔 확정만 한다.
- 회진 종료 후 대기 **0.02ms** (일괄 36.2s 대비)
- 조각당 최악 지연 6.49s / 예산 24s → 실시간 여유 3.7배
- 핵심 사실 보존 6/7 (누락: 복용 스케줄 "아침저녁 500씩")

**설계상 중요한 교훈**: 매 조각마다 메모 전체를 모델에게 재생성시키면(v1) 정보가 망각된다. 조각 1의 혈당 수치가 조각 4에서 사라졌다. **모델은 새 사실만 뽑고, 보존·병합은 코드가 해야 한다**(v2). 이러면 망각이 구조적으로 불가능해지고 연산량도 1/3로 준다.

**모델 후보**: llama3.2:3b는 한국어 출력에 데바나가리 문자가 섞이고 "혈당은 분비물질" 같은 의학적 환각이 나옴 — **사용 불가**. qwen3:8b는 품질 양호하나 10GB 점유로 Riva와 동시 구동 시 16GB 초과 우려. phi4-mini:3.8b 미검증(유력 후보).

## Riva 한국어 ASR 구동 성공 (2026-09-01) — 막힌 지점 5개와 해법
`~/mediscribe/riva/riva_quickstart_arm64_v2.19.0/`. **한국어 ASR 동작 확인됨**
(`ko-KR_sample.wav` → "길이가 십 킬로도 넘었어요").

기동: `bash riva_start.sh` (script 래퍼 필요, 아래 참고) / 종료: `bash riva_stop.sh`
포트: gRPC **50051**, HTTP **50000**. 첫 기동은 TensorRT 엔진 로딩으로 **10분 이상** 걸린다
(3분쯤 "Waiting for Riva server..."가 반복돼도 실패가 아니다).

### 막혔던 지점과 해법 (전부 적용 완료)
1. **`--gpus` 미지원** — Jetson의 NVIDIA 런타임은 `--gpus`를 거부한다
   (`invoking the NVIDIA Container Runtime Hook directly ... is not supported`).
   → `riva_start.sh`, `riva_init.sh` 3곳을 `--runtime=nvidia`로 교체. `.orig` 백업 있음.
2. **포트 8888 충돌** — `riva_start.sh:97`이 `-p 8888:8888`을 하드코딩하는데, 이 장비엔
   Yahboom 기본 Jupyter가 8888을 점유 중. → `-p 8890:8888`로 변경. 기존 Jupyter는 그대로 둠.
3. **NVIDIA_DRIVER_CAPABILITIES=all** — 이미지 기본값이 Vulkan ICD 심볼릭 링크를 만들려다
   `device or resource busy`로 컨테이너가 Created 상태에서 죽는다. Riva는 그래픽이 불필요.
   → docker run에 `-e NVIDIA_DRIVER_CAPABILITIES=compute,utility` 추가.
4. **한국어 punctuation 모델이 TensorRT에서 깨짐** —
   `riva-trt-riva-punctuation-ko-KR-nn-beomi-kcbert-base`가
   `Myelin Cask unknown internal error`로 로드 실패 → Triton 전체가 죽는다.
   원인은 미리 빌드된 엔진이 다른 기기용이라는 것(`engine plan file across different models
   of devices` 경고). → `riva_bls_config.yaml`의 `enable_punctuation: false`로 바꾸고
   punctuation 모델 2개를 `model_repository/disabled_models/`로 이동. ASR은 정상 동작한다.
   **문장부호 없는 텍스트가 나오므로 LLM 요약 단계에서 감안할 것.**
5. **model_repository 파일이 root 소유** — 컨테이너가 root로 풀어서 sudo 없이 수정 불가.
   → sudo 대신 도커로 우회:
   `docker run --rm -v "$PWD/model_repository:/data" --entrypoint /bin/bash <riva image> -c '...'`

### 기타 주의
- `riva_start.sh`/`riva_init.sh`는 내부에서 `docker run -it`를 쓰므로 TTY 없는 환경에서 실패한다.
  → `script -qec "bash riva_start.sh" /dev/null` 로 감쌀 것.
- 학교 WiFi DNS가 간헐적으로 죽어 다운로드가 끊긴다. `riva/init_with_retry.sh`가 자동 재개한다.
- 배포된 모델은 ASR 2개뿐(910MB): `conformer-ko-KR-asr-streaming-asr-bls-ensemble`(스트리밍),
  `riva-trt-conformer-ko-KR-asr-streaming-am-streaming`. **스트리밍 지원** — 증분 요약 구조와 맞물린다.

### 🔴 메모리 예산 문제 확정
Riva 구동 중 실측 **4.4GiB**(docker stats). `qwen3:8b`는 단독 **10GB**.
합 14.4GB / 총 15.3GB → ROS2·Nav2까지 올리면 **초과**.
**결론: 실전에서 qwen3:8b는 쓸 수 없다.** phi4-mini:3.8b 검증이 필수가 됐다.

## 설치 완료 현황 (2026-09-02)
| 항목 | 버전/위치 | 비고 |
|---|---|---|
| Whisper large-v3 | `whisper/models/large-v3.pt` (2.9GB) | Riva 비교용 |
| Whisper large-v3-turbo | `whisper/models/large-v3-turbo.pt` (1.6GB) | 속도 우선 후보 |
| openai-whisper | pip | PyTorch 2.10 기반(faster-whisper는 aarch64 CUDA 휠 없어 회피) |
| pyannote.audio | pip | **모델 가중치는 아직 없음** — HF 토큰 + 라이선스 동의 필요 |
| nvidia-riva-client | 2.27.0 | 서버 2.19와 버전 달라도 통신 정상 |
| pyusb | 1.3.1 | ReSpeaker DOA 제어용 |
| chromadb | 1.5.9 | 약품 RAG용 |

### torchcodec / FFmpeg 문제 (해결됨, 조치 불필요)
pyannote가 `libtorchcodec` 로드 실패 경고를 낸다. 설치된 FFmpeg이 4.4.2(`libavfilter.so.7`)인데
torchcodec 휠은 FFmpeg 7(`libavfilter.so.10`)을 요구하기 때문.
**FFmpeg을 올리지 말 것** — 설치본이 `7:4.4.2-nvidia`(하드웨어 가속 패치 빌드)라 교체하면 깨진다.
대신 오디오를 soundfile로 읽어 메모리로 넘기면 torchcodec 없이 동작한다(검증 완료):
```python
y, sr = sf.read(path, dtype="float32")
mem = {"waveform": torch.from_numpy(y).unsqueeze(0), "sample_rate": sr}
```

## 호스트에서 Riva 호출 (`python/riva_asr.py`) — 동작 확인
`ko-KR_sample.wav` → "길이가 십 킬로도 넘었어요", 부분결과 8회 수신.

**막혔던 지점 2가지**
1. `offline_recognize()` 사용 불가 — 배포된 모델이 **streaming 전용**이라
   `Unavailable model requested ... type=offline` 오류. `streaming_response_generator` 사용.
2. `sample_rate_hertz` 미지정 시 `sample_rate=0`으로 전달돼 같은 오류. 반드시 지정할 것.

**설계상 중요 관찰**: 부분결과(interim)는 중간에 틀린다.
`길리가 → 길이가 었어요 → 길이가 시켜 → 길이가 십 킬로도 넘었어요` 처럼 오인식이 섞였다가
최종에서 교정된다. **증분 요약에는 확정(is_final) 결과만 먹일 것.** 부분결과로 사실을 뽑으면
존재하지 않는 단어에서 정보를 날조하게 된다.

## 자율주행 스택 (2026-09-02 착수) — `sw/2.0/` (Pickr2 기반)

바탕화면 `sw.zip` = **Pickr2**, 파이썬 AMR 스택 13,376줄/81파일. 품질 좋음.
`nav/`(graph_slam, pose_graph, scan_match, localizer, relocalize, likelihood, astar,
costmap, obstacles, fusion), `control/`(mppi_torch GPU, apriltag 도킹, safety),
`hal/`(lidar, imu, realsense, modbus, zlac), `core/`(se2).

### 🔴 핵심 차이: 원본은 차동구동, 우리 차량은 애커만(조향식)
원본 = ZLAC8015D 듀얼 모터, 좌/우 독립 바퀴 → **제자리 회전 가능**.
1/5 스케일 차량 = 앞바퀴 조향 + 뒷바퀴 구동 → `w = v·tanδ/L`, **v=0이면 회전 불가**.
그대로 쓰면 MPPI가 물리적으로 불가능한 궤적을 계획한다(원본 `w_max=1.8`인데
가정 제원의 실제 상한은 1m/s에서 1.18 rad/s).

### 새로 만든 것
| 파일 | 내용 |
|---|---|
| `pickr/kinematics_ackermann.py` | 자전거 모델. 원호 적분 오도메트리 검증 완료(5.3m 원 주행 오차 0.63mm) |
| `pickr/control/mppi_ackermann.py` | MPPITorch 상속. 롤아웃을 자전거 모델로, 조향 서보 각속도 제한 추가 |
| `pickr/hal/arduino.py` | 아두이노 시리얼 HAL (ZLAC 대체). 송수신 스레드 + 링크 감시 |
| `firmware/PROTOCOL.md` | 젯슨↔아두이노 프로토콜 + 비상정지 배선 설계 |
| `firmware/mediscribe_car/*.ino` | Mega 2560 펌웨어. 워치독 200ms, ESC 아밍, 슬루 제한 |

**그대로 쓰는 것**: SLAM·로컬라이제이션 전부(구동방식과 무관). `astar.py`는 일단 유지하고
복도 주행 실측 후 Hybrid A* 필요 여부 판단(미리 만들면 큰 작업인데 안 쓸 수도 있음).

### ⚡ MPPI 성능 실측 — 설정을 바꿔야 한다
롤아웃이 호라이즌만큼 파이썬 for문을 돌아 **GPU 커널 런치 오버헤드가 T배**로 붙는다.
반면 샘플 K는 GPU 병렬이라 **사실상 공짜**다.

| 샘플 | 호라이즌 | 스텝당 |
|---|---|---|
| 800 | 25 | 42.6ms |
| 128~4096 | 15 | **28ms (샘플 수 무관)** |

**권장: samples=2048, horizon=15** (원본 800/25 대비 탐색은 2.5배, 연산은 33% 절감).
제어주기 50ms 대비 여유 44%. 단 예측거리가 1.25초→0.75초로 줄어 장애물 인지가 늦어진다.
더 필요하면 dt를 0.05→0.08로(같은 연산량에 1.2초). 근본 해결은 롤아웃 루프를
CUDA 그래프/`torch.compile`로 묶는 것 — 나중 과제.

### 하드웨어
- **아두이노 Mega 2560** (정품, 맨 보드). 하드웨어 시리얼 4개, 외부 인터럽트 2/3/18/19/20/21.
  **엔코더는 반드시 이 핀 중에서** 쓸 것. 5V 로직이라 E-stop 스위치 직결 가능
  (젯슨 GPIO는 3.3V라 직결 금지 — 아두이노가 이 역할을 맡는 이유).
- **카메라 D435i** (IMU 내장 → fusion 에 활용). 원본 코드는 D455+D405 기준이라 수정 필요.
- **라이다 STL-27L** — 드라이버 `ros2_ws/src/ldlidar_stl_ros2` 빌드 완료. **통신속도 921600**
  (웹 문서엔 115200으로 나오나 실제 런치파일은 921600. 그대로 믿었으면 연결 실패).
- **E-stop KGE-N4R2R** — 소프트웨어로 멈추는 설계 금지. NC 접점으로 ESC 전원을 물리 차단하고,
  아두이노는 상태만 읽는다. 젯슨이 커널 패닉이면 소프트 정지는 작동하지 않는다.

### 미확정 (사용자 확인 필요)
- 차량 제원: **축간거리 / 최대조향각 / 바퀴반지름 / 엔코더 분해능** — 현재 가정값
  (0.45m / 28도 / 0.06m / 360틱)으로 코드 작성됨. 실측 후 교체 필요.
- 아두이노 배선(ESC 종류, 조향 서보, 엔코더 유무) 미정. 핀 배치는 제안 상태.

## Day 3 결과 (2026-09-04): 마이크 실시간 인식 달성 🎤

**사용자 지시 우선순위: ① 마이크 구동+인식(완료) ② 자율주행 차량 구동(하드웨어 대기).
인식 품질 튜닝은 나중으로 미룸.**

### ReSpeaker 연결 완료
- **ReSpeaker Mic Array v2.0** (2886:0018, XMOS), card 2 `ArrayUAC10`
- **6채널 펌웨어**: ch0=빔포밍+AEC 처리(원본 대비 RMS 8배), ch1~4=원본 마이크, ch5=재생 루프백
- 녹음: `arecord -D hw:2,0 -f S16_LE -r 16000 -c 6`

### 실시간 마이크 → Riva 스트리밍 동작 (`python/live_asr.py`)
사용자 육성으로 검증: "안녕하세요 오늘 회진 시작하겠습니다" 등 문장 단위 실시간 확정.
`python3 live_asr.py --seconds 30` 으로 재현. **확정(is_final) 문장이 증분 요약의 입력이 된다.**
알려진 손실: 문장 경계에서 단어가 잘리는 경우 있음("혈압은" 유실) — 품질 단계에서 다룰 것.

### Riva vs Whisper 첫 실측 (같은 실제 마이크 녹음, 대회 핵심 데이터)
원문: "공복혈당이 180이고 당화혈색소가 8.2퍼센트입니다. 메트포르민을 하루 500밀리그램에서..."
| 엔진 | 결과 |
|---|---|
| Riva ko-KR | "목 혈당이 백팔십이고 당화 혈색소가 팔점이 퍼센트입니다 / 포르 이을 하루에 오백 밀리 그램에서 천" |
| Whisper large-v3 | **"다음 영상에서 만나요."** (전체 날조) |
| Whisper turbo | 동일 날조 / 재시도 시 "5 5 5 5..." / 힌트 프롬프트 되뱉기 |

- Riva: 숫자 정확(백팔십, 팔점이), **의학용어에서 무너짐("메트포르민"→"포르 이을")** ← 대회 논점 실증
- Whisper: 유튜브 학습편향 환각. **⚠️ 원인 불명 미해결** — 파일 정상(Riva는 같은 파일 인식),
  ffmpeg 디코딩 정상 확인, 배열 직접 입력해도 "1,2,3,4,4,4..." 반복. fp16/torch 2.10 조합 의심.
  다음 시도 후보: fp16=False, beam_size 지정, faster-whisper 대체, 조용한 방 대신 큰 소리 녹음.

### 차량 (사용자 지시로 보류 중)
- 라이다·아두이노 여전히 미연결 (`/dev/ttyUSB*` 없음)
- `sw/2.0/scripts/sim_drive.py` (A*+애커만 MPPI 닫힌루프 검증) **작성 완료, 실행은 안 함**
  — 두 번 모두 사용자 사정으로 중단. 차량 재개 시 이것부터 돌리면 Hybrid A* 필요 여부가 나온다.

### 오늘 배운 운영 교훈
- 백그라운드 작업은 `setsid`로 세션과 분리해서 띄울 것 — Claude 세션 재시작에 두 번 죽었다.
- `pkill -f`는 자기 명령줄도 매칭한다 — 패턴에 대괄호 트릭(`[a]record`)을 쓸 것.
- Riva+Whisper 동시 로드는 스왑 폭풍(5.8GB)을 부른다. 한 번에 하나만.

## USB WiFi 동글 (2026-09-04) — 내장 안테나 빠짐 문제 대안, 동작 확인
- 동글: Realtek **0bda:c832 = RTL8852C 계열**. 커널 5.15 tegra에 내장 드라이버 없음.
- 드라이버: `lwfinger/rtw8852cu` (**`rtl8852bu`/`morrownr` 저장소는 다른 칩이거나 404** — 헛수고했음).
  소스 `~/mediscribe/tools/rtw8852cu`, 빌드는 `make ARCH=arm64 KSRC=$(readlink -f /lib/modules/$(uname -r)/build)`
  (**`ARCH=arm64` 필수** — Makefile이 `uname -m`=aarch64를 넣어 `arch/aarch64` 없음 오류). 6.3MB `8852cu.ko`.
- 설치됨: `/lib/modules/5.15.148-tegra/kernel/drivers/net/wireless/8852cu.ko` + depmod. 꽂으면 자동 로드.
  **커널 업데이트하면 재빌드 필요** (DKMS 미사용). 절대 커널/우분투 업그레이드 금지 원칙과 같은 맥락.
- 인터페이스 `wlx84fc140c44ce`, NM 프로필 **`Yonsei-usb`**(Yonsei 복제, 동글 바인딩). 내장 카드 프로필 `Yonsei`는 `wlP1p1s0`에 바인딩.
- sudo 팁: 터미널 입력기가 **한글(ibus hangul) 모드면 비밀번호가 자모로 들어가 계속 실패**한다. 한/영 전환 후 입력.

## 차량 구동 1차 (2026-09-04)
- 아두이노 Mega `/dev/ttyACM0` (by-id `usb-Arduino__www.arduino.cc__0042_...`). arduino-cli `~/mediscribe/tools/bin`.
- 실제 핀맵(노션): D2/D3 조향 IN1(우)/IN2(좌) — **DC 모터, 각도 센서 없음**; D4/D5 좌측 전/후; D6/D7 우측 전/후. sign-magnitude H-브리지. 엔코더 없음.
- 펌웨어 v2 `firmware/mediscribe_car/` 업로드됨: `C <v듀티> <조향듀티>`, 워치독 200ms, 시동 킥 100ms, E-stop D22. 통신 50Hz 확인.
- `python/car_test.py` 로 전진/후진/조향 펄스 테스트 실행 완료 — **바퀴 실제 회전 방향은 사용자 확인 대기**.
- 이전 팀 텔레옵 펌웨어(9600bps, w/s/a/d)는 덮어썼음. 좌측 모터 후진 시 PWM 250 필요했다는 기록 → 시동 킥의 근거.

## Day 3 저녁 (2026-09-04): 실시간 마이크 → 증분 SBAR 파이프라인 연결 완료 (`python/live_sbar.py`)
`ReSpeaker ch0 → Riva 확정문장 → 게이트 → qwen3.5:2b 추출 → 필터 → 코드 병합 → 메모`. 문장당 추출 2~4초.
**사용자 결정: 요약 모델 = qwen3.5:2b** (8B는 Riva와 동시에 올리면 스왑 6GB로 불가).

### 프롬프트만으로는 안 된다 — 오늘 세 번 확인
- "없음"만 출력(과소, 12건 19.7%) ↔ 빈칸 형식 주면 무조건 채워 날조(혈당 180→"250", 잡담에서 약 이름 발명)
- phi4-mini:3.8b는 어떤 프롬프트에서도 숫자를 지어냄 → **추출기로 사용 불가 확정**
- 8B는 형식 예시 문장("파스를 붙입니다")을 그대로 복사

### 그래서 코드가 검증한다 (`incremental_v2.process_chunk` — eval/live 공용)
1. **임상 게이트** `has_clinical_content`: 숫자·약·검사·증상 키워드 없으면 모델에 안 보냄 (잡담 21문장 전부 차단 확인)
2. **근거 검사** `grounded`: 추출 줄의 숫자가 원문에 없으면 버림. 한글 숫자 변환기 `korean_numerals_to_digits`
   (백팔십이고→180이고, 팔점이→8.2, 천→1000; 만성·백혈구·천천히·만약은 숫자로 안 봄 — 단위 내림차순 검증)
3. **예시 복사 차단** `is_example_copy`, **빈칸 문구 차단** `is_placeholder`("(해당 없음)")
4. **섹션 보정** `fix_section`: 용량/복용 키워드 → 처방/약, 요일/재검 → 다음 진료, 어지/사탕 → 주의하세요
5. **병합** `merge_fact`: 기존 줄을 포함하는 더 긴 줄이면 교체 (예전엔 긴 쪽을 중복으로 버려 "화요일 혈액검사"가 사라졌음)
6. 채점기는 공백 무시. **채점기와 실시간이 다른 코드를 돌던 버그 수정** (예전 수치들은 비교 불가)

### 남은 약점 (내일 후보)
- 2B는 단일 추출에서 **용량·시점을 흘림** ("하루 한 번 저녁 3밀리그램" → "와파린을 시작합니다"). → **규칙 기반 회수**: 숫자+밀리그램/mg/단위/회 패턴을 원문에서 직접 확정 사실로 추가
- ASR 오류를 그대로 옮김 ("메트포르민"→"포르 민"/"매트 포럼"). 약품명 사전 교정은 품질 단계
- DOA(음원 방향)는 udev 규칙 `/etc/udev/rules.d/99-respeaker.rules` + `python/doa_monitor.py`로 읽히지만(148°),
  마운트 위치 미정이라 보류. 사용자: 방향 구분은 지금 불필요.

### 운영 교훈 (오늘 네 번 당함)
- **세션 시작 명령에 pkill 을 절대 같이 넣지 말 것.** pkill -f 가 자기 셸을 죽여 세션이 안 뜬 채 사용자가 말함.
- `sudo` 는 `echo pw | sudo -S -p "" cmd` 형태로만. `| sudo -S tee` 는 stdin 충돌로 빈 파일 생김.
- `readlines()` 는 50Hz 스트림에서 영원히 안 끝남 → 시간 제한 루프로.

## Day 4 (2026-09-07): 규칙 회수·단어 부스팅·시연 대본 완료 + 젯슨 크래시 원인 규명

### 결과 요약 (12건 채점, `python/eval_dataset.py --save` → `benchmarks/eval_qwen3.5_2b.txt`)
| 단계 | 전체 보존율 | 안전 보존율 |
|---|---|---|
| 기준선 v4 (9/4) | 34.4% | 29.5% |
| 규칙 기반 회수 (용량·일정·경고) | 60.7% | 56.8% |
| + 임상 게이트·경고 패턴 보강 | 88.5% | 93.2% |
| + 최종 (9/7 오전) | **93.4% (57/61)** | **100% (44/44)** |
| 시연 케이스 2건(demo-001/002) 첫 채점 | 85.7% | 100% |
| + 수치·한글수사 일정 규칙 (9/7 오후, 14건 재채점) | **96.0% (72/75)** | **98.1% (52/53)** |

**핵심**: 2B 모델이 흘리는 용량·일정·경고·검사수치는 `rule_facts()`가 원문에서 **모델을 거치지 않고** 확정 사실로 넣는다.
규칙 우선순위: 용량(`_DOSE`+`_MED_HINT`) → 일정(`_SCHED`, 한글 수사 "이 주 뒤" 포함) → 검사수치(`_MEASURE`, 용량 문장 제외) → 경고(`_WARN`, 질문 제외).
고유어 수사 변환 `native_numerals`("한 알"→"1 알").

### Riva 단어 부스팅 + 끝점 조정 (`python/riva_asr.py`, `python/boost_words.txt`)
- 근거리(30cm) 녹음에서 **부스팅 20 → "메트포르민" 3/3 인식** (없으면 1/3, 60이면 조사 탈락). 기본값 20.
- **거리가 결정적**: 원거리(RMS 0.037)에선 "포르 이을". 로봇 마운트 마이크는 의사 30~50cm 안에.
- 끝점 `stop_history_ms=1500` (기본 800은 "와|파린"처럼 단어 중간에서 끊었음). 확정 0.7초 늦어지지만 무해.
- 렉시콘에 없던 9개(레보티록신·이지에프알·아이엔알·티에스에이치·씨티·알렌드로네이트 등) `lexicon.txt`에 추가 완료, Riva 재시작 후 회귀 확인 통과.
  영문 약어는 한글 발음(eGFR→이지에프알)으로 넣어야 한다.

### Whisper 환각 원인 규명 → `benchmarks/2026-09-07-whisper-nearfield.md`
9/4의 "다음 영상에서 만나요"는 **원거리 음질 탓**. 근거리에선 turbo+힌트 프롬프트로 정확 인식(1.4s).
단, 발화 횟수 불안정(2회 말하면 1회 또는 3회 출력). 비교표 결론: 원거리에서 Riva는 부분 인식, Whisper는 전체 날조.

### 시연 대본 `dataset/demo_script.md` (환자 2명, 약 3분) — rounds.json에 demo-001/002로 채점셋 포함
**사용자 낭독 리허설 대기 중.** `python3 python/live_sbar.py`로 실시간 인식률·보존율 측정.

### 🔴 젯슨 하드 크래시 원인 규명 (9/4 19:21, 9/7 15:09, 9/7 16:33 — 3회, 전부 종료 기록 없음)
**원인: 메모리 초과 → 15GB 스왑(8GB 파일+7.6GB zram) 폭풍 → 시스템 다운.** 온도·전원 정상.
직접 원인은 Riva 위에 Whisper large-v3(특히 fp32 6GB)를 올린 것. CLAUDE.md에 경고가 있었는데도 두 번 반복함.

**실측: 지금까지의 메모리 예산은 틀렸다.** 젯슨은 GPU 메모리가 RAM과 공유되는데 RSS/docker stats에 안 잡힌다.
| 구성 | tegrastats RAM | MemAvailable |
|---|---|---|
| 재부팅 직후(데스크톱+VSCode) | 3.8GB | 11GB |
| + Riva 기동 | 11.7GB (**Riva 실제 ≈ 8GB**, docker stats는 4.4GB만 표시) | 3.8GB |
| + ollama qwen3.5:2b (Q8_0, ctx 4096 → 4.5GB, CPU/GPU 42/58 분할) | 14.5GB | **1.1GB** |
→ 현재 제품 조합(Riva+2B)만으로 꽉 찬다. pyannote·Nav2를 더 올릴 여유가 **없다**. 아래 "메모리 계획" 참고.

**재발 방지 장치 (적용 완료)**
1. `tools/memguard.sh [GB] -- <명령>`: cgroup 상한(systemd-run) + 스왑 금지. 초과 시 그 작업만 죽음(137). **Whisper·pyannote·채점은 반드시 이걸로.**
2. 영속 저널 활성화(`/var/log/journal`): 다음 크래시부턴 `journalctl -k -b -1`로 원인 확인 가능.
3. 규칙: Riva와 Whisper large-v3 동시 구동 절대 금지. Whisper는 turbo+fp16만, Riva 내린 뒤.
4. Riva **기동 중**엔 순간 사용량이 더 크다 → 기동 완료 전에 ollama/채점 띄우지 말 것.

### 메모리 계획 (미결 — 사용자 결정 필요)
- ollama 모델을 **Q4_K_M 양자화 + num_ctx 2048**로 바꾸면 4.5→~2GB. 단 추출 품질 재채점 필요.
- 시연 때 **데스크톱 GUI 없이(headless)** 돌리면 ~1.5GB 회수 (VSCode 1GB + gnome).
- 8GB 파일 스왑 제거(zram만 유지): 넘칠 때 멈추는 대신 빨리 OOM-kill 되도록.
- Riva 8GB가 가장 크다. Triton 인스턴스/배치 축소 옵션 조사, 또는 화자분리(pyannote)·Nav2를 **다른 장비**로 분리하는 안.

### 운영 교훈 추가
- `pkill -f "python3 -u -"`가 자기 셸을 죽여 명령 전체가 144로 죽음 — **대괄호 트릭 `[p]ython` 필수** (또 당함).
- 크래시 후 `/tmp`(스크래치패드 포함)는 지워진다. 결과는 즉시 `benchmarks/`에 파일로 남길 것.
- `last -x reboot shutdown`에서 shutdown 짝 없는 reboot = 하드 크래시.

## Day 4 저녁 (2026-09-07 16:30~): 세션 유실 복구 + 메모리 계획 실험 착수

### 세션이 "날아간" 것에 대해
16:31 하드 크래시(3회째) 뒤 이전 세션은 `~/`에서 새 세션으로 이어졌고, 사용자가 이후 **`~/Desktop/medscribe`**(zip만 있는 폴더)를 열어
대화가 사라진 것처럼 보였다. 기록은 남아 있다:
- `~/.claude/projects/-home-jetson-mediscribe/2c701166-….jsonl` (9/1~9/7 16:10) → `cd ~/mediscribe && claude --resume 2c701166-3629-498b-ada4-6ddfee09bbca`
- `~/.claude/projects/-home-jetson/b7d78d26-….jsonl` (9/7 16:10~16:42, 14건 채점까지) → `cd ~ && claude --resume b7d78d26-87c1-47d3-bc4b-5ba40181c210`
**VS Code 에서는 반드시 `~/mediscribe` 폴더를 열 것.** `~/Desktop/medscribe/CLAUDE.md` 에 이 파일을 가리키는 안내를 넣어 두었다.

### 부스팅 점수 비교 (`python/boost_sweep.py` → `benchmarks/2026-09-07-boost-sweep.md`)
근거리 녹음 `audio/med_close_ch0.wav`(같은 문장 3회):
| 점수 | 메트포르민 | 관찰 |
|---|---|---|
| 0 | 1/3 ("메트 포럼", "메트 보르민") | 부스팅 없으면 깨짐 |
| 20 | 3/3 | 조사 "을" 2/3 탈락, "인슐린은" 유지 |
| 40·60 | 3/3 | **"인슐린은"→"인슐린" 조사 탈락** (9/7 오전 관찰 재현) |
→ **기본값 20 유지.** 조사 탈락은 규칙 추출(`_DOSE`·`_MED_HINT`)에 영향 없음.

### ASR 약품명 교정기 (`python/asr_normalize.py`, 사전 `python/drug_lexicon.txt`)
부스팅으로도 남는 "메트 포럼"·"메트 보르민"을 **자모 유사도(≥0.78)** 로 사전 표기로 되돌린다. 3음절 이상만, 완전 일치는 불변.
"포르 이을"처럼 유사도가 낮으면 **고치지 않는다**(날조 금지 원칙). 데이터셋 14건 전 발화에서 오탐 0건 확인.
`process_chunk()` 첫 단계에서 적용되므로 채점·실시간 모두 같은 경로.

### 의사 1-tap 검수 + 출력 게이트 완성 (`python/review_server.py`, 표준 라이브러리만)
파이프라인의 human-in-the-loop 단계를 실제 코드로 만들었다. `live_sbar.py` 가 끝나면 `out/memo_latest.json` 을 남기고,
검수 서버(`python3 python/review_server.py`, 포트 8080)에서 의사가 섹션별로 고친 뒤 **승인**해야 `/output`(QR 2종: 링크·본문)·`/print`(A6 @page)가 열린다.
**미검수 상태에서는 `/output`·`/qr.png`·`/print` 전부 403** (curl 로 검증: 승인 전 403 → POST /approve → 200). 반려하면 폐기.
승인본은 `out/approved_<id>.md`. 폰에서 열려면 같은 WiFi 에서 `http://<젯슨IP>:8080` (학교 WiFi 는 기기간 차단 가능 → 핫스팟 권장).

### `live_sbar.py` 파일 입력 모드 — 사용자 없이 E2E 시험 가능
`--wav audio/med_close_ch0.wav [--fast]` 로 녹음을 Riva 에 실시간(또는 최대) 속도로 흘린다. `--patient`, `--num-ctx`(기본 2048) 추가.
9/7 17:10 E2E: 3문장 확정(부스팅 20 → 메트포르민 3/3), 중복 3문장이 메모 1줄로 병합, 추출 4.9~6.5s, 메모 저장 → 검수 → QR 까지 통과
(`benchmarks/e2e_wav_2026-09-07.log`). 남은 손질: 메모 줄의 한글 수사("천 밀리그램")를 환자용 숫자로 바꿀지 결정.

### 메모리 감시 (`tools/memwatch.sh`, 로그 `benchmarks/memwatch.log`)
30초마다 가용/스왑 기록. 가용<900MB 또는 스왑>4GB 면 WARN, 가용<500MB 또는 스왑>6GB 면 채점·Whisper·pyannote 를 죽이고 ollama 모델을 언로드한다.
시작: `setsid nohup tools/memwatch.sh >/dev/null 2>&1 &`. **pgrep -f 로 "이미 떠 있나" 검사하면 자기 셸에 매칭돼 안 뜬 채 넘어간다** — 이번에도 당함. `ps -eo cmd | grep "[t]ools/memwatch"` 로 확인.

### 시연 런처와 절차서
`bash tools/demo.sh [--seconds 180 --patient 이름 | --wav 파일 --fast]` 가 Riva 확인 → 메모리 확인·memwatch → 검수 서버 → 모델 워밍업 → `live_sbar.py` 순으로 띄운다.
사용자용 절차서: `docs/DEMO.md` (복붙 명령, 검수 화면 사용법, 메모리 주의).
참고: 영속 저널을 켰지만 `journalctl --list-boots` 가 부팅을 구분하지 못해(부팅 1개로 표시) 16:31 크래시의 커널 로그는 못 건짐.

### 메모리 계획 실험 (완료 9/7 18:14 — `tools/q4_chain.sh`, 로그 `benchmarks/q4_chain_2026-09-07.log`)
- `num_ctx 2048` 실측: Q8 모델 4.12→4.08GB(ollama ps), **가용 2.2→2.7GB (+0.5GB)**. 코드에 `--num-ctx` 옵션 추가(`ollama_client.DEFAULT_NUM_CTX`, eval/live 공용).
- `qwen3.5:2b-q4_K_M` 태그가 ollama 레지스트리에 있음(1.9GB). 학교 WiFi 400KB/s → 약 80분. 다운로드 후 체인이 자동으로
  Q8 언로드 → Q4 ctx2048/4096 로드 메모리 측정 → 14건 채점(`benchmarks/eval_run_q4_ctx*.log`, `eval_qwen3.5_2b-q4_K_M_ctx*.txt`)까지 돌린다.
  **결정(9/11): 시연 기본 모델 = `qwen3.5:2b-q4_K_M`, num_ctx 2048** (안전 보존율 동일, 0.85GB 절감). `--model qwen3.5:2b` 로 되돌릴 수 있음.
| 구성 | ollama ps | 가용 메모리(Riva 구동 중) | 전체 보존율 | 안전 보존율 |
|---|---|---|---|---|
| Q8 ctx4096 (현재) | 4.12GB | 2.2GB | 96.0% (72/75) | 98.1% (52/53) |
| Q8 ctx2048 | 4.08GB | 2.7GB | 96.0% (72/75) | 98.1% (52/53) — **ctx4096과 동일** |
| Q4_K_M ctx2048 | 3.23GB | 4.8GB | 94.7% (71/75) | **98.1% (52/53)** — 안전 동일, 비안전 1건('취약 시기') 추가 누락 |
| Q4_K_M ctx4096 | 3.26GB | 4.7GB | 94.7% (71/75) | 98.1% (52/53) — ctx 무관 |

## 메모리 실측 정정과 시나리오별 RAM 계획 (2026-09-07 저녁 측정, 9/11 정리)

### 🔴 "Riva 8GB"는 틀렸다 — 프로세스별 GPU 메모리(nvmap) 실측
`echo pw | sudo -S cat /sys/kernel/debug/nvmap/iovmm/clients` 로 GPU 할당을 프로세스별로 볼 수 있다 (RSS 에 안 잡히는 부분).
| 구성요소 | RSS | GPU(nvmap) | 합 |
|---|---|---|---|
| Riva (tritonserver+riva_server+gunicorn) | 1.9GB | 1.8GB | **≈3.7GB** (그중 CUDA 풀 1GB 는 `start-riva` 가 미리 잡는 것) |
| ollama qwen3.5:2b Q8 ctx2048 | 1.0GB | 3.8GB | **≈4.8GB** ← 가장 큼 (vision 인코더 포함 모델이라 텍스트 2B 보다 큼) |
| ollama qwen3.5:2b-q4_K_M ctx2048 | | | ≈3.2GB (ollama ps) |
| VS Code(16프로세스) + gnome/Xorg + Claude CLI | 2.3GB | 0.4GB | ≈2.7GB |
| 주행 스택(예상): torch+CUDA 1.5~2 + realsense 0.4 + numpy 0.2 | | | ≈2.5GB |
9/7 오전의 "Riva 8GB" 는 기동 순간 피크와 페이지캐시를 합친 값이었다. **ollama 병렬 슬롯은 이미 1** (`Parallel:1`, 로그 확인) → 환경변수로 더 줄 게 없다.
스왑은 zram(8×1GB, RAM 안에서 압축) 이 우선이고 8GB 파일 스왑은 거의 안 쓰인다. `swap 사용량` 이 높아도 가용이 넉넉하면 잔류일 뿐이다.

### 시나리오별 계획 (주행과 회진은 동시에 안 쓴다 — 사용자 결정 9/7)
| 모드 | 올라가는 것 | 합 (데스크톱 포함) | 비고 |
|---|---|---|---|
| 주행 | Riva 3.7 (내리지 않음: 재기동 10분) + 주행 스택 2.5 + 데스크톱 2.7 | ≈8.9GB | LLM 은 `keep_alive:0` 으로 언로드 (재로드 10초) |
| 회진 | Riva 3.7 + LLM Q4 3.2 + 데스크톱 2.7 | ≈9.6GB | 주행 프로세스 종료(torch 해제) |
| 둘 다 (필요해지면) | 3.7+3.2+2.5+2.7 | ≈12.1GB | headless 로 하면 ≈9.5GB — 가능은 함 |
전환은 `tools/mode.sh drive|rounds` (ollama 로드/언로드 + 주행 프로세스 시작/종료). 추가 절감 후보: headless 시연 −2GB, Riva CUDA 풀 1GB→256MB(−0.75GB, `riva/start-riva.orig` 복사해 둠, 컨테이너에 마운트해 교체 후 재기동 필요), Whisper 는 시연 중 절대 금지.

### 🔴 절대 하지 말 것 (9/7 17:50 사고)
`docker exec riva-speech start-riva --help` 는 도움말이 아니라 **Riva 서버를 한 벌 더 기동**한다 → Triton 2개 → 가용 281MB, 스왑 6GB. memwatch 가 ollama 를 내려 살아남았고, 컨테이너 안의 여분 프로세스를 kill 해 복구했다. 컨테이너 안에서 `start-riva` 를 직접 부르지 말 것.

## 자율주행 스택 결정 (2026-09-07 사용자 지시): ROS2 전혀 안 씀, Pickr2 에서 필요한 것만 추출
Pickr2 는 ROS 의존 0 (rclpy 없음), 순수 파이썬 + pyserial/pyrealsense2/torch. 조사 결과 요약:
- **그대로 쓰는 것(~1,050줄)**: core/se2, kinematics_ackermann, hal/{base,arduino,sim}, nav/{mapping,scan_match,pose_graph,graph_slam,costmap,astar,obstacles,obstacle_memory,relocalize,fusion}, control/{mppi_torch,mppi_ackermann}, io/{stream,lastpose,telemetry}, scripts/sim_drive.py
- **유일한 신규 필수 코드: `hal/lidar_stl27l.py`** — 기존 hal/lidar.py 는 RPLidar(256000bps) 후처리뿐, STL-27L(LDROBOT 0x54 헤더 47바이트 패킷, 12점, CRC8, 921600bps) 파서가 없다. `(0, angle_deg, dist_mm)` 리스트로 내보내면 `scan_to_points/scan_to_rays` 이후 전부 무수정.
- **수정**: config.py(1/5 스케일 치수·WHEELBASE/DELTA_MAX/ARDUINO_PORT), hal/realsense.py(`prefer="D435"`, 해상도 424x240 — D435i 는 480x270 미지원), hal/imu.py(L225 "D455"→"D435I"), localizer(엔코더 없음 → 명령 기반 dead-reckoning `integrate_pose` 를 odom 자리에), control/safety.py `open_side_w`(제자리회전 전제 → 후진/정지), loc_server.py(라이다 오픈부만)
- **drive_server.py(1187줄) 는 ~500줄로 새로 쓴다**: motor_thread(ZLAC 상태/폴트/엔코더 전제) 통째 재작성, 제자리 방향맞춤(orient)·open_side_w 탈출회전은 애커만 불가, 도킹·후면카메라·Reeman 제거.
- **버림**: hal/{zlac,modbus,devlock}, kinematics.py(차동), control/apriltag_dock_ctrl, api/reeman, nav/likelihood(사장), ui/mpl_viewer, 해당 tests.
- 의존성 최소 세트: numpy, pyserial, pyrealsense2, torch(MPPI 둘만 최상단 import — **lazy import 로 바꿔 개발 중 1.5GB 안 물게**). scipy/opencv/websockets/matplotlib/rplidar/apriltags 불필요.
- 메모리를 더 줄여야 하면 MPPI 대신 Pure Pursuit(CPU ~80줄) 로 torch 제거(−1.5GB). `sim_drive.py` 로 같은 맵에서 두 안 비교 가능.

## 2026-09-11: 라이다·조이스틱 연결 완료 (ROS2 없이)

### 커널 모듈 2개 직접 빌드 (Yahboom 커널에 없음) — `tools/pl2303/`, `tools/xpad/`
- 라이다 어댑터가 **PL2303**(067b:2303) 인데 `pl2303.ko` 가 커널에 없어 `/dev/ttyUSB0` 가 안 생겼다. 조이스틱 F710(046d:c21f, XInput 모드) 도 `xpad.ko` 없음.
- 해법: kernel.org 에서 v5.15.148 의 `pl2303.c/.h`, `xpad.c` 를 받아 `make -C /lib/modules/$(uname -r)/build M=$PWD ARCH=arm64 modules` 로 빌드,
  `/lib/modules/5.15.148-tegra/kernel/drivers/{usb/serial,input/joystick}/` 에 복사 + `depmod -a`. **꽂으면 자동 로드**. 커널 업데이트 시 재빌드(8852cu 와 동일).
- 결과: 라이다 `/dev/ttyUSB0` (by-id `usb-Prolific_Technology_Inc._USB-Serial_Controller_D-if00-port0`), 조이스틱 `/dev/input/js0`.

### STL-27L 파이썬 드라이버 `sw/2.0/pickr/hal/lidar_stl27l.py` — 실기 검증 완료
- 프로토콜은 ROS2 드라이버 `lipkg.cpp` 에서 옮김: 47바이트 패킷(0x54 0x2C, speed, start/end angle 0.01°, 12점×(u16 mm, u8 강도), timestamp, CRC8 테이블).
- 실측: **921600bps, 10.0Hz(597rpm), 스캔당 2,172점, CRC 오류 0%**. 230400 등 다른 보레이트는 쓰레기 → 웹 문서(115200) 믿지 말 것.
- 출력은 RPLidar `iter_scans` 와 같은 `[(강도, 각도deg, 거리mm)]` → `hal/lidar.scan_to_points/scan_to_rays` 무수정. `scan()` 은 `hal.base.Lidar` 계약.
- 진단: `cd sw/2.0 && python3 -m pickr.hal.lidar_stl27l --seconds 5`. **방향 결정(9/11 손 시험)**: 앞(커넥터 반대편) = 원시 15°, 왼쪽 = 원시 115° → 반시계 증가. `config.py`: `LIDAR_FLIP=+1.0`(RPLidar 와 반대), `ANGLE_OFFSET_DEG=-15.0`(잠정, 차량 장착 후 벽으로 재보정).
- 첫 실행에서 패킷 0 이 나온 적 있음(포트 생성 직후) — 다시 실행하면 정상. 원인 미상, 재현 시 조사.

### 조이스틱 텔레옵 `sw/2.0/scripts/teleop_joy.py` (9/11, dry 검증 완료)
F710(XInput/xpad, `/dev/input/js0`) → 펌웨어 v2 에 `C <듀티> <조향>` 직결 (m/s·rad 가 아니라 듀티 -1..1 — `hal/arduino.py` 는 m/s·rad 를 보내므로 캘리브레이션 전엔 텔레옵이 안전).
RB 데드맨(놓으면 C 0 0) · RT/LT 전후진 · 왼스틱 조향(+ = 좌) · Y/A 최대듀티 ±0.1 · B/Back = E 후 종료. `--dry` 로 아두이노 없이 매핑 확인.
dry 실측: RB 누름 → ● , RT 0.47 → 듀티 +0.16 (max 0.35). **by-id 링크는 `*-joystick` 중 `event` 없는 것을 골라야 함** (event 장치를 잡으면 값이 엉킴).
실차: `python3 scripts/teleop_joy.py --max 0.35` (아두이노 `/dev/ttyACM*` 필요, 바퀴 띄우고 시작).

### 내장 PCIe WiFi(RTL8822CE, wlP1p1s0) 영구 비활성 (9/11, 사용자 지시)
USB 동글(`wlx84fc140c44ce`, 프로필 `Yonsei-usb`)만 쓴다. 내장 카드는 `CHAN` 프로필로 접속 시도만 반복해 끔.
- `/etc/modprobe.d/blacklist-rtl8822ce.conf` (`blacklist` + `install rtl8822ce /bin/false`) — initrd 에 모듈 없음을 확인했으니 부팅 시 안 올라옴
- `/etc/NetworkManager/conf.d/99-disable-pcie-wifi.conf` (`unmanaged-devices=interface-name:wlP1p1s0`)
- 즉시 `rmmod rtl8822ce` 완료, 동글로 인터넷 정상(ping 46ms). **되살리려면 두 파일 삭제 후 재부팅.**

## 다음 할 일 (2026-09-07 갱신)

### 사용자 필요 (돌아오면)
- [ ] `docs/DEMO.md` 대로 `bash tools/demo.sh --seconds 180` 한 번 돌려 검수 화면(8080)까지 확인
- [ ] **대본 3분 낭독 리허설** (`dataset/demo_script.md`, 마이크 30~50cm) → `python3 python/live_sbar.py`로 인식률·보존율 측정
- [ ] headless 시연 여부 결정 (−2GB). Riva CUDA 풀 축소 재기동은 채점 없는 시간에

### 코드 (사용자 없이 가능)
- [x] Q4 채점 완료 → 기본 모델 `qwen3.5:2b-q4_K_M` 로 교체 (9/11)
- [x] 부스팅 60 조사 탈락 확인 → 20 유지 (`benchmarks/2026-09-07-boost-sweep.md`)

### 차량 (ROS2 없이, Pickr2 추출) — 9/7 지시
- [x] `hal/lidar_stl27l.py` 작성·실기 확인 (9/11)
- [x] 라이다 방향(FLIP=+1, 오프셋 -15° 잠정) · 조이스틱 텔레옵 dry 검증 (9/11)
- [ ] 아두이노 연결 → `teleop_joy.py` 실차(바퀴 띄우고) → 바퀴 방향·조향 방향 확인 → config 치수 실측 → drive_server 재작성 → `sim_drive.py`
- [ ] 방향 보정 → 키보드 텔레옵 → `sim_drive.py` → 라이다(STL-27L, 921600) 연결
- [ ] 의학용어 문장 20~30개 근거리 녹음 → Riva vs Whisper 비교표 확장 (근거리 결과는 `benchmarks/2026-09-07-whisper-nearfield.md`)
- [ ] 회진 대화 14건 → 50건 (팀원 분담), pyannote 가중치(HF 토큰), 식약처 약품명 API

### ⚠️ 상시 주의
- **메모리 예산 (9/7 실측으로 정정)**: Riva 실제 ~8GB + qwen3.5:2b 4.5GB + 데스크톱 3.8GB = 꽉 참(가용 1.1GB).
  무거운 작업은 `tools/memguard.sh`로만. Riva+Whisper large-v3 동시 구동 금지. qwen3:8b 실전 불가.
- **우분투 24.04 업그레이드 제안 절대 수락 금지.**
