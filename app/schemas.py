from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


# ---- 请求 ----
class UserCreate(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=6, max_length=64)


class LoginRequest(BaseModel):
    name: str
    password: str


class ChatCreate(BaseModel):
    title: str = Field(default="新会话", max_length=100)


class MessageCreate(BaseModel):
    content: str = Field(min_length=1)


# ---- 响应 ----
class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    created_at: datetime


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ChatOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    title: str
    created_at: datetime


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    chat_id: int
    role: str
    content: str
    created_at: datetime


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    chat_id: int
    type: str
    status: str
    result: str | None
    error: str | None
    created_at: datetime
    finished_at: datetime | None
