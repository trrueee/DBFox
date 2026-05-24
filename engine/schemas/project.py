from pydantic import BaseModel

class ProjectCreateRequest(BaseModel):
    name: str
    description: str | None = None
