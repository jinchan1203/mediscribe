#!/usr/bin/env python3
"""
저장 지도 위 자율주행 — MediScribe 차량(아두이노 v3, 엔코더 없음, 조향 개루프 DC모터) + STL-27L. SSH 헤드리스.

스캔(10Hz)마다:
  라이다 → 저장맵 scan-to-map 정합(측위; 매핑의 라이다 오도메와 같은 방식, 신뢰도 게이트·자동복구)
  → 목표까지 A*(코스트맵) 경로 → 전방 주시점 헤딩오차 → 목표 요레이트
  → 측위로 잰 실제 요레이트와 비교해 조향 펄스(좌/우) [각도 센서 없이 직진 복원]
  → 구동 PWM (정면 장애물 거리로 감속/정지)

목표: 맥북 뷰어 `mapview.py --nav` 에서 지도 클릭(POST /goal) 또는 브라우저. 초기 위치: --init x y (맵 m, 기본 매핑 시작점)
  + 시작 시 헤딩 360° 스윕 + 반경 탐색으로 자동 보정.
정지: 조이스틱 B/Back, 뷰어 s 키(POST /stop), Ctrl+C. 재개: 뷰어 g 키(POST /go).

실행(2.0 디렉터리):  python3 scripts/nav_drive.py --map out/joymap_<ts>.npz [--pwm 130]
"""
import os, sys, io, time, math, glob, json, select, struct, argparse, threading
from urllib.parse import urlparse, parse_qs
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.normpath(os.path.join(HERE, ".."))
sys.path.insert(0, ROOT)
from pickr.hal.lidar_stl27l import STL27L                      # noqa: E402
from pickr.hal.lidar import scan_to_rays                        # noqa: E402
from pickr.nav.mapping import OccupancyGridMap                  # noqa: E402
from pickr.nav.scan_match import ScanMatcher                    # noqa: E402
from pickr.nav.costmap import Costmap                           # noqa: E402
from pickr.nav.astar import astar                               # noqa: E402
from pickr.nav.relocalize import heading_sweep, local_search, WIDE_COARSE    # noqa: E402
from pickr.core.se2 import rel as _rel, compose as _compose, wrap as _wrap   # noqa: E402
from pickr.config import OCC_THRESH, MAX_RANGE, MATCH_DECIM     # noqa: E402

EV = struct.Struct("IhBB")
AX_LX, AX_LT, AX_RT = 0, 2, 5
BT_A, BT_B, BT_Y, BT_RB, BT_BACK, BT_START = 0, 1, 3, 5, 6, 7


def find_js():
    hits = [h for h in sorted(glob.glob("/dev/input/by-id/*-joystick")) if "event" not in h] or sorted(glob.glob("/dev/input/js*"))
    return hits[0] if hits else None


def densify(path, step=0.1):
    out = []
    for (x0, y0), (x1, y1) in zip(path, path[1:]):
        d = math.hypot(x1 - x0, y1 - y0); n = max(1, int(d / step))
        for i in range(n):
            t = i / n; out.append((x0 + (x1 - x0) * t, y0 + (y1 - y0) * t))
    out.append(tuple(path[-1])); return out


class Nav:
    def __init__(self, a):
        self.a = a
        self.lock = threading.Lock()
        gm = OccupancyGridMap.load(a.map)
        self.gm, self.res = gm, gm.res
        self.map_m = gm.W * gm.res
        self.matcher = ScanMatcher(gm); self.matcher.update_field()
        self.wall = gm.prob() > OCC_THRESH
        self.cm = Costmap(self.wall, gm.res, robot_radius_m=a.radius, inflation_m=a.inflation)
        self.pose = np.array([a.init[0], a.init[1], math.radians(a.init[2])], float)
        self.prev_pose = self.pose.copy()
        self.conf = 0.0; self.lost = 0; self.yaw_rate = 0.0; self.speed_est = 0.0
        self.goal = None; self.path = []; self.path_t = 0.0; self.lookahead = None
        self.mode = "idle"        # idle / drive / blocked / arrived / noplan / lost
        self.enabled = True       # /stop → False, /go → True
        self.pwm = 0; self.steer = 0; self.clear = float("inf"); self.hdg_err = 0.0
        self.n_scan = 0; self.ms = 0.0; self.hz = 0.0; self.err = ""
        self.trail = []
        self._png = b""

    # ---------- 측위 ----------
    def init_localize(self, pts):
        """--init 위치에서 헤딩 스윕 → 반경 탐색 → 정밀 정합."""
        g = tuple(self.pose)
        cands = []
        # A) 추정 포즈 주변 넓은 창(±0.5m/±25°) 정합 — 초기 추정이 대략 맞을 때 가장 정확
        pa = self.matcher.match(g, pts, coarse=WIDE_COARSE); cands.append(("guess", pa))
        # B) 헤딩 스윕 → 지역 격자 탐색 — 초기 추정이 틀렸을 때
        pb, _ = heading_sweep(self.matcher, g, pts)
        pb, _ = local_search(self.matcher, pb, pts, radius_m=self.a.init_radius, step_m=0.2, head_step_deg=10.0)
        pb = self.matcher.match(tuple(pb), pts); cands.append(("search", pb))
        scored = [(self.matcher._score(p[0], p[1], p[2], pts) / max(1, len(pts)), name, p) for name, p in cands]
        scored.sort(reverse=True)
        self.init_report = " | ".join(f"{n}:({p[0]-self.map_m/2:+.2f},{p[1]-self.map_m/2:+.2f},{math.degrees(p[2]):+.0f}°) {c:.2f}" for c, n, p in scored)
        c, _, p = scored[0]
        self.pose = np.array(p, float); self.prev_pose = self.pose.copy(); self.conf = float(c)
        return self.conf

    def conf_at(self, x, y, th):
        pts = getattr(self, "last_pts", None)
        if pts is None or len(pts) == 0: return None
        return self.matcher._score(x, y, th, pts) / len(pts)

    def localize(self, pts, dt):
        moving = self.pwm != 0
        if moving:
            d = _rel(self.prev_pose, self.pose) * 0.5; d[2] = max(-0.15, min(0.15, d[2]))
            pred = _compose(self.pose, d)
        else:
            pred = self.pose.copy()
        self.prev_pose = self.pose.copy()
        m = np.array(self.matcher.match(tuple(pred), pts), float)
        c = self.matcher._score(m[0], m[1], m[2], pts) / max(1, len(pts))
        if c >= self.a.min_conf:
            dth = _wrap(m[2] - self.pose[2]); dxy = math.hypot(m[0] - self.pose[0], m[1] - self.pose[1])
            if dt > 0:
                self.yaw_rate = 0.6 * self.yaw_rate + 0.4 * (dth / dt)
                self.speed_est = 0.6 * self.speed_est + 0.4 * (dxy / dt)
            self.pose = m; self.lost = 0
        else:
            self.pose = np.array(pred, float); self.lost += 1
            if self.lost % 10 == 0:                          # 1초마다 복구 시도
                lvl = 1 if self.lost < 30 else 2
                p, _ = heading_sweep(self.matcher, tuple(self.pose), pts) if lvl == 1 else \
                    local_search(self.matcher, tuple(self.pose), pts, radius_m=2.0, step_m=0.25, head_step_deg=10.0)
                p = self.matcher.match(tuple(p), pts)
                rc = self.matcher._score(p[0], p[1], p[2], pts) / max(1, len(pts))
                if rc >= max(self.a.min_conf, 0.2):
                    self.pose = np.array(p, float); self.lost = 0; c = rc
        self.conf = float(c)
        if not self.trail or math.hypot(self.trail[-1][0] - self.pose[0], self.trail[-1][1] - self.pose[1]) > 0.05:
            self.trail.append((float(self.pose[0]), float(self.pose[1])))

    # ---------- 계획 ----------
    def plan(self):
        if self.goal is None: return
        p = astar(self.cm, (self.pose[0], self.pose[1]), self.goal)
        self.path = densify(p) if p else []
        self.path_t = time.time()

    # ---------- 제어 (한 스캔) ----------
    def control(self, hits, car, manual=False):
        a = self.a
        if manual:
            ahead = hits[(hits[:, 0] > 0.05) & (np.abs(hits[:, 1]) < a.halfw)]
            self.clear = float(ahead[:, 0].min()) if len(ahead) else float("inf")
            self.mode = "manual"; return
        # 정면 클리어런스 (로봇프레임 x 전방, y 좌)
        ahead = hits[(hits[:, 0] > 0.05) & (np.abs(hits[:, 1]) < a.halfw)]
        self.clear = float(ahead[:, 0].min()) if len(ahead) else float("inf")

        if not self.enabled or self.goal is None or self.lost > 0:
            self.pwm = 0; self.steer = 0
            if self.lost > 0: self.mode = "lost"
            elif self.goal is None and self.mode not in ("arrived",): self.mode = "idle"
            if car: car.drive(0)
            return
        gd = math.hypot(self.goal[0] - self.pose[0], self.goal[1] - self.pose[1])
        if gd < a.goal_tol:
            self.mode = "arrived"; self.goal = None; self.path = []; self.lookahead = None
            self.pwm = 0; self.steer = 0
            if car: car.drive(0)
            return
        if not self.path or time.time() - self.path_t > a.replan:
            self.plan()
        if not self.path:
            self.mode = "noplan"; self.pwm = 0; self.steer = 0
            if car: car.drive(0)
            return
        # 전방 주시점: 가장 가까운 경로점부터 lookahead 거리 이상 떨어진 첫 점
        P = np.asarray(self.path); dd = np.hypot(P[:, 0] - self.pose[0], P[:, 1] - self.pose[1])
        i0 = int(dd.argmin()); tgt = P[-1]
        for i in range(i0, len(P)):
            if dd[i] >= a.lookahead: tgt = P[i]; break
        self.lookahead = (float(tgt[0]), float(tgt[1]))
        e = _wrap(math.atan2(tgt[1] - self.pose[1], tgt[0] - self.pose[0]) - self.pose[2])
        self.hdg_err = float(e)

        # 속도: 장애물·헤딩오차·목표 근접에 따라
        if self.clear < a.stop_dist:
            self.mode = "blocked"; pwm = 0
        else:
            self.mode = "drive"
            pwm = a.pwm
            if self.clear < a.slow_dist: pwm = a.pwm_min + (a.pwm - a.pwm_min) * (self.clear - a.stop_dist) / max(1e-3, a.slow_dist - a.stop_dist)
            if abs(e) > math.radians(45): pwm = min(pwm, a.pwm_min + 10)   # 크게 꺾을 땐 천천히
            if gd < 1.0: pwm = min(pwm, a.pwm_min + 15)
            pwm = int(max(a.pwm_min, pwm))
        self.pwm = pwm

        # 조향: 요레이트 서보 (조향각 센서 없음 → 측위 Δθ 로 잰 실제 회전속도를 목표에 맞춤)
        steer = 0
        if pwm > 0 and self.speed_est > 0.03:
            w_d = max(-a.w_max, min(a.w_max, a.k_e * e))
            err = w_d - self.yaw_rate
            if err > a.rate_thr: steer = -a.steer_pwm        # 좌회전 필요 → S − (S + = 오른쪽)
            elif err < -a.rate_thr: steer = +a.steer_pwm
        elif pwm > 0:                                          # 출발 직후(요레이트 아직 없음): 헤딩오차로 직접
            if e > math.radians(20): steer = -a.steer_pwm
            elif e < -math.radians(20): steer = +a.steer_pwm
        self.steer = steer
        if car:
            car.drive(pwm)
            if steer: car.steer_pulse(steer, a.pulse_ms)

    # ---------- 뷰어용 ----------
    def state_json(self):
        with self.lock:
            d = {"pose": [float(v) for v in self.pose], "conf": self.conf, "lost": self.lost, "mode": self.mode,
                 "enabled": self.enabled, "goal": self.goal, "path": self.path[::3] if self.path else [],
                 "lookahead": self.lookahead, "clear": (None if math.isinf(self.clear) else self.clear),
                 "yaw_rate": self.yaw_rate, "speed": self.speed_est, "hdg_err": self.hdg_err,
                 "pwm": self.pwm, "steer": self.steer, "scans": self.n_scan, "hz": self.hz, "ms": self.ms,
                 "trail": self.trail[-2000:], "err": self.err, "off": self.map_m / 2, "res": self.res, "map_m": self.map_m,
                 "t": time.time()}
        return json.dumps(d).encode()

    def map_png(self):
        if self._png: return self._png
        g = (255 * (1.0 - self.gm.prob())).astype(np.uint8)
        img = np.stack([g, g, g], -1)
        lethal = self.cm.grid & ~self.wall
        img[lethal] = (255, 205, 205)                    # 치명존(로봇 중심 진입 불가) 연분홍
        from PIL import Image
        buf = io.BytesIO(); Image.fromarray(img[::-1], "RGB").save(buf, "PNG", compress_level=1)
        self._png = buf.getvalue(); return self._png


INDEX_HTML = """<!doctype html><meta charset=utf-8><title>MediScribe NAV</title>
<style>body{margin:0;background:#111;color:#ddd;font:14px monospace}#s{padding:6px 10px;white-space:pre}canvas{display:block;margin:auto;background:#777;cursor:crosshair}</style>
<div id=s>연결 중…</div><canvas id=c></canvas>
<script>
const c=document.getElementById('c'),ctx=c.getContext('2d'),S=document.getElementById('s');let img=new Image(),st=null,k=1;
img.src='/map.png';
async function tick(){try{st=await (await fetch('/state?'+Date.now())).json();
 S.textContent=`[${st.mode}${st.enabled?'':' STOP'}] 신뢰 ${st.conf.toFixed(2)} lost ${st.lost} | PWM ${st.pwm} 조향 ${st.steer} | 정면 ${st.clear==null?'-':st.clear.toFixed(2)+'m'} 헤딩오차 ${(st.hdg_err*180/Math.PI).toFixed(0)}° 요레이트 ${(st.yaw_rate*180/Math.PI).toFixed(0)}°/s v ${st.speed.toFixed(2)} | ${st.hz.toFixed(1)}Hz ${st.ms.toFixed(0)}ms\\n클릭=목표  (${(st.pose[0]-st.off).toFixed(2)}, ${(st.pose[1]-st.off).toFixed(2)}, ${(st.pose[2]*180/Math.PI).toFixed(0)}°)`;
 draw();}catch(e){S.textContent='연결 끊김: '+e}}
function draw(){if(!img.complete)return;const sc=Math.min((innerWidth-4)/img.width,(innerHeight-60)/img.height);c.width=img.width*sc;c.height=img.height*sc;k=sc/st.res;const H=c.height;
 ctx.drawImage(img,0,0,c.width,c.height);
 ctx.strokeStyle='#1e90ff';ctx.lineWidth=2;ctx.beginPath();st.trail.forEach((p,i)=>{i?ctx.lineTo(p[0]*k,H-p[1]*k):ctx.moveTo(p[0]*k,H-p[1]*k)});ctx.stroke();
 ctx.strokeStyle='#2c2';ctx.lineWidth=3;ctx.beginPath();st.path.forEach((p,i)=>{i?ctx.lineTo(p[0]*k,H-p[1]*k):ctx.moveTo(p[0]*k,H-p[1]*k)});ctx.stroke();
 if(st.goal){ctx.fillStyle='#fd0';ctx.beginPath();ctx.arc(st.goal[0]*k,H-st.goal[1]*k,7,0,7);ctx.fill();}
 if(st.lookahead){ctx.fillStyle='#0ff';ctx.beginPath();ctx.arc(st.lookahead[0]*k,H-st.lookahead[1]*k,4,0,7);ctx.fill();}
 const x=st.pose[0]*k,y=H-st.pose[1]*k;ctx.fillStyle='#f33';ctx.beginPath();ctx.arc(x,y,6,0,7);ctx.fill();
 ctx.strokeStyle='#fa0';ctx.lineWidth=3;ctx.beginPath();ctx.moveTo(x,y);ctx.lineTo(x+Math.cos(st.pose[2])*18,y-Math.sin(st.pose[2])*18);ctx.stroke();}
c.onclick=ev=>{if(!st)return;const x=ev.offsetX/k,y=(c.height-ev.offsetY)/k;fetch(`/goal?x=${x}&y=${y}`,{method:'POST'});};
document.onkeydown=ev=>{if(ev.key=='s')fetch('/stop',{method:'POST'});if(ev.key=='g')fetch('/go',{method:'POST'});};
setInterval(tick,300);tick();
</script>"""


def start_http(nav, port):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a): pass
        def _send(self, body, ctype):
            self.send_response(200); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store"); self.end_headers(); self.wfile.write(body)
        def do_GET(self):
            p = urlparse(self.path).path
            if p == "/state": self._send(nav.state_json(), "application/json")
            elif p == "/conf":
                q = parse_qs(urlparse(self.path).query); x = float(q["x"][0]); y = float(q["y"][0]); th = math.radians(float(q["deg"][0]))
                with nav.lock:
                    c = nav.conf_at(x, y, th); m = nav.matcher.match((x, y, th), nav.last_pts, coarse=WIDE_COARSE) if nav.last_pts is not None else None
                    cm_ = nav.conf_at(*m) if m else None
                self._send(json.dumps({"conf_at": c, "refined": (list(m) if m else None), "conf_refined": cm_}).encode(), "application/json")
            elif p == "/map.png": self._send(nav.map_png(), "image/png")
            elif p == "/scan":
                # 로봇프레임(현재 config 오프셋 적용) 8방향 최근접 거리 — 0°=차 정면이어야 함
                with nav.lock: pts = None if nav.last_pts is None else nav.last_pts.copy()
                out = {}
                if pts is not None and len(pts):
                    q = parse_qs(urlparse(self.path).query); sec = float(q.get("sector", ["45"])[0])
                    ang = np.degrees(np.arctan2(pts[:, 1], pts[:, 0])); dist = np.hypot(pts[:, 0], pts[:, 1])
                    k = -180.0
                    while k < 180:
                        m = (((ang - k + 180) % 360) - 180 > -sec / 2) & (((ang - k + 180) % 360) - 180 <= sec / 2)
                        out[str(int(k))] = (round(float(dist[m].min()), 2) if m.any() else None); k += sec
                    i = int(dist.argmin()); out["nearest"] = {"deg": round(float(ang[i])), "m": round(float(dist[i]), 2)}
                    # 정면 원뿔(±40°, 0.5~2.5m) 안 최근접점의 정확한 각도 — 사람이 정면에 서 있을 때 오프셋 잔차
                    f = (np.abs(ang) < 40) & (dist > 0.5) & (dist < 2.5)
                    if f.any():
                        j = int(np.argmin(np.where(f, dist, 1e9))); out["front_obj"] = {"deg": round(float(ang[j]), 1), "m": round(float(dist[j]), 2)}
                self._send(json.dumps(out).encode(), "application/json")
            elif p in ("/", "/index.html"): self._send(INDEX_HTML.encode(), "text/html; charset=utf-8")
            else: self.send_response(404); self.end_headers()
        def do_POST(self):
            u = urlparse(self.path); q = parse_qs(u.query); p = u.path
            with nav.lock:
                if p == "/goal":
                    nav.goal = (float(q["x"][0]), float(q["y"][0])); nav.path = []; nav.mode = "drive"; nav.enabled = True
                elif p == "/stop": nav.enabled = False
                elif p == "/go": nav.enabled = True
                elif p == "/init":
                    nav.pose = np.array([float(q["x"][0]), float(q["y"][0]), math.radians(float(q.get("deg", ["0"])[0]))]); nav.lost = 1; nav.need_init = True
                else: self.send_response(404); self.end_headers(); return
            self._send(b"OK", "text/plain")
    srv = ThreadingHTTPServer(("0.0.0.0", port), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--map", required=True); ap.add_argument("--port", default=None); ap.add_argument("--lidar", default=None)
    ap.add_argument("--init", type=float, nargs=3, default=None, metavar=("X", "Y", "DEG"), help="초기 포즈(맵 m, deg). 기본 맵 중앙(매핑 시작점) 0°")
    ap.add_argument("--init-radius", type=float, default=1.5, help="시작 시 위치 탐색 반경 [m]")
    ap.add_argument("--pwm", type=int, default=130); ap.add_argument("--pwm-min", type=int, default=100)
    ap.add_argument("--steer-pwm", type=int, default=255); ap.add_argument("--pulse-ms", type=int, default=80)
    ap.add_argument("--lookahead", type=float, default=0.6); ap.add_argument("--goal-tol", type=float, default=0.35)
    ap.add_argument("--stop-dist", type=float, default=0.45); ap.add_argument("--slow-dist", type=float, default=1.0)
    ap.add_argument("--halfw", type=float, default=0.20, help="정면 판정 반폭 [m] (차 폭/2 + 여유)")
    ap.add_argument("--radius", type=float, default=0.22, help="코스트맵 로봇 반지름 [m]"); ap.add_argument("--inflation", type=float, default=0.25)
    ap.add_argument("--k-e", type=float, default=1.5, help="헤딩오차→목표 요레이트 이득 [1/s]")
    ap.add_argument("--w-max", type=float, default=0.8, help="목표 요레이트 상한 [rad/s]"); ap.add_argument("--rate-thr", type=float, default=0.25, help="요레이트 오차 문턱 [rad/s]")
    ap.add_argument("--replan", type=float, default=2.0); ap.add_argument("--min-conf", type=float, default=0.18)
    ap.add_argument("--min-range", type=float, default=0.15); ap.add_argument("--decim", type=int, default=MATCH_DECIM)
    ap.add_argument("--http", type=int, default=8766); ap.add_argument("--no-motor", action="store_true")
    ap.add_argument("--max-manual", type=int, default=140, help="조이스틱 수동(RB) 최대 PWM")
    a = ap.parse_args()
    if a.init is None:
        _g = OccupancyGridMap.load(a.map); a.init = (_g.W * _g.res / 2, _g.H * _g.res / 2, 0.0)   # 기본: 매핑 시작점
    nav = Nav(argparse.Namespace(**vars(a)))
    nav.need_init = True

    js = find_js(); fd = os.open(js, os.O_RDONLY | os.O_NONBLOCK) if js else None
    car = None
    if not a.no_motor:
        from pickr.hal.arduino_v3 import ArduinoV3
        car = ArduinoV3(a.port)
        if not car.ping(): sys.exit("아두이노 v3 응답 없음")
        print(f"아두이노 {car.port} OK")
    lidar = STL27L(a.lidar)
    if lidar.wait_scan(3.0) is None: sys.exit("라이다 스캔 없음")
    print(f"라이다 {lidar.port} OK | 지도 {a.map} ({nav.map_m:.0f}m, {nav.res}m/셀) | 치명존 반지름 {a.radius}m")
    if a.http:
        start_http(nav, a.http); import socket
        print(f"뷰어: python3 mapview.py --nav --host {socket.gethostname()}.local --port {a.http}   또는 http://{socket.gethostname()}.local:{a.http}")
    log = open(a.map.replace(".npz", "") + time.strftime("_nav_%Y%m%d_%H%M%S.log"), "a")

    t_prev = None; last_status = ""; t_log = 0
    axes = [0.0] * 8; btn = [0] * 12; vman = a.max_manual
    try:
        for scan in lidar.iter_scans():
            t0 = time.time()
            if fd is not None:
                try:
                    while True:
                        d = os.read(fd, EV.size)
                        if len(d) < EV.size: break
                        _, val, typ, num = EV.unpack(d); typ &= 0x7F
                        if typ == 2 and num < 8: axes[num] = val / 32767.0
                        elif typ == 1 and num < 12:
                            btn[num] = val
                            if val and num == BT_BACK: print("\n조이스틱 Back → 종료"); raise KeyboardInterrupt
                            if val and num == BT_B:
                                with nav.lock: nav.enabled = False; nav.goal = None; nav.path = []
                                print("\n조이스틱 B → 자율주행 정지(목표 해제)")
                            if val and num == BT_Y: vman = min(255, vman + 20)
                            if val and num == BT_A: vman = max(60, vman - 20)
                except BlockingIOError: pass
            manual = bool(btn[BT_RB])
            if manual and car:
                rt = (axes[AX_RT] + 1) / 2; lt = (axes[AX_LT] + 1) / 2
                mp = int(round((rt - lt) * vman))
                if abs(mp) < 15: mp = 0
                elif abs(mp) < 90: mp = 90 if mp > 0 else -90
                lx = axes[AX_LX]; ms_ = (255 if lx > 0 else -255) if abs(lx) > 0.15 else 0
                car.drive(mp)
                if ms_: car.steer_pulse(ms_, 150)
                with nav.lock: nav.pwm, nav.steer = mp, ms_
            angs, rngs = scan_to_rays(scan)
            keep = rngs >= a.min_range; angs, rngs = angs[keep], rngs[keep]
            if len(angs) < 50: continue
            m = rngs < MAX_RANGE - 1e-3
            hits = np.column_stack([rngs[m] * np.cos(angs[m]), rngs[m] * np.sin(angs[m])])
            pts = hits[::a.decim]
            with nav.lock:
                nav.last_pts = pts
                if nav.need_init:
                    c = nav.init_localize(pts); nav.need_init = False; nav.lost = 0 if c >= a.min_conf else 1
                    print(f"초기 측위 후보: {nav.init_report}  → 채택 신뢰 {c:.2f}")
                else:
                    nav.localize(pts, (t0 - t_prev) if t_prev else 0.1)
                nav.control(hits, car, manual=manual)
                nav.n_scan += 1; nav.ms = (time.time() - t0) * 1000
                if t_prev: nav.hz = 0.8 * nav.hz + 0.2 / max(1e-3, t0 - t_prev)
                st = (f"\r[{nav.mode}{'' if nav.enabled else ' STOP'}] 신뢰 {nav.conf:.2f} lost {nav.lost} | PWM {nav.pwm:4d} 조향 {nav.steer:+4d} | "
                      f"정면 {nav.clear:4.2f}m 헤딩오차 {math.degrees(nav.hdg_err):+4.0f}° 요레이트 {math.degrees(nav.yaw_rate):+4.0f}°/s | "
                      f"pose ({nav.pose[0]-nav.map_m/2:+5.2f},{nav.pose[1]-nav.map_m/2:+5.2f},{math.degrees(nav.pose[2]):+4.0f}°) {nav.hz:4.1f}Hz {nav.ms:3.0f}ms   ")
            t_prev = t0
            if st != last_status: print(st, end="", flush=True); last_status = st
            if t0 - t_log > 2.0:
                t_log = t0; log.write(time.strftime("%H:%M:%S ") + st.strip() + "\n"); log.flush()
    except KeyboardInterrupt:
        print("\n종료")
    finally:
        if car:
            try: car.close()
            except Exception: pass
        lidar.close(); log.close()
        if fd is not None: os.close(fd)


if __name__ == "__main__":
    main()
