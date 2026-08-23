"""Explicit fixtures for tests that still exercise the retired Core Workspace vertical.

Production composition must never import this module. The helpers make the
legacy capability opt-in while dbfox.workspace package conformance provides
the canonical System DLC coverage.
"""

from sqlalchemy.orm import Session

from engine.runtime_composition import build_product_tool_registry
from engine.tools.runtime import (
    BaseTool,
    ToolExecutionSpec,
    ToolInputModel,
    ToolOutputModel,
    ToolPolicy,
    ToolPresentation,
    ToolRegistry,
)
from engine.tools.runtime.attempt import CompositeResourceResolver


class _WorkspaceProbeInput(ToolInputModel):
    path: str = ""
    content: str = ""


class _WorkspaceProbeOutput(ToolOutputModel):
    ok: bool = True


class _WorkspaceProbeTool(BaseTool[_WorkspaceProbeInput, _WorkspaceProbeOutput]):
    name = "workspace_probe"
    group = "workspace"
    description = "Generic Workspace capability probe for Kernel tests."
    input_model = _WorkspaceProbeInput
    output_model = _WorkspaceProbeOutput
    presentation = ToolPresentation(title="Workspace probe", category="explore")
    execution = ToolExecutionSpec(required_resource_kinds=("workspace",))

    def run(self, _input, _context):
        return _WorkspaceProbeOutput()


class _FileReadProbe(_WorkspaceProbeTool):
    name = "file_read"


class _FileSearchProbe(_WorkspaceProbeTool):
    name = "file_search"


class _FileWriteProbe(_WorkspaceProbeTool):
    name = "file_write_patch"
    policy = ToolPolicy(risk_level="danger", requires_approval=True)


def registry_with_legacy_workspace(*, include_write: bool = False) -> ToolRegistry:
    product = build_product_tool_registry()
    registry = ToolRegistry(
        available_backends=frozenset({"in_process", "isolated_process"})
    )
    for tool in product.list_tools():
        registry.register(
            tool,
            owner=product.owner_of(tool.name),
            package_digest=product.package_digest_of(tool.name),
        )
    existing = set(product.tool_names())
    if "file_read" not in existing:
        registry.register(_FileReadProbe(), owner="dbfox.workspace.test")
    if "file_search" not in existing:
        registry.register(_FileSearchProbe(), owner="dbfox.workspace.test")
    if include_write and "file_write_patch" not in existing:
        registry.register(_FileWriteProbe(), owner="dbfox.workspace.test")
    return registry.freeze()


def legacy_workspace_resolver(db: Session) -> CompositeResourceResolver:
    def retired_workspace_resolver(_ref):
        raise ValueError(
            "The retired Core Workspace resolver is unavailable; use the "
            "dbfox.workspace package resolver"
        )

    return (
        CompositeResourceResolver()
        .register("dbfox.data.database", lambda _ref: db)
        .register("workspace", retired_workspace_resolver)
        .freeze()
    )
