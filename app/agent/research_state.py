"""定义多步骤科研检索工作流的状态和证据结构。"""

from typing import Literal, TypedDict


class RetrievalTask(TypedDict):
    """表示一项计划中的论文检索任务。"""

    task_id: str
    tool_name: Literal[
        "search_papers",
        "search_chunks",
        "get_evidence",
    ]
    arguments: dict
    purpose: str


class EvidenceItem(TypedDict):
    """表示具有数据库定位信息的候选证据。"""

    document_id: int
    chunk_id: int
    title: str
    page_start: int
    page_end: int
    content: str


class StepRecord(TypedDict):
    """记录一个工作流节点的执行结果。"""

    step: str
    status: Literal["success", "failed", "skipped"]
    detail: str


class ResearchState(TypedDict):
    """记录一次跨论文检索所需的完整状态。"""

    question: str
    retrieval_plan: list[RetrievalTask]
    tool_calls: int
    evidence: list[EvidenceItem]
    evidence_matrix: list[dict]
    supplementary_searches: int
    answer: str | None
    status: str
    steps: list[StepRecord]
    field_candidates: dict[str, list[dict]]
    fact_verifications: list[dict]
    extraction_usage: dict
    evidence_judgement: dict
    supplementary_tasks: list[RetrievalTask]
    supplementary_new_evidence: list[EvidenceItem]