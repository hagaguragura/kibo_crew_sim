#!/usr/bin/env python3
"""v0.5: Claude unified brain loop — trapped depress scenario.

Perception (image_raw + odom + env sensors) → Claude decide() → cmd_vel + comms

使用方法:
    export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
    source /opt/ros/humble/setup.bash && source $SPD_WS/install/setup.bash
    python3 brain_loop_node.py [--cycle 5.0] [--timeout 600] [--log-dir PATH]
"""
import sys
import os
import json
import math
import time
import argparse
import threading
import logging
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
import rclpy
import rclpy.executors
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from sensor_msgs.msg import Image
from std_msgs.msg import String

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src/vlm_bench"))
sys.path.insert(0, os.path.dirname(__file__))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "../.env"))
from clients.claude_client import ClaudeVLMClient
from brain.image_buffer import imgmsg_to_bgr
from brain.sensor_buffer import SensorBuffer

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

MISSION_V05 = (
    "You are alone inside the JEM 'Kibo' module of the ISS. "
    "You believe the hatches may be locked and you may be trapped. "
    "Sensor readings indicate environmental changes that warrant investigation. "
    "Your job is to assess the situation calmly, explore your surroundings, "
    "report to ground if you wish, and survive. "
    "You may communicate with ground at any time using 'communicate' action. "
    "Consider communicating periodically to keep ground informed."
)

# v0.4 mission kept for reference
MISSION_V04 = (
    "Find the missing Int-Ball2 (a small white spherical robot, ~30cm diameter). "
    "Approach it within 1 meter. Reply 'stay' once you are close enough."
)

MISSION = MISSION_V05


def _make_twist(action: str) -> Twist:
    t = Twist()
    if action in ("forward", "move_forward"):
        t.linear.y = 0.3
    elif action in ("backward", "move_backward"):
        t.linear.y = -0.2
    elif action == "turn_left":
        t.angular.z = 0.5
    elif action == "turn_right":
        t.angular.z = -0.5
    # inspect / communicate / report_status → zero twist (静止)
    return t



class BrainLoopNode(Node):
    def __init__(self, claude: ClaudeVLMClient, cycle_sec: float,
                 log_dir: Path, use_two_stage: bool):
        super().__init__("brain_loop_node")
        self.claude = claude
        self.cycle_sec = cycle_sec
        self.log_dir = log_dir
        self.use_two_stage = use_two_stage

        self._img_lock = threading.Lock()
        self._latest_img: np.ndarray | None = None
        self._img_stamp: float = 0.0

        self.odom_pos = {"x": 0.0, "y": 0.0, "z": 0.0, "yaw_deg": 0.0}
        self.memory: list[str] = []
        self.action_history: list[dict] = []
        self.cycle = 0
        self.reached = False
        self.total_cost = 0.0
        self.comms_log: list[dict] = []

        qos = QoSProfile(depth=10, reliability=ReliabilityPolicy.RELIABLE)
        self.create_subscription(Image, "/humanoid_01/image_raw", self._img_cb, qos)
        self.create_subscription(Odometry, "/humanoid_01/odom", self._odom_cb, 10)
        self.pub_cmd = self.create_publisher(Twist, "/humanoid_01/cmd_vel", 10)
        self.pub_decision = self.create_publisher(String, "/humanoid_01/decision", 10)
        self.pub_comms = self.create_publisher(String, "/humanoid_01/comms", 10)

        self.get_logger().info(
            f"BrainLoopNode ready. cycle={cycle_sec}s two_stage={use_two_stage}"
        )

    def _img_cb(self, msg: Image):
        img = imgmsg_to_bgr(msg)
        with self._img_lock:
            self._latest_img = img
            self._img_stamp = time.monotonic()

    def _odom_cb(self, msg: Odometry):
        p = msg.pose.pose.position
        q = msg.pose.pose.orientation
        yaw_rad = 2.0 * math.atan2(q.z, q.w)
        self.odom_pos = {"x": p.x, "y": p.y, "z": p.z, "yaw_deg": math.degrees(yaw_rad)}

    def get_latest_image(self) -> tuple[np.ndarray | None, float]:
        with self._img_lock:
            if self._latest_img is None:
                return None, float("inf")
            age_ms = (time.monotonic() - self._img_stamp) * 1000.0
            return self._latest_img.copy(), age_ms

    def publish_action(self, action: str, duration_sec: float):
        twist = _make_twist(action)
        t0 = time.monotonic()
        while time.monotonic() - t0 < duration_sec:
            self.pub_cmd.publish(twist)
            time.sleep(0.1)
        self.pub_cmd.publish(Twist())

    def log_cycle(self, img: np.ndarray, result: dict, sensors: dict | None = None):
        cycle_dir = self.log_dir / f"cycle_{self.cycle:04d}"
        cycle_dir.mkdir(parents=True, exist_ok=True)

        cv2.imwrite(str(cycle_dir / "image.png"), img)

        entry = {
            "cycle": self.cycle,
            "timestamp": datetime.utcnow().isoformat(),
            "odom": self.odom_pos.copy(),
            "image_age_ms": result.get("image_age_ms", 0),
            "sensors": sensors,
            "claude": {
                "latency_ms": result["latency_ms"],
                "input_tokens": result.get("input_tokens", 0),
                "output_tokens": result.get("output_tokens", 0),
                "cost_usd": result["cost_usd"],
            },
            "decision": {
                "observation": result.get("observation", ""),
                "interpretation": result.get("interpretation", ""),
                "reasoning": result.get("reasoning", ""),
                "concern_level": result.get("concern_level", "calm"),
                "action": result.get("action", "inspect"),
                "communicate_text": result.get("communicate_text", ""),
                "memory": result.get("memory", ""),
            },
        }
        (cycle_dir / "decision.json").write_text(
            json.dumps(entry, ensure_ascii=False, indent=2)
        )
        self.pub_decision.publish(String(data=json.dumps(entry, ensure_ascii=False)))

    def step(self, sensors_now: dict | None = None,
             sensors_history: list[dict] | None = None) -> bool:
        img, age_ms = self.get_latest_image()
        if img is None or age_ms > 6000:
            self.get_logger().warn(f"No fresh image (age={age_ms:.0f}ms), waiting...")
            self.pub_cmd.publish(Twist())
            time.sleep(0.5)
            return False

        self.cycle += 1
        state = {**self.odom_pos}

        result = self.claude.decide(
            img, MISSION, state,
            sensors_now=sensors_now or {},
            sensors_history=sensors_history or [],
            memory=self.memory[-5:],
            action_history=self.action_history[-8:],
        )
        result["image_age_ms"] = age_ms
        self.total_cost += result["cost_usd"]

        action = result.get("action", "inspect")
        concern = result.get("concern_level", "calm")
        logger.info(
            f"[{self.cycle}] pos=({state['x']:.2f},{state['y']:.2f}) yaw={state['yaw_deg']:.0f}° "
            f"action={action} concern={concern} "
            f"{result['latency_ms']:.0f}ms ${result['cost_usd']:.4f}"
        )
        logger.info(f"  obs: {result.get('observation','')[:80]}")
        if result.get("interpretation"):
            logger.info(f"  int: {result.get('interpretation','')[:80]}")

        comms_sent = False
        if action == "communicate":
            text = result.get("communicate_text", "")
            if text:
                self.pub_comms.publish(String(data=text))
                self.comms_log.append({"cycle": self.cycle, "text": text,
                                       "timestamp": datetime.utcnow().isoformat()})
                logger.info(f"  comms: {text[:80]}")
                comms_sent = True

        self.action_history.append({
            "cycle": self.cycle,
            "action": action,
            "x": state["x"],
            "y": state["y"],
            "concern": concern,
            "comms_sent": comms_sent,
        })
        # parseエラー時は直前のmemoryを保持（上書きしない）
        new_mem = result.get("memory", "")
        if new_mem and new_mem != "parse error":
            self.memory.append(new_mem)
        elif self.memory:
            self.memory.append(self.memory[-1])  # 直前をコピーして継続
        self.log_cycle(img, result, sensors_now)
        self.publish_action(action, self.cycle_sec)
        return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cycle", type=float,
                        default=float(os.environ.get("SPD_BRAIN_CYCLE_SEC", "5")))
    parser.add_argument("--timeout", type=float, default=600.0)
    parser.add_argument("--tag", type=str, default="",
                        help="Run label appended to directory name (e.g. run1, run2)")
    parser.add_argument("--log-dir", type=str, default=None)
    args, _ = parser.parse_known_args()

    ts = datetime.utcnow().strftime('%Y%m%dT%H%M%S')
    suffix = f"_{args.tag}" if args.tag else ""
    log_dir = Path(args.log_dir) if args.log_dir else \
              Path(os.path.expandvars(f"$SPD_RUNS/v0.5/{ts}{suffix}"))
    log_dir.mkdir(parents=True, exist_ok=True)

    model = os.environ.get("SPD_VLM_MODEL", "claude-sonnet-4-6")
    claude = ClaudeVLMClient(model=model)

    rclpy.init()
    node = BrainLoopNode(
        claude=claude,
        cycle_sec=args.cycle,
        log_dir=log_dir,
        use_two_stage=False,
    )
    sensor_buf = SensorBuffer()

    executor = rclpy.executors.MultiThreadedExecutor()
    executor.add_node(node)
    executor.add_node(sensor_buf)
    spin_thread = threading.Thread(target=executor.spin, daemon=True)
    spin_thread.start()

    print(f"[brain_loop] Start. cycle={args.cycle}s timeout={args.timeout}s")
    print(f"[brain_loop] Log: {log_dir}")

    t_start = time.monotonic()
    while rclpy.ok() and not node.reached:
        if time.monotonic() - t_start > args.timeout:
            print("[brain_loop] TIMEOUT.")
            node.pub_cmd.publish(Twist())
            break
        node.step(
            sensors_now=sensor_buf.get_latest(),
            sensors_history=sensor_buf.get_history(n=12),
        )

    elapsed = time.monotonic() - t_start
    run_summary = {
        "version": "v0.5",
        "cycles": node.cycle,
        "elapsed_sec": elapsed,
        "total_cost_usd": node.total_cost,
        "comms_count": len(node.comms_log),
    }
    (log_dir / "run.json").write_text(json.dumps(run_summary, indent=2))
    if node.comms_log:
        import jsonlines
        with jsonlines.open(log_dir / "comms.jsonl", mode="w") as writer:
            for entry in node.comms_log:
                writer.write(entry)

    print(f"[brain_loop] Done. cycles={node.cycle} "
          f"elapsed={elapsed:.0f}s total_cost=${node.total_cost:.4f} "
          f"comms={len(node.comms_log)}")
    try:
        node.destroy_node()
        rclpy.shutdown()
    except Exception:
        pass


if __name__ == "__main__":
    main()
