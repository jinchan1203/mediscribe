// MEDISCRIBE CAR v3 — Arduino Mega 2560
// 드라이버 3개 (IN1/IN2 방식, 각 2선): 조향 D2/D3, 좌측 구동 D4/D5, 우측 구동 D6/D7
// 시리얼 115200. 명령은 줄바꿈으로 끝냄.
//   V <left> <right>    구동 속도 -255..255 (좌/우 개별)
//   D <speed>           구동 속도 양쪽 동일
//   S <pwm> [ms]        조향 모터: pwm -255..255 (+우회전/-좌회전), ms 동안만 회전 후 정지 (기본 200)
//   X                   전부 정지
//   T <L|R|S> <1|-1> [pwm] [ms]   테스트 펄스 (기본 pwm 150, 500ms)
//   C <L|R|S> <0|1>     극성 반전 플래그 설정 (배선 방향 보정)
//   ?                   설정/도움말 출력
// 안전: 구동 명령이 WATCHDOG_MS 동안 안 오면 구동 모터 자동 정지. 조향은 항상 시간 제한.
// 상태줄 100ms마다: "ST <left> <right> <steer> <millis>"

const uint8_t STEER_IN1 = 2, STEER_IN2 = 3;
const uint8_t LEFT_IN1  = 4, LEFT_IN2  = 5;
const uint8_t RIGHT_IN1 = 6, RIGHT_IN2 = 7;

// 테스트 결과 기반 극성: IN1에 PWM, IN2 LOW 일 때 좌/우 구동은 전진, 조향은 우회전이었음 → 반전 없음
bool invL = false, invR = false, invS = false;

const unsigned long WATCHDOG_MS = 500;
const unsigned long STATUS_MS   = 100;
const unsigned long STEER_MAX_MS = 1500;

int curL = 0, curR = 0, curS = 0;
unsigned long lastDriveCmd = 0, steerStopAt = 0, lastStatus = 0;
char buf[48]; uint8_t blen = 0;

void driveMotor(uint8_t in1, uint8_t in2, int pwm, bool inv) {
  if (inv) pwm = -pwm;
  pwm = constrain(pwm, -255, 255);
  if (pwm > 0)      { analogWrite(in1, pwm); digitalWrite(in2, LOW); }
  else if (pwm < 0) { digitalWrite(in1, LOW); analogWrite(in2, -pwm); }
  else              { digitalWrite(in1, LOW); digitalWrite(in2, LOW); }
}

void setDrive(int l, int r) {
  curL = constrain(l, -255, 255); curR = constrain(r, -255, 255);
  driveMotor(LEFT_IN1, LEFT_IN2, curL, invL);
  driveMotor(RIGHT_IN1, RIGHT_IN2, curR, invR);
  lastDriveCmd = millis();
}

void setSteer(int pwm, unsigned long ms) {
  curS = constrain(pwm, -255, 255);
  driveMotor(STEER_IN1, STEER_IN2, curS, invS);
  steerStopAt = millis() + min(ms, STEER_MAX_MS);
}

void stopAll() { setDrive(0, 0); curS = 0; driveMotor(STEER_IN1, STEER_IN2, 0, false); steerStopAt = 0; }

void printHelp() {
  Serial.println(F("MEDISCRIBE CAR v3 | V l r | D s | S pwm [ms] | X | T L|R|S dir [pwm] [ms] | C L|R|S 0|1 | ?"));
  Serial.print(F("inv L/R/S = ")); Serial.print(invL); Serial.print(invR); Serial.println(invS);
}

void handle(char *line) {
  char cmd = toupper(line[0]);
  char *args = line + 1;
  if (cmd == 'V') { int l = 0, r = 0; sscanf(args, "%d %d", &l, &r); setDrive(l, r); Serial.println(F("OK")); }
  else if (cmd == 'D') { int s = 0; sscanf(args, "%d", &s); setDrive(s, s); Serial.println(F("OK")); }
  else if (cmd == 'S') { int p = 0; long ms = 200; sscanf(args, "%d %ld", &p, &ms); setSteer(p, ms); Serial.println(F("OK")); }
  else if (cmd == 'X') { stopAll(); Serial.println(F("OK STOP")); }
  else if (cmd == 'T') {
    char m = ' '; int dir = 1, pwm = 150; long ms = 500;
    sscanf(args, " %c %d %d %ld", &m, &dir, &pwm, &ms); m = toupper(m);
    int v = (dir < 0 ? -pwm : pwm);
    if (m == 'L') { setDrive(v, 0); delay(ms); setDrive(0, 0); }
    else if (m == 'R') { setDrive(0, v); delay(ms); setDrive(0, 0); }
    else if (m == 'S') { setSteer(v, ms); delay(ms); setSteer(0, 0); }
    Serial.print(F("OK T ")); Serial.print(m); Serial.print(' '); Serial.println(v);
  }
  else if (cmd == 'C') {
    char m = ' '; int v = 0; sscanf(args, " %c %d", &m, &v); m = toupper(m);
    if (m == 'L') invL = v; else if (m == 'R') invR = v; else if (m == 'S') invS = v;
    printHelp();
  }
  else if (cmd == '?') printHelp();
  else { Serial.print(F("ERR ")); Serial.println(line); }
}

void setup() {
  uint8_t pins[] = {STEER_IN1, STEER_IN2, LEFT_IN1, LEFT_IN2, RIGHT_IN1, RIGHT_IN2};
  for (uint8_t p : pins) { pinMode(p, OUTPUT); digitalWrite(p, LOW); }
  Serial.begin(115200);
  Serial.println(F("MEDISCRIBE CAR v3 READY"));
  printHelp();
}

void loop() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n' || c == '\r') { if (blen) { buf[blen] = 0; handle(buf); blen = 0; } }
    else if (blen < sizeof(buf) - 1) buf[blen++] = c;
  }
  unsigned long now = millis();
  if ((curL || curR) && now - lastDriveCmd > WATCHDOG_MS) { setDrive(0, 0); Serial.println(F("WD STOP")); }
  if (curS && now >= steerStopAt) { curS = 0; driveMotor(STEER_IN1, STEER_IN2, 0, false); }
  if (now - lastStatus >= STATUS_MS) {
    lastStatus = now;
    Serial.print(F("ST ")); Serial.print(curL); Serial.print(' '); Serial.print(curR);
    Serial.print(' '); Serial.print(curS); Serial.print(' '); Serial.println(now);
  }
}
