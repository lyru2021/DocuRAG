"""验证跨论文证据覆盖度判断及缺失字段识别。"""

from app.agent.evidence_judge import (
    judge_evidence_coverage,
)
from app.agent.research_graph import initial_research_state


QUESTION = (
    "Compare document 31 and document 32 "
    "for deepfake detection"
)


def make_state():
    """构造包含两个真实检索目标的测试状态。"""

    state = initial_research_state(QUESTION)

    state["retrieval_plan"] = [
        {
            "task_id": f"T{i}",
            "tool_name": "search_chunks",
            "arguments": {
                "document_id": document_id,
                "query": "detection",
                "mode": "literal",
                "limit": 5,
            },
            "purpose": "Research comparison",
        }
        for i, document_id in enumerate(
            (31, 32), start=1
        )
    ]

    return state


def make_verification(
    document_id,
    field,
    *,
    status="quote_verified",
    chunk_id=None,
):
    """构造已完成后端引用检查的事实记录。"""

    if chunk_id is None:
        chunk_id = document_id * 10

    return {
        "status": status,
        "reason": "Test verification",
        "fact": {
            "document_id": document_id,
            "chunk_id": chunk_id,
            "field": field,
            "claim": "A research statement",
            "quote": "An original excerpt",
            "page_start": 2,
            "page_end": 2,
        },
    }


def test_missing_all_fields():
    """完全没有事实时，两篇论文均缺少三个字段。"""

    result = judge_evidence_coverage(make_state())

    assert not result.sufficient_quote_coverage
    assert len(result.papers) == 2
    assert len(result.missing_fields[31]) == 3
    assert len(result.missing_fields[32]) == 3


def test_one_paper_covered_other_missing():
    """一篇论文的证据不能替另一篇论文背书。"""

    state = make_state()

    state["fact_verifications"] = [
        make_verification(31, field)
        for field in (
            "method",
            "experimental_conditions",
            "conclusion",
        )
    ]

    result = judge_evidence_coverage(state)

    assert 31 not in result.missing_fields
    assert len(result.missing_fields[32]) == 3
    assert not result.sufficient_quote_coverage


def test_all_fields_have_verified_quotes():
    """两篇论文所有字段存在可核验引文时覆盖检查通过。"""

    state = make_state()

    state["fact_verifications"] = [
        make_verification(document_id, field)
        for document_id in (31, 32)
        for field in (
            "method",
            "experimental_conditions",
            "conclusion",
        )
    ]

    result = judge_evidence_coverage(state)

    assert result.sufficient_quote_coverage
    assert result.missing_fields == {}


def test_rejected_quote_does_not_count():
    """编造的引文不能增加证据覆盖度。"""

    state = make_state()

    state["fact_verifications"] = [
        make_verification(
            31,
            "method",
            status="quote_mismatch",
        )
    ]

    result = judge_evidence_coverage(state)

    assert "method" in result.missing_fields[31]


def test_duplicate_chunk_counts_once():
    """同一 Chunk 重复引用不得重复计算。"""

    state = make_state()

    state["fact_verifications"] = [
        make_verification(31, "method"),
        make_verification(31, "method"),
    ]

    result = judge_evidence_coverage(state)

    method = result.papers[0].fields[0]

    assert method.status == "quote_verified"
    assert method.quote_count == 1


def test_unplanned_document_does_not_create_paper():
    """模型引用计划外论文不得创建新的比较对象。"""

    state = make_state()

    state["fact_verifications"] = [
        make_verification(999, "method")
    ]

    result = judge_evidence_coverage(state)

    assert [
        paper.document_id
        for paper in result.papers
    ] == [31, 32]

    assert not result.sufficient_quote_coverage