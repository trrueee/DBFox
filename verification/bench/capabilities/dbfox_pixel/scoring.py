"""Independent cell comparisons and Pillow decode; never calls product drawing/compositing helpers."""
from __future__ import annotations

import hashlib
from io import BytesIO
import json
from pathlib import Path

from PIL import Image

from dbfox_dlc_api import ArtifactRepresentationContext, ArtifactRepresentationRequest
from engine.agent.repositories.artifact import ArtifactRepository
from engine.representation import execute_artifact_representation
from verification.bench.framework.trial import TrialOutcome


def cells(document):
    return {(read["frame"]["id"], cel["layer_id"]): cel["pixels"] for read in document["frame_reads"] for cel in read["frame"]["cels"]}


def independent_rgba(document, identity):
    """Small suite oracle follows the stated topmost visible, nonzero indexed-color rule."""
    data = document["document"]
    palette = [bytes.fromhex(entry["color"][1:]) for entry in data["palette"]]
    source = cells(document)
    count = data["canvas"]["width"] * data["canvas"]["height"]
    output = bytearray()
    for index in range(count):
        selected = 0
        for layer in data["layers"]:
            value = source[(identity, layer["id"])][index]
            if layer["visible"] and value:
                selected = value
        output.extend(palette[selected])
    return bytes(output)


def summary(facts):
    value = facts.get("summary", facts)
    return value if "document_id" in value and "revision" in value else None


def score_case(runtime, case, evidence, repetition):
    checks = {"run_completed": all(run["status"] == "completed" for run in evidence["runs"])}
    invocations = {item["call_id"]: item for item in evidence["invocations"]}
    observations = {item["call_id"]: item for item in evidence["observations"]}
    for identity in case.assertions.get("truncated_frame_changes", []):
        facts = observations.get(identity, {}).get("facts", {})
        checks[f"bounded_changes.{identity}"] = facts.get("changed_frame_ids_truncated") is True and len(facts.get("changed_frame_ids", [])) == 128
    expected = [step for step in case.steps if step.kind == "tool"]
    checks["exact_tool_sequence"] = list(invocations) == [step.id for step in expected]
    checks["package_and_owner"] = all(item["owner"] == "dbfox.pixel" and item["package_digest"] == evidence["package_digest"] for item in invocations.values())
    checks["no_replay"] = all(item["attempts"] == 1 for item in invocations.values() if item["status"] == "succeeded")
    for step in expected:
        invocation = invocations.get(step.id)
        checks[f"step.{step.id}"] = invocation is not None and ((invocation["status"] == "succeeded") == step.succeeds)
    observed = evidence["observed_summary"]
    checks["document_observed"] = observed is not None
    cache = {}
    if observed:
        head = runtime.operation(evidence["project_id"], "documents.get", {"document_id": observed["document_id"]})["summary"]
        evidence["final_summary"] = head
        checks["observed_head_no_hidden_mutation"] = (head["revision"], head["content_hash"]) == (observed["revision"], observed["content_hash"])

        def document(revision):
            if revision not in cache:
                cache[revision] = runtime.document(evidence["project_id"], head["document_id"], revision)
            return cache[revision]

        final = document(head["revision"])
        indexed = cells(final)
        width = final["document"]["canvas"]["width"]
        for key in ("revision", "frame_count", "layer_count"):
            if key in case.assertions:
                checks[f"expected.{key}"] = head[key] == case.assertions[key]
        if "nonzero" in case.assertions:
            checks["expected.nonzero"] = sum(bool(value) for cel in indexed.values() for value in cel) == case.assertions["nonzero"]
        for frame, layer, x, y, color in case.assertions.get("points", []):
            checks[f"pixel.{frame}.{layer}.{x}.{y}"] = indexed.get((frame, layer), [])[y * width + x] == color
        for name, ids in case.assertions.get("tags", {}).items():
            tag = next((tag for tag in final["document"]["tags"] if tag["id"] == name), None)
            checks[f"tag_order.{name}"] = tag is not None and tag["frame_ids"] == ids
        if "distinct_frames" in case.assertions:
            hashes = {hashlib.sha256(independent_rgba(final, frame["id"])).hexdigest() for frame in final["document"]["frames"]}
            checks["distinct_animation_poses"] = len(hashes) == case.assertions["distinct_frames"]
        if "human_steps" in case.assertions:
            checks["human_steps"] = len(evidence["human_edits"]) == case.assertions["human_steps"]
        if case.assertions.get("clarification"):
            checks["clarification_asked"] = any("请明确" in run["answer"] for run in evidence["runs"])
        if "frame_pages" in case.assertions:
            pages = [observations[name]["facts"] for name in case.assertions["frame_pages"]]
            ids = [item["id"] for page in pages for item in page["items"]]
            checks["bounded_pages_complete"] = ids == [frame["id"] for frame in final["document"]["frames"]] and len(set(ids)) == len(ids)
        if "provider_pixels" in case.assertions:
            name = case.assertions["provider_pixels"]
            checks["pixels_visible_only_in_provider_window"] = "pixels" not in observations[name]["facts"] and evidence["provider_observations"][name]["facts"].get("pixels") is not None

        previous = None
        pending_failure = None
        for step in case.steps:
            if step.kind == "human":
                result = next((item["result"] for item in evidence["human_edits"] if item["step"] == step.id), None)
                checks[f"human.{step.id}"] = result is not None
                if result:
                    previous = result
                continue
            observation = observations.get(step.id)
            after = summary(observation["facts"]) if observation else None
            if step.unchanged and previous:
                actual = after or previous
                checks[f"unchanged.{step.id}"] = (actual["revision"], actual["content_hash"]) == (previous["revision"], previous["content_hash"])
                if not step.succeeds:
                    pending_failure = previous
            if pending_failure and after and step.tool == "pixel_inspect":
                checks[f"failed_write_no_partial_commit.{step.id}"] = (after["revision"], after["content_hash"]) == (pending_failure["revision"], pending_failure["content_hash"])
                pending_failure = None
            if not after:
                continue
            if step.id in case.assertions.get("noops", []):
                checks[f"noop_receipt.{step.id}"] = observation["facts"].get("changed") is False
            invocation = invocations[step.id]
            payload = invocation["input"]
            if step.succeeds and "expected_version" in payload and step.tool != "pixel_create":
                refs = invocation["resource_refs"]
                checks[f"dynamic_fence.{step.id}"] = len(refs) == 1 and refs[0]["id"] == head["document_id"] and str(refs[0]["version"]) == str(payload["expected_version"])
            if previous and step.allowed_changes is not None:
                before_cells, after_cells = cells(document(previous["revision"])), cells(document(after["revision"]))
                preserved = before_cells.keys() == after_cells.keys()
                changed_count = 0
                for (frame, layer), values in before_cells.items():
                    for index, (old, new) in enumerate(zip(values, after_cells.get((frame, layer), []), strict=True)):
                        if old == new:
                            continue
                        changed_count += 1
                        x, y = index % width, index // width
                        if not any(a["frame_id"] == frame and a["layer_id"] == layer and a["x"] <= x < a["x"] + a["width"] and a["y"] <= y < a["y"] + a["height"] for a in step.allowed_changes):
                            preserved = False
                checks[f"pixel_locality.{step.id}"] = preserved and changed_count > 0
            previous = after

        # Every persisted Artifact is tied to the exact producing Invocation, never a client envelope.
        by_id = {item["id"]: item for item in invocations.values()}
        for artifact in evidence["artifacts"]:
            producer = by_id.get(artifact["provenance"].get("tool_invocation_id"))
            checks[f"artifact.producer.{artifact['id']}"] = producer is not None and producer["status"] == "succeeded" and producer["run_id"] == artifact["run_id"] and producer["resource_refs"] == artifact["resource_refs"]
            payload = artifact["payload"]
            persisted = document(payload["revision"])["summary"]
            checks[f"artifact.fixed_revision.{artifact['id']}"] = payload == persisted
        evidence["stable_frame_ids"] = [frame["id"] for frame in final["document"]["frames"]]
        evidence["stable_layer_ids"] = [layer["id"] for layer in final["document"]["layers"]]
        evidence["frame_rgba_sha256"] = {frame["id"]: hashlib.sha256(independent_rgba(final, frame["id"])).hexdigest() for frame in final["document"]["frames"]}
    groups = evidence["pixel_contexts"]
    checks["context_present"] = any(groups)
    checks["context_budget"] = all(len(group) <= 4 and all(len(item["content"]) <= 2000 for item in group) for group in groups)
    checks["no_cels_in_context"] = all('"pixels"' not in item["content"] and '"cels"' not in item["content"] for group in groups for item in group)
    checks["observation_budget"] = evidence["max_observation_bytes"] <= 18 * 1024
    checks["no_durable_pixels"] = all("pixels" not in item["facts"] for item in observations.values())
    evidence["checks"] = checks
    failures = tuple(name for name, passed in checks.items() if not passed)
    return TrialOutcome(suite_id="capability.dbfox-pixel.scripted", case_id=case.case_id, repetition=repetition,
        verdict="fail" if failures else "pass", failed_checks=failures, metrics={"task.success_rate": float(not failures),
            "runtime.tool_calls": float(len(invocations)), "runtime.turns": float(evidence["turns"]),
            "pixel.frames": float(evidence.get("final_summary", {}).get("frame_count", 0)),
            "context.pixel_chars": float(max((sum(len(item["content"]) for item in group) for group in groups), default=0)),
            "observation.max_bytes": float(evidence["max_observation_bytes"])}, evidence=evidence)


def export_stress(runtime, outcome, output_dir: Path):
    evidence = outcome.evidence
    producer_ids = {item["call_id"]: item["id"] for item in evidence["invocations"]}
    provider = runtime.snapshot.get_artifact_representation("dbfox.pixel.revision", "dbfox.pixel.sprite.v1").provider
    exports = []
    for label in ("initial-export", "final-export"):
        identity = next(item["id"] for item in evidence["artifacts"] if item["provenance"].get("tool_invocation_id") == producer_ids[label])
        with runtime.factory() as db:
            row = ArtifactRepository(db).get(identity)
            artifact = ArtifactRepository(db).available_artifact(session_id=row.session_id, current_run_id=row.run_id, artifact_id=identity)
        assert artifact is not None
        data = runtime.document(evidence["project_id"], artifact.payload["document_id"], artifact.payload["revision"])
        for name, operation, params in (("single", "png", {"frame_id": "frame_1"}), ("all", "sheet", {}), ("idle", "sheet", {"tag_id": "idle"}), ("attack", "sheet", {"tag_id": "attack"})):
            _, stream = execute_artifact_representation(artifact=artifact, representation_type="dbfox.pixel.sprite.v1",
                request=ArtifactRepresentationRequest(operation=operation, parameters=params), provider=provider,
                context=ArtifactRepresentationContext(artifact_loader=lambda key: None), expected_kind="stream")
            raw = b"".join(stream.chunks)
            image = Image.open(BytesIO(raw)).convert("RGBA")
            if operation == "png":
                ids = [params["frame_id"]]
            elif "tag_id" in params:
                ids = next(tag["frame_ids"] for tag in data["document"]["tags"] if tag["id"] == params["tag_id"])
            else:
                ids = [frame["id"] for frame in data["document"]["frames"]]
            assert image.size == (32 * len(ids), 32)
            expected = b"".join(independent_rgba(data, frame)[y * 128:(y + 1) * 128] for y in range(32) for frame in ids)
            assert image.tobytes() == expected, f"Decoded pixels differ: {label}/{name}"
            if operation == "sheet":
                _, layout = execute_artifact_representation(artifact=artifact, representation_type="dbfox.pixel.sprite.v1",
                    request=ArtifactRepresentationRequest(operation="sheet_layout", parameters=params), provider=provider,
                    context=ArtifactRepresentationContext(artifact_loader=lambda key: None), expected_kind="json")
                assert [frame["frame_id"] for frame in layout.payload["frames"]] == ids
            filename = f"fox-knight-{label}-{name}.png"
            (output_dir / filename).write_bytes(raw)
            exports.append({"file": filename, "artifact_id": identity, "producer_invocation_id": producer_ids[label],
                "revision": artifact.payload["revision"], "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
                "dimensions": list(image.size), "frame_ids": ids, "all_decoded_pixels_match": True, "stream_metadata": stream.metadata})
    assert exports[0]["revision"] < exports[-1]["revision"]
    (output_dir / "export-evidence.json").write_text(json.dumps({"decoder": "Pillow (verification-only)", "exports": exports}, indent=2), encoding="utf-8")
