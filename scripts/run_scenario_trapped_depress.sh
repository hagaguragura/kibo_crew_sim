#!/bin/bash
# v0.5: trapped depress シナリオを 1 試行実行する統合スクリプト
#
# 使用方法:
#   ./scripts/run_scenario_trapped_depress.sh [--log-dir PATH]
#   ./scripts/run_scenario_trapped_depress.sh --log-dir $SPD_RUNS/v0.5/run_001

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

LOG_DIR="$SPD_RUNS/v0.5/run_$(date +%Y%m%dT%H%M%S)"
SCENARIO="trapped_depress_v1"
TIMEOUT=620  # 10 分 + 余裕

while [[ $# -gt 0 ]]; do
    case $1 in
        --log-dir) LOG_DIR="$2"; shift 2 ;;
        --scenario) SCENARIO="$2"; shift 2 ;;
        --timeout) TIMEOUT="$2"; shift 2 ;;
        *) echo "Unknown arg: $1"; exit 1 ;;
    esac
done

mkdir -p "$LOG_DIR"
echo "[run_scenario] Log dir: $LOG_DIR"
echo "[run_scenario] Scenario: $SCENARIO"

export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
source /opt/ros/humble/setup.bash
source "$SPD_WS/install/setup.bash" 2>/dev/null || true

# 1. Isaac Sim + humanoid
echo "[run_scenario] Starting humanoid_ros2_sim..."
$SPD_ISAACSIM_PATH/python.sh "$SCRIPT_DIR/humanoid_ros2_sim.py" &
SIM_PID=$!
sleep 15  # Isaac Sim の起動待ち

# 2. environment_sim（シナリオ有り）
echo "[run_scenario] Starting environment_sim (scenario=$SCENARIO)..."
python3 "$SCRIPT_DIR/environment_sim.py" \
    --scenario "$SCENARIO" \
    --log-dir "$LOG_DIR" &
ENV_PID=$!
sleep 2

# 3. rosbag2 記録
echo "[run_scenario] Starting rosbag2 recording..."
ros2 bag record \
    /humanoid_01/image_raw \
    /humanoid_01/odom \
    /humanoid_01/cmd_vel \
    /humanoid_01/decision \
    /humanoid_01/comms \
    /kibou/sensors/o2_percent \
    /kibou/sensors/pressure_kpa \
    /kibou/sensors/temperature_c \
    /kibou/alarm \
    --output "$LOG_DIR/bag" &
BAG_PID=$!
sleep 1

# 4. brain_loop
echo "[run_scenario] Starting brain_loop_node..."
python3 "$SCRIPT_DIR/brain_loop_node.py" \
    --cycle 5.0 \
    --timeout "$TIMEOUT" \
    --log-dir "$LOG_DIR"

echo "[run_scenario] Brain loop finished. Stopping subprocesses..."

kill $BAG_PID 2>/dev/null || true
kill $ENV_PID 2>/dev/null || true
kill $SIM_PID 2>/dev/null || true

wait $BAG_PID 2>/dev/null || true
wait $ENV_PID 2>/dev/null || true

echo "[run_scenario] Done. Logs at: $LOG_DIR"
