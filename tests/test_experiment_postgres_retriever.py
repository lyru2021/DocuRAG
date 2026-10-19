"""验证两种实验配置的 PostgreSQL 检索隔离与真实证据。"""

from app.evaluation.postgres_retriever import (
    ExperimentPostgresRetriever,
)
from app.models.document import Chunk, Document
from app.models.retrieval_experiment_chunk import (
    RetrievalExperimentChunk,
)


def test_300_literal_returns_business_chunk(db_session):
    """300 配置应读取现有 chunks 表。"""

    document = Document(
        title="Graph Study",
        filename="graph.pdf",
        parse_status="parsed",
    )
    db_session.add(document)
    db_session.flush()

    db_session.add(
        Chunk(
            document_id=document.id,
            chunk_index=0,
            content="graph neural networks",
            start_char=0,
            end_char=21,
            page_start=2,
            page_end=2,
        )
    )
    db_session.commit()

    hits = ExperimentPostgresRetriever(db_session).search(
        experiment_id="chunk300_overlap50",
        query="graph",
        mode="literal",
        document_ids=[document.id],
    )

    assert len(hits) == 1
    assert hits[0].document_id == document.id
    assert hits[0].chunk_index == 0
    assert hits[0].page_start == 2
    assert hits[0].retrieval_source == "postgres_literal"


def test_500_literal_returns_experiment_chunk(db_session):
    """500 配置应读取独立实验表。"""

    document = Document(
        title="Graph Study",
        filename="graph.pdf",
        parse_status="parsed",
    )
    db_session.add(document)
    db_session.flush()

    db_session.add(
        RetrievalExperimentChunk(
            experiment_id="chunk500_overlap50",
            document_id=document.id,
            chunk_index=0,
            content="graph neural networks",
            start_char=0,
            end_char=21,
            page_start=3,
            page_end=3,
        )
    )
    db_session.commit()

    hits = ExperimentPostgresRetriever(db_session).search(
        experiment_id="chunk500_overlap50",
        query="graph",
        mode="literal",
        document_ids=[document.id],
    )

    assert len(hits) == 1
    assert hits[0].page_start == 3
    assert hits[0].experiment_id == "chunk500_overlap50"


def test_500_fts_returns_real_ranked_hit(db_session):
    """FTS 应通过真实 PostgreSQL 返回带正分数的 Chunk。"""

    document = Document(
        title="Fraud Detection",
        filename="fraud.pdf",
        parse_status="parsed",
    )
    db_session.add(document)
    db_session.flush()

    db_session.add(
        RetrievalExperimentChunk(
            experiment_id="chunk500_overlap50",
            document_id=document.id,
            chunk_index=0,
            content="Dynamic graph neural networks detect fraud.",
            start_char=0,
            end_char=42,
            page_start=4,
            page_end=4,
        )
    )
    db_session.commit()

    hits = ExperimentPostgresRetriever(db_session).search(
        experiment_id="chunk500_overlap50",
        query="graph",
        mode="fts",
        document_ids=[document.id],
    )

    assert len(hits) == 1
    assert hits[0].score > 0
    assert hits[0].retrieval_source == "postgres_fts"


def test_experiment_configuration_is_isolated(db_session):
    """500 实验记录不能出现在 300 的查询结果中。"""

    document = Document(
        title="Isolation Study",
        filename="isolation.pdf",
        parse_status="parsed",
    )
    db_session.add(document)
    db_session.flush()

    db_session.add(
        RetrievalExperimentChunk(
            experiment_id="chunk500_overlap50",
            document_id=document.id,
            chunk_index=0,
            content="uniqueexperimentterm",
            start_char=0,
            end_char=20,
        )
    )
    db_session.commit()

    retriever = ExperimentPostgresRetriever(db_session)

    hits_300 = retriever.search(
        experiment_id="chunk300_overlap50",
        query="uniqueexperimentterm",
        mode="literal",
        document_ids=[document.id],
    )

    hits_500 = retriever.search(
        experiment_id="chunk500_overlap50",
        query="uniqueexperimentterm",
        mode="literal",
        document_ids=[document.id],
    )

    assert hits_300 == []
    assert len(hits_500) == 1


def test_fts_uses_one_sql_statement(db_session):
    """FTS 检索应一次返回候选和相关性分数。"""

    from sqlalchemy import event

    document = Document(
        title="FTS Query Count",
        filename="fts_query_count.pdf",
        parse_status="parsed",
    )
    db_session.add(document)
    db_session.flush()

    db_session.add(
        RetrievalExperimentChunk(
            experiment_id="chunk500_overlap50",
            document_id=document.id,
            chunk_index=0,
            content="Dynamic graph neural networks detect fraud.",
            start_char=0,
            end_char=42,
            page_start=1,
            page_end=1,
        )
    )
    db_session.commit()

    connection = db_session.connection()
    engine = connection.engine

    query_count = 0

    def count_statements(
        conn,
        cursor,
        statement,
        parameters,
        context,
        executemany,
    ):
        nonlocal query_count

        # 只统计该测试 Session 所用连接的 SELECT。
        if conn is connection and statement.lstrip().upper().startswith(
            "SELECT"
        ):
            query_count += 1

    event.listen(
        engine,
        "before_cursor_execute",
        count_statements,
    )

    try:
        hits = ExperimentPostgresRetriever(db_session).search(
            experiment_id="chunk500_overlap50",
            query="graph",
            mode="fts",
            document_ids=[document.id],
            limit=5,
        )
    finally:
        event.remove(
            engine,
            "before_cursor_execute",
            count_statements,
        )

    assert len(hits) == 1
    assert hits[0].score > 0
    assert query_count == 1