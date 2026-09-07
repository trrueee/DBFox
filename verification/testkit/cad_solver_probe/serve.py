"""Serve an upstream solver under actual and candidate CSP, without changing Host."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import json
import re

ROOT = Path(__file__).resolve().parents[3]
PACKAGE = (ROOT / "output/cad-solver-probe/package").resolve()
source = (ROOT / "desktop/main/appProtocol.ts").read_text(encoding="utf-8")
block = source.split("export const CONTENT_SECURITY_POLICY = [", 1)[1].split("].join", 1)[0]
POLICY = "; ".join(re.findall(r'^\s*"([^"]+)"', block, re.MULTILINE))
assert "script-src 'self' dlc-asset:" in POLICY
CANDIDATE = POLICY.replace("script-src 'self' dlc-asset:", "script-src 'self' dlc-asset: 'wasm-unsafe-eval'")


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/strict", "/wasm-only"):
            body = b'<!doctype html><meta charset="utf-8"><title>CAD solver policy probe</title><h1>CAD solver policy probe</h1><pre>Running</pre><script type="module" src="/browser.mjs"></script>'
            mime = "text/html; charset=utf-8"
        elif self.path == "/browser.mjs":
            body = Path(__file__).with_name("browser.mjs").read_bytes()
            mime = "text/javascript"
        elif self.path.startswith("/package/"):
            target = (PACKAGE / self.path.removeprefix("/package/")).resolve()
            if not target.is_relative_to(PACKAGE) or not target.is_file():
                self.send_error(404)
                return
            body = target.read_bytes()
            mime = "application/wasm" if target.suffix == ".wasm" else "text/javascript"
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        if self.path in ("/strict", "/wasm-only"):
            self.send_header("Content-Security-Policy", POLICY if self.path == "/strict" else CANDIDATE)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        pass


if __name__ == "__main__":
    print(json.dumps({"port": 18846, "actual_policy": POLICY, "candidate_policy": CANDIDATE}), flush=True)
    ThreadingHTTPServer(("127.0.0.1", 18846), Handler).serve_forever()
