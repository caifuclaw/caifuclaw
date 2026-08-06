from pydantic import BaseModel, Field


class TablePreferenceDto(BaseModel):
    id: int | None = None
    table_key: str
    config_json: dict | None = None
    created_at: str | None = None
    updated_at: str | None = None


class TablePreferenceUpsertRequest(BaseModel):
    config_json: dict = Field(default_factory=dict)
