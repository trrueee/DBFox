"""Immutable public JSON views and PyPNG encoding of validated RGBA evidence."""
from __future__ import annotations

from datetime import UTC, datetime
import io
from uuid import uuid4

from dbfox_dlc_api import (
    Artifact, ArtifactRepresentationContext, ArtifactRepresentationDescriptor,
    ArtifactRepresentationError, ArtifactRepresentationOperation, ArtifactRepresentationRequest,
    ArtifactRepresentationResult, ArtifactRepresentationStream,
)

from . import contracts as c
from .inspection import get_page, report_page
from .store import ShaderError, Store


class PreviewParameters(c.Input):
    width: int = c.Field(default=32, ge=1, le=32)
    height: int = c.Field(default=32, ge=1, le=32)


def png_bytes(width: int, height: int, pixels: bytes) -> bytes:
    from .vendor import png
    if not 1 <= width <= 256 or not 1 <= height <= 256 or len(pixels) != width * height * 4:
        raise ShaderError("SHADER_CORRUPT", "Invalid canonical preview pixels.")
    stream = io.BytesIO()
    stride = width * 4
    png.Writer(width=width, height=height, greyscale=False, alpha=True, bitdepth=8).write(stream, (pixels[offset:offset+stride] for offset in range(0, len(pixels), stride)))
    result = stream.getvalue()
    if len(result) > 1_048_576:
        raise ShaderError("SHADER_LIMIT", "PNG export exceeded its budget.")
    return result


class Representation:
    def __init__(self, store: Store, artifact_type: str, representation_type: str) -> None:
        self.store, self.artifact_type, self.representation_type = store, artifact_type, representation_type

    def describe(self, artifact: Artifact) -> ArtifactRepresentationDescriptor:
        operations: tuple[ArtifactRepresentationOperation, ...]
        if artifact.type != self.artifact_type:
            raise ArtifactRepresentationError("UNSUPPORTED_REPRESENTATION", "Artifact type does not match Shader representation.", status_code=409)
        if self.representation_type.endswith("preview-png.v1"):
            operations = (ArtifactRepresentationOperation(name="export", result_kind="stream", media_type="image/png"),)
        elif self.artifact_type == c.DOCUMENT_ARTIFACT:
            operations = (ArtifactRepresentationOperation(name="page"),)
        elif self.artifact_type == c.REPORT_ARTIFACT:
            operations = (ArtifactRepresentationOperation(name="diagnostics"),)
        else:
            operations = (ArtifactRepresentationOperation(name="metadata"), ArtifactRepresentationOperation(name="sample"))
        return ArtifactRepresentationDescriptor(representation_type=self.representation_type, version=1, operations=operations)

    def execute(self, artifact: Artifact, request: ArtifactRepresentationRequest, context: ArtifactRepresentationContext) -> ArtifactRepresentationResult | ArtifactRepresentationStream:
        descriptor = self.describe(artifact)
        if descriptor.operation(request.operation) is None:
            raise ArtifactRepresentationError("UNSUPPORTED_REPRESENTATION", "Unknown Shader representation operation.", status_code=409)
        try:
            locator = c.ArtifactLocator.model_validate(artifact.payload)
            revision = self.store.get(locator.project_id, locator.document_id, locator.version)
            if revision.content_hash != locator.content_hash:
                raise ShaderError("SHADER_CORRUPT", "Artifact revision fingerprint does not match.")
            if self.artifact_type == c.DOCUMENT_ARTIFACT:
                params = c.ReadParameters.model_validate(request.parameters)
                source = c.GetInput.model_validate({"document_id": locator.document_id, "version": locator.version, **params.model_dump(exclude_none=True)})
                payload = get_page(self.store, locator.project_id, source).model_dump(mode="json", exclude_none=True)
            else:
                if locator.report_id is None:
                    raise ValueError("Report locator required")
                report, pixels = self.store.report(locator.project_id, locator.report_id)
                if report.document_id != locator.document_id or report.version != locator.version or report.content_hash != locator.content_hash:
                    raise ShaderError("SHADER_CORRUPT", "Artifact report fingerprint does not match.")
                if self.artifact_type == c.REPORT_ARTIFACT:
                    params_page = c.PageInput.model_validate(request.parameters)
                    payload = report_page(self.store, locator.project_id, c.ReportInput(report_id=report.id, **params_page.model_dump())).model_dump(mode="json", exclude_none=True)
                else:
                    if not report.rendered or report.width is None or report.height is None:
                        raise ValueError("Artifact has no rendered preview")
                    if request.operation == "export":
                        c.Input.model_validate(request.parameters)
                        raw = png_bytes(report.width, report.height, pixels)
                        return ArtifactRepresentationStream(chunks=iter((raw,)), media_type="image/png", file_name=f"shader-{report.id}.png", metadata={"pixel_hash": report.pixel_hash or "", "document_version": str(report.version), "row_order": "top-left"})
                    payload = report.model_dump(mode="json", exclude_none=True, exclude={"diagnostics", "logs"})
                    if request.operation == "sample":
                        params_preview = PreviewParameters.model_validate(request.parameters)
                        width, height = params_preview.width, params_preview.height
                        rgba: list[int] = []
                        for y in range(height):
                            for x in range(width):
                                index = ((y * report.height // height) * report.width + x * report.width // width) * 4
                                rgba.extend(pixels[index:index+4])
                        payload.update(sample_width=width, sample_height=height, rgba=rgba, row_order="top-left", sampling="nearest")
                    else:
                        c.Input.model_validate(request.parameters)
            return ArtifactRepresentationResult(representation_type=self.representation_type, representation_version=1, operation=request.operation, payload=payload, consistency="durable_snapshot", read_at=datetime.now(UTC).isoformat(), read_id=str(uuid4()), source_version=str(locator.version), source_fingerprint=locator.content_hash)
        except ShaderError as exc:
            raise ArtifactRepresentationError("SOURCE_UNAVAILABLE", str(exc), status_code=409) from exc
        except ValueError as exc:
            raise ArtifactRepresentationError("INVALID_REQUEST", "Invalid Shader representation locator or parameters.", status_code=400) from exc
