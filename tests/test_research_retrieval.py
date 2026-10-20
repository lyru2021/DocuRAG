"""验证 LangGraph 多任务检索、共享预算及证据合并。"""

from app.agent.research_graph import (
    build_research_graph,
    initial_research_state,
)
from app.agent.tool_executor import ToolExecutor
from app.agent.tool_registry import RegisteredTool, ToolRegistry
from app.agent.tool_schemas import SearchChunksArgs


def make_evidence(document_id: int):
    """创建可追踪的测试候选证据。"""

    return {
        "document_id": document_id,
        "chunk_id": document_id + 100,
        "title": f"Paper {document_id}",
        "page_start": 1,
        "page_end": 1,
        "content": "Deepfake detection uses acoustic features.",
    }


def make_executor(handler, *, max_calls=5):
    """建立仅包含受控检索工具的测试执行器。"""

    registry = ToolRegistry()

    registry.register(
        RegisteredTool(
            name="search_chunks",
            description="Search stored paper text",
            args_model=SearchChunksArgs,
            handler=handler,
        )
    )

    return ToolExecutor(
        registry,
        max_calls=max_calls,
    )


QUESTION = (
    "Compare document 31 and document 32 "
    "for deepfake detection"
)


def test_retrieves_two_papers():
    """跨论文任务至少执行两次独立检索。"""

    searched = []

    def handler(args):
        searched.append(args.document_id)
        return [make_evidence(args.document_id)]

    executor = make_executor(handler)

    graph = build_research_graph(
        executor=executor,
        enable_supplement=False,
    )

    result = graph.invoke(
        initial_research_state(QUESTION)
    )

    assert searched == [31, 32]
    assert result["tool_calls"] == 2

    assert {
        item["document_id"]
        for item in result["evidence"]
    } == {31, 32}


def test_retrieval_uses_shared_call_budget():
    """全部论文检索共用一次请求的调用预算。"""

    executor = make_executor(
        lambda args: [make_evidence(args.document_id)],
        max_calls=1,
    )

    graph = build_research_graph(
        executor=executor,
        enable_supplement=False,
    )

    result = graph.invoke(
        initial_research_state(QUESTION)
    )

    assert result["tool_calls"] == 1
    assert len(result["evidence"]) == 1

    assert any(
        step["detail"].endswith("limit_exceeded")
        for step in result["steps"]
    )


def test_failed_tool_does_not_block_other_paper():
    """一篇论文检索失败，不影响其他论文。"""

    def handler(args):
        """模拟论文31检索失败，论文32正常返回。"""

        if args.document_id == 31:
            raise RuntimeError("simulated database error")

        return [make_evidence(args.document_id)]

    executor = make_executor(handler)

    # 本测试只验证初始检索的故障隔离，不执行补充检索。
    result = build_research_graph(
        executor=executor,
        enable_supplement=False,
    ).invoke(
        initial_research_state(QUESTION)
    )

    # 两篇论文各执行一次初始检索。
    assert result["tool_calls"] == 2

    # 论文31失败，论文32的证据仍然保留。
    assert {
        item["document_id"]
        for item in result["evidence"]
    } == {32}

    # 确认工作流记录了失败。
    assert any(
        step["status"] == "failed"
        for step in result["steps"]
    )

    # 关闭补检后，不应执行额外工具调用。
    assert result["supplementary_searches"] == 0

def test_duplicate_evidence_is_deduplicated():
    """重复数据库证据只保留一份。"""

    def handler(args):
        evidence = make_evidence(args.document_id)
        return [evidence, evidence]

    executor = make_executor(handler)

    result = build_research_graph(executor).invoke(
        initial_research_state(QUESTION)
    )

    assert len(result["evidence"]) == 2


def test_unknown_tool_is_not_executed():
    """注册表不允许执行未授权的工具名称。"""

    executor = make_executor(
        lambda args: [make_evidence(args.document_id)]
    )

    unknown = executor.execute(
        __import__(
            "app.agent.tool_schemas",
            fromlist=["ToolCall"],
        ).ToolCall(
            call_id="unknown_1",
            name="execute_python",
            arguments={"code": "print(1)"},
        )
    )

    assert unknown.status == "unknown_tool"
    assert executor.call_count == 1


def test_graph_runs_retrieval_only_for_valid_plan():
    """规划失败不得触发数据库工具执行。"""

    calls = []

    executor = make_executor(
        lambda args: calls.append(args) or []
    )

    result = build_research_graph(executor).invoke(
        initial_research_state(
            "Compare unknown papers"
        )
    )

    assert result["status"] == "insufficient_evidence"
    assert result["tool_calls"] == 0
    assert calls == []