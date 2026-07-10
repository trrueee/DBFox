from pydantic import BaseModel, ConfigDict

class SQLGenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    datasource_id: str
    question: str
    llm_credential_id: str | None = None
    api_base: str | None = None
    model_name: str | None = None
    optimize_rag: bool = False


class SchemaAlterationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    datasource_id: str
    instruction: str
    llm_credential_id: str | None = None
    api_base: str | None = None
    model: str | None = None


class GoldenSQLCreateRequest(BaseModel):
    datasource_id: str
    question: str
    golden_sql: str


class BenchmarkRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    datasource_id: str
    llm_credential_id: str | None = None
    api_base: str | None = None
    model_name: str | None = None
    optimize_rag: bool = False
