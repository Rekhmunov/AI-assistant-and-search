from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.schemas.thread import MessageOut, ThreadListItem


class AgentMessageIn(BaseModel):
    text: str = Field(default="", max_length=4000)
    file_ids: list[UUID] = Field(default_factory=list)

    @model_validator(mode="after")
    def text_or_files(self) -> "AgentMessageIn":
        if not self.text.strip() and not self.file_ids:
            raise ValueError("text_or_files_required")
        return self


class AgentThreadCreateOut(BaseModel):
    thread: ThreadListItem
    welcome_message: MessageOut


class AgentMessageOut(BaseModel):
    user_message: MessageOut
    assistant_message: MessageOut
    agent_status: str
    agent_role: str | None = None
