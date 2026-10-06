#!/usr/bin/env python3
"""키보드 수동 조종: W/S 전후진, A/D 조향, 스페이스 정지, Q 종료. 키를 떼면 자동 정지(워치독)."""
import sys, termios, tty, select, time
from car import Car

SPEED, STEER_PWM, STEER_MS = 180, 255, 200

def getch(timeout=0.1):
    r, _, _ = select.select([sys.stdin], [], [], timeout)
    return sys.stdin.read(1) if r else None

fd = sys.stdin.fileno(); old = termios.tcgetattr(fd); tty.setcbreak(fd)
try:
    with Car(sys.argv[1] if len(sys.argv) > 1 else "/dev/cu.usbmodem1101") as car:
        print("W/S 전후진  A/D 조향  space 정지  Q 종료   (속도", SPEED, ")")
        while True:
            k = getch()
            if k is None:            # 키 입력 없음 → 명령 안 보냄 → 0.5s 후 워치독이 정지
                pass
            elif k in "wW": car.drive(SPEED, SPEED)
            elif k in "sS": car.drive(-SPEED, -SPEED)
            elif k in "aA": car.steer(-STEER_PWM, STEER_MS)
            elif k in "dD": car.steer(STEER_PWM, STEER_MS)
            elif k == " ":  car.stop()
            elif k in "qQ": break
            st = car.status
            print(f"\rL={st['left']:4d} R={st['right']:4d} S={st['steer']:4d}  {car.log[-1] if car.log else '':<20}", end="", flush=True)
finally:
    termios.tcsetattr(fd, termios.TCSADRAIN, old); print()
