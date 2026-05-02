#!/usr/bin/env python3
"""Phase 2.1: ヒューマノイドをワープ移動させる（5秒後に座標B へテレポート）。

使用方法:
    $SPD_ISAACSIM_PATH/python.sh move_humanoid_warp.py

[VERIFY] GUIでヒューマノイドがA→Bに瞬間移動する
"""
import sys
import os
import time

from isaacsim import SimulationApp
simulation_app = SimulationApp({"headless": False, "renderer": "RaytracedLighting"})

import omni.usd
import omni.timeline
from isaacsim.core.utils.stage import open_stage
from pxr import Usd, UsdGeom, Gf

KIBOU_USD = os.path.expandvars("$SPD_WS/src/int-ball2_isaac_sim/int-ball2_isaac_sim/assets/KIBOU_with_humanoid.usd")
HUMANOID_PATH = "/World/Humanoid_01"
POS_A = Gf.Vec3d(20.5, 0.5, 0.8)   # ハッチ前
POS_B = Gf.Vec3d(20.5, 3.5, 0.8)   # 実験ラック前


def set_humanoid_position(stage, pos: Gf.Vec3d):
    prim = stage.GetPrimAtPath(HUMANOID_PATH)
    if not prim.IsValid():
        print(f"ERROR: {HUMANOID_PATH} not found")
        return False
    xformable = UsdGeom.Xformable(prim)
    ops = xformable.GetOrderedXformOps()
    for op in ops:
        if "translate" in op.GetOpName():
            op.Set(pos)
            return True
    # translateOpがなければ追加
    xformable.AddTranslateOp().Set(pos)
    return True


def main():
    if not os.path.exists(KIBOU_USD):
        print(f"ERROR: {KIBOU_USD} not found. Run spawn_humanoid.py first.")
        simulation_app.close()
        sys.exit(1)

    open_stage(KIBOU_USD)
    simulation_app.update()

    stage = omni.usd.get_context().get_stage()
    timeline = omni.timeline.get_timeline_interface()

    # 初期位置A
    set_humanoid_position(stage, POS_A)
    simulation_app.update()

    print("[warp] Simulation started. Humanoid at position A.")
    timeline.play()

    # 10秒待機（位置A確認）
    print("[warp] Holding at position A for 10 seconds...")
    t0 = time.time()
    while time.time() - t0 < 10.0:
        simulation_app.update()

    # 位置Bにワープ
    print("[warp] Warping to position B...")
    set_humanoid_position(stage, POS_B)
    simulation_app.update()

    # 20秒待機して目視確認
    print("[warp] Holding at position B for 20 seconds...")
    t0 = time.time()
    while time.time() - t0 < 20.0:
        simulation_app.update()

    print("[warp] DONE. Humanoid moved from A to B.")
    timeline.stop()
    simulation_app.close()


if __name__ == "__main__":
    main()
