#!/usr/bin/env python3
"""Stop a backend started by start_eval_backend.py
"""
import os
import sys
import subprocess
import time
from pathlib import Path

PIDFILE = Path(__file__).resolve().parent / "backend_eval.pid"


def read_pid():
    if not PIDFILE.exists():
        print("No pid file found.")
        return None
    try:
        return int(PIDFILE.read_text(encoding="utf-8").strip())
    except Exception:
        return None


def is_process_running(pid):
    try:
        if os.name == "nt":
            # tasklist contains pid
            out = subprocess.check_output(["tasklist", "/FI", f"PID eq {pid}"])
            return str(pid) in out.decode(errors="ignore")
        else:
            os.kill(pid, 0)
            return True
    except Exception:
        return False


def main():
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--force", action="store_true")
    args = p.parse_args()

    pid = read_pid()
    if not pid:
        print("No pid available to stop.")
        sys.exit(0)

    if not is_process_running(pid):
        print(f"Process {pid} not running.")
        PIDFILE.unlink(missing_ok=True)
        sys.exit(0)

    print(f"Stopping process {pid}...")
    try:
        if os.name == "nt":
            cmd = ["taskkill", "/PID", str(pid)]
            if args.force:
                cmd = ["taskkill", "/F", "/T", "/PID", str(pid)]
            subprocess.check_call(cmd)
        else:
            if args.force:
                os.kill(pid, 9)
            else:
                os.kill(pid, 15)
        # wait a little
        time.sleep(1.0)
    except Exception as e:
        print("Error stopping process:", e)
        sys.exit(1)

    # if port still occupied, show netstat snippet
    try:
        if os.name == "nt":
            out = subprocess.check_output(["netstat", "-ano"]) .decode(errors="ignore")
            lines = [l for l in out.splitlines() if "18625" in l]
            for l in lines:
                print(l)
    except Exception:
        pass

    PIDFILE.unlink(missing_ok=True)
    print("Stopped.")


if __name__ == "__main__":
    main()
