"""Fresh crash injection using the installed signed package and real operation boundary."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys

from dbfox_dlc_api import DlcOperationContext
from engine.runtime_composition import initialize_runtime_snapshot


def crash(storage: Path, request: Path, phase: str) -> None:
    snapshot = initialize_runtime_snapshot(storage_root=storage)
    assert not snapshot.activation_failures, snapshot.activation_failures
    store = next(item.tool.store for item in snapshot.tools if item.tool.name == "voxel_fill")
    if phase == "before_commit":
        original = store._write_receipt
        def interrupted(*args):
            original(*args)
            os._exit(73)
        store._write_receipt = interrupted
    value = json.loads(request.read_text(encoding="utf-8"))
    spec = snapshot.get_operation("dbfox.voxel", value["operation"]).spec
    spec.handler(spec.input_model.model_validate(value["payload"]), DlcOperationContext(
        dlc_id="dbfox.voxel", operation_name=value["operation"], project_id=value["project"]))
    os._exit(73)


if __name__ == "__main__":
    crash(Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3])
