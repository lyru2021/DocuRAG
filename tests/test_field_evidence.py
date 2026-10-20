"""验证字段候选证据识别不会编造事实或丢失来源。"""

from app.agent.field_evidence import classify_evidence_fields


def make_evidence(content, document_id=31, chunk_id=101):
    """创建带来源的模拟原文 Chunk。"""

    return {
        "document_id": document_id,
        "chunk_id": chunk_id,
        "title": "Test Paper",
        "page_start": 2,
        "page_end": 3,
        "content": content,
    }


def test_detects_method_candidate():
    """模型架构相关文本应成为方法候选证据。"""

    result = classify_evidence_fields([
        make_evidence(
            "The proposed model uses a transformer architecture."
        )
    ])

    assert len(result["method"]) == 1
    assert result["method"][0].reference.chunk_id == 101


def test_detects_experimental_conditions_candidate():
    """实验数据集和评价条件应成为实验候选证据。"""

    result = classify_evidence_fields([
        make_evidence(
            "Experiments were conducted on the SingFake dataset."
        )
    ])

    assert len(result["experimental_conditions"]) == 1


def test_detects_conclusion_candidate():
    """结果描述应成为结论候选证据。"""

    result = classify_evidence_fields([
        make_evidence(
            "The results demonstrate improved detection accuracy."
        )
    ])

    assert len(result["conclusion"]) == 1


def test_does_not_invent_unsupported_fields():
    """无相关线索时不得构造研究字段。"""

    result = classify_evidence_fields([
        make_evidence(
            "This paper was published in June 2025."
        )
    ])

    assert all(not candidates for candidates in result.values())


def test_preserves_database_references():
    """候选证据必须保留数据库标识和页码。"""

    result = classify_evidence_fields([
        make_evidence(
            "The model uses a transformer.",
            document_id=32,
            chunk_id=208,
        )
    ])

    reference = result["method"][0].reference

    assert reference.document_id == 32
    assert reference.chunk_id == 208
    assert reference.page_start == 2
    assert reference.page_end == 3


def test_deduplicates_candidates_and_enforces_limit():
    """重复 Chunk 不得绕过字段候选数量限制。"""

    evidence = [
        make_evidence("The model uses a transformer.", chunk_id=101),
        make_evidence("The model uses a transformer.", chunk_id=101),
        make_evidence("The model uses a CNN.", chunk_id=102),
        make_evidence("The model uses an LSTM.", chunk_id=103),
    ]

    result = classify_evidence_fields(
        evidence,
        max_candidates_per_field=2,
    )

    assert len(result["method"]) == 2

    assert [
        candidate.reference.chunk_id
        for candidate in result["method"]
    ] == [101, 102]