#!/usr/bin/env bash
# Phase 6.2: A→Bデモ 全自動実行スクリプト
#
# 実行前提:
#   1. spawn_humanoid.py が完了し KIBOU_with_humanoid.usd が存在する
#   2. ROS2 Humble + CycloneDDS がセットアップ済み
#
# 使用方法:
#   bash run_demo_a_to_b.sh [--timeout 300]
#
# [VERIFY] ヒューマノイドがAからBに到達して rosbag2 MCAP が生成される

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TIMEOUT=${1:-300}
BAGDIR="$SPD_RUNS/demo_humanoid_a_to_b/$(date +%Y-%m-%d_%H-%M-%S)"
KIBOU_WITH_HUMANOID="$SPD_WS/src/int-ball2_isaac_sim/int-ball2_isaac_sim/assets/KIBOU_with_humanoid.usd"

echo "=== PROVIDENCE LLM-Humanoid A→B Demo ==="
echo "  Bag dir : $BAGDIR"
echo "  Timeout : ${TIMEOUT}s"
echo ""

# 前提チェック
if [ ! -f "$KIBOU_WITH_HUMANOID" ]; then
    echo "ERROR: $KIBOU_WITH_HUMANOID not found."
    echo "  Run spawn_humanoid.py first:"
    echo "  \$SPD_ISAACSIM_PATH/python.sh $SCRIPT_DIR/spawn_humanoid.py"
    exit 1
fi

export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
source /opt/ros/humble/setup.bash
source "$SPD_WS/install/setup.bash" 2>/dev/null || true

mkdir -p "$BAGDIR"

# --- Step 1: Isaac Sim + ROS2 ブリッジ起動（バックグラウンド）---
echo "[demo] Starting Isaac Sim (humanoid_ros2_sim.py)..."
"$SPD_ISAACSIM_PATH/python.sh" "$SCRIPT_DIR/humanoid_ros2_sim.py" \
    > "$BAGDIR/isaacsim.log" 2>&1 &
SIM_PID=$!
echo "  Isaac Sim PID: $SIM_PID"

# トピックが出るまで待機
echo "[demo] Waiting for /humanoid_01/odom topic..."
for i in $(seq 1 30); do
    if ros2 topic list 2>/dev/null | grep -q "humanoid_01/odom"; then
        echo "  Topic found after ${i}s"
        break
    fi
    sleep 1
done

# --- Step 2: rosbag2 録画開始 ---
echo "[demo] Starting rosbag2 recording..."
ros2 bag record \
    /humanoid_01/odom \
    /humanoid_01/cmd_vel \
    -o "$BAGDIR/run" \
    > "$BAGDIR/rosbag.log" 2>&1 &
BAG_PID=$!
echo "  rosbag2 PID: $BAG_PID"

sleep 2

# --- Step 3: LLM脳ループ起動 ---
echo "[demo] Starting brain_loop_node..."
python3 "$SCRIPT_DIR/brain_loop_node.py" \
    --timeout "$TIMEOUT" \
    --log "$BAGDIR/brain_log.jsonl" \
    2>&1 | tee "$BAGDIR/brain.log"

# --- Step 4: クリーンアップ ---
echo "[demo] Stopping recording and simulation..."
kill $BAG_PID 2>/dev/null || true
kill $SIM_PID 2>/dev/null || true
wait $BAG_PID 2>/dev/null || true
wait $SIM_PID 2>/dev/null || true

echo ""
echo "=== Demo Complete ==="
echo "  Bag: $BAGDIR/run/"
echo "  Brain log: $BAGDIR/brain_log.jsonl"
ros2 bag info "$BAGDIR/run" 2>/dev/null || true
