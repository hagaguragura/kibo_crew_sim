"""
Phase 2.2 — Attach Camera Prim to Crew_01/HeadMount.
Input:  KIBOU_with_crew01.usd
Output: KIBOU_with_crew01_cam.usd

[VERIFY] usdcat KIBOU_with_crew01_cam.usd | grep Camera_01
[EXPECTED] Camera_01 prim exists under HeadMount
"""
import os
from pxr import Usd, UsdGeom, Gf

SPD_WS      = os.environ["SPD_WS"]
ASSETS      = f"{SPD_WS}/src/kibo_crew_sim/assets"
INPUT_USD   = f"{ASSETS}/KIBOU_with_crew01.usd"
OUTPUT_USD  = f"{ASSETS}/KIBOU_with_crew01_cam.usd"

stage = Usd.Stage.Open(INPUT_USD)

CAM_PATH = "/World/Crew_01/HeadMount/Camera_01"
cam = UsdGeom.Camera.Define(stage, CAM_PATH)

# 解像度・画角設定 (640x480, 横画角~70°)
cam.GetHorizontalApertureAttr().Set(20.955)   # mm, 35mm換算で~24mm相当 → 横画角~70°
cam.GetFocalLengthAttr().Set(18.147)          # mm
cam.GetClippingRangeAttr().Set(Gf.Vec2f(0.05, 50.0))

# HeadMountの正面方向（+Y）に向ける
# Isaac Sim Camera は -Z 方向が前なので +Y 前方に合わせて X軸で-90度回転
cam_xform = UsdGeom.Xformable(cam.GetPrim())
cam_xform.AddRotateXOp().Set(-90.0)

stage.GetRootLayer().Export(OUTPUT_USD)
print(f"[OK] Saved: {OUTPUT_USD}")
print(f"     Camera_01 at {CAM_PATH}")
print(f"     Focal length: 18.1mm  |  H-aperture: 21mm  |  FoV: ~70°")
print(f"     Clip: 0.05–50.0 m")
