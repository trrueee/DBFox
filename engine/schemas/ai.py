from pydantic import BaseModel

class SQLGenerateRequest(BaseModel):
    datasource_id: str
    question: str
    api_key: str | None = None
    api_base: str | None = None
    model_name: str | None = None
    optimize_rag: bool = False


class SchemaAlterationRequest(BaseModel):
    datasource_id: str
    instruction: str
    api_key: str | None = None
    api_base: str | None = None
    model: str | None = None


class GoldenSQLCreateRequest(BaseModel):
    datasource_id: str
    question: str
    golden_sql: str


class BenchmarkRequest(BaseModel):
    datasource_id: str
    api_key: str | None = None
    api_base: str | None = None
    model_name: str | None = None
    optimize_rag: bool = False
