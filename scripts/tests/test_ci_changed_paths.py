"""Unit tests for CI path classifier (scripts/ci_changed_paths.py).

Simulates all routing scenarios:
A. Docs-only
B. Frontend-only React change
C. Rust-only
D. Dependency lock change
E. Migration/model change
F. P9.0-like resource seam change
G. Future P9 GitHub DLC change
H. Workflow/CI file change (forces full run)
I. Non-PR events (push to main, schedule, dispatch -> full run)
"""

from __future__ import annotations

from scripts.ci_changed_paths import classify_changes


def test_scenario_a_docs_only() -> None:
    files = ["docs/architecture.md", "README.md", "docs/guides/user_guide.md"]
    res = classify_changes(files, event_name="pull_request")

    assert res["full"] is False
    assert res["backend"] is False
    assert res["python_quality"] is False
    assert res["migration"] is False
    assert res["agent_runtime"] is False
    assert res["isolated_worker"] is False
    assert res["sidecar"] is False
    assert res["frontend"] is False
    assert res["rust"] is False
    assert res["supply_chain"] is False


def test_scenario_b_frontend_only_react() -> None:
    files = [
        "desktop/src/components/ui/Button.tsx",
        "desktop/src/features/conversation/ConversationView.tsx",
        "desktop/src/styles/theme.css",
    ]
    res = classify_changes(files, event_name="pull_request")

    assert res["full"] is False
    assert res["frontend"] is True
    assert res["backend"] is False
    assert res["python_quality"] is False
    assert res["migration"] is False
    assert res["agent_runtime"] is False
    assert res["isolated_worker"] is False
    assert res["sidecar"] is False
    assert res["rust"] is False
    assert res["supply_chain"] is False


def test_scenario_c_rust_only() -> None:
    files = [
        "desktop/src-tauri/src/main.rs",
        "desktop/src-tauri/src/tray.rs",
    ]
    res = classify_changes(files, event_name="pull_request")

    assert res["full"] is False
    assert res["rust"] is True
    assert res["frontend"] is False
    assert res["backend"] is False
    assert res["python_quality"] is False
    assert res["migration"] is False
    assert res["agent_runtime"] is False
    assert res["isolated_worker"] is False
    assert res["sidecar"] is False
    assert res["supply_chain"] is False


def test_scenario_d_dependency_lock_change() -> None:
    files = ["requirements.lock"]
    res = classify_changes(files, event_name="pull_request")

    assert res["full"] is False
    assert res["backend"] is True
    assert res["python_quality"] is True
    assert res["agent_runtime"] is True
    assert res["isolated_worker"] is True
    assert res["sidecar"] is True
    assert res["frontend"] is True
    assert res["supply_chain"] is True
    assert res["rust"] is False


def test_scenario_e_migration_model_change() -> None:
    files = [
        "engine/migrations/versions/c1d2e3f4_new_migration.py",
        "engine/models.py",
    ]
    res = classify_changes(files, event_name="pull_request")

    assert res["full"] is False
    assert res["migration"] is True
    assert res["backend"] is True
    assert res["python_quality"] is True
    assert res["sidecar"] is True
    assert res["agent_runtime"] is True
    assert res["rust"] is False
    assert res["supply_chain"] is False


def test_scenario_f_p9_0_resource_seam_change() -> None:
    files = [
        "engine/runtime_composition.py",
        "engine/tools/runtime/resource_context.py",
        "engine/api/conversation_commands.py",
        "desktop/src/lib/api/generated/types.gen.ts",
    ]
    res = classify_changes(files, event_name="pull_request")

    assert res["full"] is False
    assert res["backend"] is True
    assert res["python_quality"] is True
    assert res["agent_runtime"] is True
    assert res["isolated_worker"] is True
    assert res["sidecar"] is True
    assert res["frontend"] is True
    assert res["rust"] is False
    assert res["supply_chain"] is False


def test_scenario_g_future_p9_github_dlc() -> None:
    files = [
        "engine/github/client.py",
        "engine/tools/builtin/github.py",
        "engine/runtime_composition.py",
        "desktop/src/features/resources/GithubConnector.tsx",
        "desktop/src/features/dock/githubDockViews.tsx",
    ]
    res = classify_changes(files, event_name="pull_request")

    assert res["full"] is False
    assert res["backend"] is True
    assert res["python_quality"] is True
    assert res["agent_runtime"] is True
    assert res["isolated_worker"] is True
    assert res["sidecar"] is True
    assert res["frontend"] is True
    assert res["rust"] is False
    assert res["supply_chain"] is False


def test_scenario_h_workflow_ci_change_forces_full() -> None:
    files = [".github/workflows/ci.yml"]
    res = classify_changes(files, event_name="pull_request")

    assert res["full"] is True
    assert res["backend"] is True
    assert res["python_quality"] is True
    assert res["migration"] is True
    assert res["agent_runtime"] is True
    assert res["isolated_worker"] is True
    assert res["sidecar"] is True
    assert res["frontend"] is True
    assert res["rust"] is True
    assert res["supply_chain"] is True


def test_scenario_i_non_pr_events_force_full() -> None:
    for event in ("push", "schedule", "workflow_dispatch"):
        res = classify_changes([], event_name=event)
        assert res["full"] is True
        assert res["backend"] is True
        assert res["frontend"] is True
        assert res["rust"] is True
        assert res["supply_chain"] is True
