"""验证 PostgreSQL Chunk 检索结果的真实性与可复现性。"""

from app.models.document import Chunk, Document
from app.services.chunk_search_repository import ChunkSearchRepository


def test_literal_search_returns_real_evidence(db_session):
    """中文关键词命中后应返回真实页码及原文。"""

    document = Document(
        title="超导磁体研究",
        filename="magnet.pdf",
        parse_status="parsed",
    )
    db_session.add(document)
    db_session.flush()

    chunk = Chunk(
        document_id=document.id,
        chunk_index=0,
        content="高温超导磁体的失超保护需要及时检测。",
        start_char=0,
        end_char=21,
        page_start=3,
        page_end=3,
    )
    db_session.add(chunk)
    db_session.commit()

    results = ChunkSearchRepository(db_session).search(
        "失超保护",
        mode="literal",
        document_id=document.id,
    )

    assert len(results) == 1
    assert results[0].document_id == document.id
    assert results[0].chunk_id == chunk.id
    assert results[0].page_start == 3
    assert results[0].page_end == 3
    assert "失超保护" in results[0].content
    assert results[0].retrieval_source == "postgres_literal"


def test_fts_search_returns_ranked_evidence(db_session):
    """英文全文检索应返回相关论文 Chunk。"""

    document = Document(
        title="Graph Fraud Detection",
        filename="graph.pdf",
        parse_status="parsed",
    )
    db_session.add(document)
    db_session.flush()

    chunk = Chunk(
        document_id=document.id,
        chunk_index=0,
        content="Dynamic graph neural networks detect fraud.",
        page_start=2,
        page_end=2,
    )
    db_session.add(chunk)
    db_session.commit()

    results = ChunkSearchRepository(db_session).search(
        "graph neural networks",
        mode="fts",
        document_id=document.id,
    )

    assert len(results) == 1
    assert results[0].chunk_id == chunk.id
    assert results[0].score > 0
    assert results[0].retrieval_source == "postgres_fts"


def test_search_ignores_unparsed_documents(db_session):
    """尚未解析的文档不应参与正文检索。"""

    document = Document(
        title="Unparsed Paper",
        filename="pending.pdf",
        parse_status="pending",
    )
    db_session.add(document)
    db_session.flush()

    db_session.add(
        Chunk(
            document_id=document.id,
            chunk_index=0,
            content="UniqueSearchTerm",
        )
    )
    db_session.commit()

    results = ChunkSearchRepository(db_session).search(
        "UniqueSearchTerm",
        document_id=document.id,
    )

    assert results == []


def test_search_results_are_reproducible(db_session):
    """相同数据库快照和参数应产生相同结果顺序。"""

    document = Document(
        title="Reproducibility",
        filename="reproducibility.pdf",
        parse_status="parsed",
    )
    db_session.add(document)
    db_session.flush()

    db_session.add_all([
        Chunk(
            document_id=document.id,
            chunk_index=i,
            content=f"RepeatedKeyword evidence {i}",
            page_start=i + 1,
            page_end=i + 1,
        )
        for i in range(3)
    ])
    db_session.commit()

    repo = ChunkSearchRepository(db_session)

    first = repo.search(
        "RepeatedKeyword",
        document_id=document.id,
    )
    second = repo.search(
        "RepeatedKeyword",
        document_id=document.id,
    )

    assert [hit.chunk_id for hit in first] == [
        hit.chunk_id for hit in second
    ]