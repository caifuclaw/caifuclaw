# Company: 深圳智柠网络科技有限公司
# Author: mohsen liang

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class AuthMeResponse(BaseModel):
    id: int
    username: str
    display_name: str = ""
    role_id: int | None = None
    role_code: str
    role_name: str = ""
    role_ids: list[int] = Field(default_factory=list)
    role_codes: list[str] = Field(default_factory=list)
    role_names: list[str] = Field(default_factory=list)
    menus: list[str] = Field(default_factory=list)


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str
