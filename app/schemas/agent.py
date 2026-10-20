"""定义科研 Agent HTTP 接口的请求和响应模型。"""

from typing import Literal

from pydantic import BaseModel, Field
from app.agent.evidence import AgentEvidence


class AgentQueryRequest(BaseModel):
    """单轮科研问答请求。"""

    question: str = Field(
        min_length=1,
        max_length=2000,
    )


class AgentToolRecord(BaseModel):
    """返回一次工具调用的执行信息。"""

    call_id: str
    name: str
    status: str
    elapsed_ms: float
    error_type: str | None = None


class AgentQueryResponse(BaseModel):
    """返回回答、工具执行状态及模型使用量。"""

    status: Literal[
        "completed",
        "llm_limit_exceeded",
        "tool_limit_exceeded",
        "llm_error",
        "llm_timeout",
        "llm_rate_limited",
        "llm_auth_error",
        "llm_incomplete",
        "llm_refusal",
        "llm_protocol_error",
        "tool_batch_limit_exceeded",
    ]
    answer: str | None
    llm_calls: int
    tool_calls: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    error_type: str | None = None
    tools: list[AgentToolRecord] = Field(default_factory=list)
    evidence: list[AgentEvidence] = Field(default_factory=list)