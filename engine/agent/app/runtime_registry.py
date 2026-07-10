"""Process-local graph runtime contexts.

LangGraph persists ``configurable`` values with checkpoints. Runtime objects
and resolved secrets live here instead, indexed by an opaque runtime id.
"""
from __future__ import annotations

from dataclasses import replace
from threading import RLock
from typing import TYPE_CHECKING
from uuid import uuid4

from engine.errors import DBFoxError

if TYPE_CHECKING:
    from engine.agent.graph.context import GraphRuntimeContext


class GraphRuntimeRegistry:
    def __init__(self) -> None:
        self._contexts: dict[str, GraphRuntimeContext] = {}
        self._lock = RLock()

    def register(self, context: GraphRuntimeContext) -> GraphRuntimeContext:
        runtime_id = f"runtime_{uuid4().hex}"
        registered = replace(context, runtime_id=runtime_id)
        with self._lock:
            self._contexts[runtime_id] = registered
        return registered

    def get(self, runtime_id: str) -> GraphRuntimeContext:
        with self._lock:
            context = self._contexts.get(runtime_id)
        if context is None:
            raise DBFoxError(
                "Graph runtime context is no longer available.",
                code="GRAPH_RUNTIME_CONTEXT_NOT_FOUND",
            )
        return context

    def discard(self, runtime_id: str) -> None:
        with self._lock:
            self._contexts.pop(runtime_id, None)


_GRAPH_RUNTIME_REGISTRY = GraphRuntimeRegistry()


def get_graph_runtime_registry() -> GraphRuntimeRegistry:
    return _GRAPH_RUNTIME_REGISTRY
