"""验证科研报告的字段展示、来源追踪和证据不足处理。"""

import pytest

from app.agent.research_report import render_research_report


QUESTION = "Compare document 31 and document 32"


def make_matrix():
    """构造包含一条已核验引文的两篇论文矩阵。"""

    return [
        {
            "document_id": 31,
            "title": "Paper A",
            "quote_verified_facts": [
                {
                    "field": "method",
                    "claim": "The model uses a transformer.",
                    "quote": "transformer model",
                    "document_id": 31,
                    "chunk_id": 3102,
                    "page_start": 2,
                    "page_end": 2,
                    "verification_status": "quote_verified",
                }
            ],
        },
        {
            "document_id": 32,
            "title": "Paper B",
            "quote_verified_facts": [],
        },
    ]


def test_report_contains_two_papers():
    """报告必须包含两篇论文。"""

    report = render_research_report(
        QUESTION,
        make_matrix(),
    )

    assert "论文 31：Paper A" in report
    assert "论文 32：Paper B" in report


def test_report_preserves_quote_and_source():
    """报告必须完整保留原文引文和来源标识。"""

    report = render_research_report(
        QUESTION,
        make_matrix(),
    )

    assert "transformer model" in report
    assert "Document 31, Chunk 3102, p.2" in report


def test_report_distinguishes_claim_from_support():
    """真实引文不得被描述成语义审核已通过。"""

    report = render_research_report(
        QUESTION,
        make_matrix(),
    )

    assert "引用已核验，陈述待审核" in report
    assert "模型陈述" in report
    assert "独立语义审核" in report


def test_report_marks_missing_fields():
    """无核验事实的研究字段必须标记证据不足。"""

    report = render_research_report(
        QUESTION,
        make_matrix(),
    )

    assert report.count(
        "证据不足：暂无经过原文匹配的字段事实。"
    ) == 5


def test_empty_matrix_and_blank_question():
    """空矩阵可降级，空研究问题必须拒绝。"""

    report = render_research_report(QUESTION, [])

    assert "未找到充分证据" in report

    with pytest.raises(ValueError):
        render_research_report("   ", [])