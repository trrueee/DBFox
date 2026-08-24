"""Direct Data capability runner over the production System DLC host."""

from __future__ import annotations

import hashlib
from pathlib import Path
import shutil
import sqlite3
from typing import Any
from uuid import uuid4

from verification.bench.capabilities.dbfox_data.direct.schema import (
    DataDirectCase,
    load_cases,
)
from verification.bench.framework.reporting import write_suite_report
from verification.bench.framework.schema import load_suite_manifest
from verification.bench.framework.trial import TrialOutcome
from verification.testkit.system_dlc_fixture import build_isolated_system_dlc_bundle


HERE = Path(__file__).resolve().parent


def _source_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _seed_database(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.executescript(
            """
            CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT NOT NULL);
            CREATE TABLE orders (
                id INTEGER PRIMARY KEY,
                customer_id INTEGER NOT NULL,
                total_cents INTEGER NOT NULL
            );
            INSERT INTO customers VALUES (1, 'Ada'), (2, 'Lin');
            INSERT INTO orders VALUES (1, 1, 4200), (2, 2, 1800);
            """
        )
        connection.commit()
    finally:
        connection.close()


def _invoke(snapshot: Any, project_id: str, name: str, payload: dict[str, Any]) -> Any:
    from engine.dlc.api import DlcOperationContext

    contribution = snapshot.get_operation("dbfox.data", name)
    if contribution is None:
        raise RuntimeError(f"Production dbfox.data operation is unavailable: {name}")
    result = contribution.spec.handler(
        contribution.spec.input_model.model_validate(payload),
        DlcOperationContext(
            dlc_id="dbfox.data",
            operation_name=name,
            project_id=project_id,
        ),
    )
    return contribution.spec.output_model.model_validate(result)


def _execute_case(
    snapshot: Any,
    *,
    suite_id: str,
    case: DataDirectCase,
    repetition: int,
    database_path: Path,
) -> TrialOutcome:
    project_id = f"data-direct-{case.case_id}-{repetition}-{uuid4().hex[:8]}"
    before = _source_digest(database_path)
    created = _invoke(
        snapshot,
        project_id,
        "profiles.create",
        {
            "name": "Data DirectBench SQLite",
            "provider": "sqlite",
            "is_read_only": True,
            "environment": "test",
            "initial_database_name": str(database_path.resolve()),
            "initial_database_display_name": "DirectBench",
        },
    )
    database = created.databases[0]
    listed = _invoke(snapshot, project_id, "profiles.list", {})
    descriptors = tuple(
        descriptor
        for provider in snapshot.resource_providers
        for descriptor in provider(None, project_id)
        if descriptor.kind == "dbfox.data.database"
    )
    refreshed = _invoke(
        snapshot,
        project_id,
        "catalog.refresh",
        {"database_id": database.id},
    )
    overview = _invoke(
        snapshot,
        project_id,
        "catalog.overview",
        {"database_id": database.id},
    )
    tables = _invoke(
        snapshot,
        project_id,
        "catalog.tables",
        {"database_id": database.id, "limit": 20},
    )
    after = _source_digest(database_path)
    discovered_names = tuple(sorted(item.table_name for item in tables.tables))
    expected_names = tuple(sorted(case.expected_tables))
    common_checks = {
        "connection_owns_database": (
            len(created.databases) == 1
            and len(listed.profiles) == 1
            and listed.profiles[0].profile.id == created.profile.id
        ),
        "database_is_authority_resource": (
            len(descriptors) == 1 and descriptors[0].id == database.id
        ),
        "source_database_unchanged": before == after,
    }
    scenario_checks = {
        "resource_discovery": bool(descriptors and descriptors[0].version),
        "catalog_refresh": (
            refreshed.status == "ready"
            and refreshed.table_count == len(expected_names)
            and refreshed.catalog_revision >= 1
        ),
        "catalog_browse": (
            overview.catalog_status == "ready"
            and overview.table_count == len(expected_names)
            and discovered_names == expected_names
        ),
    }
    checks = {**common_checks, "scenario_result": scenario_checks[case.scenario]}
    failed = tuple(name for name, passed in checks.items() if not passed)
    return TrialOutcome(
        suite_id=suite_id,
        case_id=case.case_id,
        repetition=repetition,
        verdict="pass" if not failed else "fail",
        metrics={
            "task.success_rate": 1.0 if not failed else 0.0,
            "capability.operation_accuracy": 1.0 if scenario_checks[case.scenario] else 0.0,
            "capability.resource_count": float(len(descriptors)),
            "capability.catalog_table_count": float(tables.returned_count),
            "safety.source_database_writes": 0.0 if before == after else 1.0,
        },
        failed_checks=failed,
        evidence={
            "profile_id": str(created.profile.id),
            "database_id": str(database.id),
            "resource_refs": tuple(
                (item.kind, item.id, item.version) for item in descriptors
            ),
            "catalog_revision": int(refreshed.catalog_revision),
            "table_names": discovered_names,
        },
    )


def run_data_direct_bench(
    *,
    output_dir: Path,
    repetitions: int = 1,
    case_ids: frozenset[str] = frozenset(),
) -> dict[str, Any]:
    if not 1 <= repetitions <= 20:
        raise ValueError("repetitions must be between 1 and 20")
    manifest = load_suite_manifest(HERE / "suite.json")
    dataset = load_cases(HERE / manifest.dataset)
    cases = tuple(case for case in dataset.cases if not case_ids or case.case_id in case_ids)
    if not cases:
        raise ValueError("No Data DirectBench cases matched the requested case ids")
    work_dir = output_dir.parent / f".{output_dir.name}-work"
    work_dir.mkdir(parents=True, exist_ok=False)
    previous_snapshot: Any | None = None
    snapshot_state_loaded = False
    try:
        from engine.runtime_composition import (
            active_runtime_snapshot,
            initialize_runtime_snapshot,
            set_active_runtime_snapshot,
        )
        previous_snapshot = active_runtime_snapshot()
        snapshot_state_loaded = True
        system_dlc_dir, system_dlc_manifest = build_isolated_system_dlc_bundle(
            work_dir / "system-bundle"
        )
        snapshot = initialize_runtime_snapshot(
            storage_root=work_dir / "installed-dlcs",
            system_dlc_dir=system_dlc_dir,
            system_dlc_manifest=system_dlc_manifest,
        )
        outcomes: list[TrialOutcome] = []
        for repetition in range(1, repetitions + 1):
            for case in cases:
                database_path = work_dir / f"{case.case_id}-{repetition}.sqlite"
                _seed_database(database_path)
                outcomes.append(
                    _execute_case(
                        snapshot,
                        suite_id=manifest.suite_id,
                        case=case,
                        repetition=repetition,
                        database_path=database_path,
                    )
                )
        return write_suite_report(output_dir, manifest=manifest, outcomes=tuple(outcomes))
    finally:
        if snapshot_state_loaded:
            set_active_runtime_snapshot(previous_snapshot)
        resolved_work = work_dir.resolve()
        resolved_parent = output_dir.parent.resolve()
        if resolved_work.parent == resolved_parent and resolved_work.name.startswith("."):
            shutil.rmtree(resolved_work)
