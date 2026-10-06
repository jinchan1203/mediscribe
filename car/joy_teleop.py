#!/usr/bin/env python3
"""로지텍 F710 게임패드로 차량 조종 (D 모드 = DirectInput 필요)

  왼쪽 스틱 상하 : 전진/후진
  오른쪽 스틱 좌우(또는 왼쪽 스틱 좌우) : 조향
  RB / A 버튼 : 부스트 (최대 속도)
  B 버튼      : 즉시 정지
  BACK 버튼   : 종료

안전: 스틱 놓으면 즉시 정지. 프로그램이 죽어도 펌웨어 워치독이 0.5초 내 정지.
"""
import sys, time, pygame
sys.path.insert(0, "/Users/macbook/mediscribe-car")
from car import Car

PORT       = sys.argv[1] if len(sys.argv) > 1 else "/dev/cu.usbmodem1101"
MAX_SPEED  = 200      # 일반 주행 최대 출력
BOOST      = 255      # 부스트 시 출력
MIN_SPEED  = 90       # 이 값 미만은 모터가 안 도니 데드존 처리
DEADZONE   = 0.15     # 스틱 중립 흔들림 무시
STEER_PWM  = 255      # 조향 출력 (앞바퀴 비트는 힘이 필요해 최대)
STEER_MS   = 120      # 한 번 밀 때 조향 모터 도는 시간
STEER_GAP  = 0.15     # 조향 명령 최소 간격(초)

def dz(v, d=DEADZONE):
    return 0.0 if abs(v) < d else (abs(v) - d) / (1 - d) * (1 if v > 0 else -1)

def scale(v, top):
    """-1..1 → 모터가 실제로 도는 구간(MIN_SPEED..top)으로 매핑"""
    if v == 0: return 0
    return int((MIN_SPEED + (top - MIN_SPEED) * abs(v)) * (1 if v > 0 else -1))

pygame.init(); pygame.joystick.init()
if pygame.joystick.get_count() == 0:
    print("❌ 게임패드가 안 보입니다.")
    print("   1) 패드 뒷면 스위치를 D(DirectInput)로")
    print("   2) AA 건전지 넣고 가운데 로지텍 버튼으로 전원 켜기")
    print("   3) 수신기를 뺐다 다시 꽂고 이 프로그램 재실행")
    sys.exit(1)

j = pygame.joystick.Joystick(0); j.init()
print(f"🎮 {j.get_name()} (축 {j.get_numaxes()}, 버튼 {j.get_numbuttons()})")

with Car(PORT) as car:
    print("왼쪽 스틱 = 전후진 / 오른쪽 스틱 좌우 = 조향 / B = 정지 / BACK = 종료")
    last_steer = 0.0
    try:
        while True:
            pygame.event.pump()
            n = j.get_numaxes()
            fwd   = -dz(j.get_axis(1)) if n > 1 else 0.0          # 위로 밀면 +
            steer =  dz(j.get_axis(3)) if n > 3 else (dz(j.get_axis(0)) if n > 0 else 0.0)

            boost = any(j.get_button(b) for b in (5, 0) if b < j.get_numbuttons())
            speed = scale(fwd, BOOST if boost else MAX_SPEED)
            car.drive(speed, speed)

            now = time.time()
            if steer and now - last_steer > STEER_GAP:
                car.steer(int(STEER_PWM * (1 if steer > 0 else -1)), STEER_MS)
                last_steer = now

            if j.get_numbuttons() > 1 and j.get_button(1):        # B
                car.stop()
            if j.get_numbuttons() > 6 and j.get_button(6):        # BACK
                break

            st = car.status
            print(f"\r구동 L={st['left']:4d} R={st['right']:4d}  조향={st['steer']:4d}  "
                  f"[스틱 전후 {fwd:+.2f} 조향 {steer:+.2f}]{' 부스트' if boost else '      '}",
                  end="", flush=True)
            time.sleep(0.05)
    except KeyboardInterrupt:
        pass
    finally:
        car.stop(); print("\n정지 후 종료")
