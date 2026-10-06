"""MEDISCRIBE CAR v3 파이썬 조종 라이브러리 (ROS2 불필요, pyserial만 사용)

    from car import Car
    with Car() as car:
        car.drive(120, 120)      # 좌/우 구동 -255..255
        car.steer(150, 200)      # 조향 +우/-좌, 200ms 동안
        car.stop()

주의: 펌웨어 워치독 때문에 drive()는 0.5초 안에 반복 호출해야 계속 달린다 (안전장치).
"""
import time, threading, serial

class Car:
    def __init__(self, port="/dev/cu.usbmodem1101", baud=115200, wait_boot=2.0):
        self.ser = serial.Serial(port, baud, timeout=0.05)
        time.sleep(wait_boot)                 # 포트 열면 아두이노가 리셋됨
        self.ser.reset_input_buffer()
        self.status = {"left": 0, "right": 0, "steer": 0, "ms": 0}
        self.log = []                         # 상태줄 이외의 응답 (OK/ERR/WD STOP 등)
        self._run = True
        self._t = threading.Thread(target=self._reader, daemon=True); self._t.start()

    def _reader(self):
        while self._run:
            try:
                line = self.ser.readline().decode(errors="replace").strip()
            except Exception:
                break
            if not line: continue
            if line.startswith("ST "):
                p = line.split()
                if len(p) == 5:
                    self.status = {"left": int(p[1]), "right": int(p[2]), "steer": int(p[3]), "ms": int(p[4])}
            else:
                self.log.append(line)
                if len(self.log) > 200: self.log.pop(0)

    def send(self, cmd):
        self.ser.write((cmd.strip() + "\n").encode())

    def drive(self, left, right):  self.send(f"V {int(left)} {int(right)}")
    def forward(self, speed):      self.send(f"D {int(speed)}")
    def steer(self, pwm, ms=200):  self.send(f"S {int(pwm)} {int(ms)}")
    def stop(self):                self.send("X")
    def test(self, motor, direction=1, pwm=150, ms=500):
        self.send(f"T {motor} {direction} {pwm} {ms}")
    def set_invert(self, motor, flag): self.send(f"C {motor} {1 if flag else 0}")

    def close(self):
        try: self.stop(); time.sleep(0.1)
        finally:
            self._run = False; self.ser.close()
    def __enter__(self): return self
    def __exit__(self, *a): self.close()
