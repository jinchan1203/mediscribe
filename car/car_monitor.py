#!/usr/bin/env python3
"""MEDISCRIBE CAR 시리얼 모니터 — 아두이노가 보내는 상태줄을 파싱해서 보여준다.
사용법: python3 car_monitor.py [포트] [초]
"""
import sys, time, serial

PORT = sys.argv[1] if len(sys.argv) > 1 else "/dev/cu.usbmodem1101"
SECS = float(sys.argv[2]) if len(sys.argv) > 2 else 5
BAUD = 115200

with serial.Serial(PORT, BAUD, timeout=0.1) as s:
    time.sleep(2.0)            # 포트 열면 아두이노 리셋 → 부팅 대기
    s.reset_input_buffer()
    t0 = time.time(); n = 0; last = None
    while time.time() - t0 < SECS:
        line = s.readline().decode(errors="replace").strip()
        if not line:
            continue
        if line.startswith("S "):
            parts = line.split()
            n += 1; last = parts
        else:
            print("[MSG]", line)
    print(f"상태줄 {n}개 수신 ({n/SECS:.0f} Hz)")
    if last:
        print("마지막 상태:", last)
