"""Voxel-specific deterministic checks; never feed scorer state into the model."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from dbfox_dlc_api import ArtifactRepresentationContext, ArtifactRepresentationRequest
from engine.agent.repositories.artifact import ArtifactRepository
from verification.bench.framework.trial import TrialOutcome


def _target_bounds(operation):
    kind = operation.get("kind")
    if kind == "sphere":
        center, radius = operation["center"], operation["radius"]
        return [n - radius for n in center], [n + radius + 1 for n in center]
    if "bounds" not in operation:
        return None
    low, high = operation["bounds"]["min"], operation["bounds"]["max"]
    if kind in {"copy_region", "mirror"}:
        target = operation["destination"]
        return target, [target[i] + high[i] - low[i] for i in range(3)]
    if kind == "extrude":
        low, high = list(low), list(high)
        axis = "xyz".index(operation["axis"])
        if operation.get("direction", 1) == 1:
            high[axis] += operation["depth"]
        else:
            low[axis] -= operation["depth"]
    return low, high


def _local_changes(before, after, operation):
    bounds = _target_bounds(operation)
    if bounds is None:
        return False
    low, high = bounds
    for key in before.keys() | after.keys():
        old, new = before.get(key, bytes(4096)), after.get(key, bytes(4096))
        if old == new:
            continue
        if key[0] != operation["layer_id"]:
            return False
        for offset, (a, b) in enumerate(zip(old, new)):
            if a != b:
                xyz = [key[1] * 16 + offset % 16, key[2] * 16 + offset // 256,
                       key[3] * 16 + (offset // 16) % 16]
                if not all(low[i] <= xyz[i] < high[i] for i in range(3)):
                    return False
    return True


def score_case(runtime, case, evidence, repetition):
    expected = [step for step in case.steps if step.kind == "tool"]
    invocations = {row["call_id"]: row for row in evidence["invocations"]}
    observations = {row["call_id"]: row for row in evidence["observations"]}
    checks = {
        "all_runs_completed": all(run["status"] == "completed" for run in evidence["runs"]),
        "exact_tool_sequence": list(invocations) == [step.id for step in expected],
        "owner_and_package": all(row["owner"] == "dbfox.voxel" and row["package_digest"] == evidence["package_digest"] for row in invocations.values()),
        "no_write_replay": all(row["attempts"] == (0 if row["status"] == "rejected" else 1) for row in invocations.values()),
        "contexts_present": any(evidence["voxel_contexts"]),
        "context_budget": all(len(fragment["content"]) <= 4000 for group in evidence["voxel_contexts"] for fragment in group),
        "context_no_cells": all('"values"' not in fragment["content"] and '"chunks"' not in fragment["content"] for group in evidence["voxel_contexts"] for fragment in group),
        "observation_budget": evidence["max_observation_bytes"] <= 18000,
        "unique_invocation_ids": len(invocations) == len(evidence["invocations"]) == len({row["id"] for row in invocations.values()}),
        "exact_persisted_observation_set": len(observations) == len(evidence["observations"]) and set(observations) == set(invocations),
        "unique_artifact_ids": len({row["id"] for row in evidence["artifacts"]}) == len(evidence["artifacts"]),
    }
    by_invocation = {row["id"]: row for row in invocations.values()}
    for artifact in evidence["artifacts"]:
        producer = by_invocation.get(artifact["provenance"].get("tool_invocation_id"))
        checks[f"artifact_producer.{artifact['id']}"] = bool(producer and producer["status"] == "succeeded"
            and producer["run_id"] == artifact["run_id"] and producer["session_id"] == artifact["session_id"]
            and producer["resource_refs"] == artifact["resource_refs"]
            and artifact["provenance"].get("tool_name") == producer["tool"]
            and artifact["id"] in observations[producer["call_id"]]["artifacts"])
    observed = [row["facts"] for row in observations.values() if all(k in row["facts"] for k in ("world_id", "version", "content_hash"))]
    checks["world_observed"] = bool(observed)
    final = None
    if observed:
        latest = observed[-1]
        live = runtime.operation(evidence["project_id"], "worlds.get", {"world_id": latest["world_id"]})
        evidence["final_world"] = {k: v for k, v in live.items() if k != "document"}
        checks["no_hidden_mutation"] = live["version"] == latest["version"] and live["content_hash"] == latest["content_hash"]
        if case.nonzero_count is not None:
            checks["exact_nonzero_count"] = live["nonzero_count"] == case.nonzero_count
        checks["minimum_nonzero_count"] = live["nonzero_count"] >= case.min_nonzero_count
        cache = {}

        def read(version):
            if version not in cache:
                cache[version] = runtime.document(evidence["project_id"], live["world_id"], version)
            return cache[version]

        final = read(live["version"])
        for path, wanted in case.assertions.items():
            value = final["document"]
            for key in path.split("/"):
                value = value[int(key)] if isinstance(value, list) else value[key]
            checks[f"domain.{path}"] = value == wanted
        for point in case.points:
            x, y, z = point["xyz"]
            chunk = final["chunks"].get((point["layer"], x // 16, y // 16, z // 16), bytes(4096))
            checks[f"cell.{point['layer']}.{x}.{y}.{z}"] = chunk[x % 16 + 16 * (z % 16) + 256 * (y % 16)] == point["index"]

        previous = None
        pending_no_write = None
        for step in case.steps:
            if step.kind == "human":
                row = next(item for item in evidence["human_edits"] if item["step"] == step.id)
                previous = row["result"]
                continue
            if step.kind != "tool":
                continue
            row, obs = invocations.get(step.id), observations.get(step.id)
            checks[f"step.{step.id}"] = row is not None and ((row["status"] == "succeeded") == step.succeeds)
            if row is None or obs is None:
                continue
            if step.error_contains:
                checks[f"rejection_reason.{step.id}"] = step.error_contains in ((row["error_code"] or "") + (row["error_message"] or ""))
            facts = obs["facts"]
            checks[f"persisted_observation.{step.id}"] = facts == evidence["provider_observations"].get(step.id, {}).get("facts")
            if "world_id" in facts and "version" in facts and "content_hash" in facts:
                if pending_no_write:
                    checks[f"failed_no_commit.{step.id}"] = facts["version"] == pending_no_write["version"] and facts["content_hash"] == pending_no_write["content_hash"]
                    pending_no_write = None
                if step.unchanged and previous:
                    checks[f"unchanged.{step.id}"] = facts["version"] == previous["version"] and facts["content_hash"] == previous["content_hash"]
                payload = row["input"]
                if step.succeeds and "expected_version" in payload and step.tool != "voxel_create":
                    refs = row["resource_refs"]
                    checks[f"version_fence.{step.id}"] = len(refs) == 1 and refs[0]["id"] == live["world_id"] and refs[0]["version"] == payload["expected_version"]
                    operation = payload.get("operation", {})
                    if _target_bounds(operation) is not None:
                        before, after = read(payload["expected_version"]), read(facts["version"])
                        checks[f"locality.{step.id}"] = _local_changes(before["chunks"], after["chunks"], operation)
                        checks[f"geometry_metadata_unchanged.{step.id}"] = before["document"] == after["document"]
                previous = facts
            elif not step.succeeds:
                checks[f"failure_facts_empty.{step.id}"] = facts == {} and obs["artifacts"] == []
                if step.unchanged:
                    pending_no_write = previous
        checks["failed_write_followed_by_inspect"] = pending_no_write is None
        for artifact in evidence["artifacts"]:
            checks[f"artifact_identity.{artifact['id']}"] = artifact["payload"]["world_id"] == live["world_id"] and artifact["payload"]["project_id"] == evidence["project_id"]
            persisted = read(artifact["payload"]["version"])
            checks[f"artifact_immutable.{artifact['id']}"] = artifact["payload"]["content_hash"] == persisted["content_hash"]

    evidence["checks"] = checks
    failed = tuple(key for key, passed in checks.items() if not passed)
    return TrialOutcome(suite_id="capability.dbfox-voxel.scripted", case_id=case.case_id,
        repetition=repetition, verdict="fail" if failed else "pass", failed_checks=failed,
        metrics={"task.success_rate": float(not failed), "runtime.tool_calls": float(len(invocations)),
                 "runtime.turns": float(evidence["turns"]),
                 "voxel.nonzero": float(final["nonzero_count"] if final else 0),
                 "context.voxel_chars": float(max((sum(len(f["content"]) for f in group) for group in evidence["voxel_contexts"]), default=0)),
                 "observation.max_bytes": float(evidence["max_observation_bytes"])}, evidence=evidence)


def export_stress(runtime, outcome, output_dir: Path):
    """Save public manifest/pages for independent replay; no private store imports."""
    evidence = outcome.evidence
    final = evidence["final_world"]
    identity = next(row["id"] for row in reversed(evidence["artifacts"]) if row["payload"]["version"] == final["version"])
    with runtime.factory() as db:
        artifact = ArtifactRepository(db).get(identity)
    provider = runtime.snapshot.get_artifact_representation("dbfox.voxel.snapshot", "dbfox.voxel.world.v1").provider
    context = ArtifactRepresentationContext(artifact_loader=lambda key: None)
    manifest = provider.execute(artifact, ArtifactRepresentationRequest(operation="manifest"), context)
    pages, cursor = [], None
    while True:
        page = provider.execute(artifact, ArtifactRepresentationRequest(operation="chunks", parameters={"limit": 16, "after": cursor}), context)
        pages.append(page.payload)
        cursor = page.payload["next_after"]
        if cursor is None:
            break
    content = json.dumps({"artifact_id": identity, "manifest": manifest.payload, "chunk_pages": pages}, separators=(",", ":"), ensure_ascii=False).encode()
    (output_dir / "fox-shrine.snapshot.json").write_bytes(content)
    (output_dir / "export-evidence.json").write_text(json.dumps({"artifact_id": identity, "world_id": final["world_id"],
        "version": final["version"], "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest(),
        "pages": len(pages), "source": "registered immutable manifest/chunks Representation"}, indent=2), encoding="utf-8")
