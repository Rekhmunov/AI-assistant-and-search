from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.constants.attachments import MAX_ATTACHMENTS_PER_SEARCH


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    thread_id: UUID | None = None
    attachment_ids: list[UUID] | None = None
    retry_pending: bool = False

    @field_validator("query")
    @classmethod
    def strip_query(cls, v: str) -> str:
        return v.strip()

    @field_validator("attachment_ids")
    @classmethod
    def limit_attachments(cls, v: list[UUID] | None) -> list[UUID] | None:
        if v is not None and len(v) > MAX_ATTACHMENTS_PER_SEARCH:
            raise ValueError(f"Не более {MAX_ATTACHMENTS_PER_SEARCH} файлов за один запрос")
        return v
