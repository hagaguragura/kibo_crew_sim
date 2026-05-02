#!/usr/bin/env python3
"""Phase 1.2: KIBOUシーンにヒューマノイド（Capsule Prim）を配置してUSDを保存する。

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
from isaacsim.core.utils.extensions import enable_extension
from pxr import Usd, UsdGeom, Gf

# --- 設定 ---
KIBOU_USD = os.path.expandvars(
    "$SPD_WS/src/int-ball2_isaac_sim/int-ball2_isaac_sim/assets/KIBOU.usd"
)
OUTPUT_USD = os.path.expandvars(
    "$SPD_WS/src/int-ball2_isaac_sim/int-ball2_isaac_sim/assets/KIBOU_with_humanoid.usd"
)
HUMANOID_PRIM_PATH = "/World/Humanoid_01"

# KIBOU world座標内、モジュール内ハッチ前の床面付近
# KIBOU center: (20, 0, 0), Int-Ball2 initial: (20.17, 3.06, 2.21)
# 床面: Z ~0.8（Int-Ball2のXY飛行高度Z~2.21から下の床面付近）
HUMANOID_POS = Gf.Vec3d(20.5, 0.5, 0.8)

# Capsule パラメータ（人体近似: 全高~1.6m）
CAPSULE_RADIUS = 0.25   # m
CAPSULE_HEIGHT = 1.1    # m（cylinderパート）
CAPSULE_AXIS   = "Z"


def main():
    print(f"[spawn_humanoid] Opening: {KIBOU_USD}")
    if not os.path.exists(KIBOU_USD):
        print(f"ERROR: {KIBOU_USD} not found")
        simulation_app.close()
        sys.exit(1)

    result = open_stage(KIBOU_USD)
    if not result:
        print("ERROR: open_stage failed")
        simulation_app.close()
        sys.exit(1)

    simulation_app.update()

    stage = omni.usd.get_context().get_stage()

    # --- ヒューマノイドXformを作成 ---
    print(f"[spawn_humanoid] Creating prim: {HUMANOID_PRIM_PATH}")
    xform_prim = UsdGeom.Xform.Define(stage, HUMANOID_PRIM_PATH)
    xform_prim.AddTranslateOp().Set(HUMANOID_POS)

    # --- Capsule（ヒューマノイドの代替形状）を追加 ---
    capsule_path = f"{HUMANOID_PRIM_PATH}/Body"
    capsule = UsdGeom.Capsule.Define(stage, capsule_path)
    capsule.GetRadiusAttr().Set(CAPSULE_RADIUS)
    capsule.GetHeightAttr().Set(CAPSULE_HEIGHT)
    capsule.GetAxisAttr().Set(CAPSULE_AXIS)

    # 色: 緑（目視確認しやすいよう）
    capsule.GetDisplayColorAttr().Set([(0.1, 0.8, 0.2)])

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
