"""汇总初检与补检的核验事实，生成最终论文证据矩阵。"""

from app.agent.evidence_matrix_quotes import attach_verified_facts
from app.agent.research_state import ResearchState


def final_matrix_node(state: ResearchState) -> dict:
    """刷新最终矩阵，但不自动认定模型陈述获得语义支持。"""

    matrix = attach_verified_facts(
        matrix=state["evidence_matrix"],
        verifications=state["fact_verifications"],
        evidence=state["evidence"],
    )

    verified_count = sum(
        len(row["quote_verified_facts"])
        for row in matrix
    )

    return {
        "evidence_matrix": matrix,
        "steps": state["steps"] + [
            {
                "step": "final_matrix",
                "status": "success",
                "detail": (
                    f"Final matrix contains {len(matrix)} papers "
                    f"and {verified_count} quote-verified facts"
                ),
            }
        ],
    }