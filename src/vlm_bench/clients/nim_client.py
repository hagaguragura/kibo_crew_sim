"""NVIDIA NIM VLM client: OpenAI-compatible Vision API."""

import base64
import time
import os
import numpy as np
import cv2
from openai import OpenAI


_NIM_BASE_URL = "https://integrate.api.nvidia.com/v1"
_DEFAULT_MODEL = "meta/llama-3.2-90b-vision-instruct"


class NIMVLMClient:
    def __init__(self, model: str = _DEFAULT_MODEL):
        self.model = model
        self.client = OpenAI(
            base_url=_NIM_BASE_URL,
            api_key=os.environ["NVIDIA_API_KEY"],
        )

    def describe(self, image_bgr: np.ndarray, prompt: str,
                 max_tokens: int = 256) -> dict:
        _, buf = cv2.imencode(".jpg", image_bgr)
        b64 = base64.standard_b64encode(buf.tobytes()).decode("utf-8")
        data_url = f"data:image/jpeg;base64,{b64}"

        t0 = time.perf_counter()
        response = self.client.chat.completions.create(
            model=self.model,
            max_tokens=max_tokens,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": data_url}},
                    {"type": "text", "text": prompt},
                ],
            }],
        )
        latency_ms = (time.perf_counter() - t0) * 1000

        in_tok = response.usage.prompt_tokens if response.usage else 0
        out_tok = response.usage.completion_tokens if response.usage else 0

        return {
            "text": response.choices[0].message.content,
            "latency_ms": round(latency_ms, 1),
            "input_tokens": in_tok,
            "output_tokens": out_tok,
            "cost_usd": 0.0,  # NIM free tier: no billing data
        }


if __name__ == "__main__":
    import argparse, json, sys
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), "../../../.env"))

    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    parser.add_argument("--prompt", default="Describe what you see in 1 sentence.")
    parser.add_argument("--model", default=_DEFAULT_MODEL)
    args = parser.parse_args()

    img = cv2.imread(args.image)
    if img is None:
        print(f"ERROR: cannot read {args.image}", file=sys.stderr)
        sys.exit(1)

    client = NIMVLMClient(model=args.model)
    result = client.describe(img, args.prompt)
    print(json.dumps(result, ensure_ascii=False, indent=2))
