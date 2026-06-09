from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Generic, Type, TypeVar

from pydantic import BaseModel, ConfigDict, Field

# Define ExecutionContext, completely separating raw SQLAlchemy Session from tools
class ExecutionContext(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    thread_id: str
    datasource_id: str
    db_dialect: str = "mysql"
    user_id: str | None = None
    read_only: bool = True
    db_session: Any = Field(default=None, exclude=True)
    api_key: str | None = None
    api_base: str | None = None
    model_name: str | None = None

    # Return a fully managed database connection, preventing tools from managing Session lifecycles
    def get_connection(self) -> Any:
        if self.db_session is not None:
            return self.db_session.connection()
        return None


I = TypeVar("I", bound=BaseModel)
O = TypeVar("O", bound=BaseModel)


class BaseTool(ABC, Generic[I, O]):
    name: str
    description: str
    input_schema: Type[I]
    output_schema: Type[O]
    requires_approval: bool = False
    risk_level: str = "safe"

    def execute(self, tool_input: I | dict[str, Any], context: ExecutionContext) -> O:
        """Container invocation entry point with schema validation."""
        # 1. Pre-execution schema validation
        if isinstance(tool_input, dict):
            validated_input = self.input_schema.model_validate(tool_input)
        else:
            validated_input = self.input_schema.model_validate(tool_input)

        # 2. Execute business logic
        raw_output = self._run(validated_input, context)

        # 3. Post-execution schema validation
        if isinstance(raw_output, dict):
            validated_output = self.output_schema.model_validate(raw_output)
        else:
            validated_output = self.output_schema.model_validate(raw_output)

        return validated_output

    @abstractmethod
    def _run(self, tool_input: I, context: ExecutionContext) -> O:
        pass
