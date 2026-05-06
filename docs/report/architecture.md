# kibo_crew_sim v0.5 — System Architecture

## Overview

LLM（Claude claude-sonnet-4-6）が判断する自律ヒューマノイドエージェントを
きぼうモジュール内の減圧シナリオに配置し、探索行動・通信戦略・生存判断の
創発を観察するシミュレーション。

---

## System Diagram

```
┌──────────────────────────────────────────────────────────────────┐
│                        Isaac Sim (GUI)                           │
│                                                                  │
│  KIBOU_with_humanoid.usd                                         │
│  ├── /World/Humanoid_01        ← physics agent (XY平面移動)      │
│  │   ├── HeadMount/Camera_01  ← 一人称カメラ 640×480            │
│  │   └── CameraGraph          ← OmniGraph: image→ROS2 bridge    │
│  └── /World/Int_Ball2          ← 固定オブジェクト                │
│                                                                  │
└───────────────────┬──────────────────────────────────────────────┘
                    │ ROS 2 (CycloneDDS)
         ┌──────────┴──────────────────────────┐
         │  Topics                             │
         │  /humanoid_01/image_raw  (640×480)  │
         │  /humanoid_01/cmd_vel   (Twist)     │
         │  /humanoid_01/odom      (Odometry)  │
         │  /kibou/sensors/o2_percent          │
         │  /kibou/sensors/pressure_kpa        │
         │  /kibou/alarm           (Bool)      │
         └──────┬──────────────────┬───────────┘
                │                  │
   ┌────────────┴──────┐  ┌────────┴────────────────┐
   │ brain_loop_node   │  │ environment_sim          │
   │                   │  │                          │
   │ SensorBuffer      │  │ scenario YAML読み込み     │
   │  └ 履歴12ステップ  │  │  trapped_depress_v1.yaml │
   │                   │  │  T+30s: alarm=True        │
   │ ClaudeVLMClient   │  │  O2: 21.0→17.0% (線形)   │
   │  model: claude-   │  │  P:  101.3→85.0 kPa      │
   │  sonnet-4-6       │  └──────────────────────────┘
   │                   │
   │  Input:           │
   │  ├ image (JPEG)   │
   │  ├ mission text   │
   │  ├ odom (XY/yaw)  │
   │  ├ sensors_now    │
   │  ├ sensors_hist   │
   │  ├ memory[-5]     │  ← Previous Memory (self-feedback)
   │  └ action_hist[-8]│  ← Action History (pattern awareness)
   │                   │
   │  Output (JSON):   │
   │  ├ action         │  → cmd_vel
   │  ├ concern_level  │
   │  ├ communicate_text│ → /humanoid_01/comms
   │  └ memory         │  → next cycle's Previous Memory
   │                   │
   │  Log ($SPD_RUNS): │
   │  cycle_XXXX/      │
   │  ├ image.png      │
   │  └ decision.json  │
   └───────────────────┘
```

---

## Key Design Decisions

### Self-Feedback Memory (PDFアーキテクチャ準拠)
LLMが出力した `memory` フィールドを次サイクルの **Previous Memory** として
フィードバック。内部状態が履歴依存で進化し、行動戦略が自律的に変化する。

### Action History
直近8サイクルの行動履歴（action / position / concern / comms_sent）を
プロンプトに含め、Claudeが自分のパターンを認識できるようにする。
→ 「通信を7回試みたが応答なし → 探索へ転換」という行動が創発。

### Movable Range
`X(19.8–21.2) Y(-0.3–2.5)` の物理境界をプロンプトに明示。
Claude自身が「Y=2.5は壁」を発見し、旋回で回避する行動が出現。

---

## Action Space

| Action | 物理動作 | Twist |
|--------|---------|-------|
| move_forward | 現在heading方向へ前進 | linear.y = +0.3 |
| move_backward | 後退 | linear.y = -0.2 |
| turn_left | 左旋回 | angular.z = +0.5 |
| turn_right | 右旋回 | angular.z = -0.5 |
| inspect | 静止・観察 | zero |
| communicate | 地上へ通信 | zero |
| report_status | 内部ログ | zero |

---

## Scenario: trapped_depress_v1

```yaml
# config/scenarios/trapped_depress_v1.yaml
events:
  - t: 30      # T+30s でアラーム発動
    alarm: true
    transitions:
      o2:       { from: 21.0, to: 17.0, duration: 240 }
      pressure: { from: 101.3, to: 85.0, duration: 240 }
```

---

## File Structure

```
kibo_crew_sim/
├── scripts/
│   ├── humanoid_ros2_sim.py     # Isaac Sim + ROS2ブリッジ
│   ├── brain_loop_node.py       # メインブレインループ
│   ├── environment_sim.py       # 環境センサーPublisher
│   └── cycles_to_video.py       # 結果動画生成
├── src/vlm_bench/clients/
│   └── claude_client.py         # Claude API クライアント
├── config/scenarios/
│   └── trapped_depress_v1.yaml  # シナリオ定義
└── docs/report/                 # レポート素材（本ディレクトリ）
```

---

## Coordinate System

| 項目 | 値 |
|------|----|
| upAxis | Z |
| metersPerUnit | 1.0 (m) |
| 初期位置 | X=20.5, Y=0.0, Z=0.3 |
| 移動範囲 | X(19.8–21.2) Y(-0.3–2.5) |
| forward方向 | +Y |
| KIBOU長手 | +X方向 |
