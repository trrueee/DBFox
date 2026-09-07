"""Immutable, owner-resolved representations; never follows the live head."""
from datetime import UTC, datetime
from uuid import uuid4
from dbfox_dlc_api import (ArtifactRepresentationDescriptor, ArtifactRepresentationOperation,
    ArtifactRepresentationResult, ArtifactRepresentationStream, ArtifactRepresentationError)
from .contracts import ARTIFACT_TYPE, REPRESENTATION_TYPE, RevisionArtifact, InspectInput, PageInput, SECTIONS
from .store import canonical
from .model import AnimationError


class AnimationRepresentation:
    def __init__(self, store):
        self.store = store

    def describe(self, artifact):
        if artifact.type != ARTIFACT_TYPE:
            raise ArtifactRepresentationError("UNSUPPORTED_REPRESENTATION", "Not an Animation revision.", status_code=409)
        return ArtifactRepresentationDescriptor(representation_type=REPRESENTATION_TYPE, version=1, operations=(
            ArtifactRepresentationOperation(name="summary"),
            *(ArtifactRepresentationOperation(name=f"{section}_page") for section in SECTIONS),
            ArtifactRepresentationOperation(name="export_json", result_kind="stream", media_type="application/json"),
        ))

    def execute(self, artifact, request, context):
        del context
        self.describe(artifact)
        try:
            payload = RevisionArtifact.model_validate(artifact.payload)
            revision = self.store.get(payload.project_id, payload.animation_id, payload.version)
            if revision.animation.content_hash != payload.content_hash:
                raise AnimationError("CORRUPT", "Artifact fingerprint differs from its immutable source.")
            if request.operation == "export_json":
                if request.parameters:
                    raise ValueError("Export accepts no parameters")
                content = canonical(revision.document).encode("utf-8")
                return ArtifactRepresentationStream(chunks=(content[index:index + 65536] for index in range(0, len(content), 65536)),
                    media_type="application/json", file_name=f"animation-{payload.animation_id}-v{payload.version}.json",
                    metadata={"source-version": str(payload.version), "source-fingerprint": payload.content_hash, "consistency": "durable_snapshot"})
            if request.operation == "summary":
                if request.parameters:
                    raise ValueError("Summary accepts no parameters")
                result = {"animation": revision.animation.model_dump(mode="json"), "timing": revision.document.timing.model_dump(mode="json")}
            elif request.operation in {f"{section}_page" for section in SECTIONS}:
                page = PageInput.model_validate(request.parameters)
                result = self.store.page(payload.project_id, InspectInput(animation_id=payload.animation_id,
                    version=payload.version, section=request.operation.removesuffix("_page"), **page.model_dump())).model_dump(mode="json")
            else:
                raise ValueError("Unsupported operation")
            return ArtifactRepresentationResult(representation_type=REPRESENTATION_TYPE, representation_version=1,
                operation=request.operation, payload=result, consistency="durable_snapshot", read_at=datetime.now(UTC).isoformat(),
                read_id=uuid4().hex, source_version=str(payload.version), source_fingerprint=payload.content_hash)
        except AnimationError as exc:
            raise ArtifactRepresentationError("SOURCE_UNAVAILABLE", str(exc), status_code=409) from exc
        except ValueError as exc:
            raise ArtifactRepresentationError("INVALID_REQUEST", "Invalid Animation representation request.", status_code=422) from exc
