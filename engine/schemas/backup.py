from pydantic import BaseModel

class BackupCreateRequest(BaseModel):
    datasource_id: str
    label: str | None = None
    allow_fallback: bool = True
