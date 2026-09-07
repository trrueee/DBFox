"""Loopback-only model boundary for the unmodified production Responses client.

Reuse stdlib HTTP/SSE and the installed official SDK's event schema. All domain
identities and outcomes come from actual function_call_output messages. This
process never imports DBFox, accesses its database, or supplies Tool results.
"""
from __future__ import annotations

import copy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
from threading import Lock

from openai.types.responses import ResponseStreamEvent
from pydantic import TypeAdapter

EVENT = TypeAdapter(ResponseStreamEvent)


def events(item: dict, sequence: int):
    final = {**item, "status": "completed"}
    initial = {**item, "status": "in_progress"}
    if item["type"] == "function_call":
        initial["arguments"] = ""
    else:
        initial["content"] = []
    values = [{"type": "response.output_item.added", "sequence_number": 1, "output_index": 0, "item": initial}]
    if item["type"] == "function_call":
        values.append({"type": "response.function_call_arguments.delta", "sequence_number": 2,
                       "output_index": 0, "item_id": item["id"], "delta": item["arguments"]})
    values.extend([
        {"type": "response.output_item.done", "sequence_number": 3, "output_index": 0, "item": final},
        {"type": "response.completed", "sequence_number": 4, "response": {
            "id": f"resp_game_{sequence}", "created_at": 0, "model": "game-author-native", "object": "response",
            "output": [final], "parallel_tool_calls": False, "tool_choice": "auto", "tools": [],
            "status": "completed", "usage": None, "incomplete_details": None,
        }},
    ])
    for value in values:
        EVENT.validate_python(value)
        yield f"event: {value['type']}\ndata: {json.dumps(value, ensure_ascii=False)}\n\n".encode()


class Script:
    def __init__(self, plan: dict):
        self.plan = plan
        self.index = 0
        self.observations = {}
        self.last = {}
        self.summary = None
        self.requests = []
        self.windows = []
        self.errors = []

    def resolve(self, value):
        if isinstance(value, str) and value.startswith("$"):
            if value in ("$game_id", "$version"):
                assert self.summary is not None, 'No public document observation has arrived'
                return self.summary['id' if value == '$game_id' else 'version']
            label, *path = value[1:].split(".")
            current = self.last if label == "last" else self.observations[label]["facts"]
            for key in path:
                current = current[int(key)] if isinstance(current, list) else current[key]
            return current
        if isinstance(value, list):
            return [self.resolve(item) for item in value]
        if isinstance(value, dict):
            return {key: self.resolve(item) for key, item in value.items()}
        return value

    def next(self, request: dict) -> dict:
        assert request["stream"] is True and request["store"] is False
        visible = []
        for item in request["input"]:
            if item.get("type") != "function_call_output":
                continue
            visible.append(item["call_id"])
            if item["call_id"] not in self.observations:
                output = json.loads(item["output"])
                self.observations[item["call_id"]] = output
                self.last = output.get("facts", {})
                if 'id' in self.last.get('game', {}) and 'version' in self.last['game']:
                    self.summary = self.last['game']
        self.windows.append({"visible_call_ids": visible, "input_bytes": len(json.dumps(request["input"]).encode())})
        if self.index == len(self.plan["steps"]):
            return {"id": f"msg_{self.index}", "type": "message", "role": "assistant", "phase": "final_answer",
                    "content": [{"type": "output_text", "text": self.plan["answer"], "annotations": [], "logprobs": []}]}
        step = self.plan["steps"][self.index]
        if step.get('kind') == 'answer':
            self.index += 1
            return {"id": f"msg_{step['id']}", "type": "message", "role": "assistant", "phase": "final_answer",
                    "content": [{"type": "output_text", "text": step['text'], "annotations": [], "logprobs": []}]}
        for check in step.get("requires", []):
            actual = self.resolve(check["path"])
            assert actual == check["equals"], {"step": step["id"], "path": check["path"], "actual": actual}
        names = [tool["name"] for tool in request["tools"] if tool["name"].endswith("__" + step["tool"])]
        assert len(names) == 1, {"tool": step["tool"], "matches": names}
        args = self.resolve(copy.deepcopy(step["arguments"]))
        self.requests.append({"id": step["id"], "name": names[0], "arguments": args})
        self.index += 1
        return {"id": f"fc_{step['id']}", "type": "function_call", "call_id": step["id"], "name": names[0],
                "arguments": json.dumps(args, ensure_ascii=False)}

    def evidence(self):
        return {"next_step": self.index, "requests": self.requests, "observations": self.observations,
                "windows": self.windows, "errors": self.errors}


def serve(plans_path: Path, evidence_path: Path, port: int = 19330):
    states: dict[str, Script] = {}
    lock = Lock()

    def persist():
        evidence_path.write_text(json.dumps({key: value.evidence() for key, value in states.items()}, ensure_ascii=False, indent=2), encoding="utf-8")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass  # Never log request headers or credentials.

        def do_GET(self):
            if self.path != "/status":
                self.send_error(404)
                return
            with lock:
                body = json.dumps({key: {"next_step": value.index, "errors": value.errors} for key, value in states.items()}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            if self.path != "/v1/responses":
                self.send_error(404)
                return
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 2_097_152:
                self.send_error(413)
                return
            payload = json.loads(self.rfile.read(length))
            try:
                with lock:
                    model = payload["model"]
                    if model not in states:
                        plans = json.loads(plans_path.read_text(encoding="utf-8"))
                        states[model] = Script(plans[model])
                    state = states[model]
                    try:
                        wire = b"".join(events(state.next(payload), state.index))
                    except Exception as error:
                        state.errors.append({"type": type(error).__name__, "detail": str(error)[:1000]})
                        raise
                    finally:
                        persist()
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Content-Length", str(len(wire)))
                self.end_headers()
                self.wfile.write(wire)
            except Exception:
                self.send_error(500, "Author scripted model precondition failed; inspect its evidence")

    print(json.dumps({"boundary": "only native model Responses SSE; real tools remain in Sidecar", "port": port}), flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()


if __name__ == "__main__":
    serve(Path(sys.argv[1]), Path(sys.argv[2]))
