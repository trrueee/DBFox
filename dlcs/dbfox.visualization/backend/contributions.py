"""Visualization DLC contribution registration."""

from dbfox_dlc_api import (
    BackendExtensionHost,
    CapabilityGuidanceSpec,
    DATAFRAME_REPRESENTATION_TYPE,
    ToolKey,
)

from .authored_dataset import AuthoredDatasetDataFrameProvider
from .contracts import (
    AUTHORED_DATASET_ARTIFACT_TYPE,
    LEGACY_DATA_CHART_ARTIFACT_TYPE,
    VISUALIZATION_ARTIFACT_TYPE,
    AuthoredDatasetArtifactPayload,
    LegacyDataChartArtifactPayload,
    VisualizationArtifactPayload,
    VisualizationArtifactPayloadV2,
)
from .tool import VisualizationCreateTool


def register(host: BackendExtensionHost) -> None:
    host.tools.register(VisualizationCreateTool())
    host.artifacts.register(
        VISUALIZATION_ARTIFACT_TYPE,
        1,
        VisualizationArtifactPayload,
    )
    host.artifacts.register(
        VISUALIZATION_ARTIFACT_TYPE,
        2,
        VisualizationArtifactPayloadV2,
    )
    host.artifacts.register(
        AUTHORED_DATASET_ARTIFACT_TYPE,
        1,
        AuthoredDatasetArtifactPayload,
    )
    host.artifacts.register_representation(
        AUTHORED_DATASET_ARTIFACT_TYPE,
        DATAFRAME_REPRESENTATION_TYPE,
        AuthoredDatasetDataFrameProvider(),
    )
    host.artifacts.register(
        LEGACY_DATA_CHART_ARTIFACT_TYPE,
        1,
        LegacyDataChartArtifactPayload,
    )
    host.agent_guidance.register(
        CapabilityGuidanceSpec(
            id="visual_explanation",
            version="1",
            instructions=(
                "Use visualization_create only when a visual structure materially improves "
                "the answer: trends, comparisons, distributions, composition, relationships, "
                "a KPI summary, or a small KPI-plus-chart explanation. Do not create a visual "
                "obvious value or merely because tabular data exists.\n"
                "Choose Vega-Lite by default. Use restricted Vega only for an interaction or "
                "layout that Vega-Lite cannot express. Never provide URLs, executable code, "
                "or embedded source rows in a spec; use the named dbfox_source dataset.\n"
                "When using an Artifact source, inspect its DataFrame fields and preserve its "
                "meaning. When using small model-knowledge or user-provided data, label it "
                "truthfully. The Tool materializes those rows as a separate authored-dataset "
                "Artifact; never present that source as observed evidence.\n"
                "After creation, embed the Visualization Artifact near the explanation it "
                "supports when that improves the final answer; do not duplicate it mechanically."
            ),
            applies_to_artifact_types=(VISUALIZATION_ARTIFACT_TYPE,),
            tool_refs=(
                ToolKey(
                    owner_id="dbfox.visualization",
                    local_name="visualization_create",
                ),
            ),
        )
    )
