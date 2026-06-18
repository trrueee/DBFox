from __future__ import annotations


class ToolRuntimeError(Exception):
    """Base class for typed tool runtime errors."""


class ToolContractError(ToolRuntimeError):
    """Raised when a tool input or output violates its declared contract."""


class ToolRegistrationError(ToolRuntimeError):
    """Raised when tool registration is invalid."""
