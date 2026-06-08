#!/usr/bin/env python3
"""Check backend listening, health and token existence; output JSON.
"""
import socket
import json
from pathlib import Path
from typing import Optional

import httpx

ROOT = Path(__file__).resolve().parent
PIDFILE = ROOT / "backend_eval.pid"


def is_listening(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=1.0):
            return True
    except Exception:
        return False


def read_pid() -> Optional[int]:
    if PIDFILE.exists():
        try:
            return int(PIDFILE.read_text(encoding="utf-8").strip())
        except Exception:
            return None
    return None


def find_token_path():
    # try engine.runtime_paths first
    try:
        from engine.runtime_paths import private_runtime_file

        p = Path(private_runtime_file("auth", ".local_token"))
        if p.exists():
            return p
    except Exception:
        pass
    # fallback
    p = Path.home() / "AppData" / "Roaming" / "DataBox" / "auth" / ".local_token"
    if p.exists():
        return p
    return None


def main():
    out = {"listening": False, "health_ok": False, "token_exists": False, "pid": None, "error": None}
    try:
        listening = is_listening("127.0.0.1", 18625)
        out["listening"] = listening
        pid = read_pid()
        out["pid"] = pid

        token = find_token_path()
        out["token_exists"] = bool(token)

        if listening:
            try:
                r = httpx.get("http://127.0.0.1:18625/api/v1/health", timeout=2.0)
                out["health_ok"] = r.status_code == 200
            except Exception as e:
                out["error"] = str(e)
    except Exception as e:
        out["error"] = str(e)

    print(json.dumps(out, ensure_ascii=False))
    if not (out["listening"] and out["health_ok"] and out["token_exists"]):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
