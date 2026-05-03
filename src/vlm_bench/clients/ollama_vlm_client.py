"""Ollama local VLM client."""

import base64
import time
import os
import numpy as np
import cv2
import requests


_OLLAMA_HOST = os.environ.get("SPD_LLM_HOST", "http://localhost:11434")
_DEFAULT_MODEL = "moondream"


class OllamaVLMClient:
    def __init__(self, model: str = _DEFAULT_MODEL, host: str = _OLLAMA_HOST):
        self.model = model
        self.host = host

    def describe(self, image_bgr: np.ndarray, prompt: str,
                 max_tokens: int = 256) -> dict:
        _, buf = cv2.imencode(".jpg", image_bgr)
        b64 = base64.standard_b64encode(buf.tobytes()).decode("utf-8")

        payload = {
            "model": self.model,
            "prompt": prompt,
            "images": [b64],
            "stream": False,
            "options": {"num_predict": max_tokens},
        }

        t0 = time.perf_counter()
        resp = requests.post(f"{self.host}/api/generate", json=payload, timeout=120)
        latency_ms = (time.perf_counter() - t0) * 1000
        resp.raise_for_status()
        data = resp.json()

        return {
            "text": data.get("response", ""),
            "latency_ms": round(latency_ms, 1),
            "input_tokens": data.get("prompt_eval_count", 0),
            "output_tokens": data.get("eval_count", 0),
            "cost_usd": 0.0,
        }


if __name__ == "__main__":
    import argparse, json, sys

    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    parser.add_argument("--prompt", default="Describe what you see in 1 sentence.")
    parser.add_argument("--model", default=_DEFAULT_MODEL)
    args = parser.parse_args()

    img = cv2.imread(args.image)
    if img is None:
        print(f"ERROR: cannot read {args.image}", file=sys.stderr)
        sys.exit(1)

    client = OllamaVLMClient(model=args.model)
    result = client.describe(img, args.prompt)
    print(json.dumps(result, ensure_ascii=False, indent=2))
