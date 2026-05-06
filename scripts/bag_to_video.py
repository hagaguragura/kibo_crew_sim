#!/usr/bin/env python3
"""v0.5: rosbag2 の /humanoid_01/image_raw を MP4 動画に変換する。

使用方法:
    python3 scripts/bag_to_video.py $SPD_RUNS/v0.5/run_001/bag \
        --output $SPD_RUNS/v0.5/run_001/first_person.mp4 \
        --fps 8
"""
import sys
import os
import argparse
import subprocess
import tempfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("bag_dir", help="Path to rosbag2 directory")
    parser.add_argument("--output", required=True, help="Output MP4 path")
    parser.add_argument("--topic", default="/humanoid_01/image_raw")
    parser.add_argument("--fps", type=int, default=8)
    args = parser.parse_args()

    bag_dir = Path(args.bag_dir)
    if not bag_dir.exists():
        print(f"ERROR: bag dir not found: {bag_dir}", file=sys.stderr)
        sys.exit(1)

    import rclpy
    from rclpy.serialization import deserialize_message
    from rosidl_runtime_py.utilities import get_message
    import rosbag2_py
    import cv2
    import numpy as np

    storage_options = rosbag2_py.StorageOptions(uri=str(bag_dir), storage_id="mcap")
    converter_options = rosbag2_py.ConverterOptions("", "")
    reader = rosbag2_py.SequentialReader()
    reader.open(storage_options, converter_options)

    topic_types = reader.get_all_topics_and_types()
    type_map = {t.name: t.type for t in topic_types}
    if args.topic not in type_map:
        print(f"ERROR: topic {args.topic} not found in bag.", file=sys.stderr)
        print(f"  Available: {list(type_map.keys())}", file=sys.stderr)
        sys.exit(1)

    msg_type = get_message(type_map[args.topic])

    with tempfile.TemporaryDirectory() as tmpdir:
        idx = 0
        while reader.has_next():
            topic, data, _ = reader.read_next()
            if topic != args.topic:
                continue
            msg = deserialize_message(data, msg_type)
            # sensor_msgs/Image → numpy
            arr = np.frombuffer(msg.data, dtype=np.uint8)
            if msg.encoding in ("rgb8",):
                img = arr.reshape(msg.height, msg.width, 3)
                img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
            elif msg.encoding in ("bgr8",):
                img = arr.reshape(msg.height, msg.width, 3)
            else:
                print(f"  Unknown encoding {msg.encoding}, trying bgr8")
                img = arr.reshape(msg.height, msg.width, 3)

            frame_path = os.path.join(tmpdir, f"frame_{idx:06d}.png")
            cv2.imwrite(frame_path, img)
            idx += 1

        print(f"  Extracted {idx} frames")
        if idx == 0:
            print("ERROR: no frames extracted.", file=sys.stderr)
            sys.exit(1)

        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)

        cmd = [
            "ffmpeg", "-y",
            "-framerate", str(args.fps),
            "-i", os.path.join(tmpdir, "frame_%06d.png"),
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            str(output),
        ]
        print(f"  Running: {' '.join(cmd)}")
        subprocess.run(cmd, check=True)

    print(f"[bag_to_video] Done: {output}")


if __name__ == "__main__":
    main()
