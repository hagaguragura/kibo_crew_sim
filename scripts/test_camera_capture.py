"""
Phase 2.3 — Headless 1-frame capture from Crew_01 head camera.
Opens original KIBOU.usd and adds crew+camera at runtime (no path breakage).
Output: $SPD_RUNS/v0.2/phase2/test_capture.png

[VERIFY] ls $SPD_RUNS/v0.2/phase2/test_capture.png
[EXPECTED] PNG showing KIBOU interior from crew_01 first-person view
"""
import os
import numpy as np

SPD_WS   = os.environ["SPD_WS"]
SPD_RUNS = os.environ["SPD_RUNS"]
OUT_DIR  = f"{SPD_RUNS}/v0.2/phase2"
OUT_PNG  = f"{OUT_DIR}/test_capture.png"
os.makedirs(OUT_DIR, exist_ok=True)

KIBOU_USD = f"{SPD_WS}/src/int-ball2_isaac_sim/int-ball2_isaac_sim/assets/KIBOU.usd"
CAM_PATH  = "/World/Crew_01/HeadMount/Camera_01"
POINT_A   = (20.5, 0.5, 0.8)

from isaacsim import SimulationApp
app = SimulationApp({"headless": True, "width": 640, "height": 480,
                    "renderer": "RayTracedLighting"})

import omni.isaac.core.utils.stage as stage_utils
from omni.isaac.sensor import Camera
from pxr import UsdGeom, UsdPhysics, Gf

# 元のKIBOU.usdを開く（相対パスが正しく解決される）
stage_utils.open_stage(KIBOU_USD)
for _ in range(5):
    app.update()

import omni.usd
stage = omni.usd.get_context().get_stage()
# ペイロードを明示的にロード
stage.Load("/World/KIBOU")
stage.Load("/World/Int_Ball2")
for _ in range(5):
    app.update()

# Crew_01 をランタイムで追加
B = "/World/Crew_01"
crew = UsdGeom.Xform.Define(stage, B)
UsdGeom.XformCommonAPI(crew).SetTranslate(Gf.Vec3d(*POINT_A))

def _sph(path, r, pos, color=(0.85, 0.72, 0.60)):
    s = UsdGeom.Sphere.Define(stage, path)
    s.GetRadiusAttr().Set(r)
    UsdGeom.Xformable(s.GetPrim()).AddTranslateOp().Set(Gf.Vec3d(*pos))
    s.GetDisplayColorAttr().Set([Gf.Vec3f(*color)])

def _cyl(path, r, h, pos, axis="Z", color=(0.25, 0.40, 0.65)):
    c = UsdGeom.Cylinder.Define(stage, path)
    c.GetRadiusAttr().Set(r)
    c.GetHeightAttr().Set(h)
    c.GetAxisAttr().Set({"X": UsdGeom.Tokens.x, "Y": UsdGeom.Tokens.y, "Z": UsdGeom.Tokens.z}[axis])
    UsdGeom.Xformable(c.GetPrim()).AddTranslateOp().Set(Gf.Vec3d(*pos))
    c.GetDisplayColorAttr().Set([Gf.Vec3f(*color)])

_sph(f"{B}/Head",          0.12, (0, 0, 1.63))
_cyl(f"{B}/Torso",         0.17, 0.55, (0, 0, 1.12))
_cyl(f"{B}/LeftUpperLeg",  0.07, 0.38, (-0.10, 0, 0.48))
_cyl(f"{B}/RightUpperLeg", 0.07, 0.38, ( 0.10, 0, 0.48))
_cyl(f"{B}/LeftLowerLeg",  0.06, 0.32, (-0.10, 0, 0.16), color=(0.25, 0.25, 0.25))
_cyl(f"{B}/RightLowerLeg", 0.06, 0.32, ( 0.10, 0, 0.16), color=(0.25, 0.25, 0.25))

# HeadMount + Camera
head_mount = UsdGeom.Xform.Define(stage, f"{B}/HeadMount")
UsdGeom.XformCommonAPI(head_mount).SetTranslate(Gf.Vec3d(0.0, 0.12, 1.63))
cam_prim = UsdGeom.Camera.Define(stage, CAM_PATH)
cam_prim.GetHorizontalApertureAttr().Set(20.955)
cam_prim.GetFocalLengthAttr().Set(18.147)
cam_prim.GetClippingRangeAttr().Set(Gf.Vec2f(0.05, 50.0))
UsdGeom.Xformable(cam_prim.GetPrim()).AddRotateXOp().Set(-90.0)

# レンダラー安定化
for _ in range(15):
    app.update()

# Isaac Sim 4.x: replicator API でキャプチャ
import omni.replicator.core as rep
from omni.isaac.core import SimulationContext

# KIBOUシーンにDomeLightを追加（ライティング補完）
from pxr import UsdLux
dome = UsdLux.DomeLight.Define(stage, "/World/CaptureDomeLight")
dome.GetIntensityAttr().Set(500)

sim = SimulationContext()
sim.play()
for _ in range(20):
    sim.step(render=True)

# KIBOU世界座標: X(15.4,25.6) Y(-1.4,1.56) Z(-0.24,5.29)
# v0.1と同じ座標でHeadMount位置
HEAD_WORLD = (20.5, 0.62, 2.43)  # POINT_A + HeadMount offset
LOOK_AT    = (20.5, 1.5, 2.43)   # KIBOU内部方向
cam_rep = rep.create.camera(
    position=HEAD_WORLD,
    look_at=LOOK_AT,
)
render_product = rep.create.render_product(cam_rep, (640, 480))
rgb_annot = rep.AnnotatorRegistry.get_annotator("rgb")
rgb_annot.attach([render_product])

rep.orchestrator.run_until_complete(num_frames=20)

data = rgb_annot.get_data()
_log = open("/tmp/capture_result.txt", "w")
_log.write(f"data type={type(data)}\n")
_log.flush()

if data is None:
    _log.write("ERROR: annotator returned None\n"); _log.close()
    app.close(); raise SystemExit(1)

if isinstance(data, dict):
    _log.write(f"data keys={list(data.keys())}\n"); _log.flush()
    arr = np.asarray(data.get("data", next(iter(data.values()))))
else:
    arr = np.asarray(data)

_log.write(f"shape={arr.shape} dtype={arr.dtype} size={arr.size}\n"); _log.flush()

if arr.size == 0:
    _log.write("ERROR: empty frame\n"); _log.close()
    app.close(); raise SystemExit(1)

if arr.dtype != np.uint8:
    arr = (np.clip(arr, 0.0, 1.0) * 255).astype(np.uint8)

npy_path = OUT_PNG.replace(".png", ".npy")
np.save(npy_path, arr)
_log.write(f"numpy saved: {npy_path}\n"); _log.flush()

try:
    from PIL import Image
    if arr.ndim == 3 and arr.shape[2] == 4:
        arr = arr[..., :3]
    img = Image.fromarray(arr.copy())
    img.save(OUT_PNG)
    _log.write(f"OK PNG: {OUT_PNG} {img.size}\n")
except Exception as e:
    _log.write(f"WARN PNG failed: {e}\n")
_log.close()

app.close()
