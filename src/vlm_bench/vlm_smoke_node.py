"""ROS 2 node: subscribe /crew_01/image_raw once, call VLM, log result, shutdown."""

import json
import os
import sys
from pathlib import Path
from datetime import datetime

import cv2
import numpy as np
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from cv_bridge import CvBridge
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env")

SPD_RUNS = os.environ.get("SPD_RUNS", "/tmp")
LOG_PATH = Path(SPD_RUNS) / "v0.3" / "phase6" / "smoke.jsonl"
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

VLM_PROVIDER = os.environ.get("SPD_VLM_PROVIDER", "claude")
VLM_MODEL = os.environ.get("SPD_VLM_MODEL", "")

PROMPT = (
    "You are an astronaut inside the JEM \"Kibo\" module of the ISS. "
    "Describe what you see in this image. If you detect anything anomalous "
    "(fire, smoke, damage, intruder, leak), state it clearly at the start. "
    "Reply in 1-3 sentences."
)


def _load_client():
    if VLM_PROVIDER == "claude":
        sys.path.insert(0, str(Path(__file__).parent))
        from clients.claude_client import ClaudeVLMClient
        return ClaudeVLMClient(model=VLM_MODEL or "claude-sonnet-4-6")
    elif VLM_PROVIDER == "nim":
        sys.path.insert(0, str(Path(__file__).parent))
        from clients.nim_client import NIMVLMClient
        return NIMVLMClient(model=VLM_MODEL or "meta/llama-3.2-90b-vision-instruct")
    elif VLM_PROVIDER == "ollama":
        sys.path.insert(0, str(Path(__file__).parent))
        from clients.ollama_vlm_client import OllamaVLMClient
        return OllamaVLMClient(model=VLM_MODEL or "moondream")
    else:
        raise ValueError(f"Unknown SPD_VLM_PROVIDER: {VLM_PROVIDER}")


class VLMSmokeNode(Node):
    def __init__(self):
        super().__init__("vlm_smoke_node")
        self._bridge = CvBridge()
        self._client = _load_client()
        self._done = False
        self._sub = self.create_subscription(
            Image, "/crew_01/image_raw", self._callback, 10)
        self.get_logger().info(
            f"VLMSmokeNode ready. provider={VLM_PROVIDER} model={VLM_MODEL or 'default'}. "
            "Waiting for /crew_01/image_raw ...")

    def _callback(self, msg: Image):
        if self._done:
            return
        self._done = True
        self.get_logger().info("Image received. Calling VLM...")

        img = self._bridge.imgmsg_to_cv2(msg, desired_encoding="bgr8")
        result = self._client.describe(img, PROMPT)

        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "image_topic": "/crew_01/image_raw",
            "provider": VLM_PROVIDER,
            "model": VLM_MODEL or "default",
            **result,
        }
        with open(LOG_PATH, "a") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

        self.get_logger().info(f"VLM response ({result['latency_ms']:.0f}ms):\n"
                               f"  {result['text']}")
        self.get_logger().info(f"Log written to {LOG_PATH}")
        raise SystemExit(0)


def main():
    rclpy.init()
    node = VLMSmokeNode()
    try:
        rclpy.spin(node)
    except SystemExit:
        pass
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
