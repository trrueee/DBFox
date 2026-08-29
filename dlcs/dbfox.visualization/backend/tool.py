"""Provider-neutral visualization authoring Tool."""

from __future__ import annotations

from collections.abc import Iterable

from dbfox_dlc_api import (
    ArtifactDraft,
    ArtifactRelationDraft,
    ArtifactRelationType,
    ArtifactVisibility,
    ArtifactRepresentationRequest,
    BaseTool,
    DATAFRAME_REPRESENTATION_TYPE,
    DataFrameField,
    DataFramePage,
    ExtensionToolRunContext,
    ResourceScopeRef,
    ToolExecutionSpec,
    ToolInputError,
    ToolObservationProjection,
    ToolOutcome,
    ToolPolicy,
    ToolPresentation,
    ToolSemanticSpec,
)

from .contracts import (
    AUTHORED_DATASET_ARTIFACT_TYPE,
    VISUALIZATION_ARTIFACT_TYPE,
    ArtifactVisualizationSource,
    InlineVisualizationSource,
    VisualizationCreateInput,
    VisualizationCreateOutput,
)
from .validation import validate_visualization_document


class VisualizationCreateTool(
    BaseTool[VisualizationCreateInput, VisualizationCreateOutput]
):
    name = "visualization_create"
    group = "visualization"
    description = (
        "Create one durable, interactive visual explanation using a verified "
        "Vega-Lite or restricted Vega specification. The source may be any same-Run "
        "Artifact exposing dbfox.dataframe.v1, or a small explicitly labeled inline "
        "dataset. Use this only when a visualization improves understanding."
    )
    input_model = VisualizationCreateInput
    output_model = VisualizationCreateOutput
    version = "1"
    policy = ToolPolicy(risk_level="safe")
    execution = ToolExecutionSpec(
        recovery="retry_safe",
        concurrency="parallel_safe",
    )
    semantics = ToolSemanticSpec(
        produces=(VISUALIZATION_ARTIFACT_TYPE,),
        publishes_artifact_references=True,
    )
    presentation = ToolPresentation(
        title="创建交互式可视化",
        category="visualize",
    )

    def run(
        self,
        tool_input: VisualizationCreateInput,
        context: ExtensionToolRunContext,
    ) -> ToolOutcome[VisualizationCreateOutput]:
        source = tool_input.source
        source_artifact = None
        if isinstance(source, ArtifactVisualizationSource):
            if source.representation_type != DATAFRAME_REPRESENTATION_TYPE:
                raise ToolInputError(
                    "Visualization sources require the dbfox.dataframe.v1 representation."
                )
            try:
                source_artifact = context.artifact(source.artifact_id)
                represented = context.read_artifact_representation(
                    source.artifact_id,
                    source.representation_type,
                    ArtifactRepresentationRequest(
                        operation="page",
                        parameters={
                            "page": 1,
                            "page_size": 1,
                            "count_mode": "none",
                        },
                    ),
                )
                fields = DataFramePage.model_validate(represented.payload).fields
            except ToolInputError:
                raise
            except Exception as exc:
                raise ToolInputError(
                    "The source Artifact does not expose a readable DataFrame in this context."
                ) from exc
        else:
            fields = _inline_fields(source)

        validate_visualization_document(tool_input, fields)
        relations: tuple[ArtifactRelationDraft, ...] = ()
        resource_refs: tuple[ResourceScopeRef, ...] = ()
        if source_artifact is not None:
            relations = (
                ArtifactRelationDraft(
                    relation=ArtifactRelationType.DERIVED_FROM,
                    artifact_id=source_artifact.id,
                ),
            )
            resource_refs = source_artifact.resource_refs

        payload = tool_input.model_dump(mode="json", by_alias=True)
        source_draft = None
        payload_draft_refs: dict[str, str] = {}
        if isinstance(source, InlineVisualizationSource):
            source_draft = ArtifactDraft(
                key="authored_dataset",
                type=AUTHORED_DATASET_ARTIFACT_TYPE,
                schema_version=1,
                title=f"{tool_input.title} · 数据",
                summary=(
                    "用户提供的小型数据集"
                    if source.provenance == "user_provided"
                    else "模型知识生成的小型数据集"
                ),
                payload={
                    "provenance": source.provenance,
                    "records": source.records,
                },
                visibility=ArtifactVisibility.SUPPORTING,
            )
            payload["source"] = {
                "kind": "artifact",
                "artifactId": "pending_same_outcome_artifact",
                "representationType": DATAFRAME_REPRESENTATION_TYPE,
                "pageSize": min(500, len(source.records)),
            }
            payload_draft_refs = {"/source/artifactId": source_draft.key}

        draft = ArtifactDraft(
            key="visualization",
            type=VISUALIZATION_ARTIFACT_TYPE,
            schema_version=2,
            title=tool_input.title,
            summary=tool_input.insight,
            payload=payload,
            payload_draft_refs=payload_draft_refs,
            relations=relations,
            resource_refs=resource_refs,
            select_if_none=True,
        )
        if source_draft is not None:
            draft = draft.model_copy(
                update={
                    "relations": (
                        ArtifactRelationDraft(
                            relation=ArtifactRelationType.DERIVED_FROM,
                            draft_key=source_draft.key,
                        ),
                    ),
                }
            )

        grammars = sorted(
            {block.grammar for block in tool_input.blocks if block.kind == "chart"}
        )
        return ToolOutcome(
            output=VisualizationCreateOutput(
                created=True,
                source_kind=(
                    "artifact"
                    if isinstance(source, ArtifactVisualizationSource)
                    else "authored_dataset"
                ),
                source_artifact_id=(
                    source.artifact_id
                    if isinstance(source, ArtifactVisualizationSource)
                    else None
                ),
                grammar=grammars,
                block_count=len(tool_input.blocks),
                insight=tool_input.insight,
            ),
            artifacts=((source_draft, draft) if source_draft is not None else (draft,)),
        )

    def project_observation(self, *, status, output, artifacts):
        if status != "success":
            return ToolObservationProjection(summary="可视化创建失败。")
        artifact = next(
            (
                item
                for item in artifacts
                if str(getattr(item, "type", "")) == VISUALIZATION_ARTIFACT_TYPE
            ),
            None,
        )
        artifact_id = str(getattr(artifact, "id", "") or "") or None
        authored_dataset = next(
            (
                item
                for item in artifacts
                if str(getattr(item, "type", "")) == AUTHORED_DATASET_ARTIFACT_TYPE
            ),
            None,
        )
        authored_dataset_id = str(
            getattr(authored_dataset, "id", "") or ""
        ) or None
        return ToolObservationProjection(
            summary="交互式可视化已创建。",
            facts={
                "visualization_artifact_id": artifact_id,
                "source_kind": output.get("source_kind"),
                "source_artifact_id": output.get("source_artifact_id"),
                "authored_dataset_artifact_id": authored_dataset_id,
                "grammars": output.get("grammar") or [],
                "block_count": output.get("block_count"),
                "insight": output.get("insight"),
            },
        )


def _inline_fields(source: InlineVisualizationSource) -> list[DataFrameField]:
    names = list(dict.fromkeys(name for record in source.records for name in record))
    return [
        DataFrameField(
            key=name,
            name=name,
            type=_infer_type(record.get(name) for record in source.records),
            nullable=any(record.get(name) is None for record in source.records),
            values=[],
        )
        for name in names
    ]


def _infer_type(values: Iterable[object]) -> str:
    kinds = {
        "boolean" if isinstance(value, bool)
        else "integer" if isinstance(value, int)
        else "number" if isinstance(value, float)
        else "string"
        for value in values
        if value is not None
    }
    if not kinds:
        return "unknown"
    if kinds <= {"integer", "number"}:
        return "number" if "number" in kinds else "integer"
    return next(iter(kinds)) if len(kinds) == 1 else "string"
