"""定义科研 Agent 工具参数及严格的输入校验规则。"""

from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)


class StrictToolArgs(BaseModel):
    """工具参数基类：拒绝未知字段。"""

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
    )


class SearchPapersArgs(StrictToolArgs):
    """按已存储的论文元数据查找文档。"""

    document_id: int | None = Field(
        default=None,
        gt=0,
    )

    title: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
    )

    doi: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
    )

    author: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
    )

    year: int | None = Field(
        default=None,
        ge=1000,
        le=2100,
    )

    limit: int = Field(default=5, ge=1, le=5)

    @model_validator(mode="after")
    def require_filter(self):
        """禁止无条件扫描整个论文库。"""

        if all(
            value is None
            for value in (
                self.document_id,
                self.title,
                self.doi,
                self.author,
                self.year,
            )
        ):
            raise ValueError(
                "at least one metadata filter is required"
            )

        return self


class SearchChunksArgs(StrictToolArgs):
    """使用受控关键词策略检索真实 Chunk。"""

    query: str = Field(
        min_length=1,
        max_length=300,
    )

    mode: Literal["literal", "fts"] = "literal"

    document_id: int | None = Field(
        default=None,
        gt=0,
    )

    limit: int = Field(default=5, ge=1, le=5)

    @model_validator(mode="after")
    def validate_query(self):
        """禁止空白检索词。"""

        if not self.query.strip():
            raise ValueError("query must not be blank")

        return self


class GetEvidenceArgs(StrictToolArgs):
    """使用数据库标识符获取指定 Chunk 的真实证据。"""

    document_id: int = Field(gt=0)
    chunk_id: int = Field(gt=0)


class ToolCall(BaseModel):
    """表示 LLM 提出的工具调用，而非已执行操作。"""

    model_config = ConfigDict(extra="forbid")

    call_id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=64)
    arguments: dict