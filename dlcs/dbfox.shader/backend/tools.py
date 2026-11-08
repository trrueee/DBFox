"""Thirteen public tools with explicit bounded observations and receipt recovery."""
from __future__ import annotations

from dbfox_dlc_api import (
    Artifact, ArtifactDraft, BaseTool, ExtensionToolRunContext, ResourceScopeRef,
    ToolExecutionSpec, ToolInputError, ToolObservationProjection, ToolOutcome,
    ToolPolicy, ToolPresentation, ToolReconciliation, ToolResourceRequirement, ToolSemanticSpec,
)
from pydantic import JsonValue

from . import contracts as c
from .compute import ComputeBridge
from .inspection import diff, inspect, limit_page, report_page
from .store import ShaderError, Store


WRITE = ToolExecutionSpec(timeout_seconds=12, recovery="reconcile", retryable=False, concurrency="sequential", max_output_bytes=32768, required_resources=(ToolResourceRequirement(kind=c.STUDIO_KIND),))
READ = ToolExecutionSpec(timeout_seconds=12, recovery="retry_safe", retryable=True, max_retries=1, concurrency="parallel_safe", max_output_bytes=32768, required_resources=(ToolResourceRequirement(kind=c.STUDIO_KIND),))


def scope(context: ExtensionToolRunContext) -> tuple[c.Studio, ResourceScopeRef]:
    refs = context.scopes(c.STUDIO_KIND)
    if len(refs) != 1 or type(refs[0].version) is not int:
        raise ToolInputError("One exact Shader Studio resource is required.")
    resolved = context.resource(refs[0])
    if not isinstance(resolved, c.Studio) or resolved.project_id != refs[0].id or resolved.generation != refs[0].version:
        raise ToolInputError("Resolved Shader studio does not match the frozen invocation.")
    return resolved, refs[0]


def artifact_drafts(result: c.MutationResult | c.ComputeOutcome, project: str, ref: ResourceScopeRef) -> tuple[ArtifactDraft, ...]:
    summary = result.document
    locator = c.ArtifactLocator(project_id=project, document_id=summary.id, version=summary.version, content_hash=summary.content_hash, title=summary.title, report_id=result.report_id if isinstance(result, c.ComputeOutcome) else None)
    if isinstance(result, c.ComputeOutcome):
        types = [c.REPORT_ARTIFACT, *([c.PREVIEW_ARTIFACT] if result.rendered else [])]
        description = f"Shader v{summary.version}: compiled={result.compiled}; rendered={result.rendered}; {result.diagnostic_count} diagnostics."
    else:
        types = [c.DOCUMENT_ARTIFACT]
        description = f"Shader v{summary.version}; changed={result.changed}; deleted={summary.deleted}."
    return tuple(ArtifactDraft(key="shader_"+str(index), type=kind, schema_version=1, title=f"{summary.title} · v{summary.version}", payload=locator.model_dump(mode="json", exclude_none=True), summary=description, semantic_key=f"shader:{summary.id}:{summary.version}:{locator.report_id or 'revision'}:{index}", resource_refs=(ref,)) for index, kind in enumerate(types))


def projection(status: str, output: dict[str, JsonValue]) -> ToolObservationProjection:
    if status != "success":
        return ToolObservationProjection(summary="Shader operation did not complete; no successful GPU result is implied.")
    if "section" in output:
        page = c.PageResult.model_validate(output)
        if page.section == "diagnostics":
            page.items = page.items[:20]
            for item in page.items:
                if isinstance(item.get("message"), str):
                    item["message"] = str(item["message"])[:256]
            page.next_offset = page.offset + len(page.items)
            page.has_more = page.next_offset < page.total
        if page.source is not None:
            payload = page.model_dump(mode="json", exclude_none=True)
            facts = page.model_dump(mode="json", exclude_none=True, exclude={"source"})
        else:
            page = limit_page(page, 8192)
            facts = page.model_dump(mode="json", exclude_none=True)
            payload = facts
        return ToolObservationProjection(summary=f"Shader {page.section}: exact document version and next_offset={page.next_offset}; has_more={page.has_more}.", facts=facts, provider_payload=payload)
    if "report_id" in output:
        result = c.ComputeOutcome.model_validate(output)
        summary = f"Shader v{result.document.version}: compiled={result.compiled}, rendered={result.rendered}." + (" Compiler/binding errors were observed." if not result.compiled else "")
    else:
        mutation = c.MutationResult.model_validate(output)
        summary = f"Shader {mutation.document.id} v{mutation.document.version}; studio generation {mutation.studio_generation}; changed={mutation.changed}."
    if len(c.encoded(output)) > 8192:
        raise ValueError("Shader observation facts exceed 8 KiB")
    return ToolObservationProjection(summary=summary, facts=output, provider_payload=output)


class ShaderTool(BaseTool[c.Input, c.Contract]):
    name = "shader_modify"
    description = "Apply one bounded typed Shader mutation batch."
    input_model = c.ApplyInput
    group = "shader"
    version = "1"
    policy = ToolPolicy(risk_level="warning", requires_approval=False)
    execution = WRITE
    output_model = c.MutationResult
    presentation = ToolPresentation(title="编辑 Shader", category="manage")
    semantics = ToolSemanticSpec(produces=(c.DOCUMENT_ARTIFACT,))
    action = "apply"

    def __init__(self, store: Store, bridge: ComputeBridge) -> None:
        self.store, self.bridge = store, bridge

    def project_observation(self, *, status: str, output: dict[str, JsonValue], artifacts: tuple[Artifact, ...]) -> ToolObservationProjection:
        return projection(status, output)

    def run(self, tool_input: c.Input, context: ExtensionToolRunContext) -> ToolOutcome[c.Contract]:
        studio, ref = scope(context)
        try:
            if isinstance(tool_input, c.InspectInput):
                return ToolOutcome(output=inspect(self.store, studio.project_id, tool_input, studio.generation))
            if isinstance(tool_input, c.DiffInput):
                return ToolOutcome(output=diff(self.store, studio.project_id, tool_input, studio.generation))
            if isinstance(tool_input, c.ReportInput):
                return ToolOutcome(output=report_page(self.store, studio.project_id, tool_input, studio.generation))
            if isinstance(tool_input, (c.CreateInput, c.VersionInput)):
                result: c.MutationResult | c.ComputeOutcome
                if self.action in {"compile", "preview"} and isinstance(tool_input, c.VersionInput):
                    prior = self.store.reconcile(studio.project_id, "agent", context.invocation_id, self.action, tool_input, studio.generation)
                    if prior is not None:
                        if not isinstance(prior, c.ComputeOutcome):
                            raise ShaderError("SHADER_CORRUPT", "Compute receipt kind mismatch.")
                        result = prior
                    else:
                        revision, snapshot = self.store.compute_snapshot(studio.project_id, tool_input, studio.generation)
                        computed, capabilities, elapsed, commit_guard = self.bridge.execute(context.invocation_id, revision, snapshot, self.action, context.is_cancelled)
                        report, pixels = self.store.make_report(revision, self.action, computed, capabilities, elapsed)
                        result = self.store.save_report(studio.project_id, context.invocation_id, self.action, tool_input, studio.generation, report, pixels, cancelled=commit_guard)
                else:
                    result = self.store.mutate(studio.project_id, "agent", context.invocation_id, self.action, tool_input, generation=studio.generation, cancelled=context.is_cancelled)
                return ToolOutcome(output=result, artifacts=artifact_drafts(result, studio.project_id, ref))
            raise ToolInputError("Shader tool input does not match its contract.")
        except ShaderError as exc:
            raise ToolInputError(f"{exc.code}: {exc}") from exc

    def reconcile(self, tool_input: c.Input, context: ExtensionToolRunContext) -> ToolReconciliation:
        studio, ref = scope(context)
        try:
            result = self.store.reconcile(studio.project_id, "agent", context.invocation_id, self.action, tool_input, studio.generation)
            if result is None:
                return ToolReconciliation(status="unknown")
            # Validate source is still present, including history and pixels, before rebuilding drafts.
            if isinstance(result, c.ComputeOutcome):
                self.store.report(studio.project_id, result.report_id)
            else:
                self.store.get(studio.project_id, result.document.id, result.document.version)
            return ToolReconciliation(status="succeeded", output=result.model_dump(mode="json", exclude_none=True), artifacts=artifact_drafts(result, studio.project_id, ref))
        except ShaderError as exc:
            return ToolReconciliation(status="unknown", error=f"{exc.code}: {exc}")


class ShaderCreate(ShaderTool):
    reconcile = ShaderTool.reconcile
    name = "shader_create"
    description = "Create one durable ESSL 3.00 Shader document in the selected studio at expected_generation; returns document and default stage/pass ids."
    input_model = c.CreateInput
    action = "create"


class ShaderInspect(ShaderTool):
    name = "shader_inspect"
    description = "Inspect documents or one fixed document version in bounded pages. Read source by stage id and complete line offset; use returned ids/version for incremental edits."
    input_model = c.InspectInput
    output_model = c.PageResult
    execution = READ
    semantics = ToolSemanticSpec()


class ShaderModify(ShaderTool):
    reconcile = ShaderTool.reconcile
    name = "shader_modify"
    description = "Apply 1-64 structured Shader edits atomically at expected_version. Source patch requires a single exact old_text occurrence; local refs only reference earlier creates. Never replaces the whole document."
    input_model = c.ApplyInput


class UniformSet(ShaderTool):
    reconcile = ShaderTool.reconcile
    name = "uniform_set"
    description = "Set one existing uniform value, preserving identity and exact declared type, at expected_version."
    input_model = c.UniformSetInput
    action = "uniform_set"


class TextureBind(ShaderTool):
    reconcile = ShaderTool.reconcile
    name = "texture_bind"
    description = "Bind an existing texture or earlier pass to one named sampler of a pass. No URLs, paths, or external code are accepted."
    input_model = c.TextureBindInput
    action = "texture_bind"


class PassCreate(ShaderTool):
    reconcile = ShaderTool.reconcile
    name = "pass_create"
    description = "Append a bounded fullscreen pass with existing stage ids and earlier inputs; returns the generated pass id."
    input_model = c.PassCreateInput
    action = "pass_create"


class Compile(ShaderTool):
    reconcile = ShaderTool.reconcile
    name = "compile"
    description = "Compile/link and validate bindings through the active visible Chromium WebGL2 executor. Saves an immutable exact-version report; compiled=false means actual errors. Unavailable/timeout never claims success."
    input_model = c.VersionInput
    output_model = c.ComputeOutcome
    action = "compile"
    semantics = ToolSemanticSpec(produces=(c.REPORT_ARTIFACT,))


class InspectCompileError(ShaderTool):
    name = "inspect_compile_error"
    description = "Read a named immutable compile report diagnostic page; its version/hash identify the observed source, not the current head."
    input_model = c.ReportInput
    output_model = c.PageResult
    execution = READ
    semantics = ToolSemanticSpec()


class RenderPreview(Compile):
    reconcile = ShaderTool.reconcile
    name = "render_preview"
    description = "Compile then render one fixed-time WebGL2 preview. Publishes validated readPixels evidence only after actual executor success; no replay after timeout/cancellation."
    action = "preview"
    semantics = ToolSemanticSpec(produces=(c.REPORT_ARTIFACT, c.PREVIEW_ARTIFACT))


class ShaderDelete(ShaderTool):
    reconcile = ShaderTool.reconcile
    name = "shader_delete"
    description = "Append a deletion tombstone at expected_version. Historical revisions, reports and Artifact sources remain immutable and readable."
    input_model = c.VersionInput
    action = "delete"


class ShaderUndo(ShaderTool):
    reconcile = ShaderTool.reconcile
    name = "shader_undo"
    description = "Restore target_version content and deletion state as a new revision at expected_version; equal content is a no-op, and undo can itself be undone."
    input_model = c.UndoInput
    action = "undo"


class ShaderDiff(ShaderTool):
    name = "shader_diff"
    description = "Read bounded object differences or exact-stage source diff between two immutable versions. Large source returns hashes and inspect locator."
    input_model = c.DiffInput
    output_model = c.PageResult
    execution = READ
    semantics = ToolSemanticSpec()


class ShaderExport(ShaderTool):
    reconcile = ShaderTool.reconcile
    name = "shader_export"
    description = "Publish an immutable Shader document revision Artifact at expected_version. Its paged JSON representation is the formal composition/export boundary; does not run GLSL."
    input_model = c.VersionInput
    action = "export"


TOOL_TYPES = (ShaderCreate, ShaderInspect, ShaderModify, UniformSet, TextureBind, PassCreate, Compile, InspectCompileError, RenderPreview, ShaderDelete, ShaderUndo, ShaderDiff, ShaderExport)
