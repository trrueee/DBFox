"""Immutable Pixel views and PNG streams using the unmodified PyPNG Writer."""
from __future__ import annotations

from io import BytesIO

from dbfox_dlc_api import (ArtifactRepresentationDescriptor, ArtifactRepresentationError,
    ArtifactRepresentationOperation, ArtifactRepresentationResult, ArtifactRepresentationStream)

from . import contracts as c
from .domain import PixelError, check_rect, directory, require, rgba
from .store import digest, now
from .vendor import png


class FrameInput(c.Input):
    frame_id: c.Id
    rect: c.Rect


class PngInput(c.Input):
    frame_id: c.Id


class SheetInput(c.Input):
    tag_id: c.Id | None = None


def sheet_dimensions(document, count):
    # Preserve frame order without exceeding the existing PNG dimension or pixel
    # budgets. Exact rows avoid allocating padding beyond the canonical slots.
    columns = min(count, 8192 // document.canvas.width)
    while count % columns:
        columns -= 1
    width = document.canvas.width * columns
    height = document.canvas.height * (count // columns)
    require(0 < width <= 8192 and 0 < height <= 8192 and width * height <= c.MAX_SLOTS,
            "Sprite sheet exceeds its pixel or dimension budget.", "LIMIT")
    return columns, width, height


def sheet_layout(document, tag_id):
    ids = [frame.id for frame in document.frames]
    if tag_id is not None:
        tag = next((tag for tag in document.tags if tag.id == tag_id), None)
        require(tag is not None, "Pixel animation tag does not exist.", "NOT_FOUND")
        ids = tag.frame_ids
    columns, width, height = sheet_dimensions(document, len(ids))
    frames = {frame.id: frame for frame in document.frames}
    return {"width": width, "height": height, "frames": [{"frame_id": identity, "x": (index % columns) * document.canvas.width,
        "y": (index // columns) * document.canvas.height, "width": document.canvas.width,
        "height": document.canvas.height, "duration_ms": frames[identity].duration_ms}
        for index, identity in enumerate(ids)]}


def encode_png(document, frame_ids):
    columns, width, height = sheet_dimensions(document, len(frame_ids))
    frames = [rgba(document, identity) for identity in frame_ids]
    stride = document.canvas.width * 4
    rows = (b"".join(frame[(y % document.canvas.height) * stride:((y % document.canvas.height) + 1) * stride]
                    for frame in frames[(y // document.canvas.height) * columns:(y // document.canvas.height + 1) * columns])
            for y in range(height))
    output = BytesIO()
    png.Writer(width, height, greyscale=False, alpha=True, bitdepth=8, interlace=False).write(output, rows)
    encoded = output.getvalue()
    require(len(encoded) <= c.MAX_DOCUMENT_BYTES, "PNG output exceeds 2 MiB.", "LIMIT")
    return encoded


class PixelRepresentation:
    def __init__(self, store):
        self.store = store

    @staticmethod
    def describe(artifact):
        if artifact.type != c.ARTIFACT_TYPE or artifact.schema_version != 1:
            raise ArtifactRepresentationError("UNSUPPORTED_REPRESENTATION", "This is not a supported Pixel revision.", status_code=409)
        return ArtifactRepresentationDescriptor(representation_type=c.REPRESENTATION_TYPE, version=1, operations=(
            ArtifactRepresentationOperation(name="metadata", purpose="model_read"),
            ArtifactRepresentationOperation(name="frame", purpose="model_read"),
            ArtifactRepresentationOperation(name="sheet_layout", purpose="model_read"),
            ArtifactRepresentationOperation(name="png", result_kind="stream", media_type="image/png"),
            ArtifactRepresentationOperation(name="sheet", result_kind="stream", media_type="image/png", purpose="file")))

    def execute(self, artifact, request, context):
        del context
        self.describe(artifact)
        try:
            payload = c.DocumentSummary.model_validate(artifact.payload)
            require(any((ref.kind == c.DOCUMENT_KIND and ref.id == payload.document_id) or
                        (ref.kind == c.LIBRARY_KIND and ref.id == payload.project_id) for ref in artifact.resource_refs),
                    "Pixel Artifact has no matching resource provenance.", "AUTHORITY")
            source = self.store.get_revision(payload.project_id, payload.document_id, payload.revision)
            require(source.summary == payload, "Pixel Artifact differs from its immutable revision.", "CORRUPT_STATE")
            document = source.document
            operation = request.operation
            if operation == "metadata":
                params = c.MetadataInput.model_validate(request.parameters)
                items = directory(document, params.kind, params.tag_id)
                offset = params.page * params.page_size
                result = {"summary": payload.model_dump(), "kind": params.kind, "tag_id": params.tag_id,
                    "page": params.page, "page_size": params.page_size, "total": len(items),
                    "has_more": offset + params.page_size < len(items), "items": items[offset:offset + params.page_size]}
            elif operation == "frame":
                params = FrameInput.model_validate(request.parameters)
                rect = params.rect
                require(rect.width <= 32 and rect.height <= 32, "RGBA inspection is limited to 32x32 pixels.", "LIMIT")
                check_rect(rect, document.canvas.width, document.canvas.height)
                pixels = rgba(document, params.frame_id)
                result = {"frame_id": params.frame_id, "rect": rect.model_dump(), "rgba": [value
                    for y in range(rect.y, rect.y + rect.height)
                    for value in pixels[(y * document.canvas.width + rect.x) * 4:(y * document.canvas.width + rect.x + rect.width) * 4]]}
            elif operation == "png":
                params = PngInput.model_validate(request.parameters)
                data = encode_png(document, [params.frame_id])
                result = None
            elif operation in ("sheet", "sheet_layout"):
                params = SheetInput.model_validate(request.parameters)
                result = sheet_layout(document, params.tag_id)
                if operation == "sheet":
                    data = encode_png(document, [frame["frame_id"] for frame in result["frames"]])
            else:
                raise PixelError("INVALID", "Unknown Pixel representation operation.")
            if operation in ("png", "sheet"):
                return ArtifactRepresentationStream(chunks=iter((data,)), media_type="image/png",
                    file_name=f"{payload.document_id}-r{payload.revision}-{operation}.png",
                    metadata={"consistency": "durable_snapshot", "source_version": str(payload.revision), "source_fingerprint": payload.content_hash})
            return ArtifactRepresentationResult(representation_type=c.REPRESENTATION_TYPE, representation_version=1,
                operation=operation, payload=result, consistency="durable_snapshot", read_at=now(),
                read_id=digest(c.canonical([artifact.id, operation, request.parameters])),
                source_version=str(payload.revision), source_fingerprint=payload.content_hash)
        except PixelError as exc:
            code = ("SOURCE_UNAVAILABLE" if exc.code in ("PIXEL_CORRUPT_STATE", "PIXEL_NOT_FOUND", "PIXEL_BUSY") else
                    "FORBIDDEN" if exc.code == "PIXEL_AUTHORITY" else "INVALID_REQUEST")
            raise ArtifactRepresentationError(code, str(exc), status_code=403 if code == "FORBIDDEN" else 409) from exc
        except (ValueError, TypeError) as exc:
            raise ArtifactRepresentationError("INVALID_REQUEST", "Pixel Artifact or representation parameters are invalid.", status_code=422) from exc
