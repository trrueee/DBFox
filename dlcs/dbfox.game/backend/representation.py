"""Public immutable Game pages and a portable document/RGBA JSON bundle."""
from __future__ import annotations

import base64
from datetime import datetime, timezone
from uuid import uuid4

from dbfox_dlc_api import (
    Artifact, ArtifactRepresentationContext, ArtifactRepresentationDescriptor,
    ArtifactRepresentationError, ArtifactRepresentationOperation, ArtifactRepresentationRequest,
    ArtifactRepresentationResult, ArtifactRepresentationStream,
)
from pydantic import JsonValue

from . import contracts as c
from . import views
from .store import GameError, Store

DOCUMENT = "dbfox.game.document.v1"
REPORT = "dbfox.game.playtest.v1"


def bundle(store: Store, revision: c.Revision) -> dict[str, JsonValue]:
    assets: dict[str, JsonValue] = {}
    for asset in revision.game.assets:
        if asset.content_hash not in assets:
            assets[asset.content_hash] = base64.b64encode(store.asset_bytes(revision, asset.id)).decode("ascii")
    result: dict[str, JsonValue] = {"format": "dbfox.game.bundle.v1", "revision": revision.summary().data(), "document": revision.game.data(), "rgba_assets": assets}
    if len(c.encoded(result)) > 8 * 1024 * 1024:
        raise GameError("BUNDLE_BUDGET", "Game bundle exceeds its 8 MiB byte budget")
    return result


class DocumentRepresentation:
    def __init__(self, store: Store) -> None:
        self.store = store

    def describe(self, artifact: Artifact) -> ArtifactRepresentationDescriptor:
        if artifact.type != c.DOCUMENT_ARTIFACT or artifact.schema_version != 1:
            raise ArtifactRepresentationError("UNSUPPORTED_REPRESENTATION", "Artifact is not a Game revision")
        return ArtifactRepresentationDescriptor(representation_type=DOCUMENT, version=1, operations=(ArtifactRepresentationOperation(name="page"), ArtifactRepresentationOperation(name="export", result_kind="stream", media_type="application/json")))

    def execute(self, artifact: Artifact, request: ArtifactRepresentationRequest, context: ArtifactRepresentationContext) -> ArtifactRepresentationResult | ArtifactRepresentationStream:
        self.describe(artifact)
        try:
            locator = c.ArtifactLocator.model_validate(artifact.payload)
            if locator.report_id is not None:
                raise GameError("INVALID_ARTIFACT", "Document Artifact cannot reference a playtest report")
            revision = self.store.get(locator.project_id, locator.game_id, locator.version)
            if locator.content_hash != revision.content_hash or locator.title != revision.game.title:
                raise GameError("SOURCE_CHANGED", "Game Artifact does not match its immutable revision", 409)
            if request.operation == "export":
                c.Input.model_validate(request.parameters)
                raw = c.encoded(bundle(self.store, revision))
                return ArtifactRepresentationStream(chunks=iter((raw,)), media_type="application/json", file_name=f"game-{revision.game.id}-v{revision.version}.dbfox-game.json", metadata={"source_version": str(revision.version), "source_fingerprint": revision.content_hash})
            if request.operation != "page":
                raise GameError("INVALID_OPERATION", "Unsupported Game document Representation operation")
            parameters = c.ViewParameters.model_validate(request.parameters)
            data = c.GetInput.model_validate({**parameters.data(), "game_id": locator.game_id, "version": locator.version})
            result = views.read(self.store, revision, data)
            return ArtifactRepresentationResult(representation_type=DOCUMENT, representation_version=1, operation=request.operation, payload=result.data(), consistency="durable_snapshot", read_at=datetime.now(timezone.utc).isoformat(), read_id=str(uuid4()), source_version=str(revision.version), source_fingerprint=revision.content_hash)
        except GameError as exc:
            code = "SOURCE_UNAVAILABLE" if exc.code == "STATE_CORRUPT" else "SOURCE_CHANGED" if exc.code == "SOURCE_CHANGED" else "NOT_FOUND" if exc.status == 404 else "INVALID_REQUEST"
            raise ArtifactRepresentationError(code, str(exc)[:400], status_code=503 if exc.status == 500 else exc.status) from exc
        except ValueError as exc:
            raise ArtifactRepresentationError("INVALID_REQUEST", "Game Representation parameters or locator are invalid") from exc


class ReportRepresentation:
    def __init__(self, store: Store) -> None:
        self.store = store

    def describe(self, artifact: Artifact) -> ArtifactRepresentationDescriptor:
        if artifact.type != c.REPORT_ARTIFACT or artifact.schema_version != 1:
            raise ArtifactRepresentationError("UNSUPPORTED_REPRESENTATION", "Artifact is not a Game playtest")
        return ArtifactRepresentationDescriptor(representation_type=REPORT, version=1, operations=(ArtifactRepresentationOperation(name="page"), ArtifactRepresentationOperation(name="export", result_kind="stream", media_type="application/json")))

    def execute(self, artifact: Artifact, request: ArtifactRepresentationRequest, context: ArtifactRepresentationContext) -> ArtifactRepresentationResult | ArtifactRepresentationStream:
        self.describe(artifact)
        try:
            locator = c.ArtifactLocator.model_validate(artifact.payload)
            if locator.report_id is None:
                raise GameError("INVALID_ARTIFACT", "Playtest Artifact requires a report identity")
            revision = self.store.get(locator.project_id, locator.game_id, locator.version)
            if revision.content_hash != locator.content_hash or revision.game.title != locator.title:
                raise GameError("SOURCE_CHANGED", "Playtest Artifact does not match its source", 409)
            report = self.store.report(locator.project_id, locator.game_id, locator.version, locator.report_id)
            if request.operation == "export":
                c.Input.model_validate(request.parameters)
                return ArtifactRepresentationStream(chunks=iter((c.encoded({"source": locator.data(), "report": report.data()}),)), media_type="application/json", file_name=f"playtest-{locator.report_id}.json", metadata={"source_version": str(locator.version), "source_fingerprint": locator.content_hash})
            if request.operation != "page":
                raise GameError("INVALID_OPERATION", "Unsupported Game playtest Representation operation")
            data = c.ReportParameters.model_validate(request.parameters)
            items: list[dict[str, JsonValue]] = []
            if data.section == "events":
                items = [item.data() for item in report.events]
            elif data.section == "entities":
                items = [item.data() for item in report.entities]
            elif data.section == "variables":
                items = [{"id": identity, "value": value} for identity, value in sorted(report.variables.items())]
            result = views.page(data.section, revision, revision.library_version, items, data.offset, data.limit, metadata={"report": self.store._report_summary(locator.report_id, report).data()})
            return ArtifactRepresentationResult(representation_type=REPORT, representation_version=1, operation=request.operation, payload=result.data(), consistency="durable_snapshot", read_at=datetime.now(timezone.utc).isoformat(), read_id=str(uuid4()), source_version=str(locator.version), source_fingerprint=locator.content_hash)
        except GameError as exc:
            raise ArtifactRepresentationError("SOURCE_UNAVAILABLE" if exc.status == 500 else "INVALID_REQUEST", str(exc)[:400], status_code=503 if exc.status == 500 else exc.status) from exc
        except ValueError as exc:
            raise ArtifactRepresentationError("INVALID_REQUEST", "Game report parameters or locator are invalid") from exc
