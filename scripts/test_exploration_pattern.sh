#!/bin/bash
# Phase 4: 脳なしの探索パターンテスト。humanoid が KIBOU 内を進む・回る・進むを繰り返す。
# [VERIFY] Hagura: GUI で 30 秒間、滑らかに動くことを確認
#
# 使用方法:
#   export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
#   source /opt/ros/humble/setup.bash
#   bash scripts/test_exploration_pattern.sh

set -e
echo "[test_exploration] Start. Ctrl+C to stop."

pub() {
    ros2 topic pub /humanoid_01/cmd_vel geometry_msgs/Twist "$1" -1 2>/dev/null
}

stop() {
    ros2 topic pub /humanoid_01/cmd_vel geometry_msgs/Twist \
        '{linear: {x: 0.0, y: 0.0, z: 0.0}, angular: {x: 0.0, y: 0.0, z: 0.0}}' -1 2>/dev/null
}

while true; do
    echo "[test_exploration] move_forward 5s"
    pub '{linear: {y: 0.3}}'; sleep 5

    echo "[test_exploration] turn_left 3s"
    pub '{angular: {z: 0.5}}'; sleep 3

    echo "[test_exploration] move_forward 5s"
    pub '{linear: {y: 0.3}}'; sleep 5

    echo "[test_exploration] turn_right 3s"
    pub '{angular: {z: -0.5}}'; sleep 3

    echo "[test_exploration] inspect 2s"
    stop; sleep 2
done
