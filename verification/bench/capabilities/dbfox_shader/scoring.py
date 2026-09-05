"""Exact canonical/source comparisons through public operations and representations."""
from copy import deepcopy
from hashlib import sha256
import json

from dbfox_dlc_api import ArtifactRepresentationContext, ArtifactRepresentationRequest
from engine.agent.repositories.artifact import ArtifactRepository
from engine.representation import execute_artifact_representation
from verification.bench.framework.trial import TrialOutcome

OWNER = "dbfox.shader"


def at(value, path):
    for key in path.split(".") if path else ():
        value = value[int(key)] if isinstance(value, list) else value[key]
    return value


def resolve(value, observations):
    if isinstance(value, str) and value.startswith("$"):
        label, _, path = value[1:].partition(".")
        return at(observations[label]["facts"], path)
    if isinstance(value, list):
        return [resolve(item, observations) for item in value]
    if isinstance(value, dict):
        return {key: resolve(item, observations) for key, item in value.items()}
    return value


def assertion(value, expectation, observations):
    try:
        selected = at(value, expectation["path"])
        expected = resolve(expectation.get("value"), observations)
        operation = expectation.get("op", "equals")
        if operation == "equals":
            return selected == expected
        if operation == "contains":
            return expected in selected
        if operation == "length":
            return len(selected) == expected
        if operation == "minimum_length":
            return len(selected) >= expected
        raise ValueError(f"Unknown assertion operation: {operation}")
    except (KeyError, IndexError, TypeError):
        return False


def unchanged_outside(before, after, objects, fields):
    def remainder(document):
        value = deepcopy(document)
        for section in ("stages", "passes", "uniforms", "textures"):
            value[section] = [item for item in value[section] if item["id"] not in objects]
        for field in fields:
            value.pop(field, None)
        return value
    return remainder(before) == remainder(after)


def score_case(runtime, case, evidence, repetition):
    checks = {"runs_completed": all(run["status"] == "completed" for run in evidence["runs"])}
    invocations = {item["call_id"]: item for item in evidence["invocations"]}
    observations = evidence["provider_observations"]
    expected = [step for step in case.steps if step.kind == "tool"]
    checks["exact_tool_sequence"] = list(invocations) == [step.id for step in expected]
    checks["package_owner_and_no_replay"] = all(item["owner"] == OWNER and item["package_digest"] == evidence["package_digest"] and item["attempts"] == 1 for item in invocations.values())
    checks["studio_authority"] = all(len(item["resource_refs"]) == 1 and item["resource_refs"][0]["kind"] == OWNER + ".studio" and item["resource_refs"][0]["id"] == evidence["project_id"] for item in invocations.values())
    for step in expected:
        invocation = invocations.get(step.id)
        checks[f"status.{step.id}"] = invocation is not None and ((invocation["status"] == "succeeded") == step.succeeds)
        for index, expectation in enumerate(step.checks):
            checks[f"observation.{step.id}.{index}"] = assertion(observations.get(step.id, {}).get("facts", {}), expectation, observations)
    cache = {}

    def document(summary):
        key = (summary["id"], summary["version"])
        if key not in cache:
            cache[key] = runtime.document(evidence["project_id"], *key)
            data = cache[key]
            encoded = json.dumps({"document": data["document"], "deleted": data["summary"]["deleted"]}, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()
            checks[f"canonical_hash.{key}"] = sha256(encoded).hexdigest() == data["summary"]["content_hash"]
        return cache[key]

    previous = None
    humans = {item["step"]: item["result"] for item in evidence["human_edits"]}
    for step in case.steps:
        facts = humans.get(step.id, {}) if step.kind == "human" else observations.get(step.id, {}).get("facts", {})
        summary = facts.get("document")
        # Read-only historical pages never become a new mutation baseline.
        is_mutation = "changed" in facts and summary is not None
        if is_mutation:
            current = document(summary)
            if previous is not None:
                checks[f"revision.{step.id}"] = summary["version"] == previous["summary"]["version"] + int(facts["changed"])
                objects = {resolve(value, observations) for value in step.allowed_objects}
                checks[f"locality.{step.id}"] = unchanged_outside(previous["document"], current["document"], objects, step.allowed_fields)
                if step.unchanged:
                    checks[f"no_op.{step.id}"] = current == previous and facts["changed"] is False
            previous = current
    checks["document_created"] = previous is not None
    if previous is not None:
        head = runtime.operation(evidence["project_id"], "documents.head", {"document_id": previous["summary"]["id"]})
        checks["no_hidden_head_mutation"] = all(head[key] == previous["summary"][key] for key in head)
        evidence["final_summary"] = previous["summary"]
        evidence["final_document"] = previous["document"]
        for index, expectation in enumerate(case.assertions):
            checks[f"final.{index}"] = assertion(previous, expectation, observations)
        if case.case_id in {"texture-binding", "coral-plasma-stress"}:
            checks["texture.top_left_rgba_exact"] = list(previous["texture_rgba"].values()) == ["ff0000ff" + "00ff00ff" + "0000ffff" + "ffffffff"]
        if case.case_id == "large-document":
            pages = [observations[label]["facts"] for label in ("page1", "page2", "page3")]
            checks["pages.complete_unique_order"] = [item["id"] for page in pages for item in page["items"]] == [item["id"] for item in previous["document"]["stages"]]
            checks["pages.fixed_version"] = all(page["document"] == previous["summary"] for page in pages)

    by_id = {item["id"]: item for item in invocations.values()}
    artifact_producers = set()
    provider = runtime.snapshot.get_artifact_representation(OWNER + ".document-revision", OWNER + ".document.v1").provider
    for artifact in evidence["artifacts"]:
        producer = by_id.get(artifact["provenance"].get("tool_invocation_id"))
        checks[f"artifact.producer.{artifact['id']}"] = producer is not None and producer["status"] == "succeeded" and producer["run_id"] == artifact["run_id"] and producer["resource_refs"] == artifact["resource_refs"]
        if producer is not None:
            artifact_producers.add(producer["call_id"])
        checks[f"artifact.no_simulated_gpu.{artifact['id']}"] = artifact["type"] == OWNER + ".document-revision"
        locator = artifact["payload"]
        fixed = document({"id": locator["document_id"], "version": locator["version"]})
        checks[f"artifact.fixed_revision.{artifact['id']}"] = locator["content_hash"] == fixed["summary"]["content_hash"] and locator["project_id"] == evidence["project_id"]
        with runtime.factory() as db:
            available = ArtifactRepository(db).available_artifact(session_id=artifact["session_id"], current_run_id=artifact["run_id"], artifact_id=artifact["id"])
        checks[f"artifact.available.{artifact['id']}"] = available is not None
        if available is not None:
            _, result = execute_artifact_representation(artifact=available, representation_type=OWNER + ".document.v1", request=ArtifactRepresentationRequest(operation="page", parameters={"section": "summary"}), provider=provider, context=ArtifactRepresentationContext(artifact_loader=lambda key: None), expected_kind="json")
            checks[f"representation.fixed_revision.{artifact['id']}"] = result.payload["document"] == fixed["summary"] and result.source_fingerprint == locator["content_hash"] and result.source_version == str(locator["version"])
    for step in expected:
        if "changed" in observations.get(step.id, {}).get("facts", {}):
            checks[f"artifact.required.{step.id}"] = step.id in artifact_producers
    contexts = evidence["shader_contexts"]
    checks["context_present"] = any(contexts)
    checks["context_bounded"] = all(len(group) <= 1 and all(len(item["content"]) <= 4000 and '"source"' not in item["content"] and "rgba_base64" not in item["content"] for item in group) for group in contexts)
    checks["observation_bounded"] = evidence["max_observation_bytes"] <= 20 * 1024
    checks["source_not_durable_observation"] = all("source" not in item["facts"] for item in evidence["observations"])
    if case.clarification:
        checks["clarification_separate_run"] = len(evidence["runs"]) == 2 and "请明确" in evidence["runs"][0]["answer"]
    evidence["gpu_execution"] = "not exercised; no compute bridge attached or simulated"
    evidence["checks"] = checks
    failures = tuple(name for name, passed in checks.items() if not passed)
    return TrialOutcome(suite_id="capability.dbfox-shader.scripted", case_id=case.case_id, repetition=repetition,
        verdict="fail" if failures else "pass", failed_checks=failures,
        metrics={"task.success_rate": float(not failures), "runtime.tool_calls": float(len(invocations)),
            "runtime.turns": float(evidence["turns"]), "observation.max_bytes": float(evidence["max_observation_bytes"])}, evidence=evidence)
