from pydantic import BaseModel, Field

class TableDesignColumnRequest(BaseModel):
    name: str
    type: str
    nullable: bool = True
    default_value: str | None = None
    primary_key: bool = False
    auto_increment: bool = False
    comment: str | None = None


class TableDesignIndexRequest(BaseModel):
    name: str | None = None
    columns: list[str]
    unique: bool = False


class TableDesignDDLRequest(BaseModel):
    table_name: str
    table_comment: str | None = None
    engine: str = "InnoDB"
    charset: str = "utf8mb4"
    collation: str = "utf8mb4_0900_ai_ci"
    columns: list[TableDesignColumnRequest]
    indexes: list[TableDesignIndexRequest] = Field(default_factory=list)


class TableDesignExecuteRequest(BaseModel):
    datasource_id: str
    ddl: str


class TableDesignDraftSaveRequest(BaseModel):
    project_id: str
    draft_id: str | None = None
    table_name: str
    table_comment: str | None = None
    columns: list[TableDesignColumnRequest]
    indexes: list[TableDesignIndexRequest] = Field(default_factory=list)


class TableDesignAIRequest(BaseModel):
    prompt: str
    api_key: str | None = None
    api_base: str | None = None
    model_name: str | None = None


class TestDataGenerateRequest(BaseModel):
    datasource_id: str
    table_name: str
    row_count: int = 10
    language: str = "zh"
