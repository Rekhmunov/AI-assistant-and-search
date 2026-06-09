from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.thread import MessageOut, ThreadListItem


class AgentMessageIn(BaseModel):
    text: str = Field(..., min_length=1, max_length=4000)


class AgentThreadCreateOut(BaseModel):
    thread: ThreadListItem
    welcome_message: MessageOut


class AgentMessageOut(BaseModel):
    user_message: MessageOut
    assistant_message: MessageOut
    agent_status: str
    agent_role: str | None = None
