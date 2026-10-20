"""验证 LangGraph 跨论文检索结果与 PostgreSQL 真实记录一致。"""

from sqlalchemy import select

from app.agent.paper_tools import build_paper_tool_registry
from app.agent.research_graph import (
    build_research_graph,
    initial_research_state,
)
from app.agent.tool_db import make_test_tool_session
from app.agent.tool_executor import ToolExecutor
from app.models.document import Chunk, Document


def create_paper(db_session, *, title, content, page):
    """创建带真实正文和页码的测试论文。"""

    document = Document(
        title=title,
        filename=f"{title.lower().replace(' ', '_')}.pdf",
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
        page_start=page,
        page_end=page,
    )
    db_session.add(chunk)
    db_session.flush()

    return document, chunk


def build_db_graph(db_session, *, max_calls=5):
    """构建连接测试事务的真实论文检索工作流。"""

    registry = build_paper_tool_registry(
        make_test_tool_session(db_session)
    )

    executor = ToolExecutor(
        registry,
        max_calls=max_calls,
        max_output_chars=10000,
    )

    return build_research_graph(
        executor=executor,
        enable_supplement=False,
    )


def compare_question(first_id, second_id):
    """生成 Planner 能识别的跨论文问题。"""

    return (
        f"Compare document {first_id} and document {second_id} "
        "for deepfake detection"
    )


def test_graph_retrieves_two_real_papers(db_session):
    """一次 Graph 执行必须获取两篇真实论文的证据。"""

    first, first_chunk = create_paper(
        db_session,
        title="First Deepfake Paper",
        content="Deepfake detection uses spectrogram features.",
        page=2,
    )
    second, second_chunk = create_paper(
        db_session,
        title="Second Deepfake Paper",
        content="Deepfake detection uses waveform features.",
        page=5,
    )

    graph = build_db_graph(db_session)

    result = graph.invoke(
        initial_research_state(
            compare_question(first.id, second.id)
        )
    )

    assert result["tool_calls"] == 2
    assert len(result["evidence"]) == 2

    by_document = {
        item["document_id"]: item
        for item in result["evidence"]
    }

    assert set(by_document) == {first.id, second.id}

    assert by_document[first.id]["chunk_id"] == first_chunk.id
    assert by_document[first.id]["content"] == first_chunk.content
    assert by_document[first.id]["page_start"] == 2

    assert by_document[second.id]["chunk_id"] == second_chunk.id
    assert by_document[second.id]["content"] == second_chunk.content
    assert by_document[second.id]["page_start"] == 5


def test_graph_does_not_invent_missing_document(db_session):
    """不存在的论文 ID 不得产生虚假证据。"""

    first, first_chunk = create_paper(
        db_session,
        title="Existing Deepfake Paper",
        content="Deepfake detection uses acoustic features.",
        page=3,
    )

    missing_id = 999999999

    result = build_db_graph(db_session).invoke(
        initial_research_state(
            compare_question(first.id, missing_id)
        )
    )

    assert result["tool_calls"] == 2

    assert {
        item["document_id"]
        for item in result["evidence"]
    } == {first.id}

    assert all(
        item["document_id"] != missing_id
        for item in result["evidence"]
    )


def test_graph_continues_when_second_paper_has_no_hits(db_session):
    """一篇论文无匹配证据时，保留另一篇的真实结果。"""

    first, _ = create_paper(
        db_session,
        title="Matching Deepfake Paper",
        content="Deepfake detection based on neural networks.",
        page=1,
    )

    second, _ = create_paper(
        db_session,
        title="Unrelated Paper",
        content="Weather forecasting and climate simulation.",
        page=7,
    )

    result = build_db_graph(db_session).invoke(
        initial_research_state(
            compare_question(first.id, second.id)
        )
    )

    assert result["tool_calls"] == 2

    assert {
        item["document_id"]
        for item in result["evidence"]
    } == {first.id}


def test_graph_keeps_test_transaction_usable(db_session):
    """多个工具查询结束后，外层测试事务必须仍可使用。"""

    first, _ = create_paper(
        db_session,
        title="Transaction Paper One",
        content="Deepfake detection uses spectral features.",
        page=1,
    )

    second, _ = create_paper(
        db_session,
        title="Transaction Paper Two",
        content="Deepfake detection uses temporal features.",
        page=2,
    )

    build_db_graph(db_session).invoke(
        initial_research_state(
            compare_question(first.id, second.id)
        )
    )

    assert db_session.is_active

    documents = db_session.scalars(
        select(Document).where(
            Document.id.in_([first.id, second.id])
        )
    ).all()

    assert len(documents) == 2


def test_graph_respects_real_tool_budget(db_session):
    """真实 PostgreSQL 工具也不能突破执行次数上限。"""

    first, _ = create_paper(
        db_session,
        title="Budget Paper One",
        content="Deepfake detection using spectrograms.",
        page=1,
    )

    second, _ = create_paper(
        db_session,
        title="Budget Paper Two",
        content="Deepfake detection using waveforms.",
        page=2,
    )

    result = build_db_graph(
        db_session,
        max_calls=1,
    ).invoke(
        initial_research_state(
            compare_question(first.id, second.id)
        )
    )

    assert result["tool_calls"] == 1

    assert any(
        step["detail"].endswith("limit_exceeded")
        for step in result["steps"]
    )