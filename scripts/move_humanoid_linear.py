#!/usr/bin/env python3
"""Phase 2.2: ヒューマノイドを連続（速度ベース）移動させる（5秒かけてA→B）。

使用方法:
    $SPD_ISAACSIM_PATH/python.sh move_humanoid_linear.py

[VERIFY] GUIでヒューマノイドが滑らかにA→Bへスライドする
"""
import sys
import os
import time
import numpy as np

from isaacsim import SimulationApp
simulation_app = SimulationApp({"headless": False, "renderer": "RaytracedLighting"})

import omni.usd
import omni.timeline
from isaacsim.core.utils.stage import open_stage
from pxr import Usd, UsdGeom, Gf

KIBOU_USD = os.path.expandvars("$SPD_WS/src/int-ball2_isaac_sim/int-ball2_isaac_sim/assets/KIBOU_with_humanoid.usd")
HUMANOID_PATH = "/World/Humanoid_01"
POS_A = np.array([20.5, 0.5, 0.8])
POS_B = np.array([20.5, 3.5, 0.8])
DURATION = 5.0   # 秒
RENDER_HZ = 30.0


def get_translate_op(stage, prim_path: str):
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
        print(f"ERROR: {KIBOU_USD} not found. Run spawn_humanoid.py first.")
        simulation_app.close()
        sys.exit(1)

    open_stage(KIBOU_USD)
    simulation_app.update()

    stage = omni.usd.get_context().get_stage()
    timeline = omni.timeline.get_timeline_interface()
    translate_op = get_translate_op(stage, HUMANOID_PATH)

    if translate_op is None:
        print(f"ERROR: translateOp not found on {HUMANOID_PATH}")
        simulation_app.close()
        sys.exit(1)

    # 初期位置A
    translate_op.Set(Gf.Vec3d(*POS_A))
    simulation_app.update()
    timeline.play()

    print("[linear] Moving A → B over 5 seconds...")
    dt = 1.0 / RENDER_HZ
    steps = int(DURATION * RENDER_HZ)

    for i in range(steps):
        t = i / float(steps)  # 0 → 1
        pos = POS_A + t * (POS_B - POS_A)
        translate_op.Set(Gf.Vec3d(*pos))
        simulation_app.update()
        time.sleep(dt)

    # 最終位置B
    translate_op.Set(Gf.Vec3d(*POS_B))
    simulation_app.update()

    print("[linear] DONE. Holding at B for 3 seconds...")
    t0 = time.time()
    while time.time() - t0 < 3.0:
        simulation_app.update()

    timeline.stop()
    simulation_app.close()


if __name__ == "__main__":
    main()
