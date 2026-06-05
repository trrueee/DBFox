#!/usr/bin/env python3
"""Check overall eval environment: docker, spider mysql, mysql tables, backend health and token.

Outputs JSON and human readable summary. Exits non-zero if any check fails.
"""
import json
import argparse
import socket
import subprocess
from pathlib import Path

import httpx

from eval_common import load_llm_config

ROOT = Path(__file__).resolve().parent


def docker_available():
    try:
        subprocess.check_call(["docker", "ps"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception:
        return False


def mysql_port_open(host, port=3307):
    try:
        with socket.create_connection((host, port), timeout=2.0):
            return True
    except Exception:
        return False


def mysql_show_tables_ok(host="127.0.0.1", port=3307, user="root", password="root"):
    # Try simple mysql client invocation if available
    try:
        out = subprocess.check_output(["mysql", f"-h{host}", f"-P{port}", f"-u{user}", f"-p{password}", "-e", "SHOW TABLES;"], stderr=subprocess.STDOUT)
        txt = out.decode(errors="ignore")
        return "Tables_in_" in txt or txt.strip() != ""
    except Exception:
        return False


def backend_health_ok(base_url="http://127.0.0.1:18625"):
    try:
        r = httpx.get(f"{base_url.rstrip('/')}/api/v1/health", timeout=2.0)
        return r.status_code == 200
    except Exception:
        return False


def token_exists():
    # check known locations
    try:
        from engine.runtime_paths import private_runtime_file
        p = Path(private_runtime_file("auth", ".local_token"))
        if p.exists():
            return True
    except Exception:
        pass
    p = Path.home() / "AppData" / "Roaming" / "DataBox" / "auth" / ".local_token"
    return p.exists()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=None)
    args = parser.parse_args()
    out = {
        "docker": docker_available(),
        "mysql_port_3307": mysql_port_open("127.0.0.1", 3307),
        "mysql_show_tables": mysql_show_tables_ok(),
        "backend_health": backend_health_ok(),
        "token_exists": token_exists(),
    }
    llm_cfg = load_llm_config(args.config)
    out["llm_config"] = {
        "config_file_exists": bool(llm_cfg.get("source", {}).get("config_exists")),
        "provider": llm_cfg.get("provider"),
        "model_name": llm_cfg.get("model_name"),
        "has_api_key": bool(llm_cfg.get("api_key")),
        "api_key_source": llm_cfg.get("source", {}).get("config_path") if llm_cfg.get("source", {}).get("config_exists") else "env",
        "api_base_set": bool(llm_cfg.get("api_base")),
    }
    ok = all(out.values())
    print(json.dumps(out, ensure_ascii=False))
    print("\nSummary:")
    for k, v in out.items():
        print(f" - {k}: {v}")
    # If running a P1 targeted run, require API key to be configured
    if not out["llm_config"]["has_api_key"]:
        print("\nERROR: P1 complex fallback requires a configured LLM API key. Current environment has_api_key=false.")
        raise SystemExit(5)
    if not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
