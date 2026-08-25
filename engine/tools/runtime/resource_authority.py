"""Bind a model-authored domain Tool call to exact Project Resource authority."""

from __future__ import annotations

from typing import Any

from engine.agent.resource_refs import ProjectResourceDescriptor
from engine.errors import ToolInputError
from engine.resource import ResourceScopeRef
from engine.tools.runtime.base import BaseTool


def bind_tool_invocation_resources(
    tool: BaseTool[Any, Any],
    authorized_input: dict[str, Any],
    *,
    discovered: tuple[ProjectResourceDescriptor, ...],
    explicit_authority: tuple[ResourceScopeRef, ...] = (),
    artifact_authority: dict[str, tuple[ResourceScopeRef, ...]] | None = None,
) -> tuple[ResourceScopeRef, ...]:
    """Resolve only the resources required by one Invocation.

    Discovery controls Tool availability, not authority. A selector in the
    validated Tool input chooses an exact identity. Selector-free requirements
    are valid only when the Project exposes one unambiguous resource of that
    kind (for example one logical Music Library or one Workspace root).
    """

    discovered_by_kind: dict[str, list[ProjectResourceDescriptor]] = {}
    for descriptor in discovered:
        discovered_by_kind.setdefault(descriptor.kind, []).append(descriptor)
    explicit_by_kind: dict[str, list[ResourceScopeRef]] = {}
    for ref in explicit_authority:
        explicit_by_kind.setdefault(ref.kind, []).append(ref)

    bound: list[ResourceScopeRef] = []
    artifact_authority = artifact_authority or {}
    for requirement in tool.execution.required_resources:
        candidates = discovered_by_kind.get(requirement.kind, [])
        explicit = explicit_by_kind.get(requirement.kind, [])
        selected_id = (
            str(authorized_input.get(requirement.selector_field) or "").strip()
            if requirement.selector_field is not None
            else ""
        )
        if requirement.artifact_selector_field is not None:
            artifact_refs = tuple(
                ref
                for ref in artifact_authority.get(
                    requirement.artifact_selector_field,
                    (),
                )
                if ref.kind == requirement.kind
            )
            if len(artifact_refs) != 1:
                raise ToolInputError(
                    f"The referenced Artifact does not bind exactly one {requirement.kind} resource."
                )
            bound.append(artifact_refs[0])
            continue
        if selected_id:
            selected_descriptor = next(
                (candidate for candidate in candidates if candidate.id == selected_id),
                None,
            )
            if selected_descriptor is not None:
                bound.append(selected_descriptor.to_scope_ref())
                continue
            raise ToolInputError(
                f"Project resource {requirement.kind}:{selected_id} is unavailable."
            )

        # Explicit Input authority may disambiguate identity, but it can never
        # substitute for current Project membership or its canonical version.
        if len(explicit) == 1:
            current = next(
                (candidate for candidate in candidates if candidate.id == explicit[0].id),
                None,
            )
            if current is None:
                raise ToolInputError(
                    f"Project resource {requirement.kind}:{explicit[0].id} is unavailable."
                )
            bound.append(current.to_scope_ref())
            continue
        if len(candidates) == 1:
            bound.append(candidates[0].to_scope_ref())
            continue
        if not candidates:
            raise ToolInputError(
                f"This Project has no available {requirement.kind} resource."
            )
        if requirement.selector_field is None:
            raise ToolInputError(
                f"Tool {tool.name} cannot choose among multiple {requirement.kind} resources."
            )
        raise ToolInputError(
            f"{requirement.selector_field} is required because this Project has multiple "
            f"{requirement.kind} resources."
        )

    return tuple(bound)
