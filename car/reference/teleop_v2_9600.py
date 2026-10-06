# [참고용 — 현재 펌웨어(v3)와 호환 안 됨]
# 이전 세션에서 만든 v2 펌웨어용 키보드 텔레옵.
# v2: 9600bps, 한 글자 명령(w/s/a/d/x/c/q)
# v3: 115200bps, "V l r" / "S pwm ms" 형식 + 워치독
# 실제 테스트 결과 현재 아두이노에 올라간 펌웨어는 이 명령에 반응하지 않았음.

import serial
import sys
import termios
import tty
import time
import threading

# ============ 설정 ============
SERIAL_PORT = '/dev/cu.usbmodem1101'
BAUD_RATE = 9600
# ==============================

try:
    ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=0.1)
    time.sleep(2)  # 아두이노 부팅 대기
    print(f"✅ 아두이노 연결: {SERIAL_PORT}")
except serial.SerialException as e:
    print(f"❌ 시리얼 연결 실패: {e}")
    print("   아두이노 USB 연결 확인하세요")
    sys.exit(1)

print()
print("=" * 50)
print("   키보드 텔레옵")
print("=" * 50)
print("  W : 전진")
print("  S : 후진")
print("  A : 좌회전")
print("  D : 우회전")
print("  X : 정지 (구동만)")
print("  C : 조향 중앙")
print("  Q : 전체 정지")
print("  ESC 또는 Ctrl+C : 종료")
print("=" * 50)
print()

def read_arduino():
    while True:
        try:
            if ser.in_waiting > 0:
                line = ser.readline().decode('utf-8', errors='ignore').strip()
                if line:
                    print(f"  [Arduino] {line}")
        except:
            break
        time.sleep(0.01)

reader = threading.Thread(target=read_arduino, daemon=True)
reader.start()

def getch():
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
    return ch

try:
    while True:
        ch = getch().lower()

        if ch in ['w', 's', 'a', 'd', 'x', 'c', 'q']:
            ser.write(ch.encode())
            ser.flush()
            print(f"  → 명령 전송: {ch}")
        elif ch == '\x1b':  # ESC
            print("\n종료...")
            break
        elif ch == '\x03':  # Ctrl+C
            print("\n종료...")
            break
        else:
            pass

except KeyboardInterrupt:
    print("\n종료...")

finally:
    ser.write(b'q')
    ser.flush()
    time.sleep(0.5)
    ser.close()
    print("✅ 종료 완료")
