"""验证检索执行编排、执行日志和异常隔离。"""

from unittest.mock import Mock

from app.schemas.search import SearchResult
from app.services.search_orchestrator import SearchOrchestrator
from app.services.search_router import SearchRequest


def make_result() -> SearchResult:
    """构造合法的检索结果。"""

    return SearchResult(
        document_id=31,
        title="Audio Deepfake Detection",
        chunk_id=101,
        content="spectrogram",
        retrieval_source="postgres_fts",
    )


def test_execute_keyword_retriever():
    """实际执行选中的关键词 Retriever。"""

    retriever = Mock()
    retriever.retrieve.return_value = [make_result()]

    orchestrator = SearchOrchestrator({
        "keyword_fts": retriever,
    })

    response = orchestrator.execute(
        SearchRequest(
            query="spectrogram",
            document_id=31,
            limit=5,
        )
    )

    assert response.planner == "rule_based"
    assert response.selected_retrievers == ["keyword_fts"]
    assert len(response.results) == 1

    retriever.retrieve.assert_called_once_with(
        "spectrogram",
        document_id=31,
        limit=5,
    )

    log = response.execution_log[0]
    assert log.status == "success"
    assert log.result_count == 1
    assert log.elapsed_ms >= 0


def test_empty_results_are_success():
    """零条命中不等于工具故障。"""

    retriever = Mock()
    retriever.retrieve.return_value = []

    orchestrator = SearchOrchestrator({
        "keyword_literal": retriever,
    })

    response = orchestrator.execute(
        SearchRequest(
            query="失超",
        )
    )

    assert response.results == []
    assert response.execution_log[0].status == "success"
    assert response.execution_log[0].result_count == 0


def test_missing_retriever_is_not_configured():
    """未配置的 Retriever 不应伪装成已执行。"""

    orchestrator = SearchOrchestrator({})

    response = orchestrator.execute(
        SearchRequest(query="spectrogram")
    )

    assert response.selected_retrievers == ["keyword_fts"]
    assert response.results == []
    assert response.execution_log[0].status == "not_configured"


def test_failed_retriever_does_not_fabricate_results():
    """检索器抛出异常时，不得产生虚假候选证据。"""

    retriever = Mock()
    retriever.retrieve.side_effect = RuntimeError(
        "database unavailable"
    )

    orchestrator = SearchOrchestrator({
        "keyword_fts": retriever,
    })

    response = orchestrator.execute(
        SearchRequest(query="spectrogram")
    )

    assert response.results == []
    assert response.execution_log[0].status == "failed"
    assert response.execution_log[0].error_type == "RuntimeError"
    assert response.execution_log[0].result_count == 0


def test_invalid_retriever_output_is_rejected():
    """返回值不符合 SearchResult Schema 时必须记录失败。"""

    retriever = Mock()
    retriever.retrieve.return_value = [
        {"document_id": 31, "title": "Fake"}
    ]

    orchestrator = SearchOrchestrator({
        "keyword_fts": retriever,
    })

    response = orchestrator.execute(
        SearchRequest(query="spectrogram")
    )

    assert response.results == []
    assert response.execution_log[0].status == "failed"
    assert response.execution_log[0].error_type == "TypeError"