"""验证工具执行器的白名单、校验、预算和输出限制。"""

from app.agent.tool_executor import ToolExecutor
from app.agent.tool_registry import RegisteredTool, ToolRegistry
from app.agent.tool_schemas import SearchChunksArgs, ToolCall


def build_executor(
    handler,
    *,
    max_calls=5,
    max_output_chars=10000,
):
    """创建仅含受控测试工具的执行器。"""

    registry = ToolRegistry()

    registry.register(
        RegisteredTool(
            name="search_chunks",
            description="Search stored chunks",
            args_model=SearchChunksArgs,
            handler=handler,
        )
    )

    return ToolExecutor(
        registry,
        max_calls=max_calls,
        max_output_chars=max_output_chars,
    )


def make_call(
    call_id="call_1",
    name="search_chunks",
    arguments=None,
):
    """构造一次模型提出的工具调用。"""

    if arguments is None:
        arguments = {"query": "spectrogram"}

    return ToolCall(
        call_id=call_id,
        name=name,
        arguments=arguments,
    )


def test_valid_tool_call_executes_handler():
    """合法参数应进入已注册 Handler。"""

    calls = []

    executor = build_executor(
        lambda args: calls.append(args.query) or [
            {"document_id": 31, "content": "spectrogram"}
        ]
    )

    result = executor.execute(make_call())

    assert result.status == "success"
    assert result.output[0]["document_id"] == 31
    assert result.elapsed_ms >= 0
    assert calls == ["spectrogram"]


def test_unknown_tool_is_rejected():
    """不存在的工具不得执行。"""

    calls = []

    executor = build_executor(
        lambda args: calls.append(args)
    )

    result = executor.execute(
        make_call(name="execute_python")
    )

    assert result.status == "unknown_tool"
    assert result.output is None
    assert calls == []


def test_invalid_arguments_do_not_execute_handler():
    """参数不符合 Schema 时，Handler 不得执行。"""

    calls = []

    executor = build_executor(
        lambda args: calls.append(args)
    )

    result = executor.execute(
        make_call(
            arguments={
                "query": "graph",
                "shell_command": "rm -rf /",
            }
        )
    )

    assert result.status == "invalid_arguments"
    assert calls == []


def test_tool_call_limit_is_enforced():
    """超过每轮调用上限后不再执行。"""

    calls = []

    executor = build_executor(
        lambda args: calls.append(args.query) or [],
        max_calls=2,
    )

    assert executor.execute(
        make_call(call_id="1")
    ).status == "success"

    assert executor.execute(
        make_call(call_id="2")
    ).status == "success"

    assert executor.execute(
        make_call(call_id="3")
    ).status == "limit_exceeded"

    assert calls == ["spectrogram", "spectrogram"]
    assert executor.call_count == 2


def test_unknown_tool_consumes_call_budget():
    """非法工具调用也必须消耗预算。"""

    executor = build_executor(
        lambda args: [],
        max_calls=1,
    )

    first = executor.execute(
        make_call(call_id="1", name="run_shell")
    )
    second = executor.execute(
        make_call(call_id="2")
    )

    assert first.status == "unknown_tool"
    assert second.status == "limit_exceeded"


def test_handler_exception_is_reported():
    """Handler 故障不能伪装成成功。"""

    def fail(args):
        raise RuntimeError("database error")

    executor = build_executor(fail)

    result = executor.execute(make_call())

    assert result.status == "execution_error"
    assert result.error_type == "RuntimeError"
    assert result.output is None


def test_oversized_output_is_rejected():
    """超过输出长度限制时返回明确错误。"""

    executor = build_executor(
        lambda args: [{"content": "X" * 1000}],
        max_output_chars=100,
    )

    result = executor.execute(make_call())

    assert result.status == "output_too_large"
    assert result.output is None


def test_pydantic_output_is_serializable():
    """允许 Handler 返回标准 Pydantic 数据对象。"""

    from app.schemas.search import SearchResult

    executor = build_executor(
        lambda args: [
            SearchResult(
                document_id=31,
                title="Deepfake Detection",
                retrieval_source="metadata",
            )
        ]
    )

    result = executor.execute(make_call())

    assert result.status == "success"
    assert result.output[0]["document_id"] == 31
    assert result.output[0]["retrieval_source"] == "metadata"


def test_duplicate_call_id_is_rejected():
    """相同 call_id 不得重复执行工具。"""

    calls = []

    executor = build_executor(
        lambda args: calls.append(args.query) or []
    )

    first = executor.execute(
        make_call(call_id="same")
    )
    second = executor.execute(
        make_call(call_id="same")
    )

    assert first.status == "success"
    assert second.status == "duplicate_call_id"
    assert calls == ["spectrogram"]
    assert executor.call_count == 1


def test_duplicate_call_id_with_different_arguments_is_rejected():
    """改变参数也不能重用已使用的调用 ID。"""

    calls = []

    executor = build_executor(
        lambda args: calls.append(args.query) or []
    )

    executor.execute(
        make_call(
            call_id="same",
            arguments={"query": "graph"},
        )
    )

    result = executor.execute(
        make_call(
            call_id="same",
            arguments={"query": "fraud"},
        )
    )

    assert result.status == "duplicate_call_id"
    assert calls == ["graph"]


def test_invalid_call_id_cannot_be_reused():
    """首次非法工具调用的 ID 也不能重新使用。"""

    executor = build_executor(
        lambda args: []
    )

    first = executor.execute(
        make_call(
            call_id="same",
            name="execute_python",
        )
    )

    second = executor.execute(
        make_call(
            call_id="same",
            name="search_chunks",
        )
    )

    assert first.status == "unknown_tool"
    assert second.status == "duplicate_call_id"