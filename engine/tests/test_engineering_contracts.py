"""Regression contracts for reproducible, least-privilege engineering gates."""

from __future__ import annotations

import json
import re
import tomllib
from datetime import date
from pathlib import Path
from urllib.parse import unquote

import pytest

from engine import __version__


pytestmark = pytest.mark.engineering_contract


ROOT = Path(__file__).resolve().parents[2]
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
AGENT_EVALUATION_WORKFLOW = ROOT / ".github" / "workflows" / "agent-evaluation.yml"
WINDOWS_SIGNED_RELEASE_WORKFLOW = (
    ROOT / ".github" / "workflows" / "windows-signed-release.yml"
)
NPM_LOCK = ROOT / "desktop" / "package-lock.json"
NPM_MANIFEST = ROOT / "desktop" / "package.json"
PYTHON_LOCKS = {
    "requirements.txt": "requirements.lock",
    "requirements-dev.txt": "requirements-dev.lock",
    "requirements-build.txt": "requirements-build.lock",
}
SIDECAR_PYTHON_VERSION_FILE = ROOT / ".sidecar-python-version"
SIDECAR_PYTHON_BUILD_FILE = ROOT / ".sidecar-python-build"
OSV_CONFIG = ROOT / "osv-scanner.toml"


def _normalise_package_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _direct_requirement_names(path: Path) -> set[str]:
    names: set[str] = set()
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith(
            ("#", "-r", "--requirement", "-c", "--constraint")
        ):
            continue
        match = re.match(r"([A-Za-z0-9][A-Za-z0-9._-]*)", line)
        assert match, f"Unrecognised direct requirement in {path.name}: {line}"
        names.add(_normalise_package_name(match.group(1)))
    return names


def _locked_package_names(path: Path) -> set[str]:
    return {
        _normalise_package_name(name)
        for name in re.findall(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==", path.read_text(encoding="utf-8"), re.MULTILINE)
    }


def test_ci_actions_are_pinned_to_full_commit_shas() -> None:
    for workflow_path in (CI_WORKFLOW, WINDOWS_SIGNED_RELEASE_WORKFLOW):
        workflow = workflow_path.read_text(encoding="utf-8")
        actions = re.findall(r"^\s*- uses: ([^\s]+)$", workflow, flags=re.MULTILINE)

        assert actions, workflow_path.name
        for action in actions:
            owner_and_repo, separator, revision = action.partition("@")
            assert separator and owner_and_repo
            assert re.fullmatch(r"[0-9a-f]{40}", revision), action


def test_migration_archaeology_uses_a_committed_fixture_not_git_history() -> None:
    root = Path(__file__).resolve().parents[2]
    migration_tests = (root / "engine" / "tests" / "test_migrations.py").read_text(
        encoding="utf-8"
    )
    fixture = (
        root
        / "engine"
        / "tests"
        / "fixtures"
        / "historical_models_918ea80d.py"
    )

    assert fixture.is_file()
    assert "git archive" not in migration_tests


def test_ci_enforces_the_required_layered_quality_gates() -> None:
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")

    for command in (
        "python -m alembic check",
        "python -m compileall -q engine build_sidecar.py conftest.py scripts",
        "python -m pyflakes engine build_sidecar.py conftest.py scripts",
        "python -m mypy --no-warn-unused-configs --follow-imports=skip",
        "engine build_sidecar.py",
        "python -m pytest engine/agent/tests",
        "production-python-compatibility:",
        "Run all deterministic backend contracts on the production interpreter",
        "build_sidecar.py",
        "npm run lint",
        "npm test -- --maxWorkers=1",
        "npm run build",
    ):
        assert command in workflow


def test_electron_release_does_not_mutate_the_manifest_bound_sidecar() -> None:
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")
    build_step = workflow.split(
        "- name: Build and probe the frozen Sidecar",
        1,
    )[1].split("- name: Run the authenticated frozen Sidecar smoke", 1)[0]

    assert '"$SIDECAR_PYTHON" build_sidecar.py' in build_step
    assert "npm run electron:package" in build_step
    assert "rustc" not in build_step
    assert "desktop/electron-resources/sidecar/dbfox-engine" in workflow
    assert "chown root:root release-electron/linux-unpacked/chrome-sandbox" in workflow
    assert "chmod 4755 release-electron/linux-unpacked/chrome-sandbox" in workflow
    assert "--no-sandbox" not in workflow


def test_ci_only_uses_runner_context_after_a_job_reaches_its_runner() -> None:
    for workflow_path in (CI_WORKFLOW, AGENT_EVALUATION_WORKFLOW):
        in_job_env = False
        for line in workflow_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("    env:"):
                in_job_env = True
                continue
            if in_job_env and line.startswith("    ") and not line.startswith("      "):
                in_job_env = False
            if in_job_env:
                assert "${{ runner." not in line, (
                    f"{workflow_path.name}: runner context is unavailable in jobs.<job_id>.env: {line}"
                )


def test_rust_and_tauri_are_absent_from_the_production_graph() -> None:
    package = json.loads(NPM_MANIFEST.read_text(encoding="utf-8"))
    workflow = CI_WORKFLOW.read_text(encoding="utf-8").lower()
    dependabot = (ROOT / ".github" / "dependabot.yml").read_text(encoding="utf-8").lower()
    governance = (ROOT / "scripts" / "dependency_governance.py").read_text(encoding="utf-8").lower()

    assert not (ROOT / "desktop" / "src-tauri").exists()
    assert not (ROOT / "desktop" / "scripts" / "run-rust-tool.mjs").exists()
    assert all("tauri" not in name for name in package["dependencies"])
    assert all("tauri" not in name for name in package["devDependencies"])
    assert re.search(r"\bcargo\b", workflow) is None
    assert re.search(r"\brust\b", workflow) is None
    assert "package-ecosystem: cargo" not in dependabot
    assert '"rust"' not in governance


def test_application_manifests_match_the_engine_version() -> None:
    npm_version = json.loads(NPM_MANIFEST.read_text(encoding="utf-8"))["version"]

    assert npm_version == __version__


def test_no_orphan_root_npm_lockfile_exists() -> None:
    assert not (ROOT / "package-lock.json").exists()
    assert (ROOT / "desktop" / "package-lock.json").is_file()


def test_development_requirements_do_not_reference_nonexistent_keyring_stubs() -> None:
    requirements = (ROOT / "requirements-dev.txt").read_text(encoding="utf-8")

    assert "types-keyring" not in requirements.lower()


def test_python_dependency_locks_cover_all_direct_inputs_and_have_hashes() -> None:
    runtime_lock_names = _locked_package_names(ROOT / "requirements.lock")

    for source_name, lock_name in PYTHON_LOCKS.items():
        source = ROOT / source_name
        lock = ROOT / lock_name
        lock_text = lock.read_text(encoding="utf-8")
        lock_names = _locked_package_names(lock)

        assert lock.is_file(), lock_name
        expected_python = (
            SIDECAR_PYTHON_VERSION_FILE.read_text(encoding="utf-8").strip()
            if lock_name == "requirements-build.lock"
            else "3.12"
        )
        assert (
            f"--universal --generate-hashes --python-version {expected_python}"
            in lock_text.splitlines()[1]
        )
        assert "--hash=sha256:" in lock_text
        assert _direct_requirement_names(source) <= lock_names
        assert not re.search(
            r"^(?:--(?:extra-)?index-url|--find-links|-f |--trusted-host|-e |--editable|git\+|https?://|file:)",
            lock_text,
            re.MULTILINE,
        ), lock_name
        assert not re.search(r"^[A-Za-z0-9._-]+\s+@\s+", lock_text, re.MULTILINE), lock_name

        package_headers = list(
            re.finditer(
                r"^[A-Za-z0-9][A-Za-z0-9._-]*==[^\s\\]+ \\\s*$",
                lock_text,
                re.MULTILINE,
            )
        )
        assert package_headers, lock_name
        for index, header in enumerate(package_headers):
            end = package_headers[index + 1].start() if index + 1 < len(package_headers) else len(lock_text)
            package_block = lock_text[header.start() : end]
            assert re.search(r"^\s+--hash=sha256:[0-9a-f]{64}", package_block, re.MULTILINE), (
                lock_name,
                package_block.splitlines()[0],
            )

    assert runtime_lock_names <= _locked_package_names(ROOT / "requirements-dev.lock")
    assert runtime_lock_names <= _locked_package_names(ROOT / "requirements-build.lock")


def test_ci_installs_only_hash_checked_python_locks() -> None:
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")
    agent_evaluation = AGENT_EVALUATION_WORKFLOW.read_text(encoding="utf-8")
    all_python_workflows = workflow + agent_evaluation

    # Hash checking belongs to each repository dependency install.  A global
    # PIP_REQUIRE_HASHES leaks into setup-python and PEP 517 build-isolation
    # subprocesses, where bootstrap tools are intentionally outside our lock.
    assert "PIP_REQUIRE_HASHES" not in all_python_workflows
    assert workflow.count("--require-hashes -r requirements-dev.lock") == 5
    assert agent_evaluation.count("--require-hashes -r requirements-dev.lock") == 3
    assert workflow.count("uv pip sync requirements-dev.lock") == 4
    assert "python-version-file: .sidecar-python-version" in workflow
    assert "SIDECAR_PYTHON_VERSION" not in workflow
    assert "python -m pip install -r requirements-dev.txt" not in all_python_workflows
    assert "python -m pip install -r requirements-build.txt" not in all_python_workflows


def test_windows_release_uses_electron_and_hash_checked_sidecar_contracts() -> None:
    workflow = WINDOWS_SIGNED_RELEASE_WORKFLOW.read_text(encoding="utf-8")
    builder = (ROOT / "desktop" / "electron-builder.yml").read_text(encoding="utf-8")

    assert 'NODE_VERSION: "22.18.0"' in workflow
    assert "RUST_VERSION" not in workflow
    assert "TAURI_SIGNING_PRIVATE_KEY" not in workflow
    assert "python-version-file: .sidecar-python-version" in workflow
    assert "PIP_REQUIRE_HASHES" not in workflow
    assert "uv pip sync --require-hashes requirements-dev.lock" in workflow
    assert "electron-builder --projectDir electron-app" in workflow
    assert "--config.forceCodeSigning=true" in workflow
    assert "--refresh-artifact-manifest" in workflow
    assert "releaseType: draft" in builder
    assert "refs/heads/main" in workflow


def test_windows_release_requires_verified_source_and_attests_installers() -> None:
    workflow = WINDOWS_SIGNED_RELEASE_WORKFLOW.read_text(encoding="utf-8")

    assert "id-token: write" in workflow
    assert "attestations: write" in workflow
    assert "Require a GitHub-verified source commit" in workflow
    assert ".commit.verification.verified" in workflow
    assert "actions/attest@508db95dd578ae2727ebd6217d5ba78e4fbda05d" in workflow
    assert "desktop/release-electron/DBFox-*.exe" in workflow
    assert "desktop/release-electron/DBFox-*.exe.blockmap" in workflow
    assert "desktop/release-electron/latest.yml" in workflow


def test_sidecar_build_uses_exact_python_distribution_sources() -> None:
    version = SIDECAR_PYTHON_VERSION_FILE.read_text(encoding="utf-8").strip()
    build = SIDECAR_PYTHON_BUILD_FILE.read_text(encoding="utf-8").strip()
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")
    builder = (ROOT / "build_sidecar.py").read_text(encoding="utf-8")

    assert re.fullmatch(r"\d+\.\d+\.\d+", version)
    assert re.fullmatch(r"\d{8}", build)
    assert workflow.count("python-version-file: .sidecar-python-version") == 1
    assert version not in workflow
    assert build not in workflow
    assert "SIDECAR_PYTHON_VERSION_PATH" in builder
    assert "SIDECAR_PYTHON_BUILD_PATH" in builder
    assert workflow.count("uv venv --managed-python") == 3
    assert workflow.count("UV_PYTHON_CPYTHON_BUILD") == 3


def test_npm_lock_is_registry_resolved_and_integrity_verified() -> None:
    package = json.loads((ROOT / "desktop" / "package.json").read_text(encoding="utf-8"))
    lock = json.loads(NPM_LOCK.read_text(encoding="utf-8"))
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")

    assert lock["lockfileVersion"] == 3
    assert lock["requires"] is True
    packages = lock["packages"]
    assert isinstance(packages, dict) and packages
    assert package["engines"]["node"] == ">=22.18.0"
    assert package["packageManager"] == "npm@10.9.3"
    assert packages[""]["engines"]["node"] == package["engines"]["node"]
    assert 'NODE_VERSION: "22.18.0"' in workflow

    for package_path, package in packages.items():
        if not package_path:
            continue
        assert isinstance(package, dict), package_path
        assert package.get("version"), package_path
        assert not package.get("link"), package_path
        assert str(package.get("resolved", "")).startswith("https://registry.npmjs.org/"), package_path
        assert re.fullmatch(r"sha512-[A-Za-z0-9+/=]+", str(package.get("integrity", ""))), package_path


def test_frontend_security_floors_and_cross_platform_build_peers_are_locked() -> None:
    package = json.loads(NPM_MANIFEST.read_text(encoding="utf-8"))
    lock = json.loads(NPM_LOCK.read_text(encoding="utf-8"))
    packages = lock["packages"]

    assert package["overrides"] == {
        "@hey-api/json-schema-ref-parser": {"js-yaml": "4.3.1"}
    }
    assert package["devDependencies"]["@emnapi/core"] == "2.0.0-alpha.4"
    assert package["devDependencies"]["@emnapi/runtime"] == "2.0.0-alpha.4"
    assert packages["node_modules/js-yaml"]["version"] == "4.3.1"
    assert packages["node_modules/brace-expansion"]["version"] == "5.0.9"
    assert packages["node_modules/@emnapi/core"]["version"] == "2.0.0-alpha.4"
    assert packages["node_modules/@emnapi/runtime"]["version"] == "2.0.0-alpha.4"


def test_ci_runs_bounded_lockfile_vulnerability_audits() -> None:
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")

    assert "supply-chain-audit:" in workflow
    assert 'cron: "17 3 * * 1"' in workflow
    assert "timeout-minutes: 15" in workflow
    assert "osv-scanner/releases/download/v2.3.8/osv-scanner_linux_amd64" in workflow
    assert "bc98e15319ed0d515e3f9235287ba53cdc5535d576d24fd573978ecfe9ab92dc" in workflow
    assert "sha256sum --check --strict" in workflow
    assert "scan source --no-resolve --data-source=native --verbosity=warn" in workflow
    assert "--config=osv-scanner.toml" in workflow
    assert "--lockfile=requirements.txt:requirements.lock" in workflow
    assert "--lockfile=requirements.txt:requirements-dev.lock" in workflow
    assert "--lockfile=requirements.txt:requirements-build.lock" in workflow
    assert "timeout 90s npm audit --package-lock-only --ignore-scripts" in workflow
    assert "--audit-level=high --registry=https://registry.npmjs.org" in workflow


def test_osv_exception_is_narrow_documented_and_expires() -> None:
    config = tomllib.loads(OSV_CONFIG.read_text(encoding="utf-8"))
    ignored = config.get("IgnoredVulns")

    assert isinstance(ignored, list)
    assert len(ignored) == 1
    exception = ignored[0]
    assert exception["id"] == "PYSEC-2026-2858"
    assert exception["ignoreUntil"] == date(2026, 11, 15)
    assert "no patched release" in exception["reason"]
    assert "a448945" in exception["reason"]


def test_cryptography_security_floor_is_locked_everywhere() -> None:
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    constraints = (ROOT / "constraints.txt").read_text(encoding="utf-8")
    assert "-c constraints.txt" in requirements
    assert "cryptography>=50.0.0,<51.0.0" in constraints
    for lock_name in PYTHON_LOCKS.values():
        lock_text = (ROOT / lock_name).read_text(encoding="utf-8")
        assert re.search(r"^cryptography==50\.0\.0\s+\\$", lock_text, re.MULTILINE), lock_name


def test_test_fixtures_do_not_use_llm_key_shaped_literals() -> None:
    test_files = [
        *ROOT.glob("engine/**/test*.py"),
        *ROOT.glob("desktop/src/**/*test*.ts"),
        *ROOT.glob("desktop/src/**/*test*.tsx"),
    ]
    key_shape = re.compile(r"(?<![A-Za-z0-9])sk-[A-Za-z0-9_-]{3,}")

    offenders = [
        path.relative_to(ROOT).as_posix()
        for path in test_files
        if key_shape.search(path.read_text(encoding="utf-8"))
    ]

    assert not offenders, offenders


def test_pytest_does_not_collect_generated_or_vendored_test_suites() -> None:
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    excluded = set(config["tool"]["pytest"]["ini_options"]["norecursedirs"])

    assert {
        ".build_venv",
        ".venv",
        "desktop/node_modules",
        "output",
        "pyinstaller_build",
        "pyinstaller_dist",
    } <= excluded


def _current_documentation_files() -> list[Path]:
    docs_root = ROOT / "docs"
    return sorted(
        path
        for path in docs_root.rglob("*.md")
        if "archive" not in path.relative_to(docs_root).parts
    )


def test_current_documentation_uses_the_shared_header_contract() -> None:
    allowed_states = {"当前", "已接受", "草案"}
    errors: list[str] = []

    for path in _current_documentation_files():
        relative = path.relative_to(ROOT).as_posix()
        header = "\n".join(path.read_text(encoding="utf-8").splitlines()[:24])
        document_types = re.findall(r"^> 文档类型：(.+?)\s*$", header, re.MULTILINE)
        statuses = re.findall(r"^> 状态：(.+?)\s*$", header, re.MULTILINE)
        verified_dates = re.findall(
            r"^> 最后核验：(\d{4}-\d{2}-\d{2})\s*$",
            header,
            re.MULTILINE,
        )

        if len(document_types) != 1:
            errors.append(f"{relative}: expected one document type")
        if len(statuses) != 1 or statuses[0] not in allowed_states:
            errors.append(f"{relative}: invalid status {statuses!r}")
        if len(verified_dates) != 1:
            errors.append(f"{relative}: expected one last-verified date")

    assert not errors, errors


def test_documentation_file_names_are_stable_and_portable() -> None:
    invalid: list[str] = []
    for path in (ROOT / "docs").rglob("*"):
        if not path.is_file() or path.name == "README.md":
            continue
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*\.(?:md|png|svg)", path.name):
            invalid.append(path.relative_to(ROOT).as_posix())

    assert not invalid, invalid


def test_current_documentation_relative_links_resolve() -> None:
    sources = [ROOT / "README.md", ROOT / "CONTRIBUTING.md", *_current_documentation_files()]
    markdown_link = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
    html_link = re.compile(r"(?:href|src)=\"([^\"]+)\"")
    broken: list[str] = []

    for source in sources:
        text = source.read_text(encoding="utf-8")
        targets = [*markdown_link.findall(text), *html_link.findall(text)]
        for raw_target in targets:
            target = raw_target.strip().strip("<>")
            if not target or target.startswith(("#", "http://", "https://", "mailto:")):
                continue
            path_text = unquote(target.split("#", 1)[0])
            if not path_text:
                continue
            destination = (source.parent / path_text).resolve()
            try:
                destination.relative_to(ROOT.resolve())
            except ValueError:
                broken.append(f"{source.relative_to(ROOT).as_posix()}: escapes repository: {target}")
                continue
            if not destination.exists():
                broken.append(f"{source.relative_to(ROOT).as_posix()}: {target}")

    assert not broken, broken


def test_pull_request_template_requires_investigation_and_reuse_rationale() -> None:
    template = (ROOT / ".github" / "pull_request_template.md").read_text(
        encoding="utf-8"
    )
    for required_field in (
        "技术调研与复用决策",
        "调查过的现有方案",
        "未采用其他方案的原因",
        "新增依赖或自研实现的主要风险",
        "删除条件与负责人",
        "调查限制",
    ):
        assert required_field in template


def test_quality_readme_indexes_investigation_and_reuse_guide() -> None:
    quality_readme = (ROOT / "docs" / "quality" / "README.md").read_text(
        encoding="utf-8"
    )
    assert (
        "[技术调研、方案复用与架构克制](./technical-investigation-and-reuse.md)"
        in quality_readme
    )


def test_generated_api_artifact_contract_is_open_type_with_schema_version() -> None:
    generated_types = (
        ROOT / "desktop" / "src" / "lib" / "api" / "generated" / "types.gen.ts"
    ).read_text(encoding="utf-8")
    assert "schema_version?: number;" in generated_types
    assert "type: string;" in generated_types


def test_r5_core_product_graph_has_no_static_github_domain() -> None:
    """GitHub may enter the product only through an activated DLC package."""
    retired_paths = (
        ROOT / "desktop" / "src" / "features" / "resources" / "GithubConnector.tsx",
        ROOT / "desktop" / "src" / "features" / "dock" / "GithubFileDock.tsx",
        ROOT
        / "desktop"
        / "src"
        / "features"
        / "workspace"
        / "artifacts"
        / "GithubFileSnapshotArtifactView.tsx",
        ROOT / "desktop" / "src" / "lib" / "api" / "github.ts",
    )
    assert not [path.relative_to(ROOT).as_posix() for path in retired_paths if path.exists()]
    retired_source_roots = (
        ROOT / "engine" / "github",
        ROOT / "desktop" / "src" / "features" / "github",
    )
    assert not [
        path.relative_to(ROOT).as_posix()
        for source_root in retired_source_roots
        if source_root.exists()
        for path in source_root.rglob("*")
        if path.is_file() and path.suffix in {".py", ".ts", ".tsx"}
    ]

    production_roots = (
        ROOT / "engine" / "api" / "__init__.py",
        ROOT / "engine" / "dlc" / "compiler.py",
        ROOT / "engine" / "dlc" / "snapshot.py",
        ROOT / "engine" / "models.py",
        ROOT / "desktop" / "src" / "features" / "dock" / "dockViewComposition.ts",
        ROOT
        / "desktop"
        / "src"
        / "features"
        / "resources"
        / "resourceConnectorComposition.tsx",
        ROOT
        / "desktop"
        / "src"
        / "features"
        / "resources"
        / "requestedResourceComposition.ts",
        ROOT
        / "desktop"
        / "src"
        / "features"
        / "workspace"
        / "artifacts"
        / "artifactRendererRegistry.tsx",
    )
    forbidden = re.compile(
        r"engine\.github|GithubRepositoryBinding|builtin\.github|"
        r"githubDockViews|GithubConnector|githubRequestedResourceContributor|"
        r"githubArtifactRenderers|githubApi"
    )
    offenders = [
        path.relative_to(ROOT).as_posix()
        for path in production_roots
        if forbidden.search(path.read_text(encoding="utf-8"))
    ]
    assert not offenders, offenders

    generated_root = ROOT / "desktop" / "src" / "lib" / "api" / "generated"
    generated_contract = "\n".join(
        path.read_text(encoding="utf-8") for path in generated_root.rglob("*.ts")
    )
    assert "/projects/{project_id}/github" not in generated_contract


def test_readme_architecture_diagram_is_static_svg() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    diagram_path = ROOT / "docs" / "images" / "system-architecture.svg"
    diagram = diagram_path.read_text(encoding="utf-8")

    assert "![DBFox 系统架构](docs/images/system-architecture.svg)" in readme
    assert "```mermaid" not in readme
    assert "<svg" in diagram
    assert "DBFox 系统架构" in diagram
    assert "React 工作区" in diagram
    assert "Electron / TypeScript" in diagram
    assert "FastAPI" in diagram and "Sidecar" in diagram
    assert "本地 SQLite" in diagram
    assert "用户数据库" in diagram
    assert "模型服务" in diagram
