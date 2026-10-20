"""验证 LLM 标准响应、工具调用协议和 Mock 模型。"""

import pytest
from pydantic import ValidationError

from app.agent.llm_adapter import (
    LLMAdapter,
    LLMMessage,
    LLMResponse,
    LLMUsage,
)
from app.agent.mock_llm import MockLLMAdapter
from app.agent.tool_schemas import ToolCall


def make_tool_response():
    """创建包含合法工具调用的模拟响应。"""

    return LLMResponse(
        response_type="tool_calls",
        tool_calls=[
            ToolCall(
                call_id="call_001",
                name="search_chunks",
                arguments={"query": "spectrogram"},
            )
        ],
        provider="mock",
        model="mock-function-calling",
        usage=LLMUsage(
            input_tokens=20,
            output_tokens=10,
            total_tokens=30,
        ),
    )


def test_mock_llm_returns_tool_call():
    """Mock 可以返回模型提出的工具调用。"""

    adapter = MockLLMAdapter([make_tool_response()])

    response = adapter.generate(
        [LLMMessage(role="user", content="Find spectrogram papers")],
        tools=[],
    )

    assert isinstance(adapter, LLMAdapter)
    assert response.response_type == "tool_calls"
    assert response.tool_calls[0].name == "search_chunks"


def test_mock_llm_records_messages_and_tools():
    """Mock 必须保留实际收到的调用参数。"""

    adapter = MockLLMAdapter([make_tool_response()])

    messages = [
        LLMMessage(role="user", content="Find papers"),
    ]

    tools = [{
        "type": "function",
        "name": "search_chunks",
        "parameters": {},
    }]

    adapter.generate(messages, tools)

    assert adapter.calls[0]["messages"] == messages
    assert adapter.calls[0]["tools"] == tools


def test_mock_llm_supports_final_answer():
    """Mock 可以返回最终文本回答。"""

    adapter = MockLLMAdapter([
        LLMResponse(
            response_type="final_answer",
            content="The paper discusses spectrogram detection.",
            provider="mock",
            model="mock-function-calling",
        )
    ])

    response = adapter.generate(
        [LLMMessage(role="user", content="Summarize")],
        tools=[],
    )

    assert response.is_final
    assert response.content is not None


def test_mock_llm_rejects_exhausted_responses():
    """预设响应耗尽时不得自行编造模型输出。"""

    adapter = MockLLMAdapter([])

    with pytest.raises(RuntimeError, match="exhausted"):
        adapter.generate([], tools=[])


def test_empty_tool_calls_response_is_invalid():
    """工具调用状态必须包含实际工具调用。"""

    with pytest.raises(ValidationError):
        LLMResponse(
            response_type="tool_calls",
            tool_calls=[],
            provider="mock",
            model="mock-function-calling",
        )


def test_final_answer_with_tool_calls_is_invalid():
    """最终回答不能同时携带待执行工具。"""

    with pytest.raises(ValidationError):
        LLMResponse(
            response_type="final_answer",
            content="Done",
            tool_calls=[
                ToolCall(
                    call_id="call_001",
                    name="search_chunks",
                    arguments={"query": "graph"},
                )
            ],
            provider="mock",
            model="mock-function-calling",
        )


def test_negative_token_usage_is_rejected():
    """模型用量不能出现负数。"""

    with pytest.raises(ValidationError):
        LLMUsage(input_tokens=-1)