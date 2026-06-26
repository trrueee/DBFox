from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

SQL_IDENTIFIER_PATTERN = r"^[A-Za-z_][A-Za-z0-9_]*$"
SQL_IDENTIFIER = Annotated[str, Field(min_length=1, max_length=128, pattern=SQL_IDENTIFIER_PATTERN)]


class TableDesignColumnRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: SQL_IDENTIFIER
    type: str = Field(min_length=1, max_length=128)
    nullable: bool = True
    default_value: str | None = Field(default=None, max_length=512)
    primary_key: bool = False
    auto_increment: bool = False
    comment: str | None = Field(default=None, max_length=1024)


class TableDesignIndexRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: SQL_IDENTIFIER | None = None
    columns: list[SQL_IDENTIFIER] = Field(min_length=1, max_length=16)
    unique: bool = False


class TableDesignDDLRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    table_name: SQL_IDENTIFIER
    table_comment: str | None = Field(default=None, max_length=1024)
    engine: str = Field(default="InnoDB", min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_]+$")
    charset: str = Field(default="utf8mb4", min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_]+$")
    collation: str = Field(default="utf8mb4_0900_ai_ci", min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_]+$")
    columns: list[TableDesignColumnRequest] = Field(min_length=1, max_length=200)
    indexes: list[TableDesignIndexRequest] = Field(default_factory=list, max_length=64)


class TableDesignExecuteRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    datasource_id: str = Field(min_length=1, max_length=128)
    ddl: str = Field(min_length=1, max_length=200_000)
    confirm_token: str | None = Field(default=None, max_length=256)
    confirm_text: str | None = Field(default=None, max_length=512)


class TableDesignDraftSaveRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    project_id: str = Field(min_length=1, max_length=128)
    draft_id: str | None = Field(default=None, max_length=128)
    table_name: SQL_IDENTIFIER
    table_comment: str | None = Field(default=None, max_length=1024)
    columns: list[TableDesignColumnRequest] = Field(min_length=1, max_length=200)
    indexes: list[TableDesignIndexRequest] = Field(default_factory=list, max_length=64)


class TableDesignAIRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    prompt: str = Field(min_length=1, max_length=20_000)
    api_key: str | None = Field(default=None, max_length=4096)
    api_base: str | None = Field(default=None, max_length=2048)
    model_name: str | None = Field(default=None, max_length=128)


class TestDataGenerateRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    datasource_id: str = Field(min_length=1, max_length=128)
    table_name: str = Field(min_length=1, max_length=256)
    row_count: int = Field(default=10, ge=1, le=10_000)
    language: Literal["zh", "en"] = "zh"
    confirm_token: str | None = Field(default=None, max_length=256)
    confirm_text: str | None = Field(default=None, max_length=512)
