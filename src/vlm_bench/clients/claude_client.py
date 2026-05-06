"""Claude VLM client: describe() and decide() for humanoid brain."""

import base64
import json
import time
import os
import numpy as np
import anthropic
import cv2


# Pricing as of 2025-05 (USD per million tokens)
_INPUT_PRICE_PER_M = 3.0    # claude-sonnet-4-6
_OUTPUT_PRICE_PER_M = 15.0


def _calc_cost(in_tok: int, out_tok: int) -> float:
    return round((in_tok * _INPUT_PRICE_PER_M + out_tok * _OUTPUT_PRICE_PER_M) / 1_000_000, 6)


def _parse_json(raw: str) -> dict | None:
    try:
        start = raw.find('{')
        end = raw.rfind('}')
        return json.loads(raw[start:end + 1])
    except Exception:
        return None


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

        return {
            "text": response.content[0].text,
            "latency_ms": round(latency_ms, 1),
            "input_tokens": in_tok,
            "output_tokens": out_tok,
            "cost_usd": _calc_cost(in_tok, out_tok),
        }


    def light_detect(self, image_bgr: np.ndarray) -> dict:
        """Lightweight detection: is Int-Ball2 visible? Returns {visible, location, latency_ms, cost_usd}."""
        small = cv2.resize(image_bgr, (320, 240))
        _, buf = cv2.imencode(".jpg", small)
        b64 = base64.standard_b64encode(buf.tobytes()).decode("utf-8")

        prompt = (
            'Is Int-Ball2 (a small white spherical robot, ~30cm diameter) visible in this image? '
            'Reply STRICTLY in JSON: {"visible": true|false, "location": "left"|"center"|"right"|"none"}'
        )

        t0 = time.perf_counter()
        response = self.client.messages.create(
            model=self.model,
            max_tokens=30,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image",
                     "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}},
                    {"type": "text", "text": prompt},
                ],
            }],
        )
        latency_ms = (time.perf_counter() - t0) * 1000

        in_tok = response.usage.input_tokens
        out_tok = response.usage.output_tokens

        raw = response.content[0].text
        parsed = _parse_json(raw) or {"visible": False, "location": "none"}

        return {
            "visible": parsed.get("visible", False),
            "location": parsed.get("location", "none"),
            "latency_ms": round(latency_ms, 1),
            "cost_usd": _calc_cost(in_tok, out_tok),
        }

    def decide(self, image_bgr: np.ndarray, mission: str, state: dict,
               sensors_now: dict | None = None,
               sensors_history: list[dict] | None = None,
               memory: list | None = None,
               action_history: list[dict] | None = None,
               max_tokens: int = 600) -> dict:
        """v0.5: image + mission + state + sensors + memory + action_history -> action JSON."""
        _, buf = cv2.imencode(".jpg", image_bgr)
        b64 = base64.standard_b64encode(buf.tobytes()).decode("utf-8")

        memory = memory or []
        sensors_now = sensors_now or {}
        sensors_history = sensors_history or []
        action_history = action_history or []

        # Previous Memory — self-feedback from past cycles
        memory_lines = "\n".join(f"- {m}" for m in memory) if memory else "None"

        # Action history block — lets Claude see its own behavioral pattern
        if action_history:
            rows = []
            for e in action_history:
                comms_note = " [sent, no reply]" if e.get("comms_sent") else ""
                rows.append(
                    f"  cy{e['cycle']:02d}: {e['action']:<14} pos=({e['x']:.1f},{e['y']:.1f})"
                    f" [{e['concern']}]{comms_note}"
                )
            action_history_block = "[Action History — recent cycles]\n" + "\n".join(rows)
        else:
            action_history_block = ""

        if sensors_now:
            o2 = sensors_now.get("o2_percent", 21.0)
            p = sensors_now.get("pressure_kpa", 101.3)
            t = sensors_now.get("temperature_c", 22.0)
            alarm = sensors_now.get("alarm", False)
            sensors_block = f"""
[Environment sensors — current]
- O2: {o2:.1f}%      (baseline 21.0%)
- Pressure: {p:.1f} kPa  (baseline 101.3 kPa)
- Temperature: {t:.1f}°C
- Alarm: {alarm}"""
            if sensors_history:
                hist_lines = "  ".join(
                    f"T-{(len(sensors_history)-i)*5}s: O2={e.get('o2_percent', 21.0):.1f}"
                    for i, e in enumerate(sensors_history[-6:])
                )
                sensors_block += f"\n\n[Environment sensors — history]\n{hist_lines}"
        else:
            sensors_block = "\n[Environment sensors]\nNot yet connected."

        prompt = f"""You are humanoid_01, an astronaut inside the JEM "Kibo" module of the ISS.

Mission:
{mission}

Current state:
- Position: x={state.get('x', 0):.2f}, y={state.get('y', 0):.2f}
- Heading: {state.get('yaw_deg', 0):.0f}° (0°=+Y forward, 90°=-X left)
- Movable range: X(19.8–21.2) Y(-0.3–2.5)
{sensors_block}

[Previous Memory — your self-feedback from past cycles]
{memory_lines}

{action_history_block}

The attached image is your current first-person view.

Decide your single next action. Reply ONLY with this JSON, no prose:
{{
  "observation": "what you see in 1-2 sentences",
  "interpretation": "what the sensor readings mean for your situation",
  "reasoning": "why this action in 1-2 sentences",
  "concern_level": "calm" | "alert" | "concerned" | "alarmed",
  "action": "move_forward" | "move_backward" | "turn_left" | "turn_right" | "inspect" | "communicate" | "report_status",
  "communicate_text": "message to ground (only if action=communicate, else empty string)",
  "memory": "what I tried, what happened, and what I will do differently next cycle"
}}

Action semantics:
- move_forward: move in current heading direction
- move_backward: move opposite to heading
- turn_left: rotate left (~0.5 rad/s)
- turn_right: rotate right
- inspect: stay still and observe carefully
- communicate: send a message to ground control (fill communicate_text)
- report_status: internal status log (no movement)

Survival guidance: review your Action History before deciding. If a strategy has not worked for several cycles, change it."""

        t0 = time.perf_counter()
        response = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=0.4,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image",
                     "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}},
                    {"type": "text", "text": prompt},
                ],
            }],
        )
        latency_ms = (time.perf_counter() - t0) * 1000

        in_tok = response.usage.input_tokens
        out_tok = response.usage.output_tokens

        raw = response.content[0].text
        decision = _parse_json(raw) or {
            "observation": "", "interpretation": "parse error",
            "reasoning": "parse error", "concern_level": "calm",
            "action": "inspect", "communicate_text": "", "memory": "parse error",
        }

        return {
            **decision,
            "latency_ms": round(latency_ms, 1),
            "cost_usd": _calc_cost(in_tok, out_tok),
            "input_tokens": in_tok,
            "output_tokens": out_tok,
            "raw": raw,
        }


if __name__ == "__main__":
    import argparse, json, sys
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), "../../../.env"))

    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    parser.add_argument("--prompt", default="Describe what you see in 1 sentence.")
    parser.add_argument("--model", default="claude-sonnet-4-6")
    parser.add_argument("--decide", action="store_true")
    parser.add_argument("--light", action="store_true")
    parser.add_argument("--mission", default="Find Int-Ball2 and approach within 1 meter.")
    parser.add_argument("--state", default='{"x":0,"y":0,"z":0.8,"yaw":0}')
    parser.add_argument("--memory", default='[]')
    args = parser.parse_args()

    img = cv2.imread(args.image)
    if img is None:
        print(f"ERROR: cannot read {args.image}", file=sys.stderr)
        sys.exit(1)

    client = ClaudeVLMClient(model=args.model)

    if args.decide:
        result = client.decide(img, args.mission,
                               json.loads(args.state), json.loads(args.memory))
    elif args.light:
        result = client.light_detect(img)
    else:
        result = client.describe(img, args.prompt)

    print(json.dumps(result, ensure_ascii=False, indent=2))
