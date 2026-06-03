from pydantic import BaseModel, EmailStr, Field

from app.schemas.user import UserProfile


class InitDataRequest(BaseModel):
    init_data: str = Field(..., min_length=1)


class BindMaxCompleteRequest(BaseModel):
    bind_token: str = Field(..., min_length=8, max_length=128)
    init_data: str = Field(..., min_length=1)


class BindMaxStartResponse(BaseModel):
    bind_token: str
    expires_in: int = 900


class EmailRegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    first_name: str | None = Field(default=None, max_length=255)


class EmailLoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1, max_length=128)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=1, max_length=128)
    new_password: str = Field(..., min_length=8, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class AuthResponse(TokenResponse):
    user: UserProfile


class SessionStatus(BaseModel):
    authenticated: bool
    is_guest: bool = False
    searches_today: int = 0
    searches_limit: int = 5
    pro_price_rub: int = 299
    user: UserProfile | None = None
