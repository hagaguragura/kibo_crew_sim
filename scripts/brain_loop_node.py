#!/usr/bin/env python3
"""v0.4: Claude unified brain loop.

Perception (image_raw + odom) → Claude decide() → cmd_vel + decision topic

使用方法:
    export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
    source /opt/ros/humble/setup.bash && source $SPD_WS/install/setup.bash
    python3 brain_loop_node.py [--cycle 3.0] [--timeout 300]

[VERIFY] humanoid_01 が Int-Ball2 を視覚的に発見し 1m 以内に接近して停止する
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
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from sensor_msgs.msg import Image
from std_msgs.msg import String

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src/vlm_bench"))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "../.env"))
from clients.claude_client import ClaudeVLMClient

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

MISSION = (
    "Find the missing Int-Ball2 (a small white spherical robot, ~30cm diameter). "
    "Approach it within 1 meter. Reply 'stay' once you are close enough."
)

def _make_twist(action: str) -> Twist:
    t = Twist()
    if action == "forward":
        t.linear.x = 0.3
    elif action == "backward":
        t.linear.x = -0.2
    elif action == "left":
        t.angular.z = 0.5
    elif action == "right":
        t.angular.z = -0.5
    return t


def _imgmsg_to_bgr(msg: Image) -> np.ndarray:
    img = np.frombuffer(msg.data, dtype=np.uint8).reshape((msg.height, msg.width, -1))
    if msg.encoding in ("rgb8", "rgb"):
        img = img[:, :, ::-1].copy()
    return img


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

        self.odom_pos = {"x": 0.0, "y": 0.0, "z": 0.0}
        self.memory: list[str] = []
        self.cycle = 0
        self.reached = False
        self.total_cost = 0.0

        qos = QoSProfile(depth=1, reliability=ReliabilityPolicy.BEST_EFFORT)
        self.create_subscription(Image, "/humanoid_01/image_raw", self._img_cb, qos)
        self.create_subscription(Odometry, "/humanoid_01/odom", self._odom_cb, 10)
        self.pub_cmd = self.create_publisher(Twist, "/humanoid_01/cmd_vel", 10)
        self.pub_decision = self.create_publisher(String, "/humanoid_01/decision", 10)

        self.get_logger().info(
            f"BrainLoopNode ready. cycle={cycle_sec}s two_stage={use_two_stage}"
        )

    def _img_cb(self, msg: Image):
        img = _imgmsg_to_bgr(msg)
        with self._img_lock:
            self._latest_img = img
            self._img_stamp = time.monotonic()

    def _odom_cb(self, msg: Odometry):
        p = msg.pose.pose.position
        self.odom_pos = {"x": p.x, "y": p.y, "z": p.z}

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

    def log_cycle(self, img: np.ndarray, result: dict, light: dict | None = None):
        cycle_dir = self.log_dir / f"cycle_{self.cycle:04d}"
        cycle_dir.mkdir(parents=True, exist_ok=True)

        cv2.imwrite(str(cycle_dir / "image.png"), img)

        entry = {
            "cycle": self.cycle,
            "timestamp": datetime.utcnow().isoformat(),
            "odom": self.odom_pos.copy(),
            "image_age_ms": result.get("image_age_ms", 0),
            "light_detect": light,
            "claude": {
                "latency_ms": result["latency_ms"],
                "input_tokens": result.get("input_tokens", 0),
                "output_tokens": result.get("output_tokens", 0),
                "cost_usd": result["cost_usd"],
            },
            "decision": {
                "observation": result.get("observation", ""),
                "target_visible": result.get("target_visible", False),
                "target_location": result.get("target_location", "none"),
                "reasoning": result.get("reasoning", ""),
                "action": result.get("action", "stay"),
                "memory": result.get("memory", ""),
            },
        }
        (cycle_dir / "decision.json").write_text(
            json.dumps(entry, ensure_ascii=False, indent=2)
        )
        self.pub_decision.publish(String(data=json.dumps(entry, ensure_ascii=False)))

    def step(self) -> bool:
        img, age_ms = self.get_latest_image()
        if img is None or age_ms > 6000:
            self.get_logger().warn(f"No fresh image (age={age_ms:.0f}ms), waiting...")
            self.pub_cmd.publish(Twist())
            time.sleep(0.5)
            return False

        self.cycle += 1
        state = {**self.odom_pos, "yaw": 0.0}

        light = None
        if self.use_two_stage and self.cycle % 10 != 0:
            light = self.claude.light_detect(img)
            self.total_cost += light["cost_usd"]
            logger.info(
                f"[{self.cycle}] light: visible={light['visible']} "
                f"loc={light['location']} {light['latency_ms']:.0f}ms"
            )
            if not light["visible"]:
                action = "left"
                self.publish_action(action, self.cycle_sec)
                return False

        result = self.claude.decide(img, MISSION, state, self.memory[-3:])
        result["image_age_ms"] = age_ms
        self.total_cost += result["cost_usd"]

        action = result.get("action", "stay")
        logger.info(
            f"[{self.cycle}] pos=({state['x']:.2f},{state['y']:.2f}) "
            f"visible={result.get('target_visible')} action={action} "
            f"{result['latency_ms']:.0f}ms ${result['cost_usd']:.4f}"
        )
        logger.info(f"  obs: {result.get('observation','')[:80]}")

        self.memory.append(result.get("memory", ""))
        self.log_cycle(img, result, light)

        if action == "stay" and result.get("target_visible"):
            self.get_logger().info("Goal reached! Stopping.")
            self.pub_cmd.publish(Twist())
            self.reached = True
            return True

        self.publish_action(action, self.cycle_sec)
        return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cycle", type=float,
                        default=float(os.environ.get("SPD_BRAIN_CYCLE_SEC", "3")))
    parser.add_argument("--timeout", type=float, default=300.0)
    parser.add_argument("--two-stage", action="store_true",
                        help="Enable light_detect → full decide two-stage loop")
    parser.add_argument("--log-dir", type=str,
                        default=os.path.expandvars(
                            f"$SPD_RUNS/v0.4/{datetime.utcnow().strftime('%Y%m%dT%H%M%S')}"))
    args, _ = parser.parse_known_args()

    log_dir = Path(args.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    model = os.environ.get("SPD_VLM_MODEL", "claude-sonnet-4-6")
    claude = ClaudeVLMClient(model=model)

    rclpy.init()
    node = BrainLoopNode(
        claude=claude,
        cycle_sec=args.cycle,
        log_dir=log_dir,
        use_two_stage=args.two_stage,
    )

    spin_thread = threading.Thread(target=rclpy.spin, args=(node,), daemon=True)
    spin_thread.start()

    print(f"[brain_loop] Start. cycle={args.cycle}s timeout={args.timeout}s "
          f"two_stage={args.two_stage}")
    print(f"[brain_loop] Log: {log_dir}")

    t_start = time.monotonic()
    while rclpy.ok() and not node.reached:
        if time.monotonic() - t_start > args.timeout:
            print("[brain_loop] TIMEOUT.")
            node.pub_cmd.publish(Twist())
            break
        node.step()

    elapsed = time.monotonic() - t_start
    print(f"[brain_loop] Done. cycles={node.cycle} "
          f"elapsed={elapsed:.0f}s total_cost=${node.total_cost:.4f}")
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
