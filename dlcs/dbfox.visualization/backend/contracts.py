"""Safe durable contracts for model-authored visual explanations."""

from __future__ import annotations

import math
from typing import Annotated, Literal

from dbfox_dlc_api import (
    BaseModel,
    ConfigDict,
    DATAFRAME_REPRESENTATION_TYPE,
    Field,
    ToolOutputModel,
)
from pydantic import JsonValue, field_validator, model_validator


VISUALIZATION_ARTIFACT_TYPE = "dbfox.visualization.document"
AUTHORED_DATASET_ARTIFACT_TYPE = "dbfox.visualization.authored_dataset"
LEGACY_DATA_CHART_ARTIFACT_TYPE = "dbfox.data.chart"
VISUALIZATION_SPEC_VERSION = "1.0"
NAMED_DATASET = "dbfox_source"

DataScalar = Annotated[str, Field(max_length=16_384)] | int | float | bool | None


class ArtifactVisualizationSource(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    kind: Literal["artifact"]
    artifact_id: str = Field(alias="artifactId", min_length=1, max_length=128)
    representation_type: str = Field(
        default=DATAFRAME_REPRESENTATION_TYPE,
        alias="representationType",
        pattern=r"^[a-z][a-z0-9_.-]{2,127}$",
    )
    page_size: int = Field(default=500, alias="pageSize", ge=1, le=500)


class InlineVisualizationSource(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    kind: Literal["inline"]
    provenance: Literal["model_knowledge", "user_provided"]
    records: list[dict[str, DataScalar]] = Field(min_length=1, max_length=200)

    @field_validator("records")
    @classmethod
    def validate_records(
        cls,
        records: list[dict[str, DataScalar]],
    ) -> list[dict[str, DataScalar]]:
        fields: set[str] = set()
        for record in records:
            if not record or len(record) > 64:
                raise ValueError("Inline visualization records require 1 to 64 fields")
            for raw_name, raw_value in record.items():
                name = str(raw_name).strip()
                if not name or len(name) > 256 or name in {"rows", "series"}:
                    raise ValueError("Inline visualization field names are invalid")
                if isinstance(raw_value, float) and not math.isfinite(raw_value):
                    raise ValueError("Inline visualization values must be finite")
                fields.add(name)
        if len(fields) > 64:
            raise ValueError("Inline visualization data exceeds 64 distinct fields")
        return records


VisualizationSource = Annotated[
    ArtifactVisualizationSource | InlineVisualizationSource,
    Field(discriminator="kind"),
]


class AuthoredDatasetArtifactPayload(BaseModel):
    """Small durable fact set authored from model knowledge or user input."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    provenance: Literal["model_knowledge", "user_provided"]
    records: list[dict[str, DataScalar]] = Field(min_length=1, max_length=200)

    @field_validator("records")
    @classmethod
    def validate_records(
        cls,
        records: list[dict[str, DataScalar]],
    ) -> list[dict[str, DataScalar]]:
        return InlineVisualizationSource(
            kind="inline",
            provenance="model_knowledge",
            records=records,
        ).records


class VisualizationLayout(BaseModel):
    model_config = ConfigDict(extra="forbid")

    columns: int = Field(default=2, ge=1, le=4)
    density: Literal["comfortable", "compact"] = "comfortable"


class VisualizationBlockBase(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    id: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$")
    span: Literal[1, 2, 3, 4] = 1


class MetricBlock(VisualizationBlockBase):
    kind: Literal["metric"]
    label: str = Field(min_length=1, max_length=120)
    field: str | None = Field(default=None, min_length=1, max_length=256)
    value: DataScalar = None
    aggregation: Literal["sum", "mean", "median", "min", "max", "count", "distinct"] | None = None
    format: Literal["number", "integer", "percent", "currency", "compact", "text"] = "number"
    unit: str | None = Field(default=None, max_length=32)
    emphasis: Literal["neutral", "positive", "negative", "warning"] = "neutral"

    @model_validator(mode="after")
    def validate_metric_source(self) -> "MetricBlock":
        if self.field is None and self.value is None:
            raise ValueError("Metric blocks require a field or explicit value")
        if self.field is not None and self.value is not None:
            raise ValueError("Metric blocks cannot mix a field and explicit value")
        if self.field is None and self.aggregation is not None:
            raise ValueError("Explicit metric values cannot declare aggregation")
        return self


class TextBlock(VisualizationBlockBase):
    kind: Literal["text"]
    title: str | None = Field(default=None, max_length=160)
    text: str = Field(min_length=1, max_length=2_000)
    tone: Literal["neutral", "insight", "warning"] = "neutral"


class TableBlock(VisualizationBlockBase):
    kind: Literal["table"]
    title: str | None = Field(default=None, max_length=160)
    description: str | None = Field(default=None, max_length=1_000)
    fields: list[str] = Field(default_factory=list, max_length=12)
    limit: int = Field(default=10, ge=1, le=100)


class ChartBlock(VisualizationBlockBase):
    kind: Literal["chart"]
    title: str | None = Field(default=None, max_length=160)
    description: str | None = Field(default=None, max_length=1_000)
    grammar: Literal["vega-lite", "vega"] = "vega-lite"
    spec: dict[str, JsonValue]
    min_height: int = Field(default=280, alias="minHeight", ge=160, le=720)


VisualizationBlock = Annotated[
    MetricBlock | TextBlock | TableBlock | ChartBlock,
    Field(discriminator="kind"),
]


class VisualizationDocument(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    spec_version: Literal["1.0"] = Field(
        default=VISUALIZATION_SPEC_VERSION,
        alias="specVersion",
    )
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2_000)
    insight: str = Field(min_length=1, max_length=1_000)
    source: VisualizationSource
    layout: VisualizationLayout = Field(default_factory=VisualizationLayout)
    blocks: list[VisualizationBlock] = Field(min_length=1, max_length=16)

    @model_validator(mode="after")
    def validate_document(self) -> "VisualizationDocument":
        identifiers = [block.id for block in self.blocks]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("Visualization block ids must be unique")
        if not any(block.kind in {"chart", "metric"} for block in self.blocks):
            raise ValueError(
                "A visualization document requires at least one chart or metric block"
            )
        if any(block.span > self.layout.columns for block in self.blocks):
            raise ValueError("Visualization block span exceeds the layout column count")
        return self


class VisualizationArtifactPayload(VisualizationDocument):
    """Historical v1 payload; retained to read earlier inline-source documents."""


class VisualizationArtifactPayloadV2(VisualizationDocument):
    """Current durable payload; all source rows live behind a Representation."""

    source: ArtifactVisualizationSource


class LegacyDataChartArtifactPayload(BaseModel):
    """Read-only schema retained so historical Data charts remain inspectable."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    source_result_artifact_id: str = Field(
        alias="sourceResultArtifactId",
        min_length=1,
        max_length=128,
    )
    chart_type: Literal["line", "bar", "pie", "scatter", "area"] = Field(
        alias="chartType"
    )
    x: str | None = Field(default=None, max_length=256)
    y: list[str] = Field(default_factory=list, max_length=1)
    aggregation: Literal["sum", "none"] | None = None
    title: str | None = Field(default=None, max_length=200)


class VisualizationCreateInput(VisualizationDocument):
    pass


class VisualizationCreateOutput(ToolOutputModel):
    created: bool
    source_kind: Literal["artifact", "authored_dataset"]
    source_artifact_id: str | None = None
    grammar: list[Literal["vega-lite", "vega"]]
    block_count: int = Field(ge=1, le=16)
    insight: str
