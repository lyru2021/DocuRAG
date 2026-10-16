"""验证统一论文检索服务的结果结构与证据来源。"""

from app.models.document import Chunk, Document
from app.schemas.search import SearchResult
from app.services.search_service import SearchService


def test_search_papers_returns_standard_results(db_session):
    """元数据检索使用统一结果结构。"""

    document = Document(
        title="Temporal Graph Learning",
        filename="temporal.pdf",
        authors="Alice Chen",
        publication_year=2025,
    )

    db_session.add(document)
    db_session.commit()

    results = SearchService(db_session).search_papers(
        author="Alice",
        year=2025,
    )

    assert len(results) == 1
    assert isinstance(results[0], SearchResult)
    assert results[0].document_id == document.id
    assert results[0].retrieval_source == "metadata"
    assert results[0].score is None


def test_search_chunks_returns_standard_evidence(db_session):
    """Chunk 检索返回真实原文与页码。"""

    document = Document(
        title="HTS Quench Detection",
        filename="hts.pdf",
        parse_status="parsed",
    )

    db_session.add(document)
    db_session.flush()

    chunk = Chunk(
        document_id=document.id,
        chunk_index=0,
        content="光纤传感器可以监测高温超导磁体中的温度变化。",
        page_start=4,
        page_end=4,
    )

    db_session.add(chunk)
    db_session.commit()

    results = SearchService(db_session).search_chunks(
        "光纤传感器",
        document_id=document.id,
    )

    assert len(results) == 1
    assert results[0].chunk_id == chunk.id
    assert results[0].title == document.title
    assert results[0].page_start == 4
    assert "光纤传感器" in results[0].content
    assert results[0].retrieval_source == "postgres_literal"


def test_missing_section_returns_none(db_session):
    """不存在的章节不能生成虚构证据。"""

    result = SearchService(db_session).get_paper_section(
        document_id=999999,
        section_id=999999,
    )

    assert result is None