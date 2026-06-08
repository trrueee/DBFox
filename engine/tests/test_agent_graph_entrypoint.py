from __future__ import annotations

from engine.agent_kernel import graph
from engine.agent_kernel.graph_standalone import build_agent_kernel_graph as standalone_builder


def test_graph_entrypoint_uses_standalone_builder() -> None:
    assert graph.build_agent_kernel_graph is standalone_builder
