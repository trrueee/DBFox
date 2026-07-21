"""Regression contracts for reproducible, least-privilege engineering gates."""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
NPM_LOCK = ROOT / "desktop" / "package-lock.json"
NPM_MANIFEST = ROOT / "desktop" / "package.json"
CARGO_LOCK = ROOT / "desktop" / "src-tauri" / "Cargo.lock"
PYTHON_LOCKS = {
    "requirements.txt": "requirements.lock",
    "requirements-dev.txt": "requirements-dev.lock",
    "requirements-build.txt": "requirements-build.lock",
}


def _normalise_package_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _direct_requirement_names(path: Path) -> set[str]:
    names: set[str] = set()
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith(("#", "-r", "--requirement")):
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
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")
    actions = re.findall(r"^\s*- uses: ([^\s]+)$", workflow, flags=re.MULTILINE)

    assert actions
    for action in actions:
        owner_and_repo, separator, revision = action.partition("@")
        assert separator and owner_and_repo
        assert re.fullmatch(r"[0-9a-f]{40}", revision), action


def test_ci_enforces_the_required_layered_quality_gates() -> None:
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")

    for command in (
        "python -m alembic check",
        "python -m compileall -q engine build_sidecar.py",
        "python -m mypy --no-warn-unused-configs --follow-imports=skip",
        "engine build_sidecar.py",
        "python -m pytest engine/agent/tests",
        "engine/evaluation/tests",
        "build_sidecar.py",
        "npm run lint",
        "npm test -- --maxWorkers=1",
        "npm run build",
        "cargo fmt --all -- --check",
        "cargo clippy --locked --all-targets -- -D warnings",
        "cargo test --locked",
    ):
        assert command in workflow


def test_rust_toolchain_and_lockfile_are_explicit() -> None:
    manifest = (ROOT / "desktop" / "src-tauri" / "Cargo.toml").read_text(encoding="utf-8")
    toolchain = (ROOT / "desktop" / "src-tauri" / "rust-toolchain.toml").read_text(
        encoding="utf-8"
    )
    rust_host = (ROOT / "desktop" / "src-tauri" / "src" / "lib.rs").read_text(
        encoding="utf-8"
    )

    assert 'rust-version = "1.95"' in manifest
    assert 'channel = "1.95.0"' in toolchain
    assert (ROOT / "desktop" / "src-tauri" / "Cargo.lock").is_file()
    assert 'target_env = "gnu"' in rust_host
    assert "Windows desktop builds require the MSVC Rust toolchain" in rust_host


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
        assert "--universal --generate-hashes --python-version 3.12" in lock_text.splitlines()[1]
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

    assert "PIP_REQUIRE_HASHES: \"1\"" in workflow
    assert workflow.count("--require-hashes -r requirements-dev.lock") == 4
    assert "--require-hashes -r requirements-build.lock" in workflow
    assert "python -m pip install -r requirements-dev.txt" not in workflow
    assert "python -m pip install -r requirements-build.txt" not in workflow


def test_npm_lock_is_registry_resolved_and_integrity_verified() -> None:
    lock = json.loads(NPM_LOCK.read_text(encoding="utf-8"))

    assert lock["lockfileVersion"] == 3
    assert lock["requires"] is True
    packages = lock["packages"]
    assert isinstance(packages, dict) and packages

    for package_path, package in packages.items():
        if not package_path:
            continue
        assert isinstance(package, dict), package_path
        assert package.get("version"), package_path
        assert not package.get("link"), package_path
        assert str(package.get("resolved", "")).startswith("https://registry.npmjs.org/"), package_path
        assert re.fullmatch(r"sha512-[A-Za-z0-9+/=]+", str(package.get("integrity", ""))), package_path


def test_monaco_uses_the_explicitly_patched_dompurify_release() -> None:
    manifest = json.loads(NPM_MANIFEST.read_text(encoding="utf-8"))
    lock = json.loads(NPM_LOCK.read_text(encoding="utf-8"))

    override = manifest["overrides"]["monaco-editor"]["dompurify"]
    assert override == "3.4.12"
    assert lock["packages"]["node_modules/dompurify"]["version"] == override


def test_cargo_lock_is_registry_resolved_and_checksum_verified() -> None:
    lock = tomllib.loads(CARGO_LOCK.read_text(encoding="utf-8"))

    assert lock["version"] == 4
    packages = lock["package"]
    assert isinstance(packages, list) and packages
    root_packages = [package for package in packages if package["name"] == "dbfox"]
    assert len(root_packages) == 1

    for package in packages:
        if package["name"] == "dbfox":
            continue
        assert package.get("source") == "registry+https://github.com/rust-lang/crates.io-index", package["name"]
        assert re.fullmatch(r"[0-9a-f]{64}", str(package.get("checksum", ""))), package["name"]


def test_ci_runs_bounded_lockfile_vulnerability_audits() -> None:
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")

    assert "supply-chain-audit:" in workflow
    assert 'cron: "17 3 * * 1"' in workflow
    assert "timeout-minutes: 15" in workflow
    assert "osv-scanner/releases/download/v2.3.8/osv-scanner_linux_amd64" in workflow
    assert "bc98e15319ed0d515e3f9235287ba53cdc5535d576d24fd573978ecfe9ab92dc" in workflow
    assert "sha256sum --check --strict" in workflow
    assert "scan source --no-resolve --data-source=native --verbosity=warn" in workflow
    assert "--lockfile=requirements.txt:requirements.lock" in workflow
    assert "--lockfile=requirements.txt:requirements-dev.lock" in workflow
    assert "--lockfile=requirements.txt:requirements-build.lock" in workflow
    assert "timeout 90s npm audit --package-lock-only --ignore-scripts" in workflow
    assert "--audit-level=high --registry=https://registry.npmjs.org" in workflow
    assert "rustsec/rustsec/releases/download/cargo-audit/v0.22.2/cargo-audit-x86_64-unknown-linux-gnu-v0.22.2.tgz" in workflow
    assert "ab28a1bdb54db4d5d8ad5981cf1f959410370b3d28250dbd35f6a44248620e39" in workflow
    assert '"$CARGO_AUDIT_BIN" audit --db "$RUNNER_TEMP/rustsec-advisory-db" --file Cargo.lock' in workflow


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
