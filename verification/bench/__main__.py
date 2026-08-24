"""Single CLI for Core, Capability and Composition benchmark suites."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
import sys

from verification.bench.capabilities.dbfox_data.agent import cli as data_agent_cli
from verification.bench.capabilities.dbfox_data.agent.comparison import (
    compare_summaries as compare_data_summaries,
)
from verification.bench.capabilities.dbfox_data.agent.schema import (
    load_manifest as load_data_manifest,
)
from verification.bench.core.loop.runtime import run_core_loop_bench
from verification.bench.core.loop.schema import load_cases
from verification.bench.framework.comparison import compare_summaries, load_summary
from verification.bench.framework.schema import load_suite_manifest


ROOT = Path(__file__).resolve().parents[2]
CORE_LOOP = Path(__file__).resolve().parent / "core" / "loop"
DATA_AGENT = (
    Path(__file__).resolve().parent
    / "capabilities"
    / "dbfox_data"
    / "agent"
)
SUITES = {
    "core.loop.scripted": CORE_LOOP / "suite.json",
    "capability.dbfox_data.agent": DATA_AGENT / "suite.json",
}


def _stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _parse(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m verification.bench")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list", help="list versioned benchmark suites")

    validate = commands.add_parser("validate", help="validate suite and dataset contracts")
    validate.add_argument("suite", nargs="?", choices=sorted(SUITES))

    run = commands.add_parser("run", help="execute a suite through production boundaries")
    run.add_argument("suite", choices=sorted(SUITES))
    run.add_argument("--case", action="append", default=[])
    run.add_argument("--tag", action="append", default=[])
    run.add_argument("--repetitions", type=int, default=1)
    run.add_argument("--dataset", type=Path)
    run.add_argument("--output", type=Path)

    calibrate = commands.add_parser("calibrate", help="calibrate a suite-owned scorer")
    calibrate.add_argument("suite", choices=["capability.dbfox_data.agent"])
    calibrate.add_argument("--fixtures", type=Path)
    calibrate.add_argument("--output", type=Path)

    replay = commands.add_parser("replay", help="re-score a stored suite trace")
    replay.add_argument("suite", choices=["capability.dbfox_data.agent"])
    replay.add_argument("--dataset", type=Path)
    replay.add_argument("--trials", type=Path, required=True)
    replay.add_argument("--output", type=Path, required=True)

    compare = commands.add_parser("compare", help="apply generic paired regression gates")
    compare.add_argument("--baseline", type=Path, required=True)
    compare.add_argument("--candidate", type=Path, required=True)
    compare.add_argument("--output", type=Path, required=True)
    return parser.parse_args(argv)


def _validate_suite(suite_id: str) -> dict[str, object]:
    path = SUITES[suite_id]
    manifest = load_suite_manifest(path)
    dataset_path = path.parent / manifest.dataset
    if suite_id == "core.loop.scripted":
        case_count = len(load_cases(dataset_path).cases)
    else:
        case_count = len(load_data_manifest(dataset_path).cases)
    return {**manifest.public_summary(), "case_count": case_count}


def _run_data_cli(command: str, args: argparse.Namespace) -> int:
    forwarded = [command]
    if command == "real":
        if args.dataset:
            forwarded.extend(["--dataset", str(args.dataset)])
        for tag in args.tag:
            forwarded.extend(["--tag", tag])
        for case_id in args.case:
            forwarded.extend(["--case", case_id])
        forwarded.extend(["--repetitions", str(args.repetitions)])
    elif command == "calibrate" and args.fixtures:
        forwarded.extend(["--suite", str(args.fixtures)])
    elif command == "replay":
        if args.dataset:
            forwarded.extend(["--dataset", str(args.dataset)])
        forwarded.extend(["--trials", str(args.trials)])
    if args.output:
        forwarded.extend(["--output", str(args.output)])
    return data_agent_cli.main(forwarded)


def main(argv: list[str] | None = None) -> int:
    args = _parse(argv)
    if args.command == "list":
        print(json.dumps([_validate_suite(item) for item in sorted(SUITES)], indent=2))
        return 0
    if args.command == "validate":
        selected = [args.suite] if args.suite else sorted(SUITES)
        print(json.dumps([_validate_suite(item) for item in selected], indent=2))
        return 0
    if args.command == "compare":
        baseline = load_summary(args.baseline)
        candidate = load_summary(args.candidate)
        suite_id = str((candidate.get("suite") or {}).get("suite_id") or "")
        if suite_id == "capability.dbfox_data.agent":
            result = compare_data_summaries(baseline, candidate)
        else:
            result = compare_summaries(baseline, candidate)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(result.model_dump(mode="json"), indent=2),
            encoding="utf-8",
        )
        return 0 if result.passed else 1
    if args.command == "calibrate":
        return _run_data_cli("calibrate", args)
    if args.command == "replay":
        return _run_data_cli("replay", args)
    if args.suite == "capability.dbfox_data.agent":
        if args.output is None:
            args.output = ROOT / "output" / "agent-evaluation" / f"data-agent-{_stamp()}"
        return _run_data_cli("real", args)
    output = args.output or ROOT / "output" / "agent-evaluation" / f"core-loop-{_stamp()}"
    summary = run_core_loop_bench(
        output_dir=output,
        repetitions=args.repetitions,
        case_ids=frozenset(args.case),
    )
    print(f"REPORT={output / 'report.md'}")
    return 0 if summary["passed_trials"] == summary["scored_trials"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
