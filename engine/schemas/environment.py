from pydantic import BaseModel

class EnvironmentCreateRequest(BaseModel):
    project_id: str
    name: str = "Local MySQL"
    mysql_version: str = "8.0"
    seed_demo: bool = True

class DemoStartRequest(BaseModel):
    project_id: str | None = None
