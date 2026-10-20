"""验证科研 Agent 的三个工具均访问真实 PostgreSQL 记录。"""

from app.agent.paper_tools import build_paper_tool_registry
from app.agent.tool_db import make_test_tool_session
from app.agent.tool_executor import ToolExecutor
from app.agent.tool_schemas import ToolCall
from app.models.document import Chunk, Document


def create_paper(db_session):
    """创建带页码和真实原文的测试论文。"""

    content = "Dynamic graph neural networks detect fraud."

    document = Document(
        title="Graph Fraud Detection",
        filename="graph_fraud.pdf",
        parse_status="parsed",
    )
    db_session.add(document)
    db_session.flush()

    chunk = Chunk(
        document_id=document.id,
        chunk_index=0,
        content=content,
        start_char=0,
        end_char=len(content),
        page_start=3,
        page_end=3,
    )
    db_session.add(chunk)
    db_session.commit()

    return document, chunk


def run_tool(executor, name, arguments):
    """通过 ToolExecutor 执行，而不是直接调用 Handler。"""

    return executor.execute(
        ToolCall(
            call_id=f"test_{name}",
            name=name,
            arguments=arguments,
        )
    )


def test_search_papers_returns_real_document(db_session):
    """元数据检索必须返回数据库中的论文。"""

    document, _ = create_paper(db_session)
    executor = ToolExecutor(build_paper_tool_registry(make_test_tool_session(db_session)))

    result = run_tool(
        executor,
        "search_papers",
        {"document_id": document.id},
    )

    assert result.status == "success"
    assert len(result.output) == 1
    assert result.output[0]["document_id"] == document.id
    assert result.output[0]["title"] == document.title


def test_search_chunks_returns_real_evidence(db_session):
    """关键词检索必须返回真实 Chunk、正文和页码。"""

    document, chunk = create_paper(db_session)
    executor = ToolExecutor(build_paper_tool_registry(make_test_tool_session(db_session)))

    result = run_tool(
        executor,
        "search_chunks",
        {
            "query": "graph",
            "mode": "fts",
            "document_id": document.id,
        },
    )

    assert result.status == "success"
    assert len(result.output) == 1

    hit = result.output[0]

    assert hit["chunk_id"] == chunk.id
    assert hit["document_id"] == document.id
    assert hit["page_start"] == 3
    assert hit["content"] == chunk.content


def test_get_evidence_returns_exact_stored_chunk(db_session):
    """精确证据查询必须与数据库原文完全一致。"""

    document, chunk = create_paper(db_session)
    executor = ToolExecutor(build_paper_tool_registry(make_test_tool_session(db_session)))

    result = run_tool(
        executor,
        "get_evidence",
        {
            "document_id": document.id,
            "chunk_id": chunk.id,
        },
    )

    assert result.status == "success"

    evidence = result.output

    assert evidence["document_id"] == document.id
    assert evidence["chunk_id"] == chunk.id
    assert evidence["content"] == chunk.content
    assert evidence["page_start"] == 3
    assert evidence["page_end"] == 3


def test_get_evidence_rejects_wrong_document(db_session):
    """Chunk ID 正确但 Document ID 错误时必须拒绝。"""

    document, chunk = create_paper(db_session)
    executor = ToolExecutor(build_paper_tool_registry(make_test_tool_session(db_session)))

    result = run_tool(
        executor,
        "get_evidence",
        {
            "document_id": document.id + 100000,
            "chunk_id": chunk.id,
        },
    )

    assert result.status == "execution_error"
    assert result.error_type == "EvidenceNotFoundError"
    assert result.output is None


def test_get_evidence_rejects_nonexistent_chunk(db_session):
    """不存在的 Chunk 不得被伪造成证据。"""

    document, _ = create_paper(db_session)
    executor = ToolExecutor(build_paper_tool_registry(make_test_tool_session(db_session)))

    result = run_tool(
        executor,
        "get_evidence",
        {
            "document_id": document.id,
            "chunk_id": 999999999,
        },
    )

    assert result.status == "execution_error"
    assert result.error_type == "EvidenceNotFoundError"


def test_registry_exposes_only_three_paper_tools(db_session):
    """Agent 不能获得 Python 或 Shell 执行工具。"""

    registry = build_paper_tool_registry(make_test_tool_session(db_session))

    assert registry.names() == [
        "get_evidence",
        "search_chunks",
        "search_papers",
    ]


def test_registry_creation_does_not_open_session():
    """创建 Registry 时不能提前获取数据库连接。"""

    calls = []

    def forbidden_factory():
        calls.append("opened")
        raise AssertionError("database session opened too early")

    registry = build_paper_tool_registry(
        forbidden_factory
    )

    assert registry.names() == [
        "get_evidence",
        "search_chunks",
        "search_papers",
    ]
    assert calls == []


def test_each_tool_call_uses_session_context(db_session):
    """工具执行必须进入并退出受控 Session 上下文。"""

    from contextlib import contextmanager

    document, chunk = create_paper(db_session)

    events = []

    @contextmanager
    def tracked_factory():
        events.append("enter")

        with make_test_tool_session(db_session)() as db:
            yield db

        events.append("exit")

    executor = ToolExecutor(
        build_paper_tool_registry(tracked_factory)
    )

    first = run_tool(
        executor,
        "get_evidence",
        {
            "document_id": document.id,
            "chunk_id": chunk.id,
        },
    )

    second = run_tool(
        executor,
        "search_chunks",
        {
            "query": "fraud",
            "mode": "literal",
            "document_id": document.id,
        },
    )

    assert first.status == "success"
    assert second.status == "success"

    assert events == [
        "enter",
        "exit",
        "enter",
        "exit",
    ]


def test_tool_context_exits_after_database_error(db_session):
    """工具异常时也必须退出数据库上下文。"""

    from contextlib import contextmanager

    events = []

    @contextmanager
    def broken_factory():
        events.append("enter")

        try:
            with make_test_tool_session(db_session)() as db:
                yield db
        finally:
            events.append("exit")

    executor = ToolExecutor(
        build_paper_tool_registry(broken_factory)
    )

    result = run_tool(
        executor,
        "get_evidence",
        {
            "document_id": 999999,
            "chunk_id": 999999,
        },
    )

    assert result.status == "execution_error"
    assert result.error_type == "EvidenceNotFoundError"
    assert events == ["enter", "exit"]