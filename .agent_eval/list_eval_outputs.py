"""List all JSONL eval outputs with summary statistics.

Usage:
    python .agent_eval/list_eval_outputs.py
    python .agent_eval/list_eval_outputs.py --dir .agent_eval/outputs
    python .agent_eval/list_eval_outputs.py --json  # JSON output
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from datetime import datetime


def scan_jsonl(jsonl_path: Path) -> dict | None:
    """Scan a single JSONL file and return summary stats."""
    try:
        lines = []
        for line in jsonl_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            lines.append(line)
    except Exception:
        return None

    if not lines:
        return None

    total = len(lines)
    status_counts: dict[str, int] = {}
    pass_count = 0

    for line in lines:
        try:
            obj = json.loads(line)
            status = obj.get("status", "null")
            status_counts[status] = status_counts.get(status, 0) + 1
            if status == "pass":
                pass_count += 1
        except json.JSONDecodeError:
            status_counts["parse_error"] = status_counts.get("parse_error", 0) + 1

    stat = os.stat(jsonl_path)
    size_kb = round(stat.st_size / 1024, 1)
    mtime = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")

    return {
        "filename": jsonl_path.name,
        "path": str(jsonl_path),
        "total": total,
        "pass": pass_count,
        "pass_rate": f"{pass_count}/{total}",
        "status_counts": status_counts,
        "size_kb": size_kb,
        "modified": mtime,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="List JSONL eval outputs with summary stats")
    parser.add_argument("--dir", default=None, help="Directory to scan (default: .agent_eval/outputs)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    if args.dir:
        output_dir = Path(args.dir)
    else:
        output_dir = Path(__file__).resolve().parent / "outputs"

    if not output_dir.exists():
        print(f"Directory not found: {output_dir}")
        return

    results = []
    for f in sorted(output_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True):
        info = scan_jsonl(f)
        if info:
            results.append(info)

    if args.json:
        print(json.dumps(results, indent=2, ensure_ascii=False))
        return

    # Table output
    if not results:
        print("No JSONL files found.")
        return

    # Header
    header = f"{'filename':<45} {'total':>5} {'pass':>5} {'rate':>8} {'size':>8} {'modified':>16}  status_counts"
    print(header)
    print("-" * len(header))

    for r in results:
        status_str = ", ".join(f"{k}={v}" for k, v in sorted(r["status_counts"].items()))
        print(
            f"{r['filename']:<45} {r['total']:>5} {r['pass']:>5} {r['pass_rate']:>8} "
            f"{r['size_kb']:>7.0f}KB {r['modified']:>16}  {status_str}"
        )


if __name__ == "__main__":
    main()
