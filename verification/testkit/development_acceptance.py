"""Real local-model development tasks through an independently launched product.

No model responses or repair steps are scripted. Outputs are private local
evidence, never release artifacts. Run from the repository root with --help.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import sqlite3
import subprocess
import sys
from threading import Event, Thread
import time
from uuid import uuid4

import httpx

ROOT = Path(__file__).resolve().parents[2]
TERMINAL = {"completed", "failed", "cancelled"}


def prepare_project(directory: Path, language: str) -> list[str]:
    directory.mkdir()
    if language == "python":
        (directory / "shipping.py").write_text(
            "def shipping_fee(weight_kg):\n    return 5 + int(weight_kg) * 2\n", encoding="utf-8",
        )
        (directory / "test_shipping.py").write_text(
            "import unittest\nfrom shipping import shipping_fee\n\n"
            "class ShippingTests(unittest.TestCase):\n"
            "    def test_started_kilogram(self):\n"
            "        self.assertEqual(shipping_fee(1.2), 9)\n"
            "        self.assertEqual(shipping_fee(0.1), 7)\n"
            "    def test_whole_kilogram(self):\n"
            "        self.assertEqual(shipping_fee(2), 9)\n"
            "        self.assertEqual(shipping_fee(0), 5)\n",
            encoding="utf-8",
        )
        (directory / "README.md").write_text(
            "# Parcel fees\n\nShipping is 5 plus 2 per started kilogram. "
            "Run `python -m unittest discover -v`. Fix implementation, preserving tests.\n", encoding="utf-8",
        )
        # A new project's own pytest root prevents it from inheriting DBFox's
        # import mode when evidence is stored under this checkout.
        (directory / "pyproject.toml").write_text(
            '[tool.pytest.ini_options]\npythonpath = ["."]\ntestpaths = ["."]\n', encoding="utf-8",
        )
        check = [sys.executable, "-m", "unittest", "discover", "-v"]
    else:
        (directory / "src").mkdir()
        (directory / "test").mkdir()
        (directory / "src" / "duration.ts").write_text(
            "export function durationMinutes(startMs: number, endMs: number): number {\n"
            "  return ((endMs - startMs) / 60000).toFixed(2);\n}\n", encoding="utf-8",
        )
        (directory / "test" / "duration.test.mjs").write_text(
            "import { test } from 'node:test';\nimport assert from 'node:assert/strict';\n"
            "import { durationMinutes } from '../src/duration.ts';\n"
            "test('numeric fractional minutes', () => {\n"
            "  assert.equal(durationMinutes(1000, 91000), 1.5);\n"
            "  assert.equal(durationMinutes(60000, 0), -1);\n"
            "  assert.equal(durationMinutes(0, 60020), 1);\n});\n", encoding="utf-8",
        )
        tsc = ROOT / "desktop/node_modules/typescript/lib/tsc.js"
        if not tsc.is_file():
            raise RuntimeError("Install the locked desktop dependencies before acceptance")
        (directory / "package.json").write_text(json.dumps({
            "name": "interval-check", "private": True, "type": "module",
            "scripts": {"check": f'node "{tsc.as_posix()}" --noEmit && node --test test/duration.test.mjs'},
        }, indent=2), encoding="utf-8")
        (directory / "tsconfig.json").write_text(json.dumps({
            "compilerOptions": {"strict": True, "noEmit": True, "target": "ES2023", "module": "ESNext"},
            "include": ["src/**/*.ts"],
        }), encoding="utf-8")
        (directory / "README.md").write_text(
            "# Intervals\n\n`npm run check` verifies types and runtime behavior. "
            "durationMinutes returns a number rounded to two decimal places. Preserve tests and configuration.\n",
            encoding="utf-8",
        )
        check = [shutil.which("npm.cmd") or "npm", "run", "check"]
    subprocess.run(["git", "init", "--quiet"], cwd=directory, check=True, capture_output=True)
    subprocess.run(["git", "add", "."], cwd=directory, check=True, capture_output=True)
    return check


def check_project(directory: Path, command: list[str]) -> dict:
    result = subprocess.run(command, cwd=directory, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
    return {"argv": command, "exit_code": result.returncode, "stdout": result.stdout, "stderr": result.stderr}


def approved_fixture_action(approval: dict, project: Path) -> bool:
    action = approval["payload"]["requested_action"]
    arguments = action["arguments"]
    name = action["tool_name"].split("__")[-1]
    if name in {"file_edit", "file_write"}:
        return arguments.get("path") in {"shipping.py", "src/duration.ts"}
    if name not in {"command_start", "command_run"}:
        return False
    review = action.get("review", {})
    if Path(review.get("cwd", "")).resolve() != project.resolve():
        return False
    if arguments.get("env") or arguments.get("lifetime", "foreground") != "foreground":
        return False
    argv = arguments.get("argv", [])
    if argv:
        program = Path(review.get("executable", "")).name.lower()
        if program in {"python.exe", "python3.exe", "py.exe"}:
            return argv[1:] == ["--version"] or argv[1:3] == ["-m", "unittest"]
        if program == "node.exe":
            return argv[1:] in (["--version"], ["--test", "test/duration.test.mjs"], ["node", "--test", "test/duration.test.mjs"]) or (
                len(argv) >= 2 and Path(argv[1]).resolve() == ROOT / "desktop/node_modules/typescript/lib/tsc.js"
            )
        if program == "pytest.exe":
            return bool(argv[1:]) and set(argv[1:]) <= {"test_shipping.py", "-v", "-q"}
        if program == "git.exe":
            args = argv[1:]
            if args[:2] == ["-C", "."]:
                args = args[2:]
            return bool(args) and (args[0] in {"diff", "status", "log", "rev-parse"} or args in (["branch", "-a"], ["branch", "--show-current"]))
    return arguments.get("shell_script", "").strip() in {"npm run check", "npm.cmd run check", "python -m unittest discover -v"}


def run_case(client: httpx.Client, output: Path, language: str, timeout: int, manual_approvals: bool, *, continue_delivery: bool = False) -> dict:
    project = output / language

    def api(path: str, data=None, method: str = "POST"):
        response = client.request(method, "/api/v1/" + path, json=data)
        response.raise_for_status()
        return response.json()

    prior = None
    if continue_delivery:
        previous_delivery = output / f"{language}-delivery-evidence.json"
        prior_path = previous_delivery if previous_delivery.exists() else output / f"{language}-evidence.json"
        prior_bytes = prior_path.read_bytes()
        prior = json.loads(prior_bytes)
        if previous_delivery.exists():
            count = len(prior["user_inputs"])
            with (output / f"{language}-delivery-inputs-{count}-evidence.json").open("xb") as archive:
                archive.write(prior_bytes)
        if not prior["independent_check_passed"]:
            raise RuntimeError("Delivery follow-up requires an independently verified repair")
        before, command = prior["before"], prior["before"]["argv"]
        session_id = prior["session_id"]
        project_id = prior["snapshot"]["session"]["project_id"]
        prompt = (
            "Publish the missing formal execution Artifact for the passing check and link it to the code modification Artifact. "
            "I need to open that execution Artifact in the workbench. Keep the repaired code, tests and configuration unchanged."
        )
        if any(artifact["type"] == "dbfox.workspace.command_result" for artifact in prior["artifacts"]):
            prompt = (
                "The execution records now exist, but their related file is a read snapshot. Link the passing execution evidence "
                "to the existing result of the actual code modification. Keep the repaired code, tests and configuration unchanged."
            )
    else:
        command = prepare_project(project, language)
        before = check_project(project, command)
        if before["exit_code"] == 0:
            raise RuntimeError("Acceptance fixture must fail before the model sees it")
        record = api("projects", {"name": f"Development acceptance {language}", "idempotency_key": str(uuid4())})
        project_id = record["id"]
        api(f"dlcs/dbfox.workspace/operations/binding.create?project_id={project_id}", {"root_path": str(project)})
        conversation = api("conversations", {"project_id": project_id, "title": f"Real local model {language}",
            "resource_intents": [{"kind": "dbfox.workspace.root", "id": project_id}]})
        session_id = conversation["session"]["id"]
        prompt = (
            "Fix the failing checks in this project. Discover the project files, available toolchain and documented check command. "
            "Reproduce the failure and read its actual diagnostics before editing the implementation. Preserve tests and configuration. "
            "Rerun the same check and inspect its exit code and output. Deliver the file change and execution record as results "
            "I can open in the workbench, linking the passing execution record to your file modification. Complete the actual repair and verification."
        )
    resource = {"kind": "dbfox.workspace.root", "id": project_id}
    suffix = "-delivery" if continue_delivery else ""
    admission = api(f"conversations/{session_id}/inputs", {"content": prompt, "idempotency_key": str(uuid4()), "requested_resources": [resource]})
    approvals, seen, previous = [], set(), None
    deadline = time.monotonic() + timeout
    snapshot = {}
    while time.monotonic() < deadline:
        snapshot = api(f"conversations/{session_id}", method="GET")
        run = next(item for item in snapshot["runs"] if item["id"] == admission["run_id"])
        if run["status"] != previous:
            print(f"{language}: {run['status']}", flush=True)
            previous = run["status"]
        for approval in snapshot["items"]:
            if approval["type"] != "approval" or approval["status"] != "waiting" or approval["id"] in seen:
                continue
            approved = approved_fixture_action(approval, project)
            if not approved and manual_approvals:
                print("REVIEW_ACTION " + json.dumps(approval["payload"]["requested_action"], ensure_ascii=False), flush=True)
                approved = input("Fixture action review (approve/reject): ").strip() == "approve"
            approvals.append({"approval": approval, "approved": approved})
            seen.add(approval["id"])
            action = approval["payload"]["requested_action"]
            print(f"{language}: {'approve' if approved else 'reject'} {action['tool_name']} {action['arguments']}", flush=True)
            api(f"approvals/{approval['id']}/resolve", {"expected_version": approval["payload"]["version"], "decision": "approve" if approved else "reject"})
        (output / f"{language}{suffix}-progress.json").write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
        if run["status"] in TERMINAL:
            break
        time.sleep(.5)
    else:
        api(f"runs/{admission['run_id']}/cancel", {})
    jobs = api(f"conversations/{session_id}/execution-jobs", method="GET")
    pages = []
    for job in jobs:
        cursor = 0
        while True:
            page = api(f"conversations/{session_id}/execution-jobs/{job['id']}?after={cursor}", method="GET")
            pages.append(page)
            if not page["has_more"] or page["next_cursor"] <= cursor:
                break
            cursor = page["next_cursor"]
    artifacts = [artifact for item in snapshot["runs"]
        for artifact in api(f"conversations/{session_id}/runs/{item['id']}/artifacts", method="GET")]
    after = check_project(project, command)
    # Only this driver-created fixture is trusted, for these read-only commands.
    # Desktop and sandbox verification may run under different Windows owners.
    git = ["git", "-c", f"safe.directory={project}", "diff", "--no-ext-diff"]
    diff = subprocess.check_output(git, cwd=project, text=True, encoding="utf-8")
    changed = subprocess.check_output([*git, "--name-only"], cwd=project, text=True).splitlines()
    expected = ["shipping.py"] if language == "python" else ["src/duration.ts"]
    result = {"language": language, "session_id": session_id, "run_id": admission["run_id"], "prompt": prompt,
              "before": before, "after": after, "diff": diff, "changed_files": changed,
              "snapshot": snapshot, "approvals": approvals, "jobs": jobs, "log_pages": pages, "artifacts": artifacts}
    result["user_inputs"] = (prior.get("user_inputs", [{"run_id": prior["run_id"], "prompt": prior["prompt"]}]) if prior else []) + [
        {"run_id": admission["run_id"], "prompt": prompt}]
    result["independent_check_passed"] = before["exit_code"] != 0 and after["exit_code"] == 0 and changed == expected
    current_hash = hashlib.sha256((project / expected[0]).read_bytes()).hexdigest()
    patches = {artifact["id"] for artifact in artifacts if artifact["type"] == "dbfox.workspace.code_patch"
               and artifact["payload"]["relativePath"] == expected[0] and artifact["payload"]["newSha256"] == current_hash
               and artifact["payload"]["oldSha256"] != current_hash}
    failed_jobs = [job for job in jobs if job["state"] == "exited" and job["root_exit_code"] not in (None, 0)
                   and job["active_processes"] == 0 and job["output_finalized"]]
    result["repeated_checks"] = [{"failed_job_id": failed["id"], "passed_job_id": job["id"]}
        for job in jobs if job["state"] == "exited" and job["root_exit_code"] == 0
        and job["active_processes"] == 0 and job["output_finalized"]
        for failed in failed_jobs
        if all(job[key] == failed[key] for key in ("executable", "argv", "shell_script", "cwd"))]
    completed_jobs = {pair["passed_job_id"] for pair in result["repeated_checks"]}
    result["linked_execution_evidence"] = [artifact["id"] for artifact in artifacts
        if artifact["type"] == "dbfox.workspace.command_result" and artifact["payload"]["job_id"] in completed_jobs
        and any(relation["relation"] == "supports" and relation["artifact_id"] in patches
                for relation in artifact["relations"])]
    result["delivery_passed"] = result["independent_check_passed"] and bool(result["linked_execution_evidence"]) and run["status"] == "completed"
    (output / f"{language}{suffix}-evidence.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / f"{language}{suffix}.diff").write_text(diff, encoding="utf-8")
    print(f"{language}: independent exit {before['exit_code']} -> {after['exit_code']}, files={changed}", flush=True)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="New private evidence directory")
    parser.add_argument("--profile", type=Path, required=True, help="Existing local-model.json; never uses a paid provider")
    parser.add_argument("--cases", nargs="+", choices=["python", "typescript"], default=["python", "typescript"])
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--manual-approvals", action="store_true", help="Review commands outside the known fixture-check allowlist on stdin")
    parser.add_argument("--continue-delivery", action="store_true", help="Append a natural-language delivery request to verified repairs; preserve initial evidence")
    parser.add_argument("--sidecar", type=Path, help="Use a built Sidecar instead of source Python")
    parser.add_argument("--system-bundle", type=Path, help="Bundle directory matching the built Sidecar's pinned publisher")
    args = parser.parse_args()
    output = args.output.resolve()
    if args.continue_delivery and not output.is_dir():
        raise RuntimeError("Delivery continuation requires an existing acceptance output")
    output.mkdir(parents=True, exist_ok=args.continue_delivery)
    runtime = output / "runtime"
    runtime.mkdir(exist_ok=args.continue_delivery)
    # Packaging imports the production model definitions; establish this
    # process's isolation before that first import as well as for the child.
    os.environ["DBFOX_RUNTIME_DIR"] = str(runtime)
    profile = json.loads(args.profile.read_text(encoding="utf-8-sig"))
    for field, child in (("state_dir", "model-state"), ("scratch_dir", "model-tmp")):
        path = output / child
        path.mkdir(exist_ok=args.continue_delivery)
        profile[field] = str(path)
    (runtime / "local-model.json").write_text(json.dumps(profile), encoding="utf-8")
    env = {key: value for key, value in os.environ.items() if not key.upper().startswith("DBFOX_")}
    if args.system_bundle:
        bundle = args.system_bundle.resolve()
        manifest = bundle / "system-dlcs.json"
    else:
        print("Building signed first-party packages", flush=True)
        from verification.testkit.system_dlc_fixture import build_isolated_system_dlc_bundle
        bundle, manifest = build_isolated_system_dlc_bundle(output / "system-dlcs")
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    token = secrets.token_urlsafe(32)
    env.update(DBFOX_RUNTIME_DIR=str(runtime), DBFOX_ENGINE_PORT=str(port), DBFOX_ENGINE_TOKEN=token,
               DBFOX_SYSTEM_DLC_DIR=str(bundle), DBFOX_SYSTEM_DLC_MANIFEST=str(manifest))
    command = [str(args.sidecar.resolve()), "--no-reload"] if args.sidecar else [sys.executable, "-m", "engine.main", "--no-reload"]
    process = None
    reader = None
    stop_reader = Event()
    results = []
    from engine.local_execution.windows import WindowsProcess

    log = (output / "sidecar.log").open("wb")
    try:
        def drain_output() -> None:
            while not stop_reader.is_set():
                for stream in ("stdout", "stderr"):
                    chunk = process.read(stream, 65536)
                    if chunk:
                        log.write(chunk)
                        log.flush()
                stop_reader.wait(.05)

        process = WindowsProcess.launch(Path(command[0]), subprocess.list2cmdline(command), ROOT, env, interactive=False)
        reader = Thread(target=drain_output, daemon=True)
        reader.start()
        print("Launching isolated production Sidecar", flush=True)
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", headers={
            "X-Local-Token": token, "Origin": "dbfox-app://localhost",
        }, trust_env=False, timeout=30) as client:
            deadline = time.monotonic() + 90
            while time.monotonic() < deadline:
                if process.root_exit_code() is not None:
                    raise RuntimeError("Sidecar exited before health; inspect private sidecar.log")
                try:
                    health = client.get("/api/v1/health")
                    if health.is_success:
                        break
                    if health.status_code != 503:
                        health.raise_for_status()
                except httpx.TransportError:
                    pass
                time.sleep(.25)
            else:
                raise RuntimeError("Sidecar did not become healthy")
            model = client.get("/api/v1/agent/local-model")
            model.raise_for_status()
            (output / "model.json").write_text(json.dumps(model.json(), indent=2), encoding="utf-8")
            for language in args.cases:
                results.append(run_case(client, output, language, args.timeout, args.manual_approvals, continue_delivery=args.continue_delivery))
    finally:
        try:
            if process is not None:
                process.terminate()
                deadline = time.monotonic() + 15
                while process.active_processes() and time.monotonic() < deadline:
                    time.sleep(.05)
                if process.active_processes():
                    raise RuntimeError("Acceptance Sidecar process tree did not stop")
        finally:
            stop_reader.set()
            if reader is not None:
                reader.join(timeout=2)
            if process is not None:
                process.close()
            log.close()
    with sqlite3.connect(f"file:{runtime / 'data/dbfox_local.db'}?mode=ro", uri=True) as db:
        facts = db.execute("SELECT id, invocation_id, state, root_exit_code, active_processes, output_finalized FROM local_execution_jobs ORDER BY created_at").fetchall()
    (output / ("independent-jobs-delivery.json" if args.continue_delivery else "independent-jobs.json")).write_text(json.dumps(facts, indent=2), encoding="utf-8")
    if not all(result["delivery_passed"] for result in results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
