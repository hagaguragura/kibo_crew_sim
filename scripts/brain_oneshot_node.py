#!/usr/bin/env python3
"""Phase 4.2: LLMヒューマノイド脳（単発判断）ROS2ノード。

/humanoid_01/odom を1回受信 → LLM判断 → /humanoid_01/cmd_vel を1秒間Publish → 終了。

使用方法:
    export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
    source /opt/ros/humble/setup.bash && source $SPD_WS/install/setup.bash
    python3 brain_oneshot_node.py [--goal-y 3.5]

[VERIFY] LLMのreasoningがstdoutに出て、ヒューマノイドが目標方向に動く
"""
import sys
import os
import json
import time
import argparse
import logging

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry

sys.path.insert(0, os.path.dirname(__file__))
from ollama_client import OllamaClient

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# 行動マッピング（2D: X, Yのみ）
ACTION_MAP = {
    "forward":  ( 0.0,  1.0),  # Y+
    "backward": ( 0.0, -1.0),  # Y-
    "left":     (-1.0,  0.0),  # X-
    "right":    ( 1.0,  0.0),  # X+
    "stay":     ( 0.0,  0.0),
}

# デフォルト目標
DEFAULT_GOAL = {"x": 20.5, "y": 3.5, "z": 0.8}


def build_prompt(current_pos: dict, goal: dict) -> str:
    return f"""You are a human astronaut inside the KIBO module of the ISS.
You are standing on the module floor in a zero-gravity environment.

=== YOUR CURRENT STATE ===
Position: ({current_pos['x']:.3f}, {current_pos['y']:.3f}, {current_pos['z']:.3f})

=== YOUR GOAL ===
Walk to position: ({goal['x']:.3f}, {goal['y']:.3f}, {goal['z']:.3f})  (named: {goal.get('name','Goal')})

=== AVAILABLE ACTIONS ===
- "forward"  : move in +Y direction (toward experiment rack)
- "backward" : move in -Y direction (toward hatch)
- "left"     : move in -X direction
- "right"    : move in +X direction
- "stay"     : remain at current position

=== RESPOND IN JSON ONLY ===
{{
    "action": "forward" | "backward" | "left" | "right" | "stay",
    "reasoning": "brief explanation of your decision"
}}
"""


def parse_llm_response(response: str) -> dict:
    try:
        start = response.find('{')
        end = response.rfind('}')
        if start != -1 and end != -1:
            return json.loads(response[start:end+1])
    except json.JSONDecodeError:
        pass
    # フォールバック
    for action in ACTION_MAP:
        if action in response.lower():
            return {"action": action, "reasoning": response[:100]}
    return {"action": "stay", "reasoning": "parse failed"}


class BrainOneshotNode(Node):
    def __init__(self, llm: OllamaClient, goal: dict, speed: float = 0.3):
        super().__init__("brain_oneshot_node")
        self.llm = llm
        self.goal = goal
        self.speed = speed
        self.current_pos = None
        self.done = False

        self.pub = self.create_publisher(Twist, "/humanoid_01/cmd_vel", 10)
        self.sub = self.create_subscription(
            Odometry, "/humanoid_01/odom", self._odom_cb, 10
        )
        self.get_logger().info("BrainOneshotNode started. Waiting for odom...")

    def _odom_cb(self, msg: Odometry):
        if self.current_pos is not None:
            return  # 1回だけ受信
        p = msg.pose.pose.position
        self.current_pos = {"x": p.x, "y": p.y, "z": p.z}
        self.get_logger().info(
            f"Current position: ({p.x:.3f}, {p.y:.3f}, {p.z:.3f})"
        )
        self._decide_and_act()

    def _decide_and_act(self):
        self.get_logger().info("Calling LLM...")
        prompt = build_prompt(self.current_pos, self.goal)
        response = self.llm.generate(prompt)

        if not response:
            self.get_logger().error("LLM returned empty response")
            self.done = True
            return

        decision = parse_llm_response(response)
        action = decision.get("action", "stay")
        reasoning = decision.get("reasoning", "")

        print(f"\n[LLM reasoning] {reasoning}")
        print(f"[LLM action] {action}\n")

        dx, dy = ACTION_MAP.get(action, (0.0, 0.0))

        # 1秒間 cmd_vel を送信
        twist = Twist()
        twist.linear.x = dx * self.speed
        twist.linear.y = dy * self.speed

        t0 = time.time()
        while time.time() - t0 < 1.0:
            self.pub.publish(twist)
            time.sleep(0.05)

        # 停止
        self.pub.publish(Twist())
        self.done = True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--goal-x", type=float, default=DEFAULT_GOAL["x"])
    parser.add_argument("--goal-y", type=float, default=DEFAULT_GOAL["y"])
    parser.add_argument("--goal-z", type=float, default=DEFAULT_GOAL["z"])
    parser.add_argument("--speed", type=float, default=0.3)
    args, _ = parser.parse_known_args()

    goal = {
        "x": args.goal_x, "y": args.goal_y, "z": args.goal_z,
        "name": "Experiment_Rack"
    }

    llm_host = os.environ.get("SPD_LLM_HOST", "http://localhost:11434")
    llm_model = os.environ.get("SPD_LLM_MODEL", "qwen2.5:latest")
    llm = OllamaClient(base_url=llm_host, model=llm_model, max_tokens=200)

    rclpy.init()
    node = BrainOneshotNode(llm=llm, goal=goal, speed=args.speed)

    while rclpy.ok() and not node.done:
        rclpy.spin_once(node, timeout_sec=0.1)

    node.destroy_node()
    rclpy.shutdown()
    print("[brain_oneshot] Completed.")


if __name__ == "__main__":
    main()
