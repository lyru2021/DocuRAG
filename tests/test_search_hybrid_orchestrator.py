"""验证 Hybrid 编排、RRF 去重、来源追踪和失败降级。"""

from unittest.mock import Mock

import pytest

from app.schemas.search import SearchResult
from app.services.search_orchestrator import SearchOrchestrator
from app.services.search_router import SearchRequest


def make_hit(
    chunk_id: int,
    source: str,
) -> SearchResult:
    """构造真实结构的 Chunk 检索候选。"""

    return SearchResult(
        document_id=31,
        title="Audio Deepfake Detection",
        chunk_id=chunk_id,
        content=f"chunk-{chunk_id}",
        retrieval_source=source,
        score=1.0,
    )


def test_hybrid_rrf_deduplicates_chunks():
    """两路检索的相同 Chunk 应去重并融合排名。"""

    literal = Mock()
    literal.retrieve.return_value = [
        make_hit(101, "postgres_literal"),
        make_hit(102, "postgres_literal"),
    ]

    fts = Mock()
    fts.retrieve.return_value = [
        make_hit(102, "postgres_fts"),
        make_hit(103, "postgres_fts"),
    ]

    orchestrator = SearchOrchestrator({
        "keyword_literal": literal,
        "keyword_fts": fts,
    })

    response = orchestrator.execute(
        SearchRequest(
            query="spectrogram",
            strategy="hybrid",
            limit=5,
        )
    )

    assert response.selected_retrievers == [
        "keyword_literal",
        "keyword_fts",
    ]
    assert response.fusion_method == "rrf"
    assert [item.chunk_id for item in response.results] == [
        102, 101, 103,
    ]

    assert response.results[0].score == pytest.approx(
        1 / 62 + 1 / 61
    )

    assert response.candidate_sources["chunk:31:102"] == [
        "keyword_literal",
        "keyword_fts",
    ]

    assert len(response.execution_log) == 2
    assert all(
        log.status == "success"
        for log in response.execution_log
    )


def test_hybrid_failure_keeps_successful_keyword_results():
    """一路失败时，保留另一条路径的原始证据和分数。"""

    literal = Mock()
    literal.retrieve.return_value = [
        make_hit(101, "postgres_literal")
    ]

    fts = Mock()
    fts.retrieve.side_effect = RuntimeError(
        "FTS unavailable"
    )

    orchestrator = SearchOrchestrator({
        "keyword_literal": literal,
        "keyword_fts": fts,
    })

    response = orchestrator.execute(
        SearchRequest(
            query="spectrogram",
            strategy="hybrid",
        )
    )

    assert response.fusion_method is None
    assert len(response.results) == 1
    assert response.results[0].score == 1.0
    assert response.results[0].chunk_id == 101

    assert response.candidate_sources["chunk:31:101"] == [
        "keyword_literal"
    ]

    assert [log.status for log in response.execution_log] == [
        "success",
        "failed",
    ]
    assert response.execution_log[1].error_type == "RuntimeError"


def test_hybrid_missing_retriever_is_not_configured():
    """未配置的检索器不能伪装成查询成功。"""

    literal = Mock()
    literal.retrieve.return_value = [
        make_hit(201, "postgres_literal")
    ]

    orchestrator = SearchOrchestrator({
        "keyword_literal": literal,
    })

    response = orchestrator.execute(
        SearchRequest(
            query="spectrogram",
            strategy="hybrid",
        )
    )

    assert len(response.results) == 1
    assert response.fusion_method is None
    assert [log.status for log in response.execution_log] == [
        "success",
        "not_configured",
    ]

    assert response.candidate_sources["chunk:31:201"] == [
        "keyword_literal"
    ]


def test_single_route_keeps_original_score():
    """单路请求不应将 PostgreSQL 原始分数改为 RRF 分数。"""

    fts = Mock()
    fts.retrieve.return_value = [
        make_hit(301, "postgres_fts").model_copy(
            update={"score": 0.42}
        )
    ]

    orchestrator = SearchOrchestrator({
        "keyword_fts": fts,
    })

    response = orchestrator.execute(
        SearchRequest(query="spectrogram")
    )

    assert response.fusion_method is None
    assert response.results[0].score == pytest.approx(0.42)
    assert response.candidate_sources["chunk:31:301"] == [
        "keyword_fts"
    ]


def test_hybrid_both_retrievers_fail():
    """全部失败时应返回空候选，并记录实际错误。"""

    literal = Mock()
    literal.retrieve.side_effect = RuntimeError("db error")

    fts = Mock()
    fts.retrieve.side_effect = TimeoutError("timeout")

    orchestrator = SearchOrchestrator({
        "keyword_literal": literal,
        "keyword_fts": fts,
    })

    response = orchestrator.execute(
        SearchRequest(
            query="spectrogram",
            strategy="hybrid",
        )
    )

    assert response.results == []
    assert response.candidate_sources == {}
    assert response.fusion_method is None
    assert [log.status for log in response.execution_log] == [
        "failed",
        "failed",
    ]