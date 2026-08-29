"""DataFrame projection for bounded authored Visualization datasets."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any

from dbfox_dlc_api import (
    Artifact,
    ArtifactRepresentationContext,
    ArtifactRepresentationDescriptor,
    ArtifactRepresentationError,
    ArtifactRepresentationOperation,
    ArtifactRepresentationRequest,
    ArtifactRepresentationResult,
    DATAFRAME_REPRESENTATION_TYPE,
    DataFrameField,
    DataFramePage,
    DataFramePageRequest,
    json_dumps,
)

from .contracts import (
    AUTHORED_DATASET_ARTIFACT_TYPE,
    AuthoredDatasetArtifactPayload,
)


class AuthoredDatasetDataFrameProvider:
    """Expose one immutable authored dataset through the shared DataFrame contract."""

    def describe(self, artifact: Artifact) -> ArtifactRepresentationDescriptor:
        if artifact.type != AUTHORED_DATASET_ARTIFACT_TYPE:
            raise ArtifactRepresentationError(
                "UNSUPPORTED_REPRESENTATION",
                "Artifact is not an authored Visualization dataset.",
                status_code=409,
            )
        return ArtifactRepresentationDescriptor(
            representation_type=DATAFRAME_REPRESENTATION_TYPE,
            version=1,
            operations=(ArtifactRepresentationOperation(name="page"),),
        )

    def execute(
        self,
        artifact: Artifact,
        request: ArtifactRepresentationRequest,
        context: ArtifactRepresentationContext,
    ) -> ArtifactRepresentationResult:
        del context
        self.describe(artifact)
        if request.operation != "page":
            raise ArtifactRepresentationError(
                "UNSUPPORTED_REPRESENTATION",
                "Authored datasets provide only the page operation.",
                status_code=409,
            )
        try:
            page_request = DataFramePageRequest.model_validate(request.parameters)
            payload = AuthoredDatasetArtifactPayload.model_validate(artifact.payload)
        except ValueError as exc:
            raise ArtifactRepresentationError(
                "INVALID_REQUEST",
                "The authored dataset page request is invalid.",
                status_code=422,
            ) from exc

        rows = _project_rows(payload.records, page_request)
        start = (page_request.page - 1) * page_request.page_size
        page_rows = rows[start : start + page_request.page_size]
        names = list(dict.fromkeys(name for row in payload.records for name in row))
        fields = [
            DataFrameField(
                key=name,
                name=name,
                type=_infer_type(row.get(name) for row in payload.records),
                nullable=any(row.get(name) is None for row in payload.records),
                values=[row.get(name) for row in page_rows],
            )
            for name in names
        ]
        page = DataFramePage(
            fields=fields,
            page=page_request.page,
            page_size=page_request.page_size,
            row_count=(len(rows) if page_request.count_mode != "none" else None),
            has_next_page=start + len(page_rows) < len(rows),
            latency_ms=0,
        )
        fingerprint = "sha256:" + hashlib.sha256(
            json_dumps(payload.model_dump(mode="json")).encode("utf-8")
        ).hexdigest()
        now = datetime.now(UTC).isoformat()
        return ArtifactRepresentationResult(
            representation_type=DATAFRAME_REPRESENTATION_TYPE,
            representation_version=1,
            operation="page",
            payload=page.model_dump(mode="json"),
            consistency="durable_snapshot",
            original_observed_at=None,
            read_at=now,
            read_id=f"authored:{artifact.id}:{artifact.version}:{page_request.page}",
            source_version=str(artifact.version),
            source_fingerprint=fingerprint,
            notices=(f"Source provenance: {payload.provenance}.",),
        )


def _project_rows(
    records: list[dict[str, Any]],
    request: DataFramePageRequest,
) -> list[dict[str, Any]]:
    rows = [dict(record) for record in records]
    if request.search:
        needle = request.search.casefold()
        rows = [
            row for row in rows
            if any(needle in str(value).casefold() for value in row.values())
        ]
    for item in request.filters:
        rows = [row for row in rows if _matches(row.get(item.field), item.operator, item.value)]
    for item in reversed(request.sort):
        rows.sort(
            key=lambda row: _sort_key(row.get(item.field)),
            reverse=item.direction == "desc",
        )
    return rows


def _matches(value: Any, operator: str, expected: Any) -> bool:
    if operator == "is_null":
        return value is None
    if operator == "is_not_null":
        return value is not None
    if operator == "in":
        return value in (expected if isinstance(expected, list) else [])
    if operator == "not_in":
        return value not in (expected if isinstance(expected, list) else [])
    if operator == "equals":
        return value == expected
    if operator == "not_equals":
        return value != expected
    if operator in {"contains", "starts_with", "ends_with"}:
        actual_text = "" if value is None else str(value).casefold()
        expected_text = "" if expected is None else str(expected).casefold()
        if operator == "contains":
            return expected_text in actual_text
        if operator == "starts_with":
            return actual_text.startswith(expected_text)
        return actual_text.endswith(expected_text)
    try:
        if operator == "gt":
            return value > expected
        if operator == "gte":
            return value >= expected
        if operator == "lt":
            return value < expected
        if operator == "lte":
            return value <= expected
    except TypeError:
        return False
    return False


def _sort_key(value: Any) -> tuple[bool, str, Any]:
    if value is None:
        return True, "", ""
    if isinstance(value, bool):
        return False, "boolean", int(value)
    if isinstance(value, (int, float)):
        return False, "number", float(value)
    return False, type(value).__name__, str(value).casefold()


def _infer_type(values) -> str:
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
