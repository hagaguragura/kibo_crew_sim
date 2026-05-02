#!/usr/bin/env python3
"""Phase 3: ヒューマノイド Isaac Sim + ROS2 ブリッジ。

/humanoid_01/odom を Publish し、
/humanoid_01/cmd_vel (Twist) を受信してヒューマノイドを動かす。

使用方法:
    export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
    source /opt/ros/humble/setup.bash
    $SPD_ISAACSIM_PATH/python.sh humanoid_ros2_sim.py
"""
import sys
import os
import time
import numpy as np

from isaacsim import SimulationApp
simulation_app = SimulationApp({"headless": True, "renderer": "RaytracedLighting"})

from isaacsim.core.utils.extensions import enable_extension
enable_extension("isaacsim.ros2.bridge")
simulation_app.update()

import omni.usd
import omni.timeline
from isaacsim.core.utils.stage import open_stage
from pxr import Usd, UsdGeom, Gf

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry

KIBOU_USD = os.path.expandvars(
    "$SPD_WS/src/int-ball2_isaac_sim/int-ball2_isaac_sim/assets/KIBOU_with_humanoid.usd"
)
HUMANOID_PATH = "/World/Humanoid_01"
INITIAL_POS = np.array([20.5, 0.5, 0.8])

X_MIN, X_MAX = 19.0, 22.0
Y_MIN, Y_MAX = -1.0, 5.0
Z = 0.8


class HumanoidSimNode(Node):
    def __init__(self):
        super().__init__("humanoid_sim")
        self.position = INITIAL_POS.copy()
        self.cmd_vel = np.zeros(3)
        self.dt = 1.0 / 10.0  # 10Hz に合わせる

        self.pub_odom = self.create_publisher(Odometry, "/humanoid_01/odom", 10)
        self.sub_cmd = self.create_subscription(
            Twist, "/humanoid_01/cmd_vel", self._cmd_vel_cb, 10
        )
        self.get_logger().info("HumanoidSimNode initialized.")

    def _cmd_vel_cb(self, msg: Twist):
        self.cmd_vel = np.array([msg.linear.x, msg.linear.y, msg.linear.z])
        self.get_logger().info(
            f"cmd_vel received: x={msg.linear.x:.2f} y={msg.linear.y:.2f}"
        )

    def update(self, translate_op):
        # 位置更新
        delta = self.cmd_vel * self.dt
        new_pos = self.position + delta
        new_pos[0] = float(np.clip(new_pos[0], X_MIN, X_MAX))
        new_pos[1] = float(np.clip(new_pos[1], Y_MIN, Y_MAX))
        new_pos[2] = Z
        self.position = new_pos

        # USD更新
        if translate_op:
            translate_op.Set(Gf.Vec3d(*self.position))

        # odom publish
        msg = Odometry()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = "world"
        msg.pose.pose.position.x = float(self.position[0])
        msg.pose.pose.position.y = float(self.position[1])
        msg.pose.pose.position.z = float(self.position[2])
        msg.pose.pose.orientation.w = 1.0
        msg.twist.twist.linear.x = float(self.cmd_vel[0])
        msg.twist.twist.linear.y = float(self.cmd_vel[1])
        self.pub_odom.publish(msg)


def get_translate_op(stage, prim_path):
    prim = stage.GetPrimAtPath(prim_path)
    if not prim.IsValid():
        return None
    xformable = UsdGeom.Xformable(prim)
    for op in xformable.GetOrderedXformOps():
        if "translate" in op.GetOpName():
            return op
    return xformable.AddTranslateOp()


def main():
    if not os.path.exists(KIBOU_USD):
        print(f"ERROR: {KIBOU_USD} not found.")
        simulation_app.close()
        sys.exit(1)

    open_stage(KIBOU_USD)
    simulation_app.update()

    stage = omni.usd.get_context().get_stage()
    timeline = omni.timeline.get_timeline_interface()
    translate_op = get_translate_op(stage, HUMANOID_PATH)

    rclpy.init()
    node = HumanoidSimNode()
    timeline.play()

    print("[humanoid_ros2_sim] Running. Ctrl+C to stop.")
    try:
        while simulation_app.is_running():
            # cmd_vel を受信するために十分待つ
            rclpy.spin_once(node, timeout_sec=0.05)
            # 位置更新 + odom publish
            node.update(translate_op)
            # Isaac Sim 描画
            simulation_app.update()
    except KeyboardInterrupt:
        pass
    finally:
        timeline.stop()
        node.destroy_node()
        rclpy.shutdown()
        simulation_app.close()


if __name__ == "__main__":
    main()
