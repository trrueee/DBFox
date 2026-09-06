"""Build-time schema export from the same registered public operation models."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace

DIRECTORY = Path(__file__).resolve().parent
sys.path.insert(0, str(DIRECTORY.parents[1]))

from dbfox_dlc_api import BaseTool, DlcOperationSpec, DlcRuntimeInfo


class Recorder:
    def __init__(self) -> None:
        self.operations: list[DlcOperationSpec] = []
        self.tools: list[BaseTool] = []

    def register(self, item: object, *rest: object) -> None:
        if isinstance(item, DlcOperationSpec):
            self.operations.append(item)
        elif isinstance(item, BaseTool):
            self.tools.append(item)

    def register_provider(self, *args: object) -> None:
        pass

    def register_resolver(self, *args: object) -> None:
        pass

    def register_representation(self, *args: object) -> None:
        pass

    def register_support(self, *args: object) -> None:
        pass


def main() -> None:
    # Capture the public registration surface without importing Core internals.
    spec = importlib.util.spec_from_file_location("_game_schema", DIRECTORY / "backend/__init__.py", submodule_search_locations=[str(DIRECTORY / "backend")])
    if spec is None or spec.loader is None:
        raise RuntimeError("Game package source is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    contributions = importlib.import_module(spec.name + ".contributions")
    with TemporaryDirectory(prefix="dbfox-game-schema-") as temporary:
        staged = Recorder()
        host = SimpleNamespace(runtime_info=DlcRuntimeInfo(dlc_id="dbfox.game", package_version="0.1.0", package_digest="0" * 64, data_path=Path(temporary)), **{name: staged for name in ("tools", "operations", "resources", "context", "agent_guidance", "artifacts", "completion")})
        contributions.register(host)
        result = {
            "engine": contributions.c.ENGINE,
            "canonical": contributions.c.GameProject.model_json_schema(),
            "operations": {operation.name: {"scope": operation.scope, "input": operation.input_model.model_json_schema(), "output": operation.output_model.model_json_schema(), "max_output_bytes": operation.max_output_bytes} for operation in staged.operations},
            "tools": {tool.name: {"input": tool.input_model.model_json_schema(), "output": tool.output_model.model_json_schema()} for tool in staged.tools},
        }
    (DIRECTORY / "contracts.schema.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Generated Game canonical, 16 operation and 17 Tool schemas")


if __name__ == "__main__":
    main()
