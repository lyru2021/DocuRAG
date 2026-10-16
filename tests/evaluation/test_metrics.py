"""验证证据覆盖、完整命中和排序评价指标。"""

from app.evaluation.metrics import (
    RankedChunk,
    aggregate_metrics,
    evaluate_question,
)
from app.evaluation.schemas import EvaluationQuestion


def make_question():
    """构造需要两处证据才能完整命中的问题。"""

    return EvaluationQuestion(
        question_id="q010",
        query="temperature scaling",
        evidence=[
            {
                "document_id": 32,
                "start_char": 100,
                "end_char": 120,
            },
            {
                "document_id": 32,
                "start_char": 200,
                "end_char": 230,
            },
        ],
    )


def test_complete_evidence_hit():
    """前两条结果分别覆盖证据，完整命中排名为 2。"""

    chunks = [
        RankedChunk(32, 0, 90, 130),
        RankedChunk(32, 1, 190, 240),
    ]

    result = evaluate_question(make_question(), chunks)

    assert result["evidence_recall_at_k"] == 1.0
    assert result["hit_at_k"] == 1
    assert result["reciprocal_rank_at_k"] == 0.5
    assert result["first_complete_rank"] == 2


def test_partial_evidence_is_not_full_hit():
    """只找到一处必要证据，不应记为完整命中。"""

    chunks = [RankedChunk(32, 0, 90, 130)]

    result = evaluate_question(make_question(), chunks)

    assert result["evidence_recall_at_k"] == 0.5
    assert result["hit_at_k"] == 0
    assert result["reciprocal_rank_at_k"] == 0.0


def test_wrong_document_does_not_count():
    """其他文档中的相同字符位置不能算证据命中。"""

    chunks = [
        RankedChunk(31, 0, 90, 130),
        RankedChunk(31, 1, 190, 240),
    ]

    result = evaluate_question(make_question(), chunks)

    assert result["hit_at_k"] == 0
    assert result["evidence_recall_at_k"] == 0.0


def test_aggregate_metrics():
    """宏平均不得将多证据问题赋予更高权重。"""

    results = [
        {
            "evidence_recall_at_k": 1.0,
            "hit_at_k": 1,
            "reciprocal_rank_at_k": 1.0,
        },
        {
            "evidence_recall_at_k": 0.5,
            "hit_at_k": 0,
            "reciprocal_rank_at_k": 0.0,
        },
    ]

    metrics = aggregate_metrics(results)

    assert metrics["question_count"] == 2
    assert metrics["evidence_recall_at_5"] == 0.75
    assert metrics["hit_at_5"] == 0.5
    assert metrics["mrr_at_5"] == 0.5