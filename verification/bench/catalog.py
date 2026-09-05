"""Discoverable suite catalog for the benchmark command shell.

The catalog composes suite-owned loaders and entry points. It does not execute
Agent turns or introduce a benchmark-specific Runtime.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from verification.bench.capabilities.dbfox_data.agent.schema import (
    load_manifest as load_data_agent_manifest,
)
from verification.bench.capabilities.dbfox_data.direct.runtime import (
    run_data_direct_bench,
)
from verification.bench.capabilities.dbfox_data.direct.schema import (
    load_cases as load_data_direct_cases,
)
from verification.bench.capabilities.dbfox_pixel.runtime import run_pixel_bench
from verification.bench.capabilities.dbfox_pixel.schema import load_cases as load_pixel_cases
from verification.bench.capabilities.dbfox_scene.runtime import run_scene_bench
from verification.bench.capabilities.dbfox_scene.schema import load_cases as load_scene_cases
from verification.bench.composition.data_workspace.runtime import (
    run_data_workspace_bench,
)
from verification.bench.composition.data_workspace.schema import (
    load_cases as load_data_workspace_cases,
)
from verification.bench.core.authority.runtime import run_core_authority_bench
from verification.bench.core.authority.schema import load_cases as load_authority_cases
from verification.bench.core.context.runtime import run_core_context_bench
from verification.bench.core.context.schema import load_cases as load_context_cases
from verification.bench.core.loop.runtime import run_core_loop_bench
from verification.bench.core.loop.schema import load_cases as load_loop_cases
from verification.bench.capabilities.dbfox_voxel.runtime import run_voxel_bench
from verification.bench.capabilities.dbfox_voxel.schema import load_cases as load_voxel_cases


HERE = Path(__file__).resolve().parent
DeterministicRunner = Callable[..., dict[str, Any]]
CaseCountLoader = Callable[[Path], int]


def _count(loader: Callable[[Path], Any]) -> CaseCountLoader:
    return lambda path: len(loader(path).cases)


@dataclass(frozen=True)
class SuiteRegistration:
    manifest_path: Path
    case_count: CaseCountLoader
    runner: DeterministicRunner | None = None
    delegated_cli: str | None = None

    def __post_init__(self) -> None:
        if (self.runner is None) == (self.delegated_cli is None):
            raise ValueError("A suite must have exactly one execution owner")


SUITES: dict[str, SuiteRegistration] = {
    "capability.dbfox-pixel.scripted": SuiteRegistration(
        HERE / "capabilities" / "dbfox_pixel" / "suite.json",
        _count(load_pixel_cases),
        runner=run_pixel_bench,
    ),
    "capability.dbfox-scene.scripted": SuiteRegistration(
        HERE / "capabilities" / "dbfox_scene" / "suite.json",
        _count(load_scene_cases),
        runner=run_scene_bench,
    ),
    "capability.dbfox-voxel.scripted": SuiteRegistration(
        HERE / "capabilities" / "dbfox_voxel" / "suite.json",
        _count(load_voxel_cases),
        runner=run_voxel_bench,
    ),
    "core.loop.scripted": SuiteRegistration(
        HERE / "core" / "loop" / "suite.json",
        _count(load_loop_cases),
        runner=run_core_loop_bench,
    ),
    "core.context.scripted": SuiteRegistration(
        HERE / "core" / "context" / "suite.json",
        _count(load_context_cases),
        runner=run_core_context_bench,
    ),
    "core.authority.scripted": SuiteRegistration(
        HERE / "core" / "authority" / "suite.json",
        _count(load_authority_cases),
        runner=run_core_authority_bench,
    ),
    "capability.dbfox_data.direct": SuiteRegistration(
        HERE / "capabilities" / "dbfox_data" / "direct" / "suite.json",
        _count(load_data_direct_cases),
        runner=run_data_direct_bench,
    ),
    "capability.dbfox_data.agent": SuiteRegistration(
        HERE / "capabilities" / "dbfox_data" / "agent" / "suite.json",
        _count(load_data_agent_manifest),
        delegated_cli="data-agent",
    ),
    "composition.data_workspace.scripted": SuiteRegistration(
        HERE / "composition" / "data_workspace" / "suite.json",
        _count(load_data_workspace_cases),
        runner=run_data_workspace_bench,
    ),
}
