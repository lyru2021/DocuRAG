"""验证单轮科研 Agent 的工具调用、预算及异常处理。"""

from app.agent.llm_adapter import LLMResponse, LLMUsage
from app.agent.mock_llm import MockLLMAdapter
from app.agent.research_agent import ResearchAgent
from app.agent.tool_executor import ToolExecutor
from app.agent.tool_registry import RegisteredTool, ToolRegistry
from app.agent.tool_schemas import SearchChunksArgs, ToolCall


def tool_response(name="search_chunks", call_id="call_1"):
    """模拟一次模型发起的工具请求。"""

    return LLMResponse(
        response_type="tool_calls",
        tool_calls=[
            ToolCall(
                call_id=call_id,
                name=name,
                arguments={"query": "spectrogram"},
            )
        ],
        provider="mock",
        model="mock-function-calling",
        usage=LLMUsage(
            input_tokens=10,
            output_tokens=5,
            total_tokens=15,
        ),
    )


def final_response():
    """模拟模型根据工具结果生成回答。"""

    return LLMResponse(
        response_type="final_answer",
        content="Document 31 discusses spectrograms.",
        provider="mock",
        model="mock-function-calling",
        usage=LLMUsage(
            input_tokens=20,
            output_tokens=10,
            total_tokens=30,
        ),
    )


def build_agent(responses, max_calls=5, max_llm_calls=6):
    """创建固定工具结果的测试 Agent。"""

    registry = ToolRegistry()
    registry.register(
        RegisteredTool(
            name="search_chunks",
            description="Search paper chunks",
            args_model=SearchChunksArgs,
            handler=lambda args: [
                {
                    "document_id": 31,
                    "chunk_id": 101,
                    "page_start": 3,
                    "content": "A spectrogram is used.",
                }
            ],
        )
    )

    llm = MockLLMAdapter(responses)
    executor = ToolExecutor(
        registry,
        max_calls=max_calls,
    )

    return (
        ResearchAgent(
            llm,
            executor,
            max_llm_calls=max_llm_calls,
        ),
        llm,
    )


def test_agent_executes_tool_and_returns_final_answer():
    """工具调用后应把真实工具响应返回模型。"""

    agent, llm = build_agent([
        tool_response(),
        final_response(),
    ])

    result = agent.run("Find spectrogram evidence")

    assert result.status == "completed"
    assert result.llm_calls == 2
    assert result.tool_calls == 1
    assert result.tool_results[0].status == "success"
    assert result.answer is not None

    second_messages = llm.calls[1]["messages"]

    assert any(
        message.role == "tool"
        and message.tool_call_id == "call_1"
        for message in second_messages
    )


def test_agent_rejects_unknown_tool():
    """不存在的工具名称不能执行。"""

    agent, _ = build_agent([
        tool_response(name="execute_python"),
        final_response(),
    ])

    result = agent.run("Run Python")

    assert result.status == "completed"
    assert result.tool_results[0].status == "unknown_tool"


def test_agent_enforces_tool_limit():
    """超过工具调用预算应明确终止。"""

    agent, _ = build_agent([
        tool_response(call_id="1"),
        tool_response(call_id="2"),
    ], max_calls=1)

    result = agent.run("Search repeatedly")

    assert result.status == "tool_limit_exceeded"
    assert result.tool_calls == 1


def test_agent_enforces_llm_limit():
    """达到模型调用上限时不得无限循环。"""

    agent, _ = build_agent([
        tool_response(call_id="1"),
    ], max_llm_calls=1)

    result = agent.run("Search")

    assert result.status == "llm_limit_exceeded"
    assert result.llm_calls == 1


def test_agent_collects_token_usage():
    """汇总本轮所有模型响应的 token 数。"""

    agent, _ = build_agent([
        tool_response(),
        final_response(),
    ])

    result = agent.run("Find evidence")

    assert result.input_tokens == 30
    assert result.output_tokens == 15
    assert result.total_tokens == 45


def test_agent_handles_llm_failure():
    """模型异常不得伪装成有效回答。"""

    agent, _ = build_agent([])

    result = agent.run("Find evidence")

    assert result.status == "llm_error"
    assert result.error_type == "RuntimeError"


def test_agent_rejects_blank_question():
    """空白问题应在模型调用前拒绝。"""

    agent, llm = build_agent([final_response()])

    try:
        agent.run("   ")
    except ValueError:
        pass
    else:
        raise AssertionError("blank question was accepted")

    assert llm.calls == []

def test_agent_classifies_timeout():
    """模型超时应返回明确状态，不伪装成正常回答。"""

    class TimeoutLLM:
        provider = "mock"
        model = "timeout-mock"

        def generate(self, messages, tools):
            raise TimeoutError("model request timed out")

    agent, _ = build_agent([])
    agent.llm = TimeoutLLM()

    result = agent.run("Find evidence")

    assert result.status == "llm_timeout"
    assert result.answer is None
    assert result.tool_calls == 0
    assert result.error_type == "TimeoutError"


def test_agent_classifies_rate_limit():
    """模型限流应被正确分类。"""

    import httpx
    from openai import RateLimitError

    request = httpx.Request(
        "POST",
        "https://api.openai.com/v1/responses",
    )

    response = httpx.Response(
        429,
        request=request,
    )

    class RateLimitedLLM:
        provider = "mock"
        model = "rate-limit-mock"

        def generate(self, messages, tools):
            raise RateLimitError(
                "rate limited",
                response=response,
                body=None,
            )

    agent, _ = build_agent([])
    agent.llm = RateLimitedLLM()

    result = agent.run("Find evidence")

    assert result.status == "llm_rate_limited"
    assert result.answer is None
    assert result.tool_calls == 0


def test_agent_classifies_authentication_failure():
    """认证失败应被正确分类。"""

    import httpx
    from openai import AuthenticationError

    request = httpx.Request(
        "POST",
        "https://api.openai.com/v1/responses",
    )

    response = httpx.Response(
        401,
        request=request,
    )

    class AuthFailedLLM:
        provider = "mock"
        model = "auth-error-mock"

        def generate(self, messages, tools):
            raise AuthenticationError(
                "invalid key",
                response=response,
                body=None,
            )

    agent, _ = build_agent([])
    agent.llm = AuthFailedLLM()

    result = agent.run("Find evidence")

    assert result.status == "llm_auth_error"
    assert result.answer is None
    assert result.tool_calls == 0