"""对多路检索候选执行 RRF 排名融合与去重。"""

from collections import defaultdict
from collections.abc import Mapping

from app.schemas.search import SearchResult


def result_key(result: SearchResult) -> tuple:
    """使用数据库稳定 ID 识别同一候选证据。"""

    if result.chunk_id is not None:
        return ("chunk", result.document_id, result.chunk_id)

    if result.section_id is not None:
        return ("section", result.document_id, result.section_id)

    return ("document", result.document_id)


def reciprocal_rank_fusion(
    ranked_lists: Mapping[str, list[SearchResult]],
    *,
    k: int = 60,
    limit: int = 20,
) -> list[SearchResult]:
    """融合多个检索器结果，并返回去重后的标准化候选。"""

    if k < 1:
        raise ValueError("k must be positive")

    if limit < 1:
        raise ValueError("limit must be positive")

    scores = defaultdict(float)
    representatives = {}
    first_positions = {}

    for retriever_name, results in ranked_lists.items():
        # 同一 Retriever 内的重复结果不能重复贡献排名分。
        seen = set()

        for rank, result in enumerate(results, start=1):
            key = result_key(result)

            if key in seen:
                continue

            seen.add(key)

            scores[key] += 1.0 / (k + rank)

            if key not in representatives:
                representatives[key] = result
                first_positions[key] = (
                    retriever_name,
                    rank,
                )

    ordered_keys = sorted(
        scores,
        key=lambda key: (
            -scores[key],
            first_positions[key][1],
            str(key),
        ),
    )

    fused = []

    for key in ordered_keys[:limit]:
        # 不改变原始检索结果，融合分数只存在于返回副本。
        fused.append(
            representatives[key].model_copy(
                update={"score": scores[key]}
            )
        )

    return fused