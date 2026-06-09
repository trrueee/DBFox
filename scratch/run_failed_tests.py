import subprocess
import re

# Get list of failed tests from the pytest output
cmd = ["pytest", "engine/tests/test_agent_kernel.py", "--collect-only", "-q"]
output = subprocess.check_output(cmd, text=True, cwd="d:\\Project\\DataBox")
tests = re.findall(r"engine/tests/test_agent_kernel.py::\w+", output)

failing_tests = [
    "test_agent_kernel_tool_registry_schema_snapshot",
    "test_agent_kernel_stream_emits_run_step_artifact_and_completion_events",
    "test_agent_kernel_checkpointer_factory_prefers_sqlite",
    "test_agent_kernel_controller_state_view_includes_actionable_context",
    "test_agent_kernel_controller_prompt_teaches_followup_artifact_and_approval_policy",
    "test_fallback_controller_uses_named_transition_table",
    "test_controller_routes_review_only_final_answer_to_answer_synthesizer",
    "test_agent_kernel_fallback_execute_false_returns_review_response",
    "test_agent_kernel_controller_final_answer_uses_workspace_sql_without_schema_restart",
    "test_agent_kernel_pending_approval_followup_explains_sql_without_schema_restart",
    "test_agent_kernel_pending_approval_followup_hydrates_approval_context",
    "test_agent_kernel_pending_approval_modify_calls_revise_not_execute",
    "test_agent_kernel_pending_approval_revision_revalidates_and_expires_old_approval",
    "test_agent_kernel_pending_approval_revision_without_fixed_sql_keeps_old_approval_valid",
    "test_agent_kernel_service_uses_graph_factory",
    "test_agent_kernel_response_assembler_does_not_call_legacy_runtime",
    "test_agent_kernel_resume_after_approval_continues_from_interrupt",
    "test_agent_kernel_resume_after_service_restart_uses_saved_checkpoint"
]

print(f"Running {len(failing_tests)} failing tests and saving output...")

with open("scratch/failed_tests_detail.txt", "w", encoding="utf-8") as out_f:
    for test in failing_tests:
        print(f"Running {test}...")
        res = subprocess.run(
            ["pytest", f"engine/tests/test_agent_kernel.py::{test}", "-vv", "--tb=short"],
            capture_output=True,
            text=True,
            cwd="d:\\Project\\DataBox"
        )
        out_f.write(f"=========================================================\n")
        out_f.write(f"TEST: {test}\n")
        out_f.write(f"=========================================================\n")
        out_f.write(res.stdout)
        out_f.write(res.stderr)
        out_f.write("\n\n")

print("Done! Details written to scratch/failed_tests_detail.txt")
