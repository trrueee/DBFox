from __future__ import annotations

import os
import tempfile
from pathlib import Path

from engine.runtime_paths import private_runtime_root


def test_pytest_process_uses_an_isolated_private_runtime_root() -> None:
    configured_root = Path(os.environ["DBFOX_RUNTIME_DIR"])

    assert configured_root.is_relative_to(Path(tempfile.gettempdir()))
    assert configured_root.name.startswith("dbfox-pytest-runtime-")
    assert private_runtime_root() == configured_root
