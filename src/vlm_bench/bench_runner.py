"""Batch benchmark runner: runs all images × N_RUNS against a VLM provider."""

import argparse
import csv
import os
import sys
import time
from pathlib import Path
import cv2

KIBO_PROMPT = (
    "You are an astronaut inside the JEM \"Kibo\" module of the ISS. "
    "Describe what you see in this image. If you detect anything anomalous "
    "(fire, smoke, damage, intruder, leak), state it clearly at the start. "
    "Reply in 1-3 sentences."
)

FIELDNAMES = ["image", "run", "latency_ms", "input_tokens",
              "output_tokens", "cost_usd", "text"]


def load_client(provider: str, model: str):
    if provider == "claude":
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).parent.parent.parent / ".env")
        from clients.claude_client import ClaudeVLMClient
        return ClaudeVLMClient(model=model or "claude-sonnet-4-6")
    elif provider == "nim":
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).parent.parent.parent / ".env")
        from clients.nim_client import NIMVLMClient
        return NIMVLMClient(model=model or "meta/llama-3.2-90b-vision-instruct")
    elif provider == "ollama":
        from clients.ollama_vlm_client import OllamaVLMClient
        return OllamaVLMClient(model=model or "moondream")
    else:
        raise ValueError(f"Unknown provider: {provider}")


def run_bench(provider: str, model: str, image_dir: Path,
              output_csv: Path, n_runs: int = 3,
              interval_sec: float = 1.0):
    client = load_client(provider, model)
    images = sorted(image_dir.glob("*.png")) + sorted(image_dir.glob("*.jpg"))
    if not images:
        print(f"ERROR: no images in {image_dir}", file=sys.stderr)
        sys.exit(1)

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with open(output_csv, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()

        total = len(images) * n_runs
        done = 0
        for img_path in images:
            img = cv2.imread(str(img_path))
            if img is None:
                print(f"WARN: skip {img_path}", file=sys.stderr)
                continue
            for run in range(1, n_runs + 1):
                done += 1
                print(f"[{done}/{total}] {img_path.name} run={run} ... ",
                      end="", flush=True)
                try:
                    result = client.describe(img, KIBO_PROMPT)
                    row = {"image": img_path.name, "run": run, **result}
                    writer.writerow(row)
                    f.flush()
                    print(f"{result['latency_ms']:.0f}ms  "
                          f"{result['text'][:60]}...")
                except Exception as e:
                    print(f"ERROR: {e}", file=sys.stderr)
                    writer.writerow({"image": img_path.name, "run": run,
                                     "latency_ms": -1, "input_tokens": 0,
                                     "output_tokens": 0, "cost_usd": 0,
                                     "text": f"ERROR: {e}"})
                    f.flush()
                if interval_sec > 0 and done < total:
                    time.sleep(interval_sec)

    print(f"\nDone. CSV saved to {output_csv}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", required=True,
                        choices=["claude", "nim", "ollama"])
    parser.add_argument("--model", default="")
    parser.add_argument("--image-dir",
                        default=os.environ.get("SPD_RUNS", "") + "/v0.3/inputs")
    parser.add_argument("--output-dir",
                        default=os.environ.get("SPD_RUNS", "") + "/v0.3")
    parser.add_argument("--n-runs", type=int, default=3)
    parser.add_argument("--interval", type=float, default=1.0,
                        help="seconds between API calls")
    args = parser.parse_args()

    phase_map = {"claude": "phase1", "nim": "phase2", "ollama": "phase3"}
    model_slug = (args.model or "default").replace("/", "_").replace(":", "_")
    out_csv = Path(args.output_dir) / phase_map[args.provider] / \
              f"{args.provider}_bench_{model_slug}.csv"

    run_bench(
        provider=args.provider,
        model=args.model,
        image_dir=Path(args.image_dir),
        output_csv=out_csv,
        n_runs=args.n_runs,
        interval_sec=args.interval,
    )
