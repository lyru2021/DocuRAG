"""计算基于真实原文证据区间的检索评价指标。"""

from dataclasses import dataclass

from app.evaluation.schemas import EvaluationQuestion


@dataclass(frozen=True)
class RankedChunk:
    """表示一个具有原文字符偏移的排序检索结果。"""

    document_id: int
    chunk_index: int
    start_char: int
    end_char: int


def covers_evidence(chunk: RankedChunk, evidence) -> bool:
    """判断 Chunk 是否完整覆盖同一文档中的证据区间。"""

    return (
        chunk.document_id == evidence.document_id
        and chunk.start_char <= evidence.start_char
        and chunk.end_char >= evidence.end_char
    )


def evaluate_question(
    question: EvaluationQuestion,
    ranked_chunks: list[RankedChunk],
    k: int = 5,
) -> dict:
    """计算单题证据召回率、完整命中和倒数排名。"""

    if k < 1:
        raise ValueError("k must be positive")

    covered = set()
    first_complete_rank = None
    total = len(question.evidence)

    for rank, chunk in enumerate(ranked_chunks[:k], start=1):
        for index, evidence in enumerate(question.evidence):
            if covers_evidence(chunk, evidence):
                covered.add(index)

        if len(covered) == total:
            first_complete_rank = rank
            break

    return {
        "question_id": question.question_id,
        "evidence_recall_at_k": len(covered) / total,
        "hit_at_k": int(len(covered) == total),
        "reciprocal_rank_at_k": (
            1.0 / first_complete_rank
            if first_complete_rank is not None
            else 0.0
        ),
        "first_complete_rank": first_complete_rank,
    }


def aggregate_metrics(results: list[dict]) -> dict:
    """对问题进行宏平均，每道问题具有相同权重。"""

    if not results:
        raise ValueError("results must not be empty")

    count = len(results)

    return {
        "question_count": count,
        "evidence_recall_at_5": sum(
            result["evidence_recall_at_k"]
            for result in results
        ) / count,
        "hit_at_5": sum(
            result["hit_at_k"]
            for result in results
        ) / count,
        "mrr_at_5": sum(
            result["reciprocal_rank_at_k"]
            for result in results
        ) / count,
    }