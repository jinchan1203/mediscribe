#!/usr/bin/env python3
"""맥북용 실시간 SLAM 지도 뷰어 — Jetson 의 scripts/mapping_joy.py 가 여는 HTTP(/state, /map.png)를
0.3초마다 받아 matplotlib 창에 그린다. (원본 mapping_graph.py 의 창과 같은 구성: 지도·궤적·로봇·방향)

  python3 mapview.py                       # yahboom.local:8765
  python3 mapview.py --host 172.20.10.3    # mDNS 안 되면 IP 로
  python3 mapview.py --view 6              # 로봇 주변 반경[m] (0 = 전체 맵 고정)
  창에서 q = 닫기,  f = 따라가기 켜고/끄기
"""
import argparse, io, json, math, time, urllib.request
import numpy as np
from PIL import Image
import matplotlib
import matplotlib.font_manager as _fm
for _f in ("AppleGothic", "Apple SD Gothic Neo", "NanumGothic", "Malgun Gothic"):   # 한글 폰트 (없으면 기본)
    if any(_f == f.name for f in _fm.fontManager.ttflist):
        matplotlib.rcParams["font.family"] = _f; break
matplotlib.rcParams["axes.unicode_minus"] = False
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation


def fetch(url, timeout=4.0):
    return urllib.request.urlopen(url, timeout=timeout).read()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="yahboom.local"); ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--view", type=float, default=8.0, help="로봇 주변 반경 m (0=전체)")
    ap.add_argument("--interval", type=int, default=300, help="갱신 주기 ms")
    ap.add_argument("--once", default=None, help="(시험용) 한 프레임을 이 PNG 로 저장하고 종료")
    ap.add_argument("--nav", action="store_true", help="자율주행 모드(nav_drive.py, 기본 포트 8766): 클릭=목표, s=정지, g=재개")
    a = ap.parse_args()
    if a.nav and a.port == 8765: a.port = 8766
    base = f"http://{a.host}:{a.port}"

    print(f"연결 중: {base} …", end="", flush=True)
    st = json.loads(fetch(base + "/state"))
    print(" OK")
    map_m, res, off = st["map_m"], st["res"], st["off"]

    fig, ax = plt.subplots(figsize=(9, 9))
    ax.set_aspect("equal")
    n = int(round(map_m / res))
    im = ax.imshow(np.full((n, n), 128, np.uint8), origin="lower", cmap="gray", vmin=0, vmax=255,
                   extent=[0, map_m, 0, map_m], interpolation="nearest")
    trail, = ax.plot([], [], "-", color="deepskyblue", lw=1.2, alpha=0.85)
    robot, = ax.plot([off], [off], "o", ms=10, color="red", zorder=5)
    quiv = ax.quiver([off], [off], [1], [0], color="orange", scale=12, zorder=6)
    pathl, = ax.plot([], [], "-", color="limegreen", lw=2.5, alpha=0.9, zorder=4)
    goalm, = ax.plot([], [], "*", ms=16, color="gold", zorder=7)
    lookm, = ax.plot([], [], "o", ms=6, color="cyan", zorder=7)
    ax.set_xlabel("x [m]"); ax.set_ylabel("y [m]")
    state = {"follow": a.view > 0, "ok": True, "last": time.time()}

    def post(path):
        try: urllib.request.urlopen(urllib.request.Request(base + path, method="POST"), timeout=3).read()
        except Exception as e: print("POST 실패:", e)

    def on_key(e):
        k = (e.key or "").lower()
        if k == "q": plt.close(fig)
        elif k == "f": state["follow"] = not state["follow"]
        elif a.nav and k == "s": post("/stop"); print("정지 요청")
        elif a.nav and k == "g": post("/go"); print("재개 요청")

    def on_click(e):
        if not a.nav or e.inaxes is not ax or e.xdata is None: return
        if e.button == 1:
            post(f"/goal?x={e.xdata:.3f}&y={e.ydata:.3f}"); print(f"목표 → ({e.xdata-off:+.2f}, {e.ydata-off:+.2f})")
        elif e.button == 3:
            post(f"/init?x={e.xdata:.3f}&y={e.ydata:.3f}"); print(f"초기위치 재설정 → ({e.xdata-off:+.2f}, {e.ydata-off:+.2f})")
    fig.canvas.mpl_connect("key_press_event", on_key)
    fig.canvas.mpl_connect("button_press_event", on_click)
    if a.nav:
        print("NAV 모드: 왼쪽 클릭=목표, 오른쪽 클릭=현재 위치 재설정, s=정지, g=재개, f=따라가기, q=닫기")

    def update(_):
        try:
            st = json.loads(fetch(base + "/state"))
            g = np.array(Image.open(io.BytesIO(fetch(base + "/map.png"))))[::-1]   # 서버가 뒤집어 보냄 → 원복
            if g.ndim == 3 and not state.get("rgb"):
                state["rgb"] = True; im.set_cmap(None)
            state["ok"] = True; state["last"] = time.time()
        except Exception as e:
            state["ok"] = False
            ax.set_title(f"연결 끊김 ({type(e).__name__}) — 마지막 수신 {time.time()-state['last']:.0f}s 전", color="red")
            return [im, trail, robot, quiv]
        im.set_data(g)
        px, py, th = st["pose"]
        tr = np.array(st["trail"]) if st["trail"] else np.zeros((0, 2))
        if len(tr): trail.set_data(tr[:, 0], tr[:, 1])
        robot.set_data([px], [py]); quiv.set_offsets([[px, py]]); quiv.set_UVC([math.cos(th)], [math.sin(th)])
        if a.nav:
            P = np.array(st.get("path") or [])
            pathl.set_data(P[:, 0], P[:, 1]) if len(P) else pathl.set_data([], [])
            g = st.get("goal"); goalm.set_data([g[0]], [g[1]]) if g else goalm.set_data([], [])
            la = st.get("lookahead"); lookm.set_data([la[0]], [la[1]]) if la else lookm.set_data([], [])
        if state["follow"] and a.view > 0:
            ax.set_xlim(px - a.view, px + a.view); ax.set_ylim(py - a.view, py + a.view)
        else:
            ax.set_xlim(0, map_m); ax.set_ylim(0, map_m)
        if a.nav:
            cl = st.get("clear"); cl = "-" if cl is None else f"{cl:.2f}m"
            ax.set_title(f"[{st['mode']}{'' if st.get('enabled', True) else ' STOP'}]  신뢰 {st['conf']:.2f} lost {st['lost']}  "
                         f"PWM {st['pwm']} 조향 {st['steer']:+d}  정면 {cl}  헤딩오차 {math.degrees(st['hdg_err']):+.0f}°  "
                         f"요레이트 {math.degrees(st['yaw_rate']):+.0f}°/s\n"
                         f"pose=({px-off:+.2f}, {py-off:+.2f}, {math.degrees(th):+.0f}°)  {st['hz']:.1f}Hz {st['ms']:.0f}ms   "
                         f"[클릭=목표 · s 정지 · g 재개 · q 닫기]", color="black")
            return [im, trail, robot, quiv, pathl, goalm, lookm]
        dm = "●RB" if st["deadman"] else "○RB"
        ax.set_title(f"graph SLAM  KF={st['kf']} 루프={st['loops']}  스캔 {st['scans']} {st['hz']:.1f}Hz {st['ms']:.0f}ms  "
                     f"신뢰 {st.get('conf', 0):.2f} 스킵 {st.get('skip', 0)}\n"
                     f"{dm} PWM {st['pwm']:+d} (max {st['vmax']}) 조향 {st['steer']:+d}   "
                     f"pose=({px-off:+.2f}, {py-off:+.2f}, {math.degrees(th):+.0f}°)"
                     + ("   [q 닫기 · f 따라가기]" if not a.once else ""), color="black")
        return [im, trail, robot, quiv]

    if a.once:
        update(0); fig.savefig(a.once, dpi=80); print("저장:", a.once); return
    anim = FuncAnimation(fig, update, interval=a.interval, blit=False, cache_frame_data=False)
    plt.show()


if __name__ == "__main__":
    main()
