#!/usr/bin/env python3
"""Start a farm of isolated eval backend workers, each with its own SQLite DB.

Usage:
    python .agent_eval/start_eval_farm.py --workers 4
    python .agent_eval/start_eval_farm.py --stop
"""

from __future__ import annotations
import argparse, json, os, shutil, signal, subprocess, sys, time
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
RUNTIME = HERE / "runtime" / "farm"
POOL_FILE = RUNTIME / "backend_pool.json"
PID_FILE = RUNTIME / "farm_pids.json"
BASE_DB = Path("databox_local.db")


def stop_farm():
    if not PID_FILE.exists():
        print("No farm running.")
        return
    pids = json.loads(PID_FILE.read_text())
    for entry in pids:
        pid = entry.get("pid", 0)
        if pid:
            try:
                os.kill(pid, signal.SIGTERM)
                print(f"Killed worker {entry.get('worker_id','?')} pid={pid}")
            except Exception:
                pass
    PID_FILE.unlink(missing_ok=True)
    print("Farm stopped.")


def start_farm(workers: int, base_port: int, config_path: str | None):
    RUNTIME.mkdir(parents=True, exist_ok=True)

    # Stop any existing farm
    if PID_FILE.exists():
        stop_farm()

    # Load config for LLM key propagation
    env_extra = {}
    if config_path:
        cfg_path = Path(config_path)
        if cfg_path.exists():
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
            llm = cfg.get("llm", {})
            if isinstance(llm, dict):
                if llm.get("provider"):
                    env_extra["DATABOX_LLM_PROVIDER"] = str(llm["provider"])
                if llm.get("model_name"):
                    env_extra["DATABOX_LLM_MODEL"] = str(llm["model_name"])
                if llm.get("api_key"):
                    env_extra["DATABOX_LLM_API_KEY"] = str(llm["api_key"])
                if llm.get("api_base"):
                    env_extra["DATABOX_LLM_API_BASE"] = str(llm["api_base"])

    workers_info = []
    base_db_path = Path(BASE_DB)

    for i in range(workers):
        worker_dir = RUNTIME / f"worker_{i}"
        worker_dir.mkdir(parents=True, exist_ok=True)
        worker_db = worker_dir / "databox_worker.db"
        port = base_port + i

        # Copy base DB if this worker doesn't have one yet
        if not worker_db.exists() and base_db_path.exists():
            shutil.copy2(base_db_path, worker_db)

        # Environment
        env = os.environ.copy()
        env["AGENT_PERSISTENCE_MODE"] = "disabled"
        env["AGENT_PERSIST_RUNTIME_EVENTS"] = "false"
        env["AGENT_DB_WRITE_TRACE"] = "false"
        env.update(env_extra)

        # Launch uvicorn
        stdout_log = worker_dir / "stdout.log"
        stderr_log = worker_dir / "stderr.log"
        out_f = open(stdout_log, "a", encoding="utf-8")
        err_f = open(stderr_log, "a", encoding="utf-8")

        proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "engine.main:app",
             "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
            stdout=out_f, stderr=err_f, env=env,
            cwd=str(Path(__file__).resolve().parent.parent),
        )
        workers_info.append({
            "worker_id": i,
            "base_url": f"http://127.0.0.1:{port}",
            "pid": proc.pid,
            "port": port,
            "db_path": str(worker_db),
            "stdout_log": str(stdout_log),
            "stderr_log": str(stderr_log),
        })
        print(f"Worker {i}: port={port} pid={proc.pid} db={worker_db.name}")

    # Wait for all workers to be healthy
    print("Waiting for workers to be healthy...")
    deadline = time.time() + 60
    all_healthy = False
    while time.time() < deadline:
        healthy = 0
        for w in workers_info:
            try:
                r = httpx.get(f"{w['base_url']}/api/v1/health", timeout=2.0)
                if r.status_code == 200:
                    healthy += 1
            except Exception:
                pass
        if healthy == workers:
            all_healthy = True
            break
        time.sleep(1)

    if not all_healthy:
        print("ERROR: not all workers healthy. Check stderr logs.")
        for w in workers_info:
            print(f"  Worker {w['worker_id']}: {w['stderr_log']}")
        # Kill started workers
        for w in workers_info:
            try: os.kill(w["pid"], signal.SIGTERM)
            except: pass
        sys.exit(1)

    # Write pool files
    POOL_FILE.write_text(json.dumps({"workers": workers_info}, indent=2))
    PID_FILE.write_text(json.dumps([{"worker_id": w["worker_id"], "pid": w["pid"]} for w in workers_info], indent=2))

    print(f"\nFarm ready: {workers} workers on ports {base_port}-{base_port + workers - 1}")
    print(f"Pool file: {POOL_FILE}")
    print(f"PIDs: {PID_FILE}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--base-port", type=int, default=18625)
    parser.add_argument("--config", default=str(HERE / "config.local.json"))
    parser.add_argument("--stop", action="store_true")
    args = parser.parse_args()

    if args.stop:
        stop_farm()
    else:
        start_farm(args.workers, args.base_port, args.config)


if __name__ == "__main__":
    main()
