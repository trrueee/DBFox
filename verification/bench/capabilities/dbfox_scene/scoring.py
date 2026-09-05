"""Deterministic domain assertions; scorer reads never feed model decisions."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess

from dbfox_dlc_api import ArtifactRepresentationContext, ArtifactRepresentationRequest, ArtifactRepresentationStream
from engine.agent.repositories.artifact import ArtifactRepository
from verification.bench.framework.trial import TrialOutcome

from .schema import SceneCase


def score_case(runtime, case: SceneCase, evidence: dict, repetition: int) -> TrialOutcome:
    checks = {"run_completed": evidence["run_status"] == "completed"}
    invocations = {item["call_id"]: item for item in evidence["invocations"]}
    observations = {item["call_id"]: item for item in evidence["observations"]}
    expected = [step for step in case.steps if step.kind == "tool"]
    checks["exact_tool_sequence"] = list(invocations) == [step.id for step in expected]
    checks["owner_and_package"] = all(item["owner"] == "dbfox.scene" and item["package_digest"] == evidence["package_digest"]
        for item in invocations.values())
    checks["no_write_replay"] = all(item["attempts"] == 1 for item in invocations.values() if item["status"] == "succeeded")
    for step in expected:
        invocation = invocations.get(step.id)
        checks[f"step.{step.id}"] = invocation is not None and ((invocation["status"] == "succeeded") == step.succeeds)
    facts = [item["facts"] for item in observations.values() if isinstance(item["facts"].get("scene"), dict)]
    checks["scene_observed"] = bool(facts)
    final_scene = facts[-1]["scene"] if facts else None
    if final_scene:
        live = runtime.operation(evidence["project_id"], "scenes.get", {"scene_id": final_scene["id"], "limit": 1})["scene"]
        evidence["final_scene"] = live
        checks["observed_head"] = live["version"] == final_scene["version"]
        checks["object_count"] = live["object_count"] == case.object_count
        checks["material_count"] = live["material_count"] == case.material_count
        cache = {}

        def document(version):
            if version not in cache:
                cache[version] = runtime.document(evidence["project_id"], live["id"], version)
            return cache[version]

        final = document(live["version"])
        indexed = {item["id"]: item for section in ("objects", "materials") for item in final[section]}
        for key, expected_value in case.assertions.items():
            entity, *path = key.split("/")
            actual = indexed.get(entity)
            for field in path:
                actual = actual.get(field) if isinstance(actual, dict) else None
            checks[f"domain.{key}"] = actual == expected_value
        last_scene = None
        pending_unchanged = None
        for step in case.steps:
            if step.kind == "human":
                human = next((item for item in evidence["human_edits"] if item["step"] == step.id), None)
                if human:
                    last_scene = human["result"]["scene"]
                continue
            observation = observations.get(step.id)
            if pending_unchanged and observation and "scene" in observation["facts"] and step.tool == "scene_inspect":
                seen = observation["facts"]["scene"]
                checks[f"no_partial_commit.{step.id}"] = seen["version"] == pending_unchanged["version"] and seen["content_hash"] == pending_unchanged["content_hash"]
                pending_unchanged = None
            if step.unchanged and last_scene:
                after = observation["facts"].get("scene", last_scene) if observation else last_scene
                checks[f"unchanged.{step.id}"] = after["version"] == last_scene["version"] and after["content_hash"] == last_scene["content_hash"]
                if not step.succeeds:
                    pending_unchanged = last_scene
            if not observation or "scene" not in observation["facts"]:
                continue
            after = observation["facts"]["scene"]
            invocation = invocations[step.id]
            payload = invocation["input"]
            if "expected_version" in payload:
                refs = invocation["resource_refs"]
                checks[f"binding.{step.id}"] = len(refs) == 1 and refs[0]["id"] == live["id"]
                if step.succeeds:
                    checks[f"fence.{step.id}"] = refs[0]["version"] == payload["expected_version"]
            operation = payload.get("operation", {})
            if step.succeeds and step.tool in {"object_transform", "object_update", "light_update", "camera_update", "object_reparent"}:
                before_doc = document(payload["expected_version"])
                after_doc = document(after["version"])
                before_nodes = {node["id"]: node for node in before_doc["objects"]}
                after_nodes = {node["id"]: node for node in after_doc["objects"]}
                targets = set(operation.get("object_ids", []))
                targets.update(item["object_id"] for item in operation.get("transforms", []))
                targets.update(operation[field] for field in ("object_id", "light_id", "camera_id") if field in operation)
                checks[f"locality.{step.id}"] = before_nodes.keys() == after_nodes.keys() and all(
                    value == after_nodes[identity] for identity, value in before_nodes.items() if identity not in targets)
            last_scene = after
        # Final authoritative version must match the last observation even for answer-only negative steps.
        checks["no_hidden_mutation"] = live["content_hash"] == final_scene["content_hash"]
        evidence["stable_object_ids"] = sorted(node["id"] for node in final["objects"])
    checks["scene_context_present"] = any(evidence["scene_contexts"])
    checks["context_budget"] = all(sum(len(fragment["content"]) for fragment in group) <= 4000 for group in evidence["scene_contexts"])
    checks["context_no_document"] = all('"position"' not in fragment["content"] and '"vertices"' not in fragment["content"]
        for group in evidence["scene_contexts"] for fragment in group)
    checks["observation_budget"] = evidence["max_observation_bytes"] <= 65_536
    evidence["checks"] = checks
    failures = tuple(name for name, passed in checks.items() if not passed)
    return TrialOutcome(suite_id="capability.dbfox-scene.scripted", case_id=case.case_id, repetition=repetition,
        verdict="fail" if failures else "pass", failed_checks=failures, metrics={
            "task.success_rate": 0.0 if failures else 1.0,
            "runtime.tool_calls": float(len(invocations)), "runtime.turns": float(evidence["turns"]),
            "scene.objects": float(final_scene["object_count"] if final_scene else 0),
            "context.scene_chars": float(max((sum(len(f["content"]) for f in group) for group in evidence["scene_contexts"]), default=0)),
            "observation.max_bytes": float(evidence["max_observation_bytes"]),
        }, evidence=evidence)


def export_stress(runtime, outcome: TrialOutcome, output_dir: Path) -> None:
    evidence = outcome.evidence
    final = evidence["final_scene"]
    identity = next(item["id"] for item in reversed(evidence["artifacts"]) if item["payload"]["version"] == final["version"])
    with runtime.factory() as db:
        artifact = ArtifactRepository(db).get(identity)
    assert artifact is not None
    provider = runtime.snapshot.get_artifact_representation("dbfox.scene.revision", "dbfox.scene.document.v1").provider
    paths = []
    exports = []
    for suffix in ("gltf", "glb"):
        result = provider.execute(artifact, ArtifactRepresentationRequest(operation=f"export_{suffix}"),
            ArtifactRepresentationContext(artifact_loader=lambda key: None))
        assert isinstance(result, ArtifactRepresentationStream)
        content = b"".join(result.chunks)
        path = output_dir / f"fox-temple.{suffix}"
        path.write_bytes(content)
        paths.append(str(path))
        exports.append({"file": path.name, "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest(), "metadata": result.metadata})
    from .runtime import SOURCE
    validation = subprocess.run(["node", str(SOURCE / "validate-gltf.mjs"), *paths], capture_output=True, text=True, encoding="utf-8", check=False)
    report = {"artifact_id": identity, "scene_id": final["id"], "version": final["version"], "exports": exports,
        "validator_exit_code": validation.returncode, "validator_stdout": validation.stdout, "validator_stderr": validation.stderr}
    (output_dir / "export-evidence.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    if validation.returncode:
        raise AssertionError(report)
