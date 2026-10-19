"""验证编排器能够从真实 PostgreSQL SQL 错误中降级恢复。"""

from sqlalchemy import text

from app.models.document import Chunk, Document
from app.schemas.search import SearchResult
from app.services.retrieval_transaction import run_with_savepoint
from app.services.retrievers import KeywordRetriever
from app.services.search_orchestrator import SearchOrchestrator
from app.services.search_router import SearchRequest
from app.services.search_service import SearchService


class FailingSQLRetriever:
    """模拟检索器内部发生真实 PostgreSQL SQL 错误。"""

    name = "keyword_literal"

    def __init__(self, db):
        self.db = db

    def retrieve(
        self,
        query: str,
        *,
        document_id: int | None = None,
        limit: int = 20,
    ) -> list[SearchResult]:
        """访问不存在的表，触发数据库事务级错误。"""

        self.db.execute(
            text(
                "SELECT * FROM "
                "docurag_missing_retrieval_table"
            )
        )

        return []


def test_real_sql_failure_does_not_block_fts(
    db_session,
):
    """Literal 真实 SQL 失败后，FTS 仍能返回真实证据。"""

    document = Document(
        title="Graph Retrieval Isolation",
        filename="retrieval_isolation.pdf",
        parse_status="parsed",
    )
    db_session.add(document)
    db_session.flush()

    chunk = Chunk(
        document_id=document.id,
        chunk_index=0,
        content="Dynamic graph neural networks detect fraud.",
        page_start=4,
        page_end=4,
    )
    db_session.add(chunk)
    db_session.commit()

    service = SearchService(db_session)

    orchestrator = SearchOrchestrator(
        {
            "keyword_literal": FailingSQLRetriever(db_session),
            "keyword_fts": KeywordRetriever(
                service,
                mode="fts",
            ),
        },
        retrieval_runner=lambda operation: run_with_savepoint(
            db_session,
            operation,
        ),
    )

    response = orchestrator.execute(
        SearchRequest(
            query="graph",
            document_id=document.id,
            strategy="hybrid",
            limit=5,
        )
    )

    assert response.selected_retrievers == [
        "keyword_literal",
        "keyword_fts",
    ]

    assert [
        log.status for log in response.execution_log
    ] == ["failed", "success"]

    assert response.execution_log[0].error_type in {
        "ProgrammingError",
        "DBAPIError",
    }

    assert response.execution_log[0].result_count == 0
    assert response.execution_log[1].result_count == 1

    assert len(response.results) == 1

    result = response.results[0]

    assert result.document_id == document.id
    assert result.chunk_id == chunk.id
    assert result.page_start == 4
    assert result.page_end == 4
    assert result.retrieval_source == "postgres_fts"

    # 只有一个 Retriever 成功，保留原始 FTS 分数。
    assert response.fusion_method is None
    assert result.score is not None
    assert result.score > 0

    key = f"chunk:{document.id}:{chunk.id}"

    assert response.candidate_sources[key] == [
        "keyword_fts"
    ]

    # 在同一个外层事务中仍可正常执行 SQL。
    assert db_session.scalar(text("SELECT 1")) == 1