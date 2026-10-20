"""提供可重复、无需真实 API Key 的 Mock LLM。"""

from collections import deque

from app.agent.llm_adapter import (
    LLMMessage,
    LLMResponse,
)


class MockLLMAdapter:
    """按照预设顺序返回响应，并记录模型收到的输入。"""

    provider = "mock"
    model = "mock-function-calling"

    def __init__(self, responses: list[LLMResponse]):
        self._responses = deque(responses)
        self.calls: list[dict] = []

    def generate(
        self,
        messages: list[LLMMessage],
        tools: list[dict],
    ) -> LLMResponse:
        """模拟一次模型请求，不调用外部服务。"""

        self.calls.append({
            "messages": list(messages),
            "tools": list(tools),
        })

        if not self._responses:
            raise RuntimeError(
                "mock responses exhausted"
            )

        return self._responses.popleft()