#!/usr/bin/env python3
"""Phase 1.2: KIBOUシーンにヒューマノイド（球+円柱）を配置してUSDを保存する。

使用方法:
    $SPD_ISAACSIM_PATH/python.sh spawn_humanoid.py [--headless]

[VERIFY] エラーなく完了し KIBOU_with_humanoid.usd が生成される
"""
import sys
import os
import argparse

parser = argparse.ArgumentParser()
parser.add_argument("--headless", action="store_true", default=True)
args, _ = parser.parse_known_args()

from isaacsim import SimulationApp
simulation_app = SimulationApp({"headless": args.headless, "renderer": "RaytracedLighting"})

import omni.usd
from isaacsim.core.utils.stage import open_stage, save_stage
from pxr import Usd, UsdGeom, Gf

# --- 設定 ---
KIBOU_USD = os.path.expandvars(
    "$SPD_WS/src/int-ball2_isaac_sim/int-ball2_isaac_sim/assets/KIBOU.usd"
)
OUTPUT_USD = os.path.expandvars(
    "$SPD_WS/src/int-ball2_isaac_sim/int-ball2_isaac_sim/assets/KIBOU_with_humanoid.usd"
)
HUMANOID_PRIM_PATH = "/World/Humanoid_01"

POINT_A = Gf.Vec3d(20.5, 0.0, 0.3)

SKIN = (0.85, 0.72, 0.60)
SUIT = (0.25, 0.40, 0.65)
BOOT = (0.25, 0.25, 0.25)


def _sph(stage, path, r, pos, color=None):
    s = UsdGeom.Sphere.Define(stage, path)
    s.GetRadiusAttr().Set(r)
    UsdGeom.Xformable(s.GetPrim()).AddTranslateOp().Set(Gf.Vec3d(*pos))
    s.GetDisplayColorAttr().Set([Gf.Vec3f(*(color or SKIN))])


def _cyl(stage, path, r, h, pos, color=None):
    c = UsdGeom.Cylinder.Define(stage, path)
    c.GetRadiusAttr().Set(r)
    c.GetHeightAttr().Set(h)
    c.GetAxisAttr().Set(UsdGeom.Tokens.z)
    UsdGeom.Xformable(c.GetPrim()).AddTranslateOp().Set(Gf.Vec3d(*pos))
    c.GetDisplayColorAttr().Set([Gf.Vec3f(*(color or SUIT))])


def main():
    print(f"[spawn_humanoid] Opening: {KIBOU_USD}")
    if not os.path.exists(KIBOU_USD):
        print(f"ERROR: {KIBOU_USD} not found")
        simulation_app.close()
        sys.exit(1)

    if not open_stage(KIBOU_USD):
        print("ERROR: open_stage failed")
        simulation_app.close()
        sys.exit(1)

    simulation_app.update()
    stage = omni.usd.get_context().get_stage()

    # --- Humanoid_01 ルートXform ---
    B = HUMANOID_PRIM_PATH
    humanoid = UsdGeom.Xform.Define(stage, B)
    humanoid.AddTranslateOp().Set(POINT_A)

    # --- 身体パーツ（ローカルZ: 足元=0、頭頂~1.75m）---
    _sph(stage, f"{B}/Head",           0.12,         (0.00, 0.00, 1.63))
    _cyl(stage, f"{B}/Neck",           0.05, 0.12,   (0.00, 0.00, 1.49))
    _cyl(stage, f"{B}/Torso",          0.17, 0.55,   (0.00, 0.00, 1.12))
    _cyl(stage, f"{B}/Pelvis",         0.14, 0.18,   (0.00, 0.00, 0.74))
    _cyl(stage, f"{B}/LeftUpperArm",   0.05, 0.28,   (-0.22, 0.00, 1.12))
    _cyl(stage, f"{B}/RightUpperArm",  0.05, 0.28,   ( 0.22, 0.00, 1.12))
    _cyl(stage, f"{B}/LeftForearm",    0.04, 0.24,   (-0.22, 0.00, 0.86))
    _cyl(stage, f"{B}/RightForearm",   0.04, 0.24,   ( 0.22, 0.00, 0.86))
    _cyl(stage, f"{B}/LeftUpperLeg",   0.07, 0.38,   (-0.10, 0.00, 0.48))
    _cyl(stage, f"{B}/RightUpperLeg",  0.07, 0.38,   ( 0.10, 0.00, 0.48))
    _cyl(stage, f"{B}/LeftLowerLeg",   0.06, 0.32,   (-0.10, 0.00, 0.16), color=BOOT)
    _cyl(stage, f"{B}/RightLowerLeg",  0.06, 0.32,   ( 0.10, 0.00, 0.16), color=BOOT)

    # --- HeadMount: カメラアタッチメントポイント（USDに含める）---
    head_mount = UsdGeom.Xform.Define(stage, f"{B}/HeadMount")
    UsdGeom.XformCommonAPI(head_mount).SetTranslate(Gf.Vec3d(0.0, 0.12, 1.63))

    # --- 保存 ---
    print(f"[spawn_humanoid] Saving: {OUTPUT_USD}")
    ok = save_stage(OUTPUT_USD, save_and_reload_in_place=False)
    if ok:
        print(f"[spawn_humanoid] DONE. Saved to {OUTPUT_USD}")
    else:
        print("[spawn_humanoid] ERROR: save_stage failed")
        simulation_app.close()
        sys.exit(1)

    simulation_app.close()


if __name__ == "__main__":
    main()
