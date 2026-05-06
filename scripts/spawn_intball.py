#!/usr/bin/env python3
"""Int-Ball2 を KIBOU シーン内に配置するユーティリティ。

humanoid_ros2_sim.py から open_stage() の直後に呼び出す。
位置は DEFAULT_POS 定数で管理する。テスト時は --pos で上書き可能。

単独実行:
    $SPD_ISAACSIM_PATH/python.sh spawn_intball.py [--pos "21.5,1.0,1.2"]
"""
import os
import sys
import argparse

INTBALL2_USD = os.path.expandvars(
    "$SPD_WS/src/int-ball2_isaac_sim/int-ball2_isaac_sim/assets/Intball2/Intball2.usd"
)
INTBALL2_PRIM_PATH = "/World/IntBall2"
DEFAULT_POS = "21.5,1.0,1.2"


def spawn_intball(stage, pos_str: str | None = None) -> str:
    """ステージに Int-Ball2 を配置して prim path を返す。

    Args:
        stage: USD ステージ (omni.usd.get_context().get_stage())
        pos_str: "x,y,z" 文字列。None の場合は DEFAULT_POS を使用。
    Returns:
        配置した prim path ("/World/IntBall2")
    """
    from pxr import UsdGeom, Gf, Sdf

    if pos_str is None:
        pos_str = DEFAULT_POS

    try:
        x, y, z = [float(v) for v in pos_str.split(",")]
    except ValueError:
        print(f"[spawn_intball] WARNING: invalid pos '{pos_str}', using default.")
        x, y, z = [float(v) for v in DEFAULT_POS.split(",")]

    if not os.path.exists(INTBALL2_USD):
        print(f"[spawn_intball] ERROR: {INTBALL2_USD} not found.")
        return ""

    xform = UsdGeom.Xform.Define(stage, INTBALL2_PRIM_PATH)
    xform.AddTranslateOp().Set(Gf.Vec3d(x, y, z))
    xform.GetPrim().GetReferences().AddReference(INTBALL2_USD)

    print(f"[spawn_intball] Int-Ball2 placed at ({x:.2f}, {y:.2f}, {z:.2f}) → {INTBALL2_PRIM_PATH}")
    return INTBALL2_PRIM_PATH


# ── 単独実行モード ────────────────────────────────────────────────────────
def _standalone():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pos", default=DEFAULT_POS)
    parser.add_argument("--headless", action="store_true", default=True)
    args, _ = parser.parse_known_args()

    from isaacsim import SimulationApp
    simulation_app = SimulationApp({"headless": args.headless, "renderer": "RaytracedLighting"})

    import omni.usd
    from isaacsim.core.utils.stage import open_stage

    KIBOU_USD = os.path.expandvars(
        "$SPD_WS/src/int-ball2_isaac_sim/int-ball2_isaac_sim/assets/KIBOU_with_humanoid.usd"
    )
    if not os.path.exists(KIBOU_USD):
        print(f"ERROR: {KIBOU_USD} not found")
        simulation_app.close()
        sys.exit(1)

    open_stage(KIBOU_USD)
    simulation_app.update()

    stage = omni.usd.get_context().get_stage()
    spawn_intball(stage, args.pos)
    simulation_app.update()

    print("[spawn_intball] Done. Press Ctrl+C to close.")
    try:
        while simulation_app.is_running():
            simulation_app.update()
    except KeyboardInterrupt:
        pass
    finally:
        simulation_app.close()


if __name__ == "__main__":
    _standalone()
