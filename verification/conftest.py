"""Process-wide test isolation established before any DBFox module import."""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import pytest


PYTEST_RUNTIME_ROOT = Path(tempfile.mkdtemp(prefix="dbfox-pytest-runtime-"))
os.environ["DBFOX_RUNTIME_DIR"] = str(PYTEST_RUNTIME_ROOT)
os.environ["DBFOX_BYPASS_CONFIRMATION"] = "1"
os.environ["DBFOX_TESTING"] = "1"
os.environ["DBFOX_ALLOW_GUARDRAIL_BYPASS"] = "1"


@pytest.fixture(scope="session", autouse=True)
def cleanup_pytest_runtime_root():
    """Remove only the process-unique runtime owned by this pytest process."""
    yield
    shutil.rmtree(PYTEST_RUNTIME_ROOT, ignore_errors=True)
