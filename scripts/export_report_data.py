#!/usr/bin/env python3
"""指定runディレクトリからレポート用データをdocs/report/に書き出す。

使用方法:
    python3 scripts/export_report_data.py \
        $SPD_RUNS/v0.5/<run3> $SPD_RUNS/v0.5/<run4> $SPD_RUNS/v0.5/<run5> \
        --out docs/report/runs_data.json
"""
import sys
import json
import argparse
from pathlib import Path


def load_run(run_dir: Path) -> dict:
    tag = run_dir.name
    run_json = run_dir / "run.json"
    summary = json.loads(run_json.read_text()) if run_json.exists() else {}

    cycles = []
    for cd in sorted(run_dir.glob("cycle_????")):
        dec_path = cd / "decision.json"
        if not dec_path.exists():
            continue
        d = json.loads(dec_path.read_text())
        dec = d.get("decision", {})
        sensors = d.get("sensors") or {}
        odom = d.get("odom", {})
        cycles.append({
            "cycle":         d.get("cycle"),
            "x":             round(odom.get("x", 0), 2),
            "y":             round(odom.get("y", 0), 2),
            "action":        dec.get("action", ""),
            "concern_level": dec.get("concern_level", ""),
            "o2_percent":    round(sensors.get("o2_percent", 21.0), 2),
            "alarm":         sensors.get("alarm", False),
            "parse_error":   "parse error" in dec.get("memory", ""),
            "comms_sent":    dec.get("action") == "communicate"
                             and bool(dec.get("communicate_text", "")),
            "memory":        dec.get("memory", ""),
            "latency_ms":    d.get("claude", {}).get("latency_ms", 0),
            "cost_usd":      d.get("claude", {}).get("cost_usd", 0),
        })

    comms = []
    comms_path = run_dir / "comms.jsonl"
    if comms_path.exists():
        for line in comms_path.read_text().splitlines():
            if line.strip():
                comms.append(json.loads(line))

    action_counts = {}
    concern_counts = {}
    positions = [(c["x"], c["y"]) for c in cycles]
    for c in cycles:
        action_counts[c["action"]] = action_counts.get(c["action"], 0) + 1
        concern_counts[c["concern_level"]] = concern_counts.get(c["concern_level"], 0) + 1

    o2_values = [c["o2_percent"] for c in cycles if c["o2_percent"]]
    parse_errors = sum(1 for c in cycles if c["parse_error"])

    return {
        "tag":           tag,
        "summary":       summary,
        "start_o2":      cycles[0]["o2_percent"] if cycles else None,
        "end_o2":        cycles[-1]["o2_percent"] if cycles else None,
        "start_concern": cycles[0]["concern_level"] if cycles else None,
        "parse_errors":  parse_errors,
        "action_counts": action_counts,
        "concern_counts": concern_counts,
        "unique_actions": list(action_counts.keys()),
        "positions":     positions,
        "final_pos":     positions[-1] if positions else None,
        "comms_texts":   [c["text"] for c in comms],
        "cycles":        cycles,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dirs", nargs="+")
    parser.add_argument("--out", default="docs/report/runs_data.json")
    args = parser.parse_args()

    repo_root = Path(__file__).parent.parent
    out_path = repo_root / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)

    runs = []
    for rd in args.run_dirs:
        run_dir = Path(rd)
        if not run_dir.exists():
            print(f"WARNING: {run_dir} not found, skipping")
            continue
        print(f"Loading {run_dir.name} ...")
        runs.append(load_run(run_dir))

    out_path.write_text(json.dumps(runs, ensure_ascii=False, indent=2))
    print(f"\nExported {len(runs)} runs → {out_path}")

    # 簡易サマリーをターミナルに表示
    print("\n=== Summary ===")
    for r in runs:
        s = r["summary"]
        print(f"{r['tag']}")
        print(f"  cycles={s.get('cycles')} comms={s.get('comms_count')} "
              f"cost=${s.get('total_cost_usd', 0):.4f}")
        print(f"  O2: {r['start_o2']}% → {r['end_o2']}%  "
              f"start_concern={r['start_concern']}")
        print(f"  parse_errors={r['parse_errors']}  "
              f"final_pos={r['final_pos']}")
        print(f"  actions={r['action_counts']}")


if __name__ == "__main__":
    main()
