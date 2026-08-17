from __future__ import annotations

from types import MappingProxyType
from typing import Any, Callable, Mapping, Protocol, cast

from pydantic import BaseModel, ConfigDict, Field

from engine.tools.runtime.attempt import ResourceScopeRef
from sqlalchemy.orm import Session


class ToolInvocationRequest(Protocol):
    datasource_id: str
    datasource_generation: int
    question: str
    session_id: str
    run_id: str
    execution_id: str

class ToolRunContext(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    thread_id: str = ""
    datasource_id: str = ""
    db_dialect: str = "mysql"
    idempotency_key: str
    raw_input: Mapping[str, Any] = Field(default_factory=dict)
    db_session: Any | None = Field(default=None, exclude=True)
    request: Any | None = Field(default=None, exclude=True)
    cancellation_probe: Callable[[], bool] | None = Field(default=None, exclude=True)
    deadline: float | None = Field(default=None, exclude=True)
    execution_authority: Any | None = Field(default=None, exclude=True)
    scope_refs: tuple[ResourceScopeRef, ...] = ()
    resources: Mapping[str, Any] = Field(default_factory=dict, exclude=True)

    def is_cancelled(self) -> bool:
        return bool(self.cancellation_probe and self.cancellation_probe())

    def require_resource(self, kind: str) -> Any:
        if kind not in self.resources:
            raise RuntimeError(f"This tool requires the {kind!r} execution resource")
        return self.resources[kind]

    def scope(self, kind: str) -> ResourceScopeRef | None:
        return next(
            (ref for ref in self.scope_refs if ref.kind == kind),
            None,
        )

    def require_database(self) -> Session:
        if self.db_session is None:
            raise RuntimeError("This tool requires a database session")
        return cast(Session, self.db_session)

    def require_request(self) -> ToolInvocationRequest:
        if self.request is None:
            raise RuntimeError("This tool requires an agent invocation request")
        return cast(ToolInvocationRequest, self.request)

    @classmethod
    def for_invocation(
        cls,
        *,
        request: Any | None,
        db: Any | None,
        idempotency_key: str,
        db_dialect: str = "mysql",
        raw_input: dict[str, Any] | None = None,
        cancellation_probe: Callable[[], bool] | None = None,
        deadline: float | None = None,
        execution_authority: Any | None = None,
        scope_refs: tuple[ResourceScopeRef, ...] | None = None,
        resources: Mapping[str, Any] | None = None,
    ) -> "ToolRunContext":
        datasource_id = getattr(request, "datasource_id", "") if request is not None else ""
        thread_id = str(getattr(request, "session_id", "") or "")
        return cls(
            thread_id=thread_id,
            datasource_id=datasource_id,
            db_dialect=db_dialect,
            idempotency_key=idempotency_key,
            raw_input=MappingProxyType(dict(raw_input or {})),
            db_session=db,
            request=request,
            cancellation_probe=cancellation_probe,
            deadline=deadline,
            execution_authority=execution_authority,
            scope_refs=scope_refs or (),
            resources=dict(resources or {}),
        )


