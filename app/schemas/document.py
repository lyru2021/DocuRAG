from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field

class DocumentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")#禁止请求中包含未定义的额外字段

    title: str = Field(
        min_length=1,
        max_length=200,
        strict=True,
    )
    filename: str = Field(
        min_length=1,
        max_length=255,
        strict=True,
    )


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True) #允许 Pydantic 从 SQLAlchemy ORM 对象的属性读取字段
    id: int
    title: str
    filename: str
    created_at: datetime