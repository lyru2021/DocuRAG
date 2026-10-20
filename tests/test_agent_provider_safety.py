"""验证 Provider 非正常输出和过量工具调用的安全处理。"""

from types import SimpleNamespace

import pytest

from app.agent.llm_adapter import LLMResponse
from app.agent.llm_errors import (
    LLMIncompleteError,
    LLMProtocolError,
    LLMRefusalError,
)
from app.agent.openai_adapter import OpenAIAdapter
from app.agent.tool_schemas import ToolCall

from tests.test_research_agent import (
    build_agent,
    final_response,
)


class FakeResponses:
    """模拟 Responses API 返回不同状态。"""

    def __init__(self, response):
        self.response = response

    def create(self, **kwargs):
        return self.response


def make_openai_response(
    *,
    status="completed",
    output=None,
    output_text="Done",
):
    """构造完全不联网的 SDK 响应。"""

    return SimpleNamespace(
        status=status,
        output=output if output is not None else [],
        output_text=output_text,
        usage=None,
    )


def make_adapter(response):
    """创建注入虚拟 SDK Client 的 Provider Adapter。"""

    client = SimpleNamespace(
        responses=FakeResponses(response)
    )

    return OpenAIAdapter(
        model="mock-model",
        client=client,
    )


def test_incomplete_response_is_rejected():
    """未完成响应不能伪装成最终回答。"""

    adapter = make_adapter(
        make_openai_response(status="incomplete")
    )

    with pytest.raises(LLMIncompleteError):
        adapter.generate([], tools=[])


def test_failed_response_is_rejected():
    """失败响应必须返回协议错误。"""

    adapter = make_adapter(
        make_openai_response(status="failed")
    )

    with pytest.raises(LLMProtocolError):
        adapter.generate([], tools=[])


def test_refusal_response_is_rejected():
    """结构化拒绝信息不能作为普通回答。"""

    adapter = make_adapter(
        make_openai_response(
            output=[
                SimpleNamespace(
                    type="message",
                    content=[
                        SimpleNamespace(
                            type="refusal",
                            refusal="I cannot help.",
                        )
                    ],
                )
            ]
        )
    )

    with pytest.raises(LLMRefusalError):
        adapter.generate([], tools=[])


def test_completed_response_still_works():
    """正常完成的文本响应不能被误拒绝。"""

    adapter = make_adapter(
        make_openai_response(
            status="completed",
            output_text="Evidence found.",
        )
    )

    result = adapter.generate([], tools=[])

    assert result.is_final
    assert result.content == "Evidence found."


def test_tool_batch_limit_prevents_execution():
    """模型一次返回过多工具时，不执行任何 Handler。"""

    calls = [
        ToolCall(
            call_id=f"call_{i}",
            name="search_chunks",
            arguments={"query": "graph"},
        )
        for i in range(6)
    ]

    response = LLMResponse(
        response_type="tool_calls",
        tool_calls=calls,
        provider="mock",
        model="mock-function-calling",
    )

    agent, _ = build_agent([response])

    result = agent.run("Find papers")

    assert result.status == "tool_batch_limit_exceeded"
    assert result.tool_calls == 0
    assert result.tool_results == []