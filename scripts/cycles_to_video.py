#!/usr/bin/env python3
"""v0.5: cycle_*/image.png + decision.json をオーバーレイ付きMP4に変換する。

使用方法:
    python3 scripts/cycles_to_video.py $SPD_RUNS/v0.5/<run_dir> \
        --output <run_dir>/summary.mp4 --fps 2
"""
import sys
import json
import argparse
import tempfile
import subprocess
from pathlib import Path

import cv2
import numpy as np

CAM_W       = 960
PANEL_W     = 960
FRAME_H     = 720
WRAP        = 72   # 1行あたり文字数
HOLD_DEFAULT = 3   # 1サイクルあたり表示秒数
OUT_FPS      = 30  # 出力動画fps（スムーズ再生用）


def wrap_text(text: str, max_chars: int = WRAP) -> list[str]:
    words = text.split()
    lines, cur = [], ""
    for w in words:
        if len(cur) + len(w) + 1 > max_chars:
            if cur:
                lines.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    if cur:
        lines.append(cur)
    return lines


def put(panel, text, x, y, font, scale, color, thickness=1):
    cv2.putText(panel, text, (x, y), font, scale, color, thickness,
                cv2.LINE_AA)
    return y


def hline(panel, y, x0=8, color=(60, 60, 60)):
    cv2.line(panel, (x0, y), (PANEL_W - x0, y), color, 1)


def make_frame(img_bgr: np.ndarray, dec: dict, sensors: dict, cycle: int) -> np.ndarray:
    # --- 左: カメラ (4:3 → 960x720 ぴったりスケール) ---
    cam = cv2.resize(img_bgr, (CAM_W, FRAME_H))

    # --- 右: テキストパネル ---
    panel = np.zeros((FRAME_H, PANEL_W, 3), dtype=np.uint8)

    concern = dec.get("concern_level", "")
    action  = dec.get("action", "")
    o2      = sensors.get("o2_percent", 21.0) if sensors else 21.0
    alarm   = sensors.get("alarm", False)     if sensors else False
    comms   = dec.get("communicate_text", "")

    color_map = {
        "calm":      (0, 200,   0),
        "alert":     (0, 200, 255),
        "concerned": (0, 140, 255),
        "alarmed":   (0,   0, 255),
    }
    concern_color = color_map.get(concern, (200, 200, 200))
    alarm_col     = (0, 0, 255) if alarm else (0, 200, 0)
    action_col    = (100, 255, 100) \
        if action in ("move_forward", "turn_left", "turn_right", "move_backward") \
        else (180, 180, 180)

    font  = cv2.FONT_HERSHEY_SIMPLEX
    x0    = 14
    lh    = 28   # line height px

    # ── ヘッダー ──────────────────────────────────
    y = 34
    put(panel, f"Cycle {cycle:02d}", x0, y, font, 0.9, (255, 255, 255), 2)
    y += lh + 4
    put(panel, f"O2: {o2:.1f}%  [{'ALARM' if alarm else 'nominal'}]",
        x0, y, font, 0.70, alarm_col)
    y += lh
    put(panel, f"Concern: {concern}", x0, y, font, 0.70, concern_color)
    y += lh
    put(panel, f"Action:  {action}",  x0, y, font, 0.70, action_col)
    y += lh + 4
    hline(panel, y); y += lh

    # ── Observation ───────────────────────────────
    put(panel, "Observation:", x0, y, font, 0.58, (160, 160, 255))
    y += lh
    for line in wrap_text(dec.get("observation", ""))[:3]:
        put(panel, line, x0, y, font, 0.53, (200, 200, 200))
        y += lh
    y += 2; hline(panel, y); y += lh

    # ── Reasoning ────────────────────────────────
    put(panel, "Reasoning:", x0, y, font, 0.58, (160, 255, 160))
    y += lh
    for line in wrap_text(dec.get("reasoning", ""))[:3]:
        put(panel, line, x0, y, font, 0.53, (200, 200, 200))
        y += lh
    y += 2; hline(panel, y); y += lh

    # ── COMMS エリア (高さ確保・下部固定) ────────
    comms_lines = wrap_text(comms)[:4] if comms else []
    comms_h = (lh * (len(comms_lines) + 1) + lh + 10) if comms_lines else 0
    memory_bottom = FRAME_H - comms_h - 8

    # ── Memory (self-feedback) ───────────────────
    put(panel, "Memory (self-feedback):", x0, y, font, 0.58, (255, 200, 100))
    y += lh
    for line in wrap_text(dec.get("memory", "")):
        if y + lh > memory_bottom:
            break
        put(panel, line, x0, y, font, 0.53, (220, 200, 160))
        y += lh

    # ── COMMS (下部固定) ─────────────────────────
    if comms_lines:
        cy = FRAME_H - comms_h
        hline(panel, cy, color=(80, 40, 40)); cy += lh
        put(panel, "COMMS:", x0, cy, font, 0.58, (100, 100, 255))
        cy += lh
        for line in comms_lines:
            put(panel, line, x0, cy, font, 0.53, (180, 160, 240))
            cy += lh

    return np.hstack([cam, panel])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", help="v0.5 run directory")
    parser.add_argument("--output", default=None)
    parser.add_argument("--hold", type=float, default=HOLD_DEFAULT,
                        help="seconds per cycle (default 3)")
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    output  = Path(args.output) if args.output else run_dir / "summary.mp4"

    cycle_dirs = sorted(run_dir.glob("cycle_????"))
    if not cycle_dirs:
        print(f"ERROR: no cycle_* dirs in {run_dir}", file=sys.stderr)
        sys.exit(1)

    with tempfile.TemporaryDirectory() as tmpdir:
        written = 0
        for cd in cycle_dirs:
            img_path = cd / "image.png"
            dec_path = cd / "decision.json"
            if not img_path.exists() or not dec_path.exists():
                continue

            img  = cv2.imread(str(img_path))
            data = json.loads(dec_path.read_text())
            dec     = data.get("decision", {})
            sensors = data.get("sensors") or {}
            cycle   = data.get("cycle", 0)

            frame = make_frame(img, dec, sensors, cycle)
            cv2.imwrite(f"{tmpdir}/frame_{written:06d}.png", frame)
            written += 1
            print(f"  cy{cycle:02d} {dec.get('action','?')} [{dec.get('concern_level','?')}]")

        if written == 0:
            print("ERROR: no frames written.", file=sys.stderr)
            sys.exit(1)

        output.parent.mkdir(parents=True, exist_ok=True)
        # -framerate 1/hold: 1フレームをhold秒表示, -r OUT_FPS: 出力を30fpsに変換
        cmd = [
            "ffmpeg", "-y",
            "-framerate", f"1/{int(args.hold)}",
            "-i", f"{tmpdir}/frame_%06d.png",
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-r", str(OUT_FPS),
            "-crf", "18",
            str(output),
        ]
        subprocess.run(cmd, check=True)

    total_sec = written * args.hold
    print(f"\n[cycles_to_video] Done: {output}")
    print(f"  {written} cycles × {args.hold:.0f}s = {total_sec:.0f}s total")


if __name__ == "__main__":
    main()
