"""Suite discovery must not select a product database or model backend."""
from pathlib import Path
import subprocess
import sys

import pytest

from verification.bench import __main__ as cli


def test_importing_the_benchmark_shell_does_not_bind_engine_database() -> None:
    subprocess.run(
        [sys.executable, "-c", "import sys; import verification.bench.__main__; assert 'engine.db' not in sys.modules"],
        cwd=Path(__file__).resolve().parents[3], check=True, capture_output=True, text=True,
    )


def test_unified_cli_forwards_explicit_local_profile_and_retained_evidence(monkeypatch, tmp_path: Path) -> None:
    received = []
    monkeypatch.setattr(cli.data_agent_cli, "main", lambda argv: received.append(argv) or 0)
    profile = tmp_path / "local-model.json"
    assert cli.main(["run", "capability.dbfox_data.agent", "--local-model-profile", str(profile), "--keep-runtime"]) == 0
    assert received[0][received[0].index("--local-model-profile") + 1] == str(profile)
    assert "--keep-runtime" in received[0]


def test_scripted_suite_does_not_silently_ignore_local_model_selection(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="currently apply"):
        cli.main(["run", "core.loop.scripted", "--local-model-profile", str(tmp_path / "local-model.json")])
