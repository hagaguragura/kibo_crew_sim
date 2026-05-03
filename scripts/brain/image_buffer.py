"""Latest-only image buffer: subscribes to image_raw, keeps newest frame only."""

import threading
import time
from typing import Optional

import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import Image


def _imgmsg_to_bgr(msg: Image) -> np.ndarray:
    img = np.frombuffer(msg.data, dtype=np.uint8).reshape((msg.height, msg.width, -1))
    if msg.encoding in ("rgb8", "rgb"):
        img = img[:, :, ::-1].copy()
    return img


class ImageBuffer(Node):
    """Thread-safe single-frame buffer for /humanoid_01/image_raw."""

    def __init__(self):
        super().__init__("image_buffer")
        self._lock = threading.Lock()
        self._image: Optional[np.ndarray] = None
        self._stamp: float = 0.0

        qos = QoSProfile(depth=1, reliability=ReliabilityPolicy.BEST_EFFORT)
        self.create_subscription(Image, "/humanoid_01/image_raw", self._cb, qos)
        self.get_logger().info("ImageBuffer: waiting for /humanoid_01/image_raw ...")

    def _cb(self, msg: Image):
        img = _imgmsg_to_bgr(msg)
        with self._lock:
            self._image = img
            self._stamp = time.monotonic()

    def get_latest(self) -> tuple[Optional[np.ndarray], float]:
        """Return (image_bgr, age_ms). age_ms=inf if no frame received."""
        with self._lock:
            if self._image is None:
                return None, float("inf")
            age_ms = (time.monotonic() - self._stamp) * 1000.0
            return self._image.copy(), age_ms
