"""Claude VLM client: image_bgr + prompt -> text + metrics."""

import base64
import time
import os
import numpy as np
import anthropic
import cv2


# Pricing as of 2025-05 (USD per million tokens)
_INPUT_PRICE_PER_M = 3.0    # claude-sonnet-4-6
_OUTPUT_PRICE_PER_M = 15.0


class ClaudeVLMClient:
    def __init__(self, model: str = "claude-sonnet-4-6"):
        self.model = model
        self.client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    def describe(self, image_bgr: np.ndarray, prompt: str,
                 max_tokens: int = 256) -> dict:
        """
        Returns:
            {"text": str, "latency_ms": float, "input_tokens": int,
             "output_tokens": int, "cost_usd": float}
        """
        _, buf = cv2.imencode(".jpg", image_bgr)
        b64 = base64.standard_b64encode(buf.tobytes()).decode("utf-8")

        t0 = time.perf_counter()
        response = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image",
                     "source": {"type": "base64", "media_type": "image/jpeg",
                                "data": b64}},
                    {"type": "text", "text": prompt},
                ],
            }],
        )
        latency_ms = (time.perf_counter() - t0) * 1000

        in_tok = response.usage.input_tokens
        out_tok = response.usage.output_tokens
        cost = (in_tok * _INPUT_PRICE_PER_M + out_tok * _OUTPUT_PRICE_PER_M) / 1_000_000

        return {
            "text": response.content[0].text,
            "latency_ms": round(latency_ms, 1),
            "input_tokens": in_tok,
            "output_tokens": out_tok,
            "cost_usd": round(cost, 6),
        }


if __name__ == "__main__":
    import argparse, json, sys
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), "../../../.env"))

    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    parser.add_argument("--prompt", default="Describe what you see in 1 sentence.")
    parser.add_argument("--model", default="claude-sonnet-4-6")
    args = parser.parse_args()

    img = cv2.imread(args.image)
    if img is None:
        print(f"ERROR: cannot read {args.image}", file=sys.stderr)
        sys.exit(1)

    client = ClaudeVLMClient(model=args.model)
    result = client.describe(img, args.prompt)
    print(json.dumps(result, ensure_ascii=False, indent=2))
