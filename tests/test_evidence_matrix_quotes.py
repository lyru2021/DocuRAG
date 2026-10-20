"""验证真实引文进入矩阵时不会被误标记为语义支持。"""

from app.agent.evidence_matrix_quotes import attach_verified_facts


def make_matrix():
    """构造两篇论文的基础证据矩阵。"""

    def row(document_id):
        return {
            "document_id": document_id,
            "title": f"Paper {document_id}",
            "method": {
                "status": "insufficient",
                "value": None,
                "references": [],
            },
            "experimental_conditions": {
                "status": "insufficient",
                "value": None,
                "references": [],
            },
            "conclusion": {
                "status": "insufficient",
                "value": None,
                "references": [],
            },
            "candidate_references": [],
        }

    return [row(31), row(32)]


def make_evidence():
    """构造本轮实际检索的数据库 Chunk。"""

    return [{
        "document_id": 31,
        "chunk_id": 3102,
        "title": "Paper 31",
        "page_start": 2,
        "page_end": 2,
        "content": "The proposed transformer model uses spectrogram features.",
    }]


def make_verification(
    *,
    document_id=31,
    chunk_id=3102,
    quote="The proposed transformer model",
    status="quote_verified",
):
    """构造模型事实及引文核验记录。"""

    return {
        "status": status,
        "reason": "Exact quote found",
        "fact": {
            "document_id": document_id,
            "chunk_id": chunk_id,
            "field": "method",
            "claim": "The study uses a transformer model.",
            "quote": quote,
            "page_start": 2,
            "page_end": 2,
        },
    }


def test_verified_quote_enters_correct_paper():
    """核验通过的引文只能进入对应论文。"""

    result = attach_verified_facts(
        make_matrix(),
        [make_verification()],
        make_evidence(),
    )

    assert len(result[0]["quote_verified_facts"]) == 1
    assert result[1]["quote_verified_facts"] == []

    assert result[0]["quote_verified_facts"][0]["chunk_id"] == 3102


def test_verified_quote_does_not_become_supported():
    """引用真实不代表具体研究陈述获得语义支持。"""

    result = attach_verified_facts(
        make_matrix(),
        [make_verification()],
        make_evidence(),
    )

    assert result[0]["method"]["status"] == "insufficient"
    assert result[0]["method"]["value"] is None
    assert result[0]["method"]["references"] == []

    assert (
        result[0]["quote_verified_facts"][0]["verification_status"]
        == "quote_verified"
    )


def test_fabricated_quote_is_rejected_again():
    """即使上游声称已核验，也必须重新验证原文。"""

    result = attach_verified_facts(
        make_matrix(),
        [
            make_verification(
                quote="The model achieves perfect accuracy."
            )
        ],
        make_evidence(),
    )

    assert result[0]["quote_verified_facts"] == []


def test_cross_paper_reference_is_rejected():
    """其他论文的 ID 不得借用当前论文的 Chunk。"""

    result = attach_verified_facts(
        make_matrix(),
        [make_verification(document_id=32)],
        make_evidence(),
    )

    assert result[0]["quote_verified_facts"] == []
    assert result[1]["quote_verified_facts"] == []


def test_duplicate_facts_are_deduplicated():
    """重复的模型事实不能在矩阵中重复出现。"""

    verification = make_verification()

    result = attach_verified_facts(
        make_matrix(),
        [verification, verification],
        make_evidence(),
    )

    assert len(result[0]["quote_verified_facts"]) == 1