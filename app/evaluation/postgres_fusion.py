"""复用 RRF 算法融合 PostgreSQL 实验检索结果。"""

from app.evaluation.postgres_retriever import ExperimentHit
from app.schemas.search import SearchResult
from app.services.rrf_fusion import reciprocal_rank_fusion


def fuse_experiment_hits(
    literal_hits: list[ExperimentHit],
    fts_hits: list[ExperimentHit],
    *,
    limit: int = 5,
) -> list[ExperimentHit]:
    """按实验 Chunk 的文档 ID 和顺序去重并执行 RRF。"""

    if limit < 1:
        raise ValueError("limit must be positive")

    original_hits = {}

    def convert(hits: list[ExperimentHit]) -> list[SearchResult]:
        results = []

        for hit in hits:
            key = (hit.document_id, hit.chunk_index)

            # 当前每次仅融合同一个切分实验的结果。
            # chunk_index + 1 仅作为 RRF 适配 ID，不是数据库主键。
            original_hits.setdefault(key, hit)

            results.append(
                SearchResult(
                    document_id=hit.document_id,
                    title="Experiment Chunk",
                    chunk_id=hit.chunk_index + 1,
                    content=hit.content,
                    score=hit.score,
                    retrieval_source=hit.retrieval_source,
                )
            )

        return results

    ranked_lists = {
        "keyword_literal": convert(literal_hits),
        "keyword_fts": convert(fts_hits),
    }

    fused = reciprocal_rank_fusion(
        ranked_lists,
        limit=limit,
    )

    return [
        original_hits[
            (result.document_id, result.chunk_id - 1)
        ]
        for result in fused
    ]