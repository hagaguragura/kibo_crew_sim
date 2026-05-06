#!/bin/bash
# Phase 4: 脳なしの探索パターンテスト。
# [VERIFY] Hagura: GUI で 30 秒間、滑らかに動くことを確認
#
# 使用方法:
#   export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
#   source /opt/ros/humble/setup.bash
#   bash scripts/test_exploration_pattern.sh

echo "[test_exploration] Start. Ctrl+C to stop."

pub_for() {
    local msg="$1"
    local duration="$2"
    local label="$3"
    echo "[test_exploration] $label (${duration}s)"
    ros2 topic pub /humanoid_01/cmd_vel geometry_msgs/msg/Twist "$msg" -r 10 &
    local pid=$!
    sleep "$duration"
    kill "$pid" 2>/dev/null || true
    wait "$pid" 2>/dev/null || true
    ros2 topic pub /humanoid_01/cmd_vel geometry_msgs/msg/Twist '{}' -1 2>/dev/null || true
    sleep 0.3
}

while true; do
    pub_for '{linear: {y: 0.3}}'  5 "move_forward"
    pub_for '{angular: {z: 0.5}}' 3 "turn_left (~90°)"
    pub_for '{linear: {y: 0.3}}'  5 "move_forward"
    pub_for '{angular: {z: -0.5}}' 3 "turn_right (~90°)"
    echo "[test_exploration] inspect 2s"
    sleep 2
done
