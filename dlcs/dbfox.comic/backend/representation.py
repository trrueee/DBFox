"""Exact producer-bound Comic snapshots and self-contained browser exports."""
from datetime import UTC, datetime
from html import escape
from pathlib import Path
from uuid import uuid4
from dbfox_dlc_api import (ArtifactRepresentationDescriptor, ArtifactRepresentationError,
    ArtifactRepresentationOperation, ArtifactRepresentationResult, ArtifactRepresentationStream)
from .contracts import ARTIFACT_TYPE, DOCUMENT_KIND, LIBRARY_KIND, REPRESENTATION_TYPE, Id, InspectInput, PageInput, RevisionArtifact
from .store import ComicError, encoded


class PageRequest(PageInput):
    page_id: Id


def export_html(revision):
    # Include the exact production renderer. Text is JSON-escaped at the script
    # boundary and then inserted exclusively with textContent by the renderer.
    renderer = (Path(__file__).parents[1] / "frontend" / "render.js").read_text(encoding="utf-8")
    renderer = renderer.replace("export function renderPage", "function renderPage", 1)
    data = encoded(revision.document).replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    return (f'<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width">'
        f'<title>{escape(revision.document.title)}</title><style>body{{margin:24px;background:#DCE2E6;font-family:sans-serif}}'
        'svg{display:block;max-width:100%;height:auto;margin:20px auto;background:white;break-after:page}'
        '@media print{body{margin:0;background:white}svg{margin:0;max-height:100vh}}</style><body>'
        f'<h1>{escape(revision.document.title)}</h1><p>Immutable Comic revision {revision.comic.version} · {revision.comic.content_hash}</p>'
        f'<script>{renderer}\nconst comic={data}; for(const page of comic.pages) document.body.append(renderPage(page));</script></body></html>').encode("utf-8")


class ComicRepresentation:
    def __init__(self, store):
        self.store = store

    def describe(self, artifact):
        if artifact.type != ARTIFACT_TYPE or artifact.schema_version != 1:
            raise ArtifactRepresentationError("UNSUPPORTED_REPRESENTATION", "Not a supported Comic revision.", status_code=409)
        return ArtifactRepresentationDescriptor(representation_type=REPRESENTATION_TYPE, version=1, operations=(
            ArtifactRepresentationOperation(name="summary"), ArtifactRepresentationOperation(name="pages"),
            ArtifactRepresentationOperation(name="page"),
            ArtifactRepresentationOperation(name="export_json", result_kind="stream", media_type="application/json"),
            ArtifactRepresentationOperation(name="export_html", result_kind="stream", media_type="text/html"),
        ))

    def execute(self, artifact, request, context):
        self.describe(artifact)
        try:
            payload = RevisionArtifact.model_validate(artifact.payload)
            refs = artifact.resource_refs
            if len(refs) != 1 or not ((refs[0].kind == DOCUMENT_KIND and refs[0].id == payload.id and
                    type(refs[0].version) is int and refs[0].version in (payload.version, payload.version - 1)) or
                    (refs[0].kind == LIBRARY_KIND and refs[0].id == payload.project_id and refs[0].version == 1 and payload.version == 1)):
                raise ComicError("REFERENCE", "Artifact authority does not match this Comic revision.")
            producer = artifact.provenance.get("tool_invocation_id")
            if not isinstance(producer, str) or not producer:
                raise ComicError("REFERENCE", "Artifact is missing its Runtime producer.")
            revision = self.store.artifact_revision(payload, producer)
            if request.operation in ("export_json", "export_html"):
                if request.parameters:
                    raise ValueError("Export takes no parameters")
                is_html = request.operation == "export_html"
                content = export_html(revision) if is_html else encoded(revision.document).encode("utf-8")
                return ArtifactRepresentationStream(chunks=(content[i:i + 65536] for i in range(0, len(content), 65536)),
                    media_type="text/html" if is_html else "application/json", file_name=f"comic-{payload.id}-v{payload.version}.{'html' if is_html else 'json'}",
                    metadata={"source-version": str(payload.version), "source-fingerprint": payload.content_hash, "consistency": "durable_snapshot"})
            if request.operation == "summary":
                if request.parameters:
                    raise ValueError("Summary takes no parameters")
                result = payload.model_dump(mode="json")
            elif request.operation == "pages":
                page = PageInput.model_validate(request.parameters)
                result = self.store.inspect(payload.project_id, InspectInput(comic_id=payload.id, version=payload.version,
                    section="pages", offset=page.offset, limit=page.limit)).model_dump(mode="json")
            elif request.operation == "page":
                page = PageRequest.model_validate(request.parameters)
                result = self.store.inspect(payload.project_id, InspectInput(comic_id=payload.id, version=payload.version,
                    section="page", object_id=page.page_id, offset=page.offset, limit=page.limit)).model_dump(mode="json")
            else:
                raise ValueError("Unknown representation operation")
            return ArtifactRepresentationResult(representation_type=REPRESENTATION_TYPE, representation_version=1,
                operation=request.operation, payload=result, consistency="durable_snapshot", read_at=datetime.now(UTC).isoformat(),
                read_id=uuid4().hex, source_version=str(payload.version), source_fingerprint=payload.content_hash)
        except ComicError as exc:
            raise ArtifactRepresentationError("SOURCE_UNAVAILABLE", str(exc), status_code=409) from exc
        except (TypeError, ValueError) as exc:
            raise ArtifactRepresentationError("INVALID_REQUEST", "Invalid Comic representation request.", status_code=422) from exc
