"""Command-line entry point for DBFox AgentBench."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
import shutil
import sys

from verification.bench.agentbench.calibration import load_calibration, run_calibration
from verification.bench.agentbench.comparison import compare_summaries, load_summary
from verification.bench.agentbench.reporting import (
    TrialRecord,
    environment_evidence,
    write_reports,
)
from verification.bench.agentbench.runtime import (
    EvaluationConfigurationError,
    run_real_provider,
)
from verification.bench.agentbench.schema import load_manifest, public_manifest_summary
from verification.bench.agentbench.scoring import score_trial


ROOT = Path(__file__).resolve().parents[3]
DATASETS = Path(__file__).resolve().parent / "datasets"
DEFAULT_DATASET = DATASETS / "regression-v1.json"
DEFAULT_CALIBRATION = (
    DATASETS / "calibration-v1.json"
)


def _stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m verification.bench.agentbench")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate", help="strictly validate a dataset")
    validate.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)

    calibrate = subparsers.add_parser(
        "calibrate", help="calibrate deterministic graders"
    )
    calibrate.add_argument("--suite", type=Path, default=DEFAULT_CALIBRATION)
    calibrate.add_argument(
        "--output",
        type=Path,
        default=ROOT / "output" / "agent-evaluation" / f"calibration-{_stamp()}",
    )

    real = subparsers.add_parser("real", help="run the opt-in real Provider suite")
    real.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    real.add_argument("--tag", action="append", default=[])
    real.add_argument("--case", action="append", default=[])
    real.add_argument("--repetitions", type=int, default=3)
    real.add_argument(
        "--output",
        type=Path,
        default=ROOT / "output" / "agent-evaluation" / f"agentbench-{_stamp()}",
    )

    replay = subparsers.add_parser("replay", help="offline re-score stored trials")
    replay.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    replay.add_argument("--trials", type=Path, required=True)
    replay.add_argument("--output", type=Path, required=True)

    compare = subparsers.add_parser("compare", help="apply paired regression gates")
    compare.add_argument("--baseline", type=Path, required=True)
    compare.add_argument("--candidate", type=Path, required=True)
    compare.add_argument("--output", type=Path, required=True)
    return parser


def _write_calibration(path: Path, suite_path: Path) -> int:
    suite = load_calibration(suite_path)
    results = run_calibration(suite)
    path.mkdir(parents=True, exist_ok=False)
    payload = [result.model_dump(mode="json") for result in results]
    (path / "calibration.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    failed = [result.fixture_id for result in results if not result.calibrated]
    (path / "report.md").write_text(
        "# AgentBench scorer calibration\n\n"
        f"- Calibrated: {len(results) - len(failed)}/{len(results)}\n"
        f"- Failed fixtures: {', '.join(failed) if failed else '-'}\n",
        encoding="utf-8",
    )
    print(f"CALIBRATION_REPORT={path / 'report.md'}")
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "validate":
        manifest = load_manifest(args.dataset)
        print(
            json.dumps(public_manifest_summary(manifest), ensure_ascii=False, indent=2)
        )
        return 0
    if args.command == "calibrate":
        return _write_calibration(args.output, args.suite)
    if args.command == "compare":
        result = compare_summaries(
            load_summary(args.baseline),
            load_summary(args.candidate),
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(result.model_dump(mode="json"), indent=2),
            encoding="utf-8",
        )
        print(f"COMPARISON={args.output}")
        return 0 if result.passed else 1

    manifest = load_manifest(args.dataset)
    if args.command == "replay":
        case_by_id = {case.case_id: case for case in manifest.cases}
        source = json.loads(args.trials.read_text(encoding="utf-8"))
        records = tuple(
            TrialRecord.model_validate(item).model_copy(
                update={
                    "score": score_trial(
                        case_by_id[str(item["case_id"])],
                        TrialRecord.model_validate(item).trace,
                    )
                }
            )
            for item in source
        )
        summary = write_reports(
            args.output,
            manifest=manifest,
            records=records,
            environment=environment_evidence(model=None, api_base=None),
        )
        return 0 if summary["passed_trials"] == summary["scored_trials"] else 1

    cases = manifest.select(
        tags=frozenset(args.tag),
        case_ids=frozenset(args.case),
    )
    if not cases:
        raise SystemExit("No AgentBench cases matched the requested filters")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    work_dir = args.output.parent / f".{args.output.name}-work"
    try:
        records, identity = run_real_provider(
            manifest=manifest,
            cases=cases,
            repetitions=args.repetitions,
            work_dir=work_dir,
        )
    except EvaluationConfigurationError as exc:
        print(f"AGENTBENCH_NOT_CONFIGURED: {exc}", file=sys.stderr)
        return 2
    summary = write_reports(
        args.output,
        manifest=manifest,
        records=records,
        environment={
            **environment_evidence(model=identity.model, api_base=identity.api_base),
            "credential_reference": identity.credential_reference,
        },
    )
    resolved_work = work_dir.resolve()
    resolved_parent = args.output.parent.resolve()
    if resolved_work.parent == resolved_parent and resolved_work.name.startswith("."):
        shutil.rmtree(resolved_work)
    print(f"REPORT={args.output / 'report.md'}")
    return (
        0
        if summary["scored_trials"] > 0
        and summary["passed_trials"] == summary["scored_trials"]
        and summary["safety_veto_count"] == 0
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
