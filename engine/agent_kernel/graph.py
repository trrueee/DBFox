from __future__ import annotations
import os
from typing import Any

def build_agent_kernel_graph(*args, **kwargs) -> Any:
    mode = os.environ.get("AGENT_KERNEL_MODE", "loop").strip().lower()
    if mode == "legacy":
        from engine.agent_kernel.graph_legacy_sql_pipeline import build_agent_kernel_graph as build_legacy
        return build_legacy(*args, **kwargs)
    else:
        from engine.agent_kernel.graph_loop import build_agent_loop_graph
        # Pop controller_node if present since Loop Kernel handles it natively
        kwargs.pop("controller_node", None)
        return build_agent_loop_graph(*args, **kwargs)

def langgraph_available() -> bool:
    import importlib.util
    return importlib.util.find_spec("langgraph") is not None
