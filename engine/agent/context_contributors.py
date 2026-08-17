"""Runtime context contributor registry.

The Context Kernel owns lanes/budgets. Contributors are capability-owned and
registered here; ContextAssembler only consumes the generic tuple.
"""

from __future__ import annotations

from engine.agent.workspace_context import WorkspaceContextContributor


CONTEXT_CONTRIBUTORS = (WorkspaceContextContributor,)
