"""Abrupt process exit at real owner transaction boundaries; verification only."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import sys


def crash(data: Path, request: Path, phase: str) -> None:
    source = Path(__file__).resolve().parents[4] / "dlcs/dbfox.voxel/backend"
    spec = importlib.util.spec_from_file_location("_voxel_crash_owner", source / "__init__.py", submodule_search_locations=[str(source)])
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    store_module = importlib.import_module(spec.name + ".store")
    contracts = importlib.import_module(spec.name + ".contracts")
    store = store_module.VoxelStore(data)
    if phase == "before_commit":
        original = store._write_receipt
        def interrupted(*args):
            original(*args)
            os._exit(73)
        store._write_receipt = interrupted
    store.mutate("project-voxel", contracts.ApplyInput.model_validate_json(request.read_text(encoding="utf-8")),
        kind="fill", origin="human", request_id="crash-write")
    os._exit(73)


if __name__ == "__main__":
    crash(Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3])
