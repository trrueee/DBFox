"""Author-run deterministic benchmark, never a model-quality claim."""
import argparse
import importlib
import json
from pathlib import Path
import tempfile

importlib.import_module("verification.conftest")
from .runtime import AnimationRuntime, run_case
from .scoring import score
from verification.bench.framework.reporting import write_suite_report
from verification.bench.framework.schema import load_suite_manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--case")
    args = parser.parse_args()
    cases = json.loads(Path(__file__).with_name("cases.json").read_text())["cases"]
    if args.case:
        cases = [case for case in cases if case["id"] == args.case]
    directory = Path(tempfile.mkdtemp(prefix="dbfox-animation-bench-"))
    with AnimationRuntime(directory) as runtime:
        outcomes = tuple(score(run_case(runtime,case)) for case in cases)
    summary = write_suite_report(args.output,manifest=load_suite_manifest(Path(__file__).with_name("suite.json")),outcomes=outcomes)
    print(json.dumps(summary,indent=2))
    if not outcomes or any(outcome.verdict != "pass" for outcome in outcomes):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
