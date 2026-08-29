"""Conformance coverage for the independent Visualization DLC boundary."""

from __future__ import annotations

from pathlib import Path

import pytest

from dbfox_dlc_api import (
    Artifact,
    ArtifactRelationType,
    ArtifactRepresentationRequest,
    ArtifactRepresentationResult,
    ArtifactRepresentationContext,
    DataFrameField,
    DataFramePage,
    ToolInputError,
)
from engine.dlc import BuiltinContributionSet, ContributionCompiler, DlcPackageService
from engine.agent.repositories.artifact import ArtifactRepository
from engine.agent.repositories.session import SessionRepository
from engine.models import AgentSession
from engine.runtime_composition import (
    active_runtime_snapshot,
    set_active_runtime_snapshot,
)
from engine.tools.runtime import ToolRunContext
from scripts.build_dbfox_visualization_dlc_fixture import (
    SOURCE_ROOT,
    build_dbfox_visualization_dlc_fixture,
)


def _snapshot(tmp_path: Path):
    built = build_dbfox_visualization_dlc_fixture(tmp_path / "archives")
    service = DlcPackageService(tmp_path / "runtime" / "dlcs")
    service.trust_publisher_from_file(
        built.archive,
        expected_package_digest=built.package_digest,
        expected_publisher_key_id=built.publisher_fingerprint,
    )
    service.install_from_file(built.archive)
    service.set_desired_enabled("dbfox.visualization", True)
    snapshot = ContributionCompiler(service.storage_root).compile(
        built_ins=BuiltinContributionSet()
    )
    assert snapshot.activation_failures == ()
    return snapshot


def _source_artifact() -> Artifact:
    return Artifact(
        id="artifact_source",
        session_id="session-visualization",
        run_id="run-visualization",
        turn_id="turn-visualization",
        type="acme.analytics.result",
        title="Revenue result",
        payload={"backend": "external"},
    )


def _dataframe_result() -> ArtifactRepresentationResult:
    page = DataFramePage(
        fields=[
            DataFrameField(
                key="month",
                name="month",
                type="date",
                nullable=False,
                values=["2026-01-01"],
            ),
            DataFrameField(
                key="revenue",
                name="revenue",
                type="number",
                nullable=False,
                values=[128.5],
            ),
            DataFrameField(
                key="brand",
                name="brand",
                type="string",
                nullable=False,
                values=["North"],
            ),
        ],
        page=1,
        page_size=1,
        row_count=12,
        has_next_page=True,
        latency_ms=2,
    )
    return ArtifactRepresentationResult(
        representation_type="dbfox.dataframe.v1",
        representation_version=1,
        operation="page",
        payload=page.model_dump(mode="json"),
        consistency="durable_snapshot",
        original_observed_at="2026-08-28T00:00:00Z",
        read_at="2026-08-28T00:01:00Z",
        read_id="visualization-schema-read",
        source_version="1",
        source_fingerprint="sha256:source",
    )


def _context(*, representation_available: bool = True) -> ToolRunContext:
    source = _source_artifact()

    def read(
        artifact_id: str,
        representation_type: str,
        request: ArtifactRepresentationRequest,
    ) -> ArtifactRepresentationResult:
        assert artifact_id == source.id
        assert representation_type == "dbfox.dataframe.v1"
        assert request.operation == "page"
        if not representation_available:
            raise RuntimeError("representation unavailable")
        return _dataframe_result()

    return ToolRunContext.for_invocation(
        request=None,
        invocation_id="visualization-invocation",
        idempotency_key="visualization-idempotency",
        artifact_loader=lambda artifact_id: source if artifact_id == source.id else None,
        artifact_representation_reader=read,
    )


def _artifact_payload(*, field: str = "revenue", spec_patch: dict | None = None) -> dict:
    spec = {
        "data": {"name": "dbfox_source"},
        "mark": {"type": "line", "point": True},
        "encoding": {
            "x": {"field": "month", "type": "temporal"},
            "y": {"field": field, "type": "quantitative"},
            "color": {"field": "brand", "type": "nominal"},
            "tooltip": [
                {"field": "month", "type": "temporal"},
                {"field": field, "type": "quantitative"},
            ],
        },
    }
    spec.update(spec_patch or {})
    return {
        "title": "Revenue trend",
        "description": "Monthly revenue by brand.",
        "insight": "Revenue can be compared across time without losing the source trail.",
        "source": {
            "kind": "artifact",
            "artifactId": "artifact_source",
            "representationType": "dbfox.dataframe.v1",
            "pageSize": 500,
        },
        "layout": {"columns": 2, "density": "comfortable"},
        "blocks": [
            {
                "id": "total",
                "kind": "metric",
                "span": 1,
                "label": "Revenue",
                "field": "revenue",
                "aggregation": "sum",
                "format": "currency",
                "unit": "CNY",
            },
            {
                "id": "trend",
                "kind": "chart",
                "span": 2,
                "title": "Monthly trend",
                "grammar": "vega-lite",
                "spec": spec,
                "minHeight": 280,
            },
        ],
    }


def test_visualization_source_uses_only_public_extension_api() -> None:
    for source in sorted((SOURCE_ROOT / "backend").rglob("*.py")):
        value = source.read_text(encoding="utf-8")
        assert "from engine" not in value
        assert "import engine" not in value
        assert "dbfox_data" not in value


def test_visualization_package_owns_tool_contract_guidance_and_frontend(
    tmp_path: Path,
) -> None:
    snapshot = _snapshot(tmp_path)
    assert [item.tool.name for item in snapshot.tools] == ["visualization_create"]
    assert {item.artifact_type for item in snapshot.artifact_contracts} == {
        "dbfox.visualization.document",
        "dbfox.visualization.authored_dataset",
        "dbfox.data.chart",
    }
    assert [item.spec.id for item in snapshot.capability_guidance] == [
        "visual_explanation"
    ]
    assert [
        (item.artifact_type, item.representation_type)
        for item in snapshot.artifact_representations
    ] == [
        ("dbfox.visualization.authored_dataset", "dbfox.dataframe.v1")
    ]
    active = next(
        item for item in snapshot.active_dlcs if item.dlc_id == "dbfox.visualization"
    )
    assert active.frontend_entrypoint == "frontend/index.js"


def test_tool_reads_generic_dataframe_and_keeps_artifact_source_reference_only(
    tmp_path: Path,
) -> None:
    snapshot = _snapshot(tmp_path)
    tool = snapshot.tools[0].tool
    outcome = tool.run(
        tool.input_model.model_validate(_artifact_payload()),
        _context(),
    )

    assert outcome.output.created is True
    assert outcome.output.source_artifact_id == "artifact_source"
    assert outcome.output.grammar == ["vega-lite"]
    assert len(outcome.artifacts) == 1
    draft = outcome.artifacts[0]
    assert draft.type == "dbfox.visualization.document"
    assert draft.schema_version == 2
    assert draft.payload["source"] == {
        "kind": "artifact",
        "artifactId": "artifact_source",
        "representationType": "dbfox.dataframe.v1",
        "pageSize": 500,
    }
    assert "rows" not in repr(draft.payload)
    assert draft.relations[0].relation is ArtifactRelationType.DERIVED_FROM
    assert draft.relations[0].artifact_id == "artifact_source"


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (_artifact_payload(field="missing"), "not provided by the source"),
        (_artifact_payload(spec_patch={"data": {"url": "https://example.com/data"}}), "not permitted"),
        (_artifact_payload(spec_patch={"transform": [{"calculate": "window.fetch('x')", "as": "x"}]}), "forbidden operation"),
    ],
)
def test_tool_rejects_untrusted_or_invalid_specs(
    tmp_path: Path,
    payload: dict,
    message: str,
) -> None:
    snapshot = _snapshot(tmp_path)
    tool = snapshot.tools[0].tool
    with pytest.raises(ToolInputError, match=message):
        tool.run(tool.input_model.model_validate(payload), _context())


def test_tool_fails_closed_when_source_representation_is_unavailable(
    tmp_path: Path,
) -> None:
    snapshot = _snapshot(tmp_path)
    tool = snapshot.tools[0].tool
    with pytest.raises(ToolInputError, match="does not expose a readable DataFrame"):
        tool.run(
            tool.input_model.model_validate(_artifact_payload()),
            _context(representation_available=False),
        )


def test_tool_allows_bounded_interpreter_safe_calculations(tmp_path: Path) -> None:
    snapshot = _snapshot(tmp_path)
    tool = snapshot.tools[0].tool
    payload = _artifact_payload(
        spec_patch={
            "transform": [
                {"calculate": "datum.revenue * 2", "as": "double_revenue"}
            ]
        }
    )

    outcome = tool.run(tool.input_model.model_validate(payload), _context())

    assert outcome.output.created is True


def test_tool_allows_safe_zoom_legend_and_input_parameters(tmp_path: Path) -> None:
    snapshot = _snapshot(tmp_path)
    tool = snapshot.tools[0].tool
    payload = _artifact_payload(
        spec_patch={
            "params": [
                {
                    "name": "zoom_window",
                    "select": {"type": "interval", "encodings": ["x"]},
                    "bind": "scales",
                },
                {
                    "name": "brand_pick",
                    "select": {"type": "point", "fields": ["brand"]},
                    "bind": "legend",
                },
                {
                    "name": "threshold",
                    "value": 100,
                    "bind": {"input": "range", "name": "Threshold", "min": 0, "max": 500},
                },
            ]
        }
    )

    outcome = tool.run(tool.input_model.model_validate(payload), _context())

    assert outcome.output.created is True


def test_tool_rejects_parameter_bindings_that_target_external_dom(tmp_path: Path) -> None:
    snapshot = _snapshot(tmp_path)
    tool = snapshot.tools[0].tool
    payload = _artifact_payload(
        spec_patch={
            "params": [
                {
                    "name": "unsafe_control",
                    "value": 1,
                    "bind": {"input": "range", "element": "body"},
                }
            ]
        }
    )

    with pytest.raises(ToolInputError, match="parameter bindings"):
        tool.run(tool.input_model.model_validate(payload), _context())


@pytest.mark.parametrize(
    ("parameter", "message"),
    [
        (
            {"name": "bad_zoom", "select": {"type": "point"}, "bind": "scales"},
            "Scale bindings require an interval selection",
        ),
        (
            {
                "name": "missing_field",
                "select": {"type": "point", "fields": ["does_not_exist"]},
            },
            "Selection fields must exist",
        ),
        (
            {
                "name": "bad_range",
                "value": 1,
                "bind": {"input": "range", "min": 5, "max": 1, "step": 0},
            },
            "minimum must be below",
        ),
    ],
)
def test_tool_rejects_invalid_interaction_combinations(
    tmp_path: Path,
    parameter: dict,
    message: str,
) -> None:
    snapshot = _snapshot(tmp_path)
    tool = snapshot.tools[0].tool
    payload = _artifact_payload(spec_patch={"params": [parameter]})

    with pytest.raises(ToolInputError, match=message):
        tool.run(tool.input_model.model_validate(payload), _context())


def test_tool_rejects_non_finite_chart_spec_numbers(tmp_path: Path) -> None:
    snapshot = _snapshot(tmp_path)
    tool = snapshot.tools[0].tool
    payload = _artifact_payload(spec_patch={"width": float("nan")})

    with pytest.raises(ToolInputError, match="finite JSON"):
        tool.run(tool.input_model.model_validate(payload), _context())


def test_inline_dataset_rejects_non_finite_values(tmp_path: Path) -> None:
    snapshot = _snapshot(tmp_path)
    tool = snapshot.tools[0].tool
    payload = _artifact_payload()
    payload["source"] = {
        "kind": "inline",
        "provenance": "model_knowledge",
        "records": [{"revenue": float("nan")}],
    }

    with pytest.raises(ValueError, match="must be finite"):
        tool.input_model.model_validate(payload)


def test_tool_accepts_bounded_truthfully_labeled_inline_knowledge(tmp_path: Path) -> None:
    snapshot = _snapshot(tmp_path)
    tool = snapshot.tools[0].tool
    payload = _artifact_payload()
    payload["source"] = {
        "kind": "inline",
        "provenance": "model_knowledge",
        "records": [
            {"month": "2026-01-01", "revenue": 12.0, "brand": "North"},
            {"month": "2026-02-01", "revenue": 18.0, "brand": "North"},
        ],
    }
    outcome = tool.run(tool.input_model.model_validate(payload), _context())
    assert outcome.output.source_kind == "authored_dataset"
    assert len(outcome.artifacts) == 2
    dataset, visualization = outcome.artifacts
    assert dataset.type == "dbfox.visualization.authored_dataset"
    assert dataset.payload["provenance"] == "model_knowledge"
    assert dataset.payload["records"] == payload["source"]["records"]
    assert dataset.visibility.value == "supporting"
    assert visualization.payload["source"]["kind"] == "artifact"
    assert "records" not in repr(visualization.payload)
    assert visualization.payload_draft_refs == {
        "/source/artifactId": "authored_dataset"
    }
    assert visualization.relations[0].draft_key == "authored_dataset"
    assert visualization.resource_refs == ()

    provider = snapshot.artifact_representations[0].provider
    authored = Artifact(
        id="artifact_authored",
        session_id="session-visualization",
        run_id="run-visualization",
        turn_id="turn-visualization",
        type=dataset.type,
        title=dataset.title,
        payload=dataset.payload,
        visibility=dataset.visibility,
    )
    result = provider.execute(
        authored,
        ArtifactRepresentationRequest(
            operation="page",
            parameters={
                "page": 1,
                "page_size": 1,
                "count_mode": "exact",
                "sort": [{"field": "revenue", "direction": "desc"}],
            },
        ),
        ArtifactRepresentationContext(artifact_loader=lambda _artifact_id: None),
    )
    frame = DataFramePage.model_validate(result.payload)
    assert frame.row_count == 2
    assert frame.has_next_page is True
    assert next(field for field in frame.fields if field.name == "revenue").values == [18.0]


def test_tool_can_create_a_metric_only_visual_summary(tmp_path: Path) -> None:
    snapshot = _snapshot(tmp_path)
    tool = snapshot.tools[0].tool
    payload = _artifact_payload()
    payload["blocks"] = [payload["blocks"][0]]

    outcome = tool.run(tool.input_model.model_validate(payload), _context())

    assert outcome.output.grammar == []
    assert outcome.output.block_count == 1
    assert outcome.artifacts[0].payload["blocks"][0]["kind"] == "metric"


def test_tool_validates_fields_in_composed_table_blocks(tmp_path: Path) -> None:
    snapshot = _snapshot(tmp_path)
    tool = snapshot.tools[0].tool
    payload = _artifact_payload()
    payload["blocks"].append(
        {
            "id": "detail",
            "kind": "table",
            "span": 2,
            "title": "Revenue detail",
            "fields": ["month", "brand", "revenue"],
            "limit": 12,
        }
    )

    outcome = tool.run(tool.input_model.model_validate(payload), _context())

    assert outcome.artifacts[0].payload["blocks"][-1]["kind"] == "table"

    payload["blocks"][-1]["fields"] = ["missing"]
    with pytest.raises(ToolInputError, match="not provided by the source"):
        tool.run(tool.input_model.model_validate(payload), _context())


def test_inline_source_materializes_one_atomic_dataset_visualization_graph(
    tmp_path: Path,
    db_session,
) -> None:
    snapshot = _snapshot(tmp_path)
    previous = active_runtime_snapshot()
    set_active_runtime_snapshot(snapshot)
    try:
        db_session.add(AgentSession(id="visualization-materialize", title="Visualize"))
        db_session.commit()
        sessions = SessionRepository(db_session)
        admission = sessions.admit(
            session_id="visualization-materialize",
            resource_refs=(),
            content="Create a visual explanation",
            idempotency_key="visualization-materialize-input",
            llm_credential_id="credential",
            api_base=None,
            model_name="model",
            request_payload={},
        )
        lease = sessions.claim(session_id="visualization-materialize", owner="worker")
        assert lease is not None
        sessions.promote_next_input(lease=lease)
        turn = sessions.start_turn(
            lease=lease,
            run_id=admission.run_id,
            agent_definition_version="1",
            prompt_version="1",
            prompt_hash="prompt",
            context_snapshot={},
            context_hash="context",
            tool_materialization={},
            tool_materialization_hash="tools",
            provider="test",
            model_name="test",
        )
        payload = _artifact_payload()
        payload["source"] = {
            "kind": "inline",
            "provenance": "user_provided",
            "records": [{"month": "2026-01-01", "revenue": 12.0, "brand": "North"}],
        }
        tool = snapshot.tools[0].tool
        outcome = tool.run(tool.input_model.model_validate(payload), _context())

        artifacts = ArtifactRepository(
            db_session,
            payload_contract_resolver=lambda artifact_type, schema_version: (
                contribution.validator
                if (
                    contribution := snapshot.get_artifact_contract(
                        artifact_type,
                        schema_version,
                    )
                )
                is not None
                else None
            ),
        ).persist_drafts(
            lease=lease,
            run_id=admission.run_id,
            turn_id=str(turn.id),
            invocation_id="visualization-materialize-invocation",
            tool_name="visualization_create",
            drafts=list(outcome.artifacts),
        )

        dataset, visualization = artifacts
        assert dataset.type == "dbfox.visualization.authored_dataset"
        assert visualization.schema_version == 2
        assert visualization.payload["source"]["artifactId"] == dataset.id
        assert visualization.relations[0].artifact_id == dataset.id
        assert "records" not in repr(visualization.payload)
    finally:
        set_active_runtime_snapshot(previous)
