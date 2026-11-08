"""Loopback author UI fixture with the full signed package's real operations."""
from __future__ import annotations

from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import tempfile


def main():
    root = Path(__file__).resolve().parents[3]
    os.chdir(root)
    with tempfile.TemporaryDirectory(prefix="dbfox-game-author-") as directory:
        os.environ["DBFOX_RUNTIME_DIR"] = directory
        os.environ["DBFOX_TESTING"] = "1"
        from verification.bench.capabilities.dbfox_game.runtime import GameBench
        bench = GameBench(Path(directory))
        source = (root / "desktop/main/appProtocol.ts").read_text(encoding="utf-8")
        section = source.split("CONTENT_SECURITY_POLICY = [", 1)[1].split("].join", 1)[0]
        policy = "; ".join(re.findall(r'^  "([^"]+)"', section, re.M))

        class Handler(SimpleHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def end_headers(self):
                self.send_header("Content-Security-Policy", policy)
                self.send_header("Cache-Control", "no-store")
                super().end_headers()

            def do_GET(self):
                if not self.path.startswith(("/.tmp/game-phaser-review/", "/dlcs/dbfox.game/frontend/")) or ".." in self.path:
                    self.send_error(404)
                    return
                super().do_GET()

            def do_POST(self):
                size = int(self.headers.get("Content-Length", "0"))
                if self.path != "/operation" or not 0 < size <= 1048576:
                    self.send_error(400)
                    return
                try:
                    request = json.loads(self.rfile.read(size))
                    result = bench.operation("game-author-browser", request["name"], request["input"])
                    code = 200
                except Exception as error:
                    result, code = {"message": str(error)}, 400
                body = json.dumps(result).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        server = ThreadingHTTPServer(("127.0.0.1", 18941), Handler)
        print("Author Studio: http://127.0.0.1:18941/.tmp/game-phaser-review/studio.html", flush=True)
        try:
            server.serve_forever()
        finally:
            server.server_close()
            bench.close()


if __name__ == "__main__":
    main()
