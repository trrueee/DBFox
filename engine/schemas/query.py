from pydantic import BaseModel

class SQLValidateRequest(BaseModel):
    sql: str


class SQLExecuteRequest(BaseModel):
    datasource_id: str
    sql: str
    question: str | None = None
    execution_id: str | None = None


class SQLCancelRequest(BaseModel):
    execution_id: str


class SQLExplainRequest(BaseModel):
    datasource_id: str
    sql: str
