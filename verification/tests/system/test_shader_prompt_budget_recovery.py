"""Director investigation: recover a committed large call through public inspection."""
import json
import re

from engine.runtime_composition import build_product_run_loop
from verification.bench.capabilities.dbfox_shader import runtime as suite
from verification.bench.capabilities.dbfox_shader.build_cases import VERTEX
from verification.bench.capabilities.dbfox_shader.schema import ShaderCase
from verification.testkit.scripted_provider import ScriptedProvider, answer_events, tool_call_events


def test_large_native_call_eviction_preserves_ledger_and_public_recovery(tmp_path, monkeypatch):
    source = VERTEX + "".join(f"// bounded shader module line {i:03d}: preserve exact content\n" for i in range(120))
    operations = [{"kind": "stage_create", "ref": f"module_{i}", "stage_kind": "vertex",
                   "title": f"Module {i}", "source": source} for i in range(60)]
    checkpoints = {}

    class RecoveryScript(suite.ShaderScript):
        def stream(self, *, messages, tools, **kwargs):
            observed = {item["call_id"]: json.loads(item["output"])
                        for item in messages if item.get("type") == "function_call_output"}
            phase = len(self.requests)
            if phase == 0:
                name, args = "shader_create", {"title": "Large single call", "expected_generation": 0}
            elif phase == 1:
                document = observed["budget-0"]["facts"]["document"]
                checkpoints["created"] = document
                name, args = "shader_modify", {"document_id": document["id"], "expected_version": 1, "operations": operations}
                checkpoints["input_bytes"] = len(json.dumps(args).encode())
            elif phase == 2:
                # The whole native turn is evicted as a unit; no orphan output is
                # invented. Read the existing durable ledger, then ask the owner.
                assert "budget-1" not in observed
                ledger = next(item["content"] for item in messages
                              if 'source="durable_evidence_ledger"' in str(item.get("content", "")))
                assert "succeeded" in ledger and checkpoints["created"]["id"] in ledger and "v2" in ledger
                assert "artifact_ids" in ledger
                checkpoints["ledger"] = ledger
                native_calls = {item["call_id"] for item in messages if item.get("type") == "function_call"}
                assert native_calls == set(observed)
                # No cached ID/version/result is used to reconstruct the mutation.
                name, args = "shader_inspect", {"section": "documents", "limit": 10}
            elif phase == 3:
                listing = observed["budget-2"]["facts"]
                document = listing["items"][0]
                assert document["version"] == 2
                name, args = "shader_inspect", {"document_id": document["id"], "version": document["version"], "section": "stages", "limit": 10}
            elif phase == 4:
                page = observed["budget-3"]["facts"]
                module = next(item for item in page["items"] if item["title"] == "Module 0")
                name, args = "shader_inspect", {"document_id": page["document"]["id"], "version": page["document"]["version"], "section": "source", "stage_id": module["id"], "limit": 10}
            elif phase == 5:
                page = observed["budget-4"]["facts"]
                name, args = "shader_export", {"document_id": page["document"]["id"], "expected_version": page["document"]["version"]}
            else:
                assert observed["budget-5"]["status"] == "succeeded"
                yield from ScriptedProvider(answer_events("All 60 modules were saved once. Public inspection recovered the current revision after context compaction; no GPU compilation was requested.")).stream()
                return
            identity = f"budget-{phase}"
            wire = self.tool_names[name]
            assert wire in {item["name"] for item in tools}
            self.requests.append({"id": identity, "tool": name, "arguments": args})
            yield from ScriptedProvider(tool_call_events(call_id=identity, tool_name=wire, arguments=args)).stream()

    with suite.ShaderRuntime(tmp_path) as runtime:
        def production_factory(**arguments):
            loop = build_product_run_loop(session_factory=runtime.factory, snapshot=runtime.snapshot)
            loop.model_factory = arguments["model_factory"]
            return loop

        monkeypatch.setattr(suite, "RunLoop", production_factory)
        monkeypatch.setattr(suite, "ShaderScript", RecoveryScript)
        case = ShaderCase(case_id="large-call-recovery", category="context_budget", steps=(),
                          prompt="Create 60 extra shader modules in one explicit batch, then inspect the committed result. If the native transcript is compacted, use public inspection and do not replay the edit.")
        evidence, _ = suite.run_segment(runtime, case)
        assert evidence["run_status"] == "completed", evidence["run_status"]
        assert len(evidence["invocations"]) == 6, [(item["call_id"], item["status"]) for item in evidence["invocations"]]
        assert all(item["status"] == "succeeded" and item["attempts"] == 1 for item in evidence["invocations"])
        assert 400_000 < checkpoints["input_bytes"] < 786_432
        assert len([item for item in evidence["requests"] if item["tool"] == "shader_modify"]) == 1
        identity = checkpoints["created"]["id"]
        head = runtime.operation(evidence["project_id"], "documents.head", {"document_id": identity})
        assert head["version"] == 2
        complete = runtime.document(evidence["project_id"], identity, 2)
        assert len(complete["document"]["stages"]) == 62
        assert all(stage["source"] == source for stage in complete["document"]["stages"][2:])
        assert len(evidence["artifacts"]) == 3
        ledger_data = re.search(r'(\[.*\])\n</dbfox_context>', checkpoints["ledger"], re.S)
        assert ledger_data is not None
        assert sum(len(item["artifact_ids"]) for item in json.loads(ledger_data[1])) == 2
