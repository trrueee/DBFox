import argparse
import json
from pathlib import Path
import tempfile
from verification.bench.framework.reporting import write_suite_report
from verification.bench.framework.schema import load_suite_manifest
from verification.bench.framework.trial import TrialOutcome
from .runtime import ComicRuntime, run_case

parser = argparse.ArgumentParser()
parser.add_argument("--output", type=Path, required=True)
parser.add_argument("--case")
args = parser.parse_args()
here = Path(__file__).parent
manifest = load_suite_manifest(here / "suite.json")
cases = json.loads((here / "cases.json").read_text(encoding="utf-8"))
results = []
with tempfile.TemporaryDirectory(prefix="dbfox-comic-bench-") as work:
    with ComicRuntime(Path(work)) as runtime:
        for case in cases:
            if args.case and args.case != case["id"]:
                continue
            evidence = run_case(runtime, case)
            failed = tuple(k for k, v in evidence["checks"].items() if not v)
            results.append(TrialOutcome(suite_id=manifest.suite_id, case_id=case["id"], repetition=1,
                verdict="fail" if failed else "pass", failed_checks=failed,
                metrics={"task.success_rate": float(not failed), "runtime.tool_calls": len(evidence["requests"]), "context.prompt_peak": evidence["prompt_peak"]}, evidence=evidence))
            print(case["id"], "FAIL " + str(failed) if failed else "PASS", flush=True)
print(write_suite_report(output_dir=args.output, manifest=manifest, outcomes=results))

raise SystemExit(1 if any(result.verdict == "fail" for result in results) or not results else 0)
