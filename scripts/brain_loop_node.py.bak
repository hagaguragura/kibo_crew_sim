#!/usr/bin/env python3
"""Phase 5.1 / 6: LLMヒューマノイド脳（継続ループ）ROS2ノード。

Perception → Decision → Action を 2秒間隔で繰り返し、目標に到達したら停止。

使用方法:
    export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
    source /opt/ros/humble/setup.bash && source $SPD_WS/install/setup.bash
    python3 brain_loop_node.py [--goal-y 3.5] [--interval 2.0]

[VERIFY] ヒューマノイドが数ステップで目標位置に到達して停止する
"""
import sys
import os
import json
import math
import time
import argparse
import logging
import jsonlines

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry

sys.path.insert(0, os.path.dirname(__file__))
from ollama_client import OllamaClient

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

ACTION_MAP = {
    "forward":  ( 0.0,  1.0),
    "backward": ( 0.0, -1.0),
    "left":     (-1.0,  0.0),
    "right":    ( 1.0,  0.0),
    "stay":     ( 0.0,  0.0),
}

GOAL_THRESHOLD = 0.3   # m
DEFAULT_GOAL = {"x": 20.5, "y": 3.5, "z": 0.8, "name": "Experiment_Rack"}


def build_prompt(current_pos: dict, goal: dict, memory: str, step: int) -> str:
    dx = goal["x"] - current_pos["x"]
    dy = goal["y"] - current_pos["y"]
    dist = math.sqrt(dx**2 + dy**2)

    # 方向ヒント: LLMの誤判断を防ぐ
    if abs(dy) >= abs(dx):
        recommended = "forward" if dy > 0 else "backward"
        hint = f"dy={dy:.3f} → goal is in {'POSITIVE' if dy>0 else 'NEGATIVE'} Y direction → use '{recommended}'"
    else:
        recommended = "right" if dx > 0 else "left"
        hint = f"dx={dx:.3f} → goal is in {'POSITIVE' if dx>0 else 'NEGATIVE'} X direction → use '{recommended}'"

    return f"""You are a human astronaut inside the KIBO module of the ISS.

=== YOUR CURRENT STATE ===
Position: ({current_pos['x']:.3f}, {current_pos['y']:.3f}, {current_pos['z']:.3f})
Distance to goal: {dist:.3f} m

=== YOUR GOAL ===
Walk to position ({goal['x']:.3f}, {goal['y']:.3f}) named "{goal.get('name','Goal')}"
Direction to goal: dx={dx:.3f}, dy={dy:.3f}

=== NAVIGATION HINT ===
{hint}
IMPORTANT: "forward" moves +Y (increases Y). "backward" moves -Y (decreases Y).

=== PREVIOUS MEMORY ===
{memory if memory else 'No previous memory.'}

=== AVAILABLE ACTIONS ===
- "forward"  : move in +Y direction (Y increases)
- "backward" : move in -Y direction (Y decreases)
- "left"     : move in -X direction
- "right"    : move in +X direction
- "stay"     : remain at current position

=== RESPOND IN JSON ONLY ===
{{
    "action": "forward" | "backward" | "left" | "right" | "stay",
    "memory": "what you want to remember for the next step",
    "reasoning": "brief explanation of your decision"
}}

Step: {step}
"""


def parse_llm_response(response: str) -> dict:
    try:
        start = response.find('{')
        end = response.rfind('}')
        if start != -1 and end != -1:
            return json.loads(response[start:end+1])
    except json.JSONDecodeError:
        pass
    for action in ACTION_MAP:
        if action in response.lower():
            return {"action": action, "memory": "", "reasoning": response[:100]}
    return {"action": "stay", "memory": "", "reasoning": "parse failed"}


class BrainLoopNode(Node):
    def __init__(self, llm: OllamaClient, goal: dict, speed: float,
                 interval: float, log_path: str):
        super().__init__("brain_loop_node")
        self.llm = llm
        self.goal = goal
        self.speed = speed
        self.interval = interval
        self.log_path = log_path

        self.current_pos = None
        self.memory = ""
        self.step = 0
        self.reached = False

        self.pub = self.create_publisher(Twist, "/humanoid_01/cmd_vel", 10)
        self.sub = self.create_subscription(
            Odometry, "/humanoid_01/odom", self._odom_cb, 10
        )
        self.get_logger().info(
            f"BrainLoopNode started. Goal: ({goal['x']:.1f}, {goal['y']:.1f})"
        )

    def _odom_cb(self, msg: Odometry):
        p = msg.pose.pose.position
        self.current_pos = {"x": p.x, "y": p.y, "z": p.z}

    def distance_to_goal(self) -> float:
        if self.current_pos is None:
            return float("inf")
        dx = self.goal["x"] - self.current_pos["x"]
        dy = self.goal["y"] - self.current_pos["y"]
        return math.sqrt(dx**2 + dy**2)

    def step_loop(self):
        """1ループ実行。到達していたらTrueを返す。"""
        if self.current_pos is None:
            self.get_logger().info("Waiting for odom...")
            return False

        dist = self.distance_to_goal()
        if dist < GOAL_THRESHOLD:
            self.get_logger().info(f"Goal reached! distance={dist:.3f}m")
            self.pub.publish(Twist())
            self.reached = True
            return True

        self.step += 1
        self.get_logger().info(
            f"[Step {self.step}] pos=({self.current_pos['x']:.3f},{self.current_pos['y']:.3f}) dist={dist:.3f}m"
        )

        # LLM判断
        prompt = build_prompt(self.current_pos, self.goal, self.memory, self.step)
        response = self.llm.generate(prompt)
        decision = parse_llm_response(response)

        action = decision.get("action", "stay")
        reasoning = decision.get("reasoning", "")
        new_memory = decision.get("memory", "")

        # LLMが方向を逆に選んだ場合のジオメトリ補正
        dx = self.goal["x"] - self.current_pos["x"]
        dy = self.goal["y"] - self.current_pos["y"]
        if action == "forward" and dy < -0.1:
            logger.warning(f"LLM said 'forward' but dy={dy:.3f}<0 → overriding to 'backward'")
            action = "backward"
        elif action == "backward" and dy > 0.1:
            logger.warning(f"LLM said 'backward' but dy={dy:.3f}>0 → overriding to 'forward'")
            action = "forward"

        print(f"  reasoning: {reasoning}")
        print(f"  action: {action}")

        # メモリ更新
        self.memory = f"Step {self.step}: {new_memory or reasoning}"

        # ログ保存
        if self.log_path:
            with jsonlines.open(self.log_path, mode='a') as writer:
                writer.write({
                    "step": self.step,
                    "position": self.current_pos,
                    "goal": self.goal,
                    "distance": dist,
                    "action": action,
                    "reasoning": reasoning,
                    "memory": self.memory,
                })

        dx, dy = ACTION_MAP.get(action, (0.0, 0.0))
        twist = Twist()
        twist.linear.x = dx * self.speed
        twist.linear.y = dy * self.speed

        # interval秒間 cmd_vel を送信
        t0 = time.time()
        while time.time() - t0 < self.interval:
            self.pub.publish(twist)
            rclpy.spin_once(self, timeout_sec=0.05)

        # 次のステップまで停止
        self.pub.publish(Twist())
        return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--goal-x", type=float, default=DEFAULT_GOAL["x"])
    parser.add_argument("--goal-y", type=float, default=DEFAULT_GOAL["y"])
    parser.add_argument("--goal-z", type=float, default=DEFAULT_GOAL["z"])
    parser.add_argument("--speed",    type=float, default=0.1)
    parser.add_argument("--interval", type=float, default=2.0)
    parser.add_argument("--timeout",  type=float, default=300.0)
    parser.add_argument("--log",      type=str,
                        default=os.path.expandvars("$SPD_RUNS/humanoid_brain.jsonl"))
    args, _ = parser.parse_known_args()

    goal = {"x": args.goal_x, "y": args.goal_y, "z": args.goal_z,
            "name": "Experiment_Rack"}

    llm_host  = os.environ.get("SPD_LLM_HOST",  "http://localhost:11434")
    llm_model = os.environ.get("SPD_LLM_MODEL", "qwen2.5:latest")
    llm = OllamaClient(base_url=llm_host, model=llm_model, max_tokens=200)

    os.makedirs(os.path.dirname(args.log), exist_ok=True)

    rclpy.init()
    node = BrainLoopNode(
        llm=llm, goal=goal, speed=args.speed,
        interval=args.interval, log_path=args.log
    )

    t_start = time.time()
    print(f"[brain_loop] Starting. Timeout={args.timeout}s, Goal=({goal['x']},{goal['y']})")

    while rclpy.ok() and not node.reached:
        if time.time() - t_start > args.timeout:
            print("[brain_loop] TIMEOUT.")
            node.pub.publish(Twist())
            break
        rclpy.spin_once(node, timeout_sec=0.1)
        node.step_loop()

    node.destroy_node()
    rclpy.shutdown()
    print(f"[brain_loop] Finished after {node.step} steps.")
    if args.log and os.path.exists(args.log):
        print(f"[brain_loop] Log saved: {args.log}")


if __name__ == "__main__":
    main()
