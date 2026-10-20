"""不发送真实网络请求，验证 Responses API 协议转换。"""

import json
from types import SimpleNamespace

from app.agent.llm_adapter import LLMMessage
from app.agent.openai_adapter import OpenAIAdapter


class FakeResponses:
    """模拟 SDK 的 responses.create 方法。"""

    def __init__(self, output, output_text=""):
        self.output = output
        self.output_text = output_text
        self.last_request = None

    def create(self, **kwargs):
        self.last_request = kwargs

        return SimpleNamespace(
            output=self.output,
            output_text=self.output_text,
            usage=SimpleNamespace(
                input_tokens=20,
                output_tokens=10,
                total_tokens=30,
            ),
        )


def make_adapter(fake_responses):
    """构造完全不连接网络的测试 Adapter。"""

    client = SimpleNamespace(responses=fake_responses)

    return OpenAIAdapter(
        model="mock-openai-model",
        client=client,
    )


def test_adapter_parses_function_call():
    """真实 Provider 格式的工具调用应解析为 ToolCall。"""

    fake = FakeResponses([
        SimpleNamespace(
            type="function_call",
            call_id="call_1",
            name="search_chunks",
            arguments='{"query":"spectrogram"}',
        )
    ])

    adapter = make_adapter(fake)

    result = adapter.generate(
        messages=[
            LLMMessage(role="user", content="Find papers")
        ],
        tools=[],
    )

    assert result.response_type == "tool_calls"
    assert result.tool_calls[0].name == "search_chunks"
    assert result.tool_calls[0].arguments == {
        "query": "spectrogram"
    }
    assert result.usage.total_tokens == 30


def test_adapter_parses_final_answer():
    """普通文本输出应转换为统一最终回答。"""

    fake = FakeResponses(
        output=[],
        output_text="The paper uses spectrogram features.",
    )

    adapter = make_adapter(fake)

    result = adapter.generate(
        [LLMMessage(role="user", content="Summarize")],
        tools=[],
    )

    assert result.is_final
    assert result.content == "The paper uses spectrogram features."


def test_adapter_preserves_call_id():
    """工具响应必须关联原始模型工具调用。"""

    fake = FakeResponses([], output_text="Done")
    adapter = make_adapter(fake)

    messages = [
        LLMMessage(
            role="assistant",
            content=json.dumps([
                {
                    "call_id": "call_123",
                    "name": "search_chunks",
                    "arguments": {"query": "graph"},
                }
            ]),
        ),
        LLMMessage(
            role="tool",
            tool_call_id="call_123",
            content='{"status":"success","output":[]}',
        ),
    ]

    adapter.generate(messages, tools=[])

    converted = fake.last_request["input"]

    assert converted[0]["type"] == "function_call"
    assert converted[0]["call_id"] == "call_123"

    assert converted[1]["type"] == "function_call_output"
    assert converted[1]["call_id"] == "call_123"


def test_invalid_function_arguments_are_not_executed():
    """模型生成的非法 JSON 不得直接执行。"""

    fake = FakeResponses([
        SimpleNamespace(
            type="function_call",
            call_id="call_bad",
            name="search_chunks",
            arguments="{invalid json",
        )
    ])

    adapter = make_adapter(fake)

    result = adapter.generate(
        [LLMMessage(role="user", content="Search")],
        tools=[],
    )

    assert result.response_type == "tool_calls"
    assert "_invalid_json" in result.tool_calls[0].arguments