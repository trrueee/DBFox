"""Run with the repository's isolated verification environment."""
from __future__ import annotations

import argparse
import importlib
import json
from pathlib import Path

# Match pytest's verified process isolation before importing any engine module.
importlib.import_module("verification.conftest")

from .runtime import run_voxel_bench


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--case", action="append", default=[])
    parser.add_argument("--repetitions", type=int, default=1)
    args = parser.parse_args()
    print(json.dumps(run_voxel_bench(output_dir=args.output.resolve(), repetitions=args.repetitions,
        case_ids=frozenset(args.case)), indent=2))


if __name__ == "__main__":
    main()
