from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class TestDataGenerateRequest(BaseModel):
    __test__ = False
    model_config = ConfigDict(str_strip_whitespace=True)

    datasource_id: str = Field(min_length=1, max_length=128)
    table_name: str = Field(min_length=1, max_length=256)
    row_count: int = Field(default=10, ge=1, le=10_000)
    language: Literal["zh", "en"] = "zh"
    confirm_token: str | None = Field(default=None, max_length=256)
    confirm_text: str | None = Field(default=None, max_length=512)
