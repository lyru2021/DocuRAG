"""验证跨论文证据矩阵的来源关联、状态及安全约束。"""

import pytest
from pydantic import ValidationError

from app.agent.evidence_matrix import (
    EvidenceReference,
    MatrixField,
    build_evidence_matrix,
)


def make_evidence(document_id, chunk_id, page=2):
    """构造字段完整的候选证据。"""

    return {
        "document_id": document_id,
        "chunk_id": chunk_id,
        "title": f"Paper {document_id}",
        "page_start": page,
        "page_end": page,
        "content": "Deepfake detection uses acoustic features.",
    }


def test_matrix_contains_two_paper_rows():
    """两篇论文必须分别产生矩阵行。"""

    matrix = build_evidence_matrix(
        [31, 32],
        [
            make_evidence(31, 101),
            make_evidence(32, 201),
        ],
    )

    assert len(matrix) == 2
    assert [row.document_id for row in matrix] == [31, 32]


def test_matrix_preserves_candidate_source_ids():
    """候选证据必须保留真实数据库定位字段。"""

    matrix = build_evidence_matrix(
        [31],
        [make_evidence(31, 101, page=4)],
    )

    reference = matrix[0].candidate_references[0]

    assert reference.document_id == 31
    assert reference.chunk_id == 101
    assert reference.page_start == 4


def test_matrix_does_not_invent_field_claims():
    """没有语义核验时不能把候选证据冒充字段结论。"""

    matrix = build_evidence_matrix(
        [31],
        [make_evidence(31, 101)],
    )

    row = matrix[0]

    assert row.method.status == "insufficient"
    assert row.method.value is None
    assert row.method.references == []

    assert row.conclusion.status == "insufficient"


def test_matrix_preserves_missing_paper_row():
    """缺失论文应保留空行，不能伪造标题或来源。"""

    matrix = build_evidence_matrix(
        [31, 999999],
        [make_evidence(31, 101)],
    )

    missing = matrix[1]

    assert missing.document_id == 999999
    assert missing.title is None
    assert missing.method.status == "not_searched"
    assert missing.candidate_references == []


def test_supported_field_requires_reference():
    """已支持的研究结论必须绑定来源。"""

    with pytest.raises(ValidationError):
        MatrixField(
            status="supported",
            value="The model uses spectrograms.",
            references=[],
        )


def test_invalid_page_range_is_rejected():
    """倒置页码不得进入证据引用。"""

    with pytest.raises(ValidationError):
        EvidenceReference(
            document_id=31,
            chunk_id=101,
            page_start=5,
            page_end=2,
        )