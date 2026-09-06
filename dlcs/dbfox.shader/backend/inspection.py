"""Version-fixed bounded projections shared by Tools, operations and representations."""
from __future__ import annotations

import base64
import difflib
from collections.abc import Callable
from hashlib import sha256

from pydantic import JsonValue

from . import contracts as c
from .mutations import object_changes
from .store import ShaderError, Store, check_cancelled, not_cancelled


def metadata(revision: c.Revision) -> dict[str, JsonValue]:
    doc = revision.document
    return {"schema_version": 1, "language": doc.language, "preview": doc.preview.model_dump(mode="json"),
        "stage_count": len(doc.stages), "pass_count": len(doc.passes), "uniform_count": len(doc.uniforms), "texture_count": len(doc.textures),
        "source_bytes": sum(len(value.source.encode("utf-8")) for value in doc.stages)}


def limit_page(page: c.PageResult, budget: int = 32768) -> c.PageResult:
    while len(c.encoded(page.model_dump(mode="json", exclude_none=True))) > budget and page.items:
        page.items.pop()
        page.next_offset = page.offset + len(page.items)
        page.has_more = page.next_offset < page.total
    if len(c.encoded(page.model_dump(mode="json", exclude_none=True))) > budget:
        raise ShaderError("SHADER_LIMIT", "Inspection page exceeds its declared budget.")
    return page


def source_page(page: c.PageResult, lines: list[str], limit: int) -> c.PageResult:
    selected: list[str] = []
    for line in lines[page.offset:page.offset + limit]:
        selected.append(line)
        page.source = "".join(selected)
        page.next_offset = page.offset + len(selected)
        page.has_more = page.next_offset < len(lines)
        if len(c.encoded(page.model_dump(mode="json", exclude_none=True))) > 16_384:
            selected.pop()
            break
    page.source = "".join(selected)
    page.next_offset = page.offset + len(selected)
    page.has_more = page.next_offset < len(lines)
    return page


def inspect(store: Store, project: str, data: c.InspectInput, generation: int | None = None) -> c.PageResult:
    with store.transaction() as db:
        frozen = store.check_generation(db, project, generation, live=False)
        if data.section == "documents":
            revisions, total = store.catalog(db, project, frozen, offset=data.offset, limit=data.limit)
            return limit_page(c.PageResult(studio_generation=frozen, section="documents", items=[value.summary().model_dump(mode="json") for value in revisions], offset=data.offset, next_offset=data.offset+len(revisions), total=total, has_more=data.offset+len(revisions)<total))
        if data.document_id is None:
            raise ShaderError("SHADER_INVALID", "Document selector is required.")
        revision = store.read_revision(db, project, data.document_id, data.version, frozen)
        doc = revision.document
        page = c.PageResult(document=revision.summary(), studio_generation=frozen, section=data.section, offset=data.offset, next_offset=data.offset, total=0, has_more=False)
        if data.section == "summary":
            page.metadata = metadata(revision)
            return page
        if data.section == "source":
            stage = next((item for item in doc.stages if item.id == data.stage_id), None)
            if stage is None:
                raise ShaderError("SHADER_NOT_FOUND", "Stage does not exist in this revision.")
            lines = stage.source.splitlines(keepends=True)
            page.total, page.stage_id = len(lines), stage.id
            page.metadata = {"source_hash": sha256(stage.source.encode("utf-8")).hexdigest(), "source_bytes": len(stage.source.encode("utf-8"))}
            return source_page(page, lines, data.limit)
        items: list[dict[str, JsonValue]]
        if data.section == "stages":
            items = [{"id": value.id, "title": value.title, "kind": value.kind, "source_hash": sha256(value.source.encode("utf-8")).hexdigest(), "source_bytes": len(value.source.encode("utf-8")), "line_count": len(value.source.splitlines())} for value in doc.stages]
        elif data.section == "passes":
            items = [value.model_dump(mode="json") for value in doc.passes]
        elif data.section == "uniforms":
            items = [value.model_dump(mode="json") for value in doc.uniforms]
        else:
            items = [value.model_dump(mode="json") for value in doc.textures]
        page.items = items[data.offset:data.offset+data.limit]
        page.total = len(items)
        page.next_offset = data.offset + len(page.items)
        page.has_more = page.next_offset < page.total
        return limit_page(page)


def get_page(store: Store, project: str, data: c.GetInput, cancelled: Callable[[], bool] = not_cancelled) -> c.PageResult:
    check_cancelled(cancelled)
    if data.section == "document_bytes":
        with store.transaction() as db:
            revision = store.read_revision(db, project, data.document_id, data.version)
            raw = c.encoded({"document": revision.document.model_dump(mode="json"), "deleted": revision.deleted})
            if len(raw) > c.MAX_DOCUMENT + 32:
                raise ShaderError("SHADER_LIMIT", "Canonical document bytes exceed their budget.")
            if data.offset > len(raw):
                raise ShaderError("SHADER_INVALID", "Document byte offset exceeds its length.")
            selected = raw[data.offset:data.offset+data.limit]
            check_cancelled(cancelled)
            return limit_page(c.PageResult(document=revision.summary(), studio_generation=revision.studio_generation,
                section="document_bytes", offset=data.offset, next_offset=data.offset+len(selected), total=len(raw),
                has_more=data.offset+len(selected)<len(raw), document_bytes=base64.b64encode(selected).decode("ascii")))
    if data.section != "texture_bytes":
        return inspect(store, project, c.InspectInput.model_validate(data.model_dump(mode="json", exclude_none=True, exclude={"texture_id"})))
    with store.transaction() as db:
        revision = store.read_revision(db, project, data.document_id, data.version)
        texture = next((item for item in revision.document.textures if item.id == data.texture_id), None)
        if texture is None:
            raise ShaderError("SHADER_NOT_FOUND", "Texture does not belong to this document revision.")
        raw = store.read_texture(db, texture)
        if data.offset > len(raw):
            raise ShaderError("SHADER_INVALID", "Texture byte offset exceeds its length.")
        selected = raw[data.offset:data.offset+data.limit]
        check_cancelled(cancelled)
        return limit_page(c.PageResult(document=revision.summary(), studio_generation=revision.studio_generation, section="texture_bytes", offset=data.offset, next_offset=data.offset+len(selected), total=len(raw), has_more=data.offset+len(selected)<len(raw), texture_bytes=c.TexturePage(texture_id=texture.id, content_hash=texture.content_hash, total_bytes=len(raw), rgba_base64=base64.b64encode(selected).decode("ascii"))))


def revisions(store: Store, project: str, data: c.RevisionsInput) -> c.PageResult:
    with store.transaction() as db:
        current = store.read_revision(db, project, data.document_id, data.version)
        versions = db.execute("SELECT version FROM revisions WHERE project=? AND id=? AND version<=? ORDER BY version DESC LIMIT ? OFFSET ?", (project, data.document_id, current.version, data.limit, data.offset)).fetchall()
        items = [store.read_revision(db, project, data.document_id, row[0]).summary().model_dump(mode="json") for row in versions]
        return limit_page(c.PageResult(document=current.summary(), studio_generation=store.generation(db, project), section="revisions", items=items, offset=data.offset, next_offset=data.offset+len(items), total=current.version, has_more=data.offset+len(items)<current.version))


def diff(store: Store, project: str, data: c.DiffInput, generation: int | None = None) -> c.PageResult:
    with store.transaction() as db:
        frozen = store.check_generation(db, project, generation, live=False)
        before = store.read_revision(db, project, data.document_id, data.from_version, frozen)
        after = store.read_revision(db, project, data.document_id, data.to_version, frozen)
    page = c.PageResult(document=after.summary(), studio_generation=frozen, section="diff", offset=data.offset, next_offset=data.offset, total=0, has_more=False, metadata={"from_version": before.version, "from_hash": before.content_hash, "to_version": after.version, "to_hash": after.content_hash})
    if data.section == "source":
        if data.stage_id is None:
            raise ShaderError("SHADER_INVALID", "Source diff requires one stage id.")
        stages = [next((value for value in revision.document.stages if value.id == data.stage_id), None) for revision in (before, after)]
        sources = [value.source if value else "" for value in stages]
        page.stage_id = data.stage_id
        page.metadata.update({"source_hashes": [sha256(value.encode("utf-8")).hexdigest() for value in sources], "source_line_counts": [len(value.splitlines()) for value in sources]})
        if any(len(value.encode("utf-8")) > 65536 or len(value.splitlines()) > 2048 for value in sources):
            page.metadata["source_diff_available"] = False
            page.metadata["inspect_section"] = "source"
            return page
        lines = list(difflib.unified_diff(sources[0].splitlines(keepends=True), sources[1].splitlines(keepends=True), fromfile=f"v{before.version}", tofile=f"v{after.version}"))
        page.metadata["source_diff_available"] = True
        page.total = len(lines)
        return source_page(page, lines, data.limit)
    items = object_changes(before.document, after.document)
    for name in ("title", "preview"):
        if getattr(before.document, name) != getattr(after.document, name):
            items.append({"section": name, "id": data.document_id, "change": "updated"})
    if before.deleted != after.deleted:
        items.append({"section": "deleted", "id": data.document_id, "change": "updated"})
    page.items = items[data.offset:data.offset+data.limit]
    page.total, page.next_offset = len(items), data.offset+len(page.items)
    page.has_more = page.next_offset < page.total
    return limit_page(page)


def report_page(store: Store, project: str, data: c.ReportInput, generation: int | None = None) -> c.PageResult:
    report, _ = store.report(project, data.report_id, generation)
    revision = store.get(project, report.document_id, report.version, generation)
    diagnostics = [item.model_dump(mode="json", exclude_none=True) for item in report.diagnostics[data.offset:data.offset+data.limit]]
    return limit_page(c.PageResult(document=revision.summary(), studio_generation=revision.studio_generation, section="diagnostics", items=diagnostics, offset=data.offset, next_offset=data.offset+len(diagnostics), total=len(report.diagnostics), has_more=data.offset+len(diagnostics)<len(report.diagnostics), metadata={"report_id": report.id, "kind": report.kind, "compiled": report.compiled, "rendered": report.rendered, "log_truncated": report.log_truncated, "capabilities": report.capabilities.model_dump(mode="json"), "elapsed_ms": report.elapsed_ms}))
