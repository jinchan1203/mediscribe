# 게임패드 HID 패킷 구조 (이전 세션 분석)

로지텍 F710 등 게임패드의 raw HID 패킷 바이트 배열.
※ 현재 `joy_teleop.py`는 pygame으로 추상화해서 읽으므로 이 표는 직접 쓰지 않음.
   raw HID로 직접 파싱해야 할 때(예: Jetson에서 pygame 없이) 참고.

```
Byte 0:  00 (헤더, 항상 0)
Byte 1:  14 (패킷 길이 = 20)
Byte 2:  버튼 비트마스크 1 (방향키 + 시작/뒤로 + 스틱 클릭)
  - 0x01 = 위
  - 0x02 = 아래
  - 0x04 = 왼쪽
  - 0x08 = 오른쪽
Byte 3:  버튼 비트마스크 2 (A/B/X/Y, LB/RB)
  - 0x10 = LB
  - 0x20 = RB
  - 0x40 = A 비슷
  - 0x80 = B 비슷
Byte 4:  LT 트리거 (0~255, 0=안 누름)
Byte 5:  RT 트리거
Byte 6-7:   좌측 스틱 X (16비트, 중앙=0x0080)
Byte 8-9:   좌측 스틱 Y (16비트, 중앙=0x0080)
Byte 10-11: 우측 스틱 X (16비트, 중앙=0x0080)
Byte 12-13: 우측 스틱 Y (16비트, 중앙=0x0080)
```

## 차량 배선 (확정)

| 드라이버 | 역할 | PWM(IN1) | DIR(IN2) | 점퍼선 색 |
|---|---|---|---|---|
| #1 | 조향 | D2 | D3 | 검정 / 흰색 |
| #2 | 좌측 구동 | D4 | D5 | 노랑 / 청록 |
| #3 | 우측 구동 | D6 | D7 | 연보라 / 보라 |

전원: 아두이노 5V, GND 공급. 모터 전원은 차체 배터리 (스위치 확인 필수).
주의: IN2 쪽(D3 흰색, D7 보라) 접촉 불량이 반복 발생 → 고정 권장.

## 기타 (Jetson locale 설정)

```bash
sudo apt install locales -y
sudo locale-gen en_US en_US.UTF-8
sudo update-locale LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8
export LANG=en_US.UTF-8
```
