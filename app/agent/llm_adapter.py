"""定义可替换的 LLM 调用协议及标准化响应结构。"""

from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.agent.tool_schemas import ToolCall


class LLMUsage(BaseModel):
    """记录模型实际报告的 token 使用量。"""

    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)


class LLMResponse(BaseModel):
    """统一表示模型回答或工具调用请求。"""

    model_config = ConfigDict(extra="forbid")

    response_type: Literal[
        "final_answer",
        "tool_calls",
    ]

    content: str | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)

    provider: str
    model: str
    usage: LLMUsage = Field(default_factory=LLMUsage)
    latency_ms: float = Field(default=0.0, ge=0)

    @property
    def is_final(self) -> bool:
        """判断当前响应是否结束模型交互。"""

        return self.response_type == "final_answer"
    @model_validator(mode="after")
    def validate_response(self):
        """保证回答状态与模型实际输出一致。"""

        if self.response_type == "tool_calls":
            if not self.tool_calls:
                raise ValueError(
                    "tool_calls response requires at least one tool call"
                )

        if self.response_type == "final_answer":
            if self.tool_calls:
                raise ValueError(
                    "final_answer must not contain tool calls"
                )
            if self.content is None:
                raise ValueError(
                    "final_answer requires content"
                )

        return self


class LLMMessage(BaseModel):
    """表示模型对话中的一条结构化消息。"""

    model_config = ConfigDict(extra="forbid")

    role: Literal["system", "user", "assistant", "tool"]
    content: str

    tool_call_id: str | None = None


@runtime_checkable
class LLMAdapter(Protocol):
    """统一 LLM Provider 调用协议。"""

    provider: str
    model: str

    def generate(
        self,
        messages: list[LLMMessage],
        tools: list[dict],
    ) -> LLMResponse:
        """根据消息和工具描述生成模型响应。"""
        ...