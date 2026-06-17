"""Handler registry — maps handler names to callables for dynamic tool resolution.

When a tool spec is loaded from YAML, it references a handler by name
(e.g. "schema_build_context").  The HandlerRegistry resolves that name
to the actual Python callable + optional base_tool instance.

Engine code populates this registry at startup.  User plugins can register
their own handlers for custom tools.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from engine.agent_core.types import ToolObservation
from engine.agent_core.tool_registry import ToolContext

logger = logging.getLogger("dbfox.dbfox_agent.handler_registry")

ToolHandlerFn = Callable[["ToolContext", dict[str, Any]], ToolObservation]


class HandlerRegistry:
    """Maps handler names → (callable, base_tool_instance).

    This is the bridge between declarative YAML tool specs and executable
    Python handlers.  Tool specs reference handlers by name; the registry
    resolves them at load time.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, ToolHandlerFn] = {}
        self._base_tools: dict[str, Any] = {}

    # ── Registration ────────────────────────────────────────────────────────────

    def register(
        self,
        name: str,
        handler: ToolHandlerFn,
        *,
        base_tool: Any = None,
    ) -> "HandlerRegistry":
        """Register a handler function and optional base_tool instance.

        Raises ValueError if the handler name is already registered
        (use force=True to override).
        """
        if name in self._handlers:
            raise ValueError(
                f"Handler '{name}' is already registered. "
                f"Use force_register() to override."
            )
        self._handlers[name] = handler
        if base_tool is not None:
            self._base_tools[name] = base_tool
        return self

    def force_register(
        self,
        name: str,
        handler: ToolHandlerFn,
        *,
        base_tool: Any = None,
    ) -> "HandlerRegistry":
        """Register or override a handler.  Safe for hot-reload."""
        if name in self._handlers:
            logger.info("Handler '%s' overridden via force_register().", name)
        self._handlers[name] = handler
        if base_tool is not None:
            self._base_tools[name] = base_tool
        return self

    # ── Resolution ──────────────────────────────────────────────────────────────

    def resolve(self, name: str) -> ToolHandlerFn:
        """Resolve a handler name to its callable.  Raises KeyError if unknown."""
        handler = self._handlers.get(name)
        if handler is None:
            available = ", ".join(sorted(self._handlers)) or "<none>"
            raise KeyError(
                f"Unknown handler '{name}'. Available handlers: {available}"
            )
        return handler

    def resolve_base_tool(self, name: str) -> Any | None:
        """Resolve the base_tool instance for a handler, if registered."""
        return self._base_tools.get(name)

    def get(self, name: str) -> ToolHandlerFn | None:
        """Get a handler by name, or None if not found."""
        return self._handlers.get(name)

    # ── Introspection ───────────────────────────────────────────────────────────

    def list_names(self) -> list[str]:
        """Return all registered handler names."""
        return sorted(self._handlers)

    def __contains__(self, name: str) -> bool:
        return name in self._handlers

    def __len__(self) -> int:
        return len(self._handlers)

    def __repr__(self) -> str:
        return f"<HandlerRegistry handlers={len(self._handlers)}>"


# ── Module-level singleton ─────────────────────────────────────────────────────

_registry: HandlerRegistry | None = None


def get_handler_registry() -> HandlerRegistry:
    """Return the module-level HandlerRegistry singleton."""
    global _registry
    if _registry is None:
        _registry = HandlerRegistry()
    return _registry


def reset_handler_registry() -> None:
    """Reset the singleton (mainly for tests)."""
    global _registry
    _registry = None
