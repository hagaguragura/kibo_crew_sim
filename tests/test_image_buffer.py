"""Unit test for ImageBuffer: verify get_latest() returns valid frame within 5s."""

import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../scripts"))

import rclpy
from brain.image_buffer import ImageBuffer

WAIT_SEC = 5
MAX_AGE_MS = 1000


def main():
    rclpy.init()
    buf = ImageBuffer()

    print(f"Waiting up to {WAIT_SEC}s for first frame...")
    import threading
    spin_thread = threading.Thread(target=rclpy.spin, args=(buf,), daemon=True)
    spin_thread.start()

    deadline = time.monotonic() + WAIT_SEC
    while time.monotonic() < deadline:
        img, age_ms = buf.get_latest()
        if img is not None:
            break
        time.sleep(0.1)

    img, age_ms = buf.get_latest()

    buf.destroy_node()
    rclpy.shutdown()

    assert img is not None, "FAIL: no frame received within 5s"
    assert img.shape == (480, 640, 3), f"FAIL: unexpected shape {img.shape}"
    assert age_ms < MAX_AGE_MS, f"FAIL: age_ms={age_ms:.0f} >= {MAX_AGE_MS}"

    print(f"PASS: shape={img.shape}, age_ms={age_ms:.0f}")


if __name__ == "__main__":
    main()
