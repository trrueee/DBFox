"""Independent Agent edit against an already running Electron fixture's durable world."""
from __future__ import annotations

import json
from pathlib import Path
import sys
from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy.orm import sessionmaker
from dbfox_dlc_api import ToolKey
from engine.models import AgentSession
from engine.runtime_composition import initialize_runtime_snapshot, build_product_tool_registry
from verification.support.metadata import create_migrated_metadata_engine
from .runtime import VoxelRuntime, VoxelScript, _run_segment
from .schema import VoxelCase, Step


def run(directory: Path, output: Path, coordinate: int = 28) -> None:
    fixture = json.loads((directory / "browser-fixture.json").read_text(encoding="utf-8"))
    snapshot = initialize_runtime_snapshot(storage_root=directory / "dlcs")
    assert not snapshot.activation_failures
    engine = create_migrated_metadata_engine(directory / "metadata.sqlite")
    runtime = SimpleNamespace(snapshot=snapshot, engine=engine, factory=sessionmaker(bind=engine, expire_on_commit=False),
        registry=build_product_tool_registry(snapshot), package=SimpleNamespace(package_digest=fixture["package_digest"]))
    runtime.operation = lambda project, name, payload: VoxelRuntime.operation(runtime, project, name, payload)
    project, world_id = fixture["project_id"], fixture["small_world_id"]
    session_id = "voxel-browser-agent-" + uuid4().hex
    with runtime.factory() as db:
        db.add(AgentSession(id=session_id, project_id=project, title="Independent Agent and human continuity"))
        db.commit()
    case = VoxelCase(case_id="browser-agent-continuity", category="human_agent", prompt="Inspect the human-edited world; add exactly one cyan block without replacing anything else.", steps=(
        Step(id="observe-human", tool="voxel_inspect", arguments={"world_id": "$world_id"}),
        Step(id="agent-add", tool="voxel_fill", arguments={"world_id": "$world_id", "expected_version": "$version",
            "operation": {"kind": "fill", "layer_id": "base", "bounds": {"min": [coordinate]*3, "max": [coordinate+1]*3}, "palette_index": 3}}),
        Step(id="verify-current", tool="voxel_inspect", arguments={"world_id": "$world_id"}),))
    script = VoxelScript(case, lambda name, payload: runtime.operation(project, name, payload),
        {item.tool.name: runtime.registry.provider_name_for_key(ToolKey(owner_id="dbfox.voxel", local_name=item.tool.name))
            for item in snapshot.tools if item.owner_id == "dbfox.voxel"})
    script.voxel = {"world_id": world_id}  # User-selected identity only; version must come from inspect.
    evidence, _ = _run_segment(runtime, case, repetition=1, script=script, project_id=project, session_id=session_id)
    assert evidence["run_status"] == "completed"
    assert len(evidence["invocations"]) == 3 and all(item["status"] == "succeeded" and item["attempts"] == 1 for item in evidence["invocations"])
    facts = evidence["provider_observations"]
    assert facts["agent-add"]["facts"]["version"] == facts["observe-human"]["facts"]["version"] + 1
    evidence["boundary"] = "Production RunLoop, actual installed signed owner and shared metadata/store; scripted Responses only"
    output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"run_id": evidence["run_id"], "before": facts["observe-human"]["facts"]["version"], "after": facts["agent-add"]["facts"]["version"]}))
    engine.dispose()


if __name__ == "__main__":
    run(Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve(), int(sys.argv[3]) if len(sys.argv)>3 else 28)
