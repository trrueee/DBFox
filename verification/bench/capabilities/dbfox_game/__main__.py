from __future__ import annotations

import argparse
import importlib
import json
from pathlib import Path

importlib.import_module("verification.conftest")

from .runtime import run_bench


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run_bench(args.output.resolve())
    print(json.dumps(result, indent=2))
    if result["passed_trials"] != result["trials"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
