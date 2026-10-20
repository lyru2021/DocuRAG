"""验证最终矩阵聚合、来源安全、去重及状态隔离。"""

from app.agent.research_final_matrix import final_matrix_node
from app.agent.research_graph import initial_research_state


QUESTION = (
    "Compare document 31 and document 32 "
    "for deepfake detection"
)


def make_row(document_id):
    """构造包含三个研究字段的矩阵行。"""

    empty_field = {
        "status": "insufficient",
        "value": None,
        "references": [],
    }

    return {
        "document_id": document_id,
        "title": f"Paper {document_id}",
        "method": dict(empty_field),
        "experimental_conditions": dict(empty_field),
        "conclusion": dict(empty_field),
        "candidate_references": [],
    }


def make_evidence(document_id, chunk_id):
    """模拟来自指定论文的数据库 Chunk。"""

    return {
        "document_id": document_id,
        "chunk_id": chunk_id,
        "title": f"Paper {document_id}",
        "page_start": 2,
        "page_end": 2,
        "content": (
            "The proposed transformer model "
            "uses spectrogram features."
        ),
    }


def make_verification(document_id, chunk_id, *,
                      quote="transformer model"):
    """构造模型事实及其引用验证记录。"""

    return {
        "status": "quote_verified",
        "reason": "Exact quote found",
        "fact": {
            "document_id": document_id,
            "chunk_id": chunk_id,
            "field": "method",
            "claim": "The paper uses a transformer model.",
            "quote": quote,
            "page_start": 2,
            "page_end": 2,
        },
    }


def make_state():
    """构造包含两篇论文的工作流状态。"""

    state = initial_research_state(QUESTION)

    state["evidence_matrix"] = [
        make_row(31),
        make_row(32),
    ]

    return state


def test_final_matrix_merges_initial_and_supplementary_facts():
    """最终矩阵应同时包含初检与补检核验事实。"""

    state = make_state()

    state["evidence"] = [
        make_evidence(31, 3101),
        make_evidence(32, 3202),
    ]

    state["fact_verifications"] = [
        make_verification(31, 3101),
        make_verification(32, 3202),
    ]

    result = final_matrix_node(state)
    matrix = result["evidence_matrix"]

    assert len(matrix) == 2
    assert len(matrix[0]["quote_verified_facts"]) == 1
    assert len(matrix[1]["quote_verified_facts"]) == 1

    assert matrix[0]["quote_verified_facts"][0]["chunk_id"] == 3101
    assert matrix[1]["quote_verified_facts"][0]["chunk_id"] == 3202


def test_final_matrix_rejects_fake_quote():
    """虚构原文即使声称已核验，也不得进入矩阵。"""

    state = make_state()

    state["evidence"] = [
        make_evidence(31, 3101),
    ]

    state["fact_verifications"] = [
        make_verification(
            31,
            3101,
            quote="The model achieves perfect accuracy.",
        )
    ]

    result = final_matrix_node(state)

    assert result["evidence_matrix"][0][
        "quote_verified_facts"
    ] == []


def test_final_matrix_deduplicates_facts():
    """同一事实在初检和补检结果中重复时只保留一次。"""

    state = make_state()

    state["evidence"] = [
        make_evidence(31, 3101),
    ]

    fact = make_verification(31, 3101)

    state["fact_verifications"] = [
        fact,
        fact,
    ]

    result = final_matrix_node(state)

    assert len(
        result["evidence_matrix"][0]["quote_verified_facts"]
    ) == 1


def test_final_matrix_does_not_mark_claim_as_supported():
    """引文真实性不能替代事实与原文的语义审核。"""

    state = make_state()

    state["evidence"] = [
        make_evidence(31, 3101),
    ]

    state["fact_verifications"] = [
        make_verification(31, 3101),
    ]

    result = final_matrix_node(state)

    method = result["evidence_matrix"][0]["method"]

    assert method["status"] == "insufficient"
    assert method["value"] is None
    assert method["references"] == []

    assert len(
        result["evidence_matrix"][0]["quote_verified_facts"]
    ) == 1


def test_final_matrix_does_not_mutate_input_state():
    """矩阵刷新不能原地污染输入状态。"""

    state = make_state()

    state["evidence"] = [
        make_evidence(31, 3101),
    ]

    state["fact_verifications"] = [
        make_verification(31, 3101),
    ]

    result = final_matrix_node(state)

    assert (
        "quote_verified_facts"
        not in state["evidence_matrix"][0]
    )

    assert (
        "quote_verified_facts"
        in result["evidence_matrix"][0]
    )

    assert result["steps"][-1]["step"] == "final_matrix"