from pydantic import BaseModel, EmailStr, Field

from app.schemas.user import UserProfile


class InitDataRequest(BaseModel):
    init_data: str = Field(..., min_length=1)


class EmailRegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    first_name: str | None = Field(default=None, max_length=255)


class EmailLoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class AuthResponse(TokenResponse):
    user: UserProfile
