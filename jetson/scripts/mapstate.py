#!/usr/bin/env python3
"""매핑 상태 한 줄 요약: python3 tools/mapstate.py"""
import json, math, urllib.request, glob, os
d = json.load(urllib.request.urlopen("http://localhost:8765/state", timeout=3)); o = d["off"]
print(f"KF {d['kf']}  루프 {d['loops']}  스캔 {d['scans']} {d['hz']:.1f}Hz {d['ms']:.0f}ms  "
      f"PWM {d['pwm']} max {d['vmax']} 조향 {d['steer']} RB {'●' if d['deadman'] else '○'}")
print(f"pose ({d['pose'][0]-o:+.2f}, {d['pose'][1]-o:+.2f}, {math.degrees(d['pose'][2]):+.0f}°)  궤적점 {len(d['trail'])}  err={d['err']!r}")
logs = sorted(glob.glob(os.path.expanduser("~/mediscribe/sw/2.0/out/joymap_*.log")))
if logs:
    lines = open(logs[-1]).read().splitlines()
    print("로그:", os.path.basename(logs[-1]), "|", " / ".join(lines[-2:]))
