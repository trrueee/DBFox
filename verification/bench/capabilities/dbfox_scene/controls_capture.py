"""Save the JSON result emitted by a suite-owned Playwright CLI scenario."""
from __future__ import annotations

import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
SCENARIOS = ("close", "interact", "gizmo", "abort-drag", "reactivate", "finish")


def capture(name: str) -> None:
    if name not in SCENARIOS:
        raise ValueError("Unknown controls scenario")
    raw = (HERE.parents[3] / f"output/playwright/scene-controls-{name}.txt").read_text(encoding="utf-8-sig")
    result = json.loads(raw.split("### Result\n", 1)[1].split("\n### Ran", 1)[0])
    (HERE / f"evidence/controls-{name}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    capture(sys.argv[1])
