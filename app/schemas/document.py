"""文档 API 的 Pydantic 请求与响应模型。"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class DocumentCreate(BaseModel):
    """创建文档元数据的请求体。

    API 当前只允许客户端提交标题和文件名，额外字段会被拒绝，
    以避免调用方误以为可以直接写入服务端管理字段。
    """

    model_config = ConfigDict(extra="forbid")

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
    """文档元数据响应体。

    `from_attributes=True` 允许直接从 SQLAlchemy ORM 对象序列化响应。
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    filename: str
    created_at: datetime
