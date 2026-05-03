#!/usr/bin/env python3
"""Phase 3: Crew_01 Isaac Sim + ROS2 ブリッジ (v0.2)

Publish:
  /crew_01/odom        (nav_msgs/Odometry)
  /crew_01/image_raw   (sensor_msgs/Image, 5Hz)
Subscribe:
  /crew_01/cmd_vel     (geometry_msgs/Twist)

使用方法:
    export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
    source /opt/ros/humble/setup.bash
    $SPD_ISAACSIM_PATH/python.sh crew01_ros2_sim.py
"""
import os
import sys
import numpy as np
from isaacsim import SimulationApp

simulation_app = SimulationApp({"headless": True, "renderer": "RayTracedLighting"})

from isaacsim.core.utils.extensions import enable_extension
enable_extension("isaacsim.ros2.bridge")
simulation_app.update()

import omni.usd
import omni.timeline
import omni.graph.core as og
import omni.replicator.core as rep
from isaacsim.core.utils.stage import open_stage
from pxr import Usd, UsdGeom, UsdPhysics, UsdLux, Gf

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry

SPD_WS   = os.environ["SPD_WS"]
KIBOU_USD = f"{SPD_WS}/src/int-ball2_isaac_sim/int-ball2_isaac_sim/assets/KIBOU.usd"

CREW_PATH  = "/World/Crew_01"
CAM_PATH   = "/World/Crew_01/HeadMount/Camera_01"
POINT_A    = np.array([20.5, 0.5, 0.8])
POINT_B    = np.array([20.5, 1.3, 0.8])

X_MIN, X_MAX = 19.0, 22.0
Y_MIN, Y_MAX = -1.0,  1.5
Z_FIXED      = 0.8

SUIT  = (0.25, 0.40, 0.65)
SKIN  = (0.85, 0.72, 0.60)
BOOT  = (0.25, 0.25, 0.25)

CAM_RES = (640, 480)
CAM_HZ  = 5  # Hz


def build_crew01(stage):
    B = CREW_PATH
    crew = UsdGeom.Xform.Define(stage, B)
    UsdGeom.XformCommonAPI(crew).SetTranslate(Gf.Vec3d(*POINT_A))

    def _sph(path, r, pos, color=SKIN):
        s = UsdGeom.Sphere.Define(stage, path)
        s.GetRadiusAttr().Set(r)
        UsdGeom.Xformable(s.GetPrim()).AddTranslateOp().Set(Gf.Vec3d(*pos))
        s.GetDisplayColorAttr().Set([Gf.Vec3f(*color)])

    def _cyl(path, r, h, pos, axis="Z", color=SUIT):
        c = UsdGeom.Cylinder.Define(stage, path)
        c.GetRadiusAttr().Set(r)
        c.GetHeightAttr().Set(h)
        c.GetAxisAttr().Set({"X": UsdGeom.Tokens.x, "Y": UsdGeom.Tokens.y,
                              "Z": UsdGeom.Tokens.z}[axis])
        UsdGeom.Xformable(c.GetPrim()).AddTranslateOp().Set(Gf.Vec3d(*pos))
        c.GetDisplayColorAttr().Set([Gf.Vec3f(*color)])

    _sph(f"{B}/Head",          0.12, (0,     0,    1.63))
    _cyl(f"{B}/Neck",          0.05, 0.12,  (0,    0,    1.49), color=SKIN)
    _cyl(f"{B}/Torso",         0.17, 0.55,  (0,    0,    1.12))
    _cyl(f"{B}/Pelvis",        0.14, 0.18,  (0,    0,    0.74))
    _cyl(f"{B}/LeftUpperArm",  0.05, 0.28,  (-0.22,0,    1.12))
    _cyl(f"{B}/RightUpperArm", 0.05, 0.28,  ( 0.22,0,    1.12))
    _cyl(f"{B}/LeftForearm",   0.04, 0.24,  (-0.22,0,    0.86))
    _cyl(f"{B}/RightForearm",  0.04, 0.24,  ( 0.22,0,    0.86))
    _cyl(f"{B}/LeftUpperLeg",  0.07, 0.38,  (-0.10,0,    0.48))
    _cyl(f"{B}/RightUpperLeg", 0.07, 0.38,  ( 0.10,0,    0.48))
    _cyl(f"{B}/LeftLowerLeg",  0.06, 0.32,  (-0.10,0,    0.16), color=BOOT)
    _cyl(f"{B}/RightLowerLeg", 0.06, 0.32,  ( 0.10,0,    0.16), color=BOOT)

    head_mount = UsdGeom.Xform.Define(stage, f"{B}/HeadMount")
    UsdGeom.XformCommonAPI(head_mount).SetTranslate(Gf.Vec3d(0.0, 0.12, 1.63))

    cam = UsdGeom.Camera.Define(stage, CAM_PATH)
    cam.GetHorizontalApertureAttr().Set(20.955)
    cam.GetFocalLengthAttr().Set(18.147)
    cam.GetClippingRangeAttr().Set(Gf.Vec2f(0.05, 50.0))
    UsdGeom.Xformable(cam.GetPrim()).AddRotateXOp().Set(90.0)

    UsdPhysics.RigidBodyAPI.Apply(crew.GetPrim()).CreateKinematicEnabledAttr(True)
    return crew


def setup_ros2_camera(render_product_path: str):
    keys = og.Controller.Keys
    og.Controller.edit(
        {"graph_path": "/World/Crew_01/CameraGraph", "evaluator_name": "push"},
        {
            keys.CREATE_NODES: [
                ("OnTick",     "omni.graph.action.OnPlaybackTick"),
                ("ROSCtx",     "isaacsim.ros2.bridge.ROS2Context"),
                ("CamHelper",  "isaacsim.ros2.bridge.ROS2CameraHelper"),
            ],
            keys.CONNECT: [
                ("OnTick.outputs:tick",       "CamHelper.inputs:execIn"),
                ("ROSCtx.outputs:context",    "CamHelper.inputs:context"),
            ],
            keys.SET_VALUES: [
                ("CamHelper.inputs:topicName",         "/crew_01/image_raw"),
                ("CamHelper.inputs:frameId",           "crew_01_camera"),
                ("CamHelper.inputs:type",              "rgb"),
                ("CamHelper.inputs:renderProductPath", render_product_path),
                ("ROSCtx.inputs:domain_id",            0),
            ],
        },
    )


def get_translate_op(stage, prim_path):
    prim = stage.GetPrimAtPath(prim_path)
    if not prim.IsValid():
        return None
    xformable = UsdGeom.Xformable(prim)
    for op in xformable.GetOrderedXformOps():
        if "translate" in op.GetOpName():
            return op
    return xformable.AddTranslateOp()


class CrewSimNode(Node):
    def __init__(self):
        super().__init__("crew01_sim")
        self.position  = POINT_A.copy()
        self.cmd_vel   = np.zeros(3)
        self.dt        = 1.0 / 10.0

        self.pub_odom = self.create_publisher(Odometry, "/crew_01/odom", 10)
        self.sub_cmd  = self.create_subscription(
            Twist, "/crew_01/cmd_vel", self._cmd_cb, 10
        )
        self.get_logger().info("CrewSimNode ready.")

    def _cmd_cb(self, msg: Twist):
        self.cmd_vel = np.array([msg.linear.x, msg.linear.y, msg.linear.z])

    def update(self, translate_op):
        new_pos = self.position + self.cmd_vel * self.dt
        new_pos[0] = float(np.clip(new_pos[0], X_MIN, X_MAX))
        new_pos[1] = float(np.clip(new_pos[1], Y_MIN, Y_MAX))
        new_pos[2] = Z_FIXED
        self.position = new_pos

        if translate_op:
            translate_op.Set(Gf.Vec3d(*self.position))

        msg = Odometry()
        msg.header.stamp       = self.get_clock().now().to_msg()
        msg.header.frame_id    = "world"
        msg.pose.pose.position.x = float(self.position[0])
        msg.pose.pose.position.y = float(self.position[1])
        msg.pose.pose.position.z = float(self.position[2])
        msg.pose.pose.orientation.w = 1.0
        msg.twist.twist.linear.x = float(self.cmd_vel[0])
        msg.twist.twist.linear.y = float(self.cmd_vel[1])
        self.pub_odom.publish(msg)


def main():
    open_stage(KIBOU_USD)
    simulation_app.update()

    stage = omni.usd.get_context().get_stage()
    stage.Load("/World/KIBOU")

    # KIBOU内部照明（DomeLightは外壁を貫通しないのでSphereLight追加）
    for i, pos in enumerate([(20.5, 0.0, 2.5), (20.5, 0.0, 0.5)]):
        sl = UsdLux.SphereLight.Define(stage, f"/World/KibouInteriorLight_{i}")
        sl.GetIntensityAttr().Set(5000)
        sl.GetRadiusAttr().Set(0.1)
        UsdGeom.Xformable(sl.GetPrim()).AddTranslateOp().Set(Gf.Vec3d(*pos))

    build_crew01(stage)
    simulation_app.update()

    # Render product → ROS2 Camera Helper
    rp = rep.create.render_product(CAM_PATH, CAM_RES)
    setup_ros2_camera(rp.path)
    simulation_app.update()

    translate_op = get_translate_op(stage, CREW_PATH)
    timeline = omni.timeline.get_timeline_interface()

    rclpy.init()
    node = CrewSimNode()
    timeline.play()

    print("[crew01_ros2_sim] Running.")
    print("  /crew_01/odom       — Odometry")
    print("  /crew_01/image_raw  — Camera (5Hz)")
    print("  /crew_01/cmd_vel    — Command velocity (subscribe)")
    print("Ctrl+C to stop.")

    try:
        while simulation_app.is_running():
            rclpy.spin_once(node, timeout_sec=0.05)
            node.update(translate_op)
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
