from pydantic import BaseModel, Field

from app.schemas.user import UserProfile


class InitDataRequest(BaseModel):
    init_data: str = Field(..., min_length=1)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class AuthResponse(TokenResponse):
    user: UserProfile
