"""验证 Hybrid 多路检索策略及过滤条件边界。"""

import pytest

from app.services.search_router import (
    SearchRequest,
    SearchRouter,
)


def test_hybrid_selects_two_retrievers():
    """显式 Hybrid 应选择 Literal 和 FTS。"""

    plan = SearchRouter().select(
        SearchRequest(
            query="spectrogram",
            strategy="hybrid",
            limit=5,
        )
    )

    assert plan.retrievers == (
        "keyword_literal",
        "keyword_fts",
    )
    assert plan.reason == "explicit_hybrid_strategy"
    assert plan.planner == "rule_based"


def test_hybrid_preserves_document_filter():
    """指定文档 ID 不应取消 Hybrid。"""

    plan = SearchRouter().select(
        SearchRequest(
            query="spectrogram",
            document_id=31,
            strategy="hybrid",
        )
    )

    assert plan.retrievers == (
        "keyword_literal",
        "keyword_fts",
    )


def test_hybrid_rejects_empty_query():
    """没有检索词时不能执行 Hybrid。"""

    with pytest.raises(ValueError, match="requires a query"):
        SearchRouter().select(
            SearchRequest(strategy="hybrid")
        )


def test_hybrid_rejects_doi_filter():
    """不得静默忽略结构化 DOI 条件。"""

    with pytest.raises(ValueError, match="title or doi"):
        SearchRouter().select(
            SearchRequest(
                query="spectrogram",
                doi="10.1234/example",
                strategy="hybrid",
            )
        )


def test_hybrid_rejects_title_filter():
    """不得静默忽略结构化标题条件。"""

    with pytest.raises(ValueError, match="title or doi"):
        SearchRouter().select(
            SearchRequest(
                query="spectrogram",
                title="Deepfake Detection",
                strategy="hybrid",
            )
        )


def test_auto_still_selects_single_retriever():
    """新增 Hybrid 后原有 Auto 规则保持不变。"""

    plan = SearchRouter().select(
        SearchRequest(query="spectrogram")
    )

    assert plan.retrievers == ("keyword_fts",)