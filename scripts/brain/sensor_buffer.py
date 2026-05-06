"""v0.5: /kibou/sensors/* と /kibou/alarm を Subscribe して最新値・履歴を保持。"""
import threading
import time
import rclpy
from rclpy.node import Node
from std_msgs.msg import Float32, Bool


class SensorBuffer(Node):
    def __init__(self, history_sec: float = 60.0):
        super().__init__("sensor_buffer")
        self._lock = threading.Lock()
        self._history_sec = history_sec
        self._records: list[dict] = []
        self._latest: dict = {
            "o2_percent": 21.0,
            "pressure_kpa": 101.3,
            "temperature_c": 22.0,
            "alarm": False,
            "timestamp": 0.0,
        }

        self.create_subscription(Float32, "/kibou/sensors/o2_percent", self._cb_o2, 10)
        self.create_subscription(Float32, "/kibou/sensors/pressure_kpa", self._cb_p, 10)
        self.create_subscription(Float32, "/kibou/sensors/temperature_c", self._cb_t, 10)
        self.create_subscription(Bool, "/kibou/alarm", self._cb_alarm, 10)

    def _record(self):
        with self._lock:
            rec = {**self._latest, "timestamp": time.monotonic()}
            self._records.append(rec)
            cutoff = time.monotonic() - self._history_sec
            self._records = [r for r in self._records if r["timestamp"] >= cutoff]

    def _cb_o2(self, msg: Float32):
        with self._lock:
            self._latest["o2_percent"] = msg.data
        self._record()

    def _cb_p(self, msg: Float32):
        with self._lock:
            self._latest["pressure_kpa"] = msg.data

    def _cb_t(self, msg: Float32):
        with self._lock:
            self._latest["temperature_c"] = msg.data

    def _cb_alarm(self, msg: Bool):
        with self._lock:
            self._latest["alarm"] = msg.data

    def get_latest(self) -> dict:
        with self._lock:
            return {**self._latest}

    def get_history(self, n: int = 15) -> list[dict]:
        with self._lock:
            return list(self._records[-n:])
