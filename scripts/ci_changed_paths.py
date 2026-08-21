"""Classify changed repository paths to route CI jobs conservatively and efficiently.

Emits boolean flags for each CI area to avoid running irrelevant expensive jobs on PRs,
while ensuring full validation runs on push to main, schedule, manual dispatch, and
when CI configuration or dependency governance changes.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import subprocess
from collections.abc import Iterable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Patterns that force full CI execution on any PR
FULL_TRIGGER_PATTERNS = (
    ".github/*",
    ".github/**/*",
    "scripts/ci_changed_paths.py",
    "scripts/tests/test_ci_changed_paths.py",
    "scripts/verify_release_artifact.py",
    ".sidecar-python-build",
    ".sidecar-python-version",
)

BACKEND_PATTERNS = (
    "engine/*",
    "engine/**/*",
    "dlcs/*/backend/*",
    "dlcs/*/backend/**/*",
    "dlcs/*/manifest*.json",
    "conftest.py",
    "pyproject.toml",
    "pytest.ini",
    "requirements.lock",
    "requirements-dev.lock",
)

PYTHON_QUALITY_PATTERNS = (
    "engine/*",
    "engine/**/*",
    "build_sidecar.py",
    "scripts/*",
    "scripts/**/*",
    "dlcs/*/backend/*",
    "dlcs/*/backend/**/*",
    "conftest.py",
    "requirements.lock",
    "requirements-dev.lock",
    "requirements-build.lock",
    "pyproject.toml",
)

MIGRATION_PATTERNS = (
    "engine/migrations/*",
    "engine/migrations/**/*",
    "alembic.ini",
    "engine/models.py",
    "engine/db.py",
    "engine/tests/test_migrations.py",
    "engine/tests/test_fts_migration_repair.py",
    "engine/tests/test_db_init.py",
    "engine/tests/test_unique_migration.py",
)

AGENT_RUNTIME_PATTERNS = (
    "engine/agent/*",
    "engine/agent/**/*",
    "engine/tools/*",
    "engine/tools/**/*",
    "engine/runtime_composition.py",
    "engine/llm/*",
    "engine/llm/**/*",
    "engine/models.py",
    "engine/errors.py",
    "conftest.py",
    "requirements.lock",
    "requirements-dev.lock",
)

ISOLATED_WORKER_PATTERNS = (
    "engine/tools/worker.py",
    "engine/tools/runtime/*",
    "engine/tools/runtime/**/*",
    "engine/runtime_composition.py",
    "engine/tools/builtin/workspace.py",
    "engine/workspace/*",
    "engine/workspace/**/*",
    "engine/tests/test_tool_attempt_runner.py",
    "engine/tests/test_workspace_patch_tool.py",
    "requirements.lock",
    "requirements-dev.lock",
)

SIDECAR_PATTERNS = (
    "engine/*",
    "engine/**/*",
    "dlcs/*/backend/*",
    "dlcs/*/backend/**/*",
    "dlcs/*/manifest*.json",
    "build_sidecar.py",
    ".sidecar-python-version",
    ".sidecar-python-build",
    "requirements-build.lock",
    "requirements-dev.lock",
    "requirements.lock",
    "desktop/scripts/smoke-sidecar.mjs",
)

FRONTEND_PATTERNS = (
    "desktop/*",
    "desktop/**/*",
    "dlcs/*/frontend/*",
    "dlcs/*/frontend/**/*",
    "dlcs/*/manifest*.json",
    "engine/api/*",
    "engine/api/**/*",
    "engine/schemas/*",
    "engine/schemas/**/*",
    "engine/agent/session.py",
    "requirements.lock",
)

SUPPLY_CHAIN_PATTERNS = (
    "requirements.lock",
    "requirements-dev.lock",
    "requirements-build.lock",
    "desktop/package.json",
    "desktop/package-lock.json",
    "osv-scanner.toml",
    "scripts/dependency_governance.py",
)


def _match_any(path: str, patterns: Iterable[str]) -> bool:
    normalized = path.replace("\\", "/")
    return any(fnmatch.fnmatch(normalized, p) for p in patterns)


def classify_changes(
    paths: Iterable[str],
    event_name: str = "pull_request",
) -> dict[str, bool]:
    """Determine CI job execution flags based on event and changed paths."""
    # Push to main, scheduled cron, and manual dispatch always run the full suite.
    if event_name not in ("pull_request", "pull_request_target"):
        return {
            "full": True,
            "backend": True,
            "python_quality": True,
            "migration": True,
            "agent_runtime": True,
            "isolated_worker": True,
            "sidecar": True,
            "frontend": True,
            "supply_chain": True,
        }

    path_list = [p.replace("\\", "/").strip() for p in paths if p.strip()]

    # If any workflow or CI routing file changed, force full run.
    force_full = any(_match_any(p, FULL_TRIGGER_PATTERNS) for p in path_list)
    if force_full:
        return {
            "full": True,
            "backend": True,
            "python_quality": True,
            "migration": True,
            "agent_runtime": True,
            "isolated_worker": True,
            "sidecar": True,
            "frontend": True,
            "supply_chain": True,
        }

    has_frontend = any(_match_any(p, FRONTEND_PATTERNS) for p in path_list)

    return {
        "full": False,
        "backend": any(_match_any(p, BACKEND_PATTERNS) for p in path_list),
        "python_quality": any(_match_any(p, PYTHON_QUALITY_PATTERNS) for p in path_list),
        "migration": any(_match_any(p, MIGRATION_PATTERNS) for p in path_list),
        "agent_runtime": any(_match_any(p, AGENT_RUNTIME_PATTERNS) for p in path_list),
        "isolated_worker": any(_match_any(p, ISOLATED_WORKER_PATTERNS) for p in path_list),
        "sidecar": any(_match_any(p, SIDECAR_PATTERNS) for p in path_list),
        "frontend": has_frontend,
        "supply_chain": any(_match_any(p, SUPPLY_CHAIN_PATTERNS) for p in path_list),
    }


def get_git_diff_files(base_ref: str, head_ref: str = "HEAD") -> list[str]:
    """Retrieve list of modified/added/deleted files between base and head."""
    try:
        output = subprocess.check_output(
            ["git", "diff", "--name-only", f"{base_ref}...{head_ref}"],
            text=True,
            encoding="utf-8",
        )
        return [line.strip() for line in output.splitlines() if line.strip()]
    except subprocess.CalledProcessError:
        # Fallback to direct diff if merge-base triple-dot fails
        output = subprocess.check_output(
            ["git", "diff", "--name-only", base_ref, head_ref],
            text=True,
            encoding="utf-8",
        )
        return [line.strip() for line in output.splitlines() if line.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description="Classify repository changes for CI routing.")
    parser.add_argument("--event-name", default=os.getenv("GITHUB_EVENT_NAME", "pull_request"))
    parser.add_argument("--base-ref", default=None, help="Base git ref for diff")
    parser.add_argument("--head-ref", default="HEAD", help="Head git ref for diff")
    parser.add_argument("--files", nargs="*", default=None, help="Explicit list of files")
    parser.add_argument("--json", action="store_true", help="Output results as JSON")
    args = parser.parse_args()

    if args.files is not None:
        files = args.files
    elif args.base_ref:
        files = get_git_diff_files(args.base_ref, args.head_ref)
    else:
        files = []

    classification = classify_changes(files, event_name=args.event_name)

    if args.json:
        print(json.dumps(classification, indent=2))

    # Write to GITHUB_OUTPUT if available in Actions environment
    github_output_path = os.getenv("GITHUB_OUTPUT")
    if github_output_path:
        with open(github_output_path, "a", encoding="utf-8") as f:
            for k, v in classification.items():
                f.write(f"{k}={'true' if v else 'false'}\n")
    elif not args.json:
        for k, v in classification.items():
            print(f"{k}={'true' if v else 'false'}")


if __name__ == "__main__":
    main()
