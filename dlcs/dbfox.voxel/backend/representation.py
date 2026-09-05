"""Immutable JSON representation; no filesystem locators cross the owner boundary."""
from __future__ import annotations

from dbfox_dlc_api import (
    Artifact, ArtifactRepresentationContext, ArtifactRepresentationDescriptor,
    ArtifactRepresentationError, ArtifactRepresentationOperation, ArtifactRepresentationRequest,
    ArtifactRepresentationResult,
)

from .contracts import (
    LIBRARY_KIND, REPRESENTATION_TYPE, SNAPSHOT_TYPE, WORLD_KIND, ChunkPageInput,
    EmptyInput, ReadInput, RepresentationPage, SnapshotPayload,
)
from .geometry import VoxelError
from .store import VoxelStore, canonical, digest, now


class VoxelRepresentationProvider:
    def __init__(self, store: VoxelStore) -> None:
        self.store = store

    @staticmethod
    def describe(artifact: Artifact) -> ArtifactRepresentationDescriptor:
        if artifact.type != SNAPSHOT_TYPE or artifact.schema_version != 1:
            raise ArtifactRepresentationError("UNSUPPORTED_REPRESENTATION", "This Artifact is not a supported voxel snapshot.", status_code=409)
        return ArtifactRepresentationDescriptor(representation_type=REPRESENTATION_TYPE, version=1,
            operations=(ArtifactRepresentationOperation(name="manifest"), ArtifactRepresentationOperation(name="chunks")))

    def execute(self, artifact: Artifact, request: ArtifactRepresentationRequest, context: ArtifactRepresentationContext) -> ArtifactRepresentationResult:
        del context
        self.describe(artifact)
        try:
            payload = SnapshotPayload.model_validate(artifact.payload)
            if not any((ref.kind == WORLD_KIND and ref.id == payload.world_id) or (ref.kind == LIBRARY_KIND and ref.id == payload.project_id) for ref in artifact.resource_refs):
                raise VoxelError("INVALID_ARTIFACT", "The voxel snapshot has no matching resource provenance.", 409)
            snapshot = self.store.snapshot(payload.project_id, payload.world_id, payload.version)
            if self.store.summary(snapshot).model_dump() != payload.model_dump():
                raise VoxelError("CORRUPT_STATE", "The immutable voxel snapshot does not match its durable revision.", 409)
            if request.operation == "manifest":
                EmptyInput.model_validate(request.parameters)
                output = self.store.get(payload.project_id, ReadInput(world_id=payload.world_id, version=payload.version)).model_dump(mode="json")
            elif request.operation == "chunks":
                page = RepresentationPage.model_validate(request.parameters)
                output = self.store.chunks(payload.project_id, ChunkPageInput(world_id=payload.world_id, version=payload.version, **page.model_dump())).model_dump(mode="json")
            else:
                raise VoxelError("UNSUPPORTED_REPRESENTATION", "Voxel snapshots provide only manifest and chunks.", 409)
        except VoxelError as exc:
            raise ArtifactRepresentationError(exc.code, exc.message, status_code=exc.status_code) from exc
        except ValueError as exc:
            raise ArtifactRepresentationError("INVALID_REQUEST", "The voxel snapshot or page parameters are invalid.", status_code=422) from exc
        return ArtifactRepresentationResult(representation_type=REPRESENTATION_TYPE, representation_version=1,
            operation=request.operation, payload=output, consistency="durable_snapshot", read_at=now(),
            read_id=digest(canonical([artifact.id, request.operation, request.parameters]).encode("utf-8")),
            source_version=str(payload.version), source_fingerprint=payload.content_hash)
