"""Animation-specific authoritative assertions; shared framework remains domain-free."""
from verification.bench.framework.trial import TrialOutcome


def score(evidence):
    final = evidence["final_document"]
    category = evidence["category"]
    keys = {key["id"]: key for key in final.get("keyframes", [])}
    checks = {"runtime_steps":evidence["passed"],"observation_budget":evidence["max_observation_bytes"] <= 32768,
        "fixed_owner":all(item["owner"] == "dbfox.animation" and item["package_digest"] == evidence["package_digest"] for item in evidence["invocations"]),
        "no_write_replay":all(item["attempts"] == 1 for item in evidence["invocations"] if item["status"] == "succeeded"),
        "no_hidden_mutation":final.get("animation") == evidence["animation"]}
    expected_keys = 0 if category in ("simple-creation","ambiguous","stale","noop") else 2048 if category == "large" else 2
    checks["key_count"] = len(keys) == expected_keys
    checks["target_count"] = len(final.get("targets",[])) == (0 if category in ("simple-creation","ambiguous") else 1)
    if category == "incremental":
        checks["local_key_edit"] = keys["contact"]["tick"] == 5000 and keys["contact"]["value"] == 8 and keys["begin"]["tick"] == 0
    if category in ("inspect-before-edit","human-then-agent"):
        checks["local_key_edit"] = keys["begin"]["tick"] == 100 and keys["begin"]["value"] == 1 and keys["contact"]["tick"] == 4000
    if category == "multistage":
        checks["trim_preserves_keys"] = final["clips"][0]["start"] == 500 and final["clips"][0]["end"] == 3500 and keys["begin"]["tick"] == 0 and keys["contact"]["tick"] == 4000
        checks["curve_preserved"] = final["curves"][0]["x1"] == .25 and keys["begin"]["curve_id"] == "ease"
    if category in ("noop","stale","human-then-agent","invalid-recovery","multistage"):
        checks["marker_preserved"] = len(final["markers"]) == 1 and final["markers"][0]["tick"] == 1000
    if category == "noop":
        checks["noop_no_revision"] = final["animation"]["version"] == 4
    if category == "negative":
        checks["no_cascade_without_consent"] = final["targets"][0]["id"] == "fox" and final["tracks"][0]["target_id"] == "fox"
    for invocation in evidence["invocations"]:
        if invocation["status"] == "succeeded" and "expected_version" in invocation["input"]:
            refs = invocation["resource_refs"]
            checks[f"fence.{invocation['call_id']}"] = len(refs) == 1 and refs[0]["id"] == invocation["input"]["animation_id"] and refs[0]["version"] == invocation["input"]["expected_version"]
    failures = tuple(name for name, passed in checks.items() if not passed)
    evidence["checks"] = checks
    return TrialOutcome(suite_id="capability.dbfox-animation.scripted",case_id=evidence["case_id"],repetition=1,
        verdict="fail" if failures else "pass",failed_checks=failures,metrics={"task.success_rate":0 if failures else 1,
            "runtime.tool_calls":len(evidence["invocations"]),"animation.keys":len(keys),"observation.max_bytes":evidence["max_observation_bytes"]},evidence=evidence)
