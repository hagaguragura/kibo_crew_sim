#!/bin/bash
# GPU usage logger: outputs CSV rows every 1 second
# Usage: ./log_gpu.sh > output.csv
echo "timestamp,used_MiB,free_MiB,gpu_util_pct"
while true; do
    nvidia-smi --query-gpu=timestamp,memory.used,memory.free,utilization.gpu \
        --format=csv,noheader,nounits
    sleep 1
done
