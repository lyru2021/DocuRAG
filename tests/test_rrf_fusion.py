"""验证 RRF 的排名计算、跨路去重和输入边界。"""

import pytest

from app.schemas.search import SearchResult
from app.services.rrf_fusion import (
    reciprocal_rank_fusion,
)


def make_hit(
    chunk_id: int,
    source: str = "postgres_literal",
) -> SearchResult:
    """构造具有稳定 Chunk ID 的检索结果。"""

    return SearchResult(
        document_id=31,
        title="Audio Deepfake Detection",
        chunk_id=chunk_id,
        content=f"chunk-{chunk_id}",
        retrieval_source=source,
    )


def test_rrf_merges_duplicate_chunk():
    """相同 Chunk 在两路检索中应只返回一次。"""

    literal = [
        make_hit(1),
        make_hit(2),
    ]

    fts = [
        make_hit(2, "postgres_fts"),
        make_hit(3, "postgres_fts"),
    ]

    fused = reciprocal_rank_fusion({
        "keyword_literal": literal,
        "keyword_fts": fts,
    })

    assert [item.chunk_id for item in fused] == [2, 1, 3]
    assert fused[0].score == pytest.approx(
        1 / 62 + 1 / 61
    )


def test_rrf_deduplicates_within_one_retriever():
    """同一路中的重复 Chunk 不应重复计分。"""

    fused = reciprocal_rank_fusion({
        "keyword_literal": [
            make_hit(1),
            make_hit(1),
        ]
    })

    assert len(fused) == 1
    assert fused[0].score == pytest.approx(1 / 61)


def test_rrf_uses_document_and_chunk_identity():
    """不同文档中的 Chunk 不得因 ID 混淆而合并。"""

    first = make_hit(10)
    second = make_hit(10).model_copy(
        update={"document_id": 32}
    )

    fused = reciprocal_rank_fusion({
        "a": [first],
        "b": [second],
    })

    assert len(fused) == 2


def test_rrf_limit():
    """融合后应遵守结果数量上限。"""

    fused = reciprocal_rank_fusion(
        {"a": [make_hit(1), make_hit(2)]},
        limit=1,
    )

    assert len(fused) == 1


def test_rrf_rejects_invalid_parameters():
    """无效融合参数不能静默接受。"""

    with pytest.raises(ValueError):
        reciprocal_rank_fusion({}, k=0)

    with pytest.raises(ValueError):
        reciprocal_rank_fusion({}, limit=0)