"""
Phase 1.2 — Procedural humanoid (no external textures) into KIBOU scene.
Output: $SPD_WS/src/kibo_crew_sim/assets/KIBOU_with_crew01.usd

[VERIFY] ls $SPD_WS/src/kibo_crew_sim/assets/KIBOU_with_crew01.usd
[EXPECTED] File created; open in GUI for Step 1.3 visual check.
"""
import os
from pxr import Usd, UsdGeom, UsdPhysics, Gf

SPD_WS     = os.environ["SPD_WS"]
KIBOU_USD  = f"{SPD_WS}/src/int-ball2_isaac_sim/int-ball2_isaac_sim/assets/KIBOU.usd"
OUTPUT_USD = f"{SPD_WS}/src/kibo_crew_sim/assets/KIBOU_with_crew01.usd"

POINT_A    = Gf.Vec3d(20.5, 0.5, 0.8)   # feet land here

SKIN  = (0.85, 0.72, 0.60)
SUIT  = (0.25, 0.40, 0.65)   # blue jumpsuit
BOOT  = (0.25, 0.25, 0.25)

stage = Usd.Stage.Open(KIBOU_USD)
B = "/World/Crew_01"

# --- helpers ---
def _cyl(path, r, h, pos, axis="Z", color=SUIT):
    c = UsdGeom.Cylinder.Define(stage, path)
    c.GetRadiusAttr().Set(r)
    c.GetHeightAttr().Set(h)
    c.GetAxisAttr().Set({"X": UsdGeom.Tokens.x,
                         "Y": UsdGeom.Tokens.y,
                         "Z": UsdGeom.Tokens.z}[axis])
    UsdGeom.Xformable(c.GetPrim()).AddTranslateOp().Set(Gf.Vec3d(*pos))
    c.GetDisplayColorAttr().Set([Gf.Vec3f(*color)])

def _sph(path, r, pos, color=SKIN):
    s = UsdGeom.Sphere.Define(stage, path)
    s.GetRadiusAttr().Set(r)
    UsdGeom.Xformable(s.GetPrim()).AddTranslateOp().Set(Gf.Vec3d(*pos))
    s.GetDisplayColorAttr().Set([Gf.Vec3f(*color)])

# --- Crew_01 root xform ---
crew = UsdGeom.Xform.Define(stage, B)
UsdGeom.XformCommonAPI(crew).SetTranslate(POINT_A)

# --- body parts (local Z: feet=0, head~1.75m) ---
#           path                  r      h      (x,    y,    z)
_sph(f"{B}/Head",               0.12,         ( 0.00, 0.00, 1.63))
_cyl(f"{B}/Neck",               0.05,  0.12,  ( 0.00, 0.00, 1.49))
_cyl(f"{B}/Torso",              0.17,  0.55,  ( 0.00, 0.00, 1.12))
_cyl(f"{B}/Pelvis",             0.14,  0.18,  ( 0.00, 0.00, 0.74))
_cyl(f"{B}/LeftUpperArm",       0.05,  0.28,  (-0.22, 0.00, 1.12))
_cyl(f"{B}/RightUpperArm",      0.05,  0.28,  ( 0.22, 0.00, 1.12))
_cyl(f"{B}/LeftForearm",        0.04,  0.24,  (-0.22, 0.00, 0.86))
_cyl(f"{B}/RightForearm",       0.04,  0.24,  ( 0.22, 0.00, 0.86))
_cyl(f"{B}/LeftUpperLeg",       0.07,  0.38,  (-0.10, 0.00, 0.48))
_cyl(f"{B}/RightUpperLeg",      0.07,  0.38,  ( 0.10, 0.00, 0.48))
_cyl(f"{B}/LeftLowerLeg",       0.06,  0.32,  (-0.10, 0.00, 0.16), color=BOOT)
_cyl(f"{B}/RightLowerLeg",      0.06,  0.32,  ( 0.10, 0.00, 0.16), color=BOOT)

# HeadMount Xform: camera attachment point for Phase 2
head_mount = UsdGeom.Xform.Define(stage, f"{B}/HeadMount")
UsdGeom.XformCommonAPI(head_mount).SetTranslate(Gf.Vec3d(0.0, 0.12, 1.63))

# Kinematic: won't fall under gravity
UsdPhysics.RigidBodyAPI.Apply(crew.GetPrim()).CreateKinematicEnabledAttr(True)

stage.GetRootLayer().Export(OUTPUT_USD)
print(f"[OK] Saved: {OUTPUT_USD}")
print(f"     Crew_01 root at {tuple(POINT_A)}")
print(f"     HeadMount: /World/Crew_01/HeadMount  (local z=1.63, y=+0.12 forward)")
print(f"     Height: ~1.75 m, no external texture dependencies")
