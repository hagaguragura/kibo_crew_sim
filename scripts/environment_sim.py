#!/usr/bin/env python3
"""v0.5: KIBOU 環境センサー Publisher。

O2・圧力・温度・アラームを ROS 2 topic で配信する。
YAML シナリオ指定時は時間軸に沿って値を線形補間する。

使用方法:
    python3 environment_sim.py                          # 平常値固定
    python3 environment_sim.py --scenario trapped_depress_v1.yaml
    python3 environment_sim.py --baseline-only          # 平常値固定（Phase 8 用）
"""
import sys
import os
import time
import argparse
import json
import math
import yaml
from pathlib import Path
from datetime import datetime

import rclpy
from rclpy.node import Node
from std_msgs.msg import Float32, Bool

SENSOR_HZ = float(os.environ.get("SPD_SENSOR_HZ", "2"))


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * max(0.0, min(1.0, t))


class EnvironmentSimNode(Node):
    def __init__(self, scenario: dict | None, log_dir: Path | None):
        super().__init__("environment_sim")
        self.pub_o2    = self.create_publisher(Float32, "/kibou/sensors/o2_percent", 10)
        self.pub_p     = self.create_publisher(Float32, "/kibou/sensors/pressure_kpa", 10)
        self.pub_t     = self.create_publisher(Float32, "/kibou/sensors/temperature_c", 10)
        self.pub_alarm = self.create_publisher(Bool, "/kibou/alarm", 10)

        self.o2    = 21.0
        self.p     = 101.3
        self.t_env = 22.0
        self.alarm = False

        self.scenario = scenario
        self.t_start = time.monotonic()
        self.log_dir = log_dir
        self.log_records: list[dict] = []

        period = 1.0 / SENSOR_HZ
        self.create_timer(period, self._tick)
        self.get_logger().info(
            f"EnvironmentSimNode ready. Hz={SENSOR_HZ} "
            f"scenario={'yes' if scenario else 'baseline'}"
        )

    def _update_from_scenario(self, elapsed: float):
        if not self.scenario:
            return

        events = self.scenario.get("events", [])
        current_label = None

        for ev in events:
            t_ev = ev["t"]
            if elapsed < t_ev:
                break

            if ev.get("alarm"):
                self.alarm = True
            current_label = ev.get("label")

            for key, tr in ev.get("transitions", {}).items():
                t_rel = elapsed - t_ev
                frac = t_rel / max(tr["duration"], 0.001)
                val = _lerp(tr["from"], tr["to"], frac)
                if key == "o2":
                    self.o2 = max(val, tr["to"])  # 下限でクランプ
                elif key == "pressure":
                    self.p = max(val, tr["to"])

        return current_label

    def _tick(self):
        elapsed = time.monotonic() - self.t_start
        label = self._update_from_scenario(elapsed)

        self.pub_o2.publish(Float32(data=self.o2))
        self.pub_p.publish(Float32(data=self.p))
        self.pub_t.publish(Float32(data=self.t_env))
        self.pub_alarm.publish(Bool(data=self.alarm))

        record = {
            "t": round(elapsed, 1),
            "o2_percent": round(self.o2, 2),
            "pressure_kpa": round(self.p, 2),
            "temperature_c": round(self.t_env, 1),
            "alarm": self.alarm,
            "label": label,
        }
        self.log_records.append(record)

        if len(self.log_records) % 20 == 0:
            self.get_logger().info(
                f"t={elapsed:.0f}s O2={self.o2:.1f}% P={self.p:.1f}kPa alarm={self.alarm}"
            )

    def flush_log(self):
        if not self.log_dir or not self.log_records:
            return
        self.log_dir.mkdir(parents=True, exist_ok=True)
        log_path = self.log_dir / "sensor_log.jsonl"
        with open(log_path, "w") as f:
            for rec in self.log_records:
                f.write(json.dumps(rec) + "\n")
        self.get_logger().info(f"sensor_log written: {log_path} ({len(self.log_records)} records)")


def load_scenario(name: str) -> dict | None:
    search_dirs = [
        Path(os.path.dirname(__file__)) / "../config/scenarios",
        Path(os.path.expandvars("$SPD_WS/src/kibo_crew_sim/config/scenarios")),
    ]
    for d in search_dirs:
        p = d / name
        if not p.suffix:
            p = p.with_suffix(".yaml")
        if p.exists():
            with open(p) as f:
                return yaml.safe_load(f)
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", type=str, default=None,
                        help="Scenario name or path (e.g. trapped_depress_v1)")
    parser.add_argument("--baseline-only", action="store_true",
                        help="Ignore scenario, publish baseline values only")
    parser.add_argument("--log-dir", type=str,
                        default=os.path.expandvars("$SPD_RUNS/v0.5/latest"))
    args, _ = parser.parse_known_args()

    scenario = None
    if not args.baseline_only and args.scenario:
        scenario = load_scenario(args.scenario)
        if scenario is None:
            print(f"[env_sim] WARNING: scenario '{args.scenario}' not found. Using baseline.")

    log_dir = Path(args.log_dir) if args.log_dir else None

    rclpy.init()
    node = EnvironmentSimNode(scenario=scenario, log_dir=log_dir)

    print(f"[env_sim] Start. Ctrl+C to stop.")
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.flush_log()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
