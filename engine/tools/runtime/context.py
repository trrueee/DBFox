from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping

from pydantic import BaseModel, ConfigDict, Field


class ToolRunContext(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    thread_id: str = ""
    datasource_id: str = ""
    db_dialect: str = "mysql"
    read_only: bool = True
    state: Mapping[str, Any] = Field(default_factory=dict)
    db_session: Any | None = Field(default=None, exclude=True)
    request: Any | None = Field(default=None, exclude=True)

    @classmethod
    def from_projection(
        cls,
        *,
        state: dict[str, Any],
        request: Any | None,
        db: Any | None,
        read_only: bool,
        db_dialect: str = "mysql",
    ) -> "ToolRunContext":
        datasource_id = getattr(request, "datasource_id", "") if request is not None else ""
        thread_id = ""
        if state.get("thread_id") is not None:
            thread_id = str(state.get("thread_id"))
        elif state.get("session_id") is not None:
            thread_id = str(state.get("session_id"))
        return cls(
            thread_id=thread_id,
            datasource_id=datasource_id,
            db_dialect=db_dialect,
            read_only=read_only,
            state=MappingProxyType(dict(state)),
            db_session=db,
            request=request,
        )


@dataclass(frozen=True)
class ToolContext:
    """Read-only adapter context for existing low-level tool functions."""

    db: Any
    request: Any
    state_view: Mapping[str, Any] = field(default_factory=dict)
    runtime: ToolRunContext = field(default_factory=ToolRunContext)
