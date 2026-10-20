"""根据明确的论文 ID 构建受控的跨论文检索计划。"""

import re

from app.agent.research_state import RetrievalTask


class ResearchPlanningError(ValueError):
    """研究问题无法转换为可靠的检索计划。"""


# 只识别带明确文档语义的 ID，避免把年份、模型编号当论文 ID。
DOCUMENT_PATTERN = re.compile(
    r"(?:document(?:\s+id)?|doc(?:\s+id)?|论文(?:\s*id)?|文档(?:\s*id)?)"
    r"\s*(?:=|:|：|#)?\s*(\d+)",
    flags=re.IGNORECASE,
)


def extract_document_ids(question: str) -> list[int]:
    """提取明确提及的文档 ID，并按出现顺序去重。"""

    seen: set[int] = set()
    document_ids: list[int] = []

    for match in DOCUMENT_PATTERN.finditer(question):
        document_id = int(match.group(1))

        if document_id <= 0:
            continue

        if document_id in seen:
            continue

        seen.add(document_id)
        document_ids.append(document_id)

    return document_ids


def choose_retrieval_query(question: str) -> str:
    """根据科研比较问题的检索意图选择初始关键词。"""

    text = question.lower()

    # 优先识别具体研究维度，避免被 broad detection 覆盖。
    if any(word in text for word in (
        "dataset",
        "datasets",
        "experimental conditions",
        "experimental settings",
        "training data",
        "数据集",
        "实验条件",
    )):
        return "dataset"

    if any(word in text for word in (
        "evaluation metric",
        "evaluation metrics",
        "accuracy",
        "precision",
        "recall",
        "eer",
        "评价指标",
        "评估指标",
    )):
        return "evaluation"

    if any(word in text for word in (
        "findings",
        "experimental findings",
        "conclusions",
        "results",
        "研究结论",
        "实验结果",
    )):
        return "results"

    if any(word in text for word in (
        "methods",
        "method",
        "architecture",
        "framework",
        "研究方法",
        "检测方法",
    )):
        return "model"

    # 没有明确字段意图时，回退到原来的研究领域关键词。
    if any(word in text for word in (
        "deepfake",
        "singfake",
        "detection",
        "深度伪造",
    )):
        return "detection"

    if any(word in text for word in (
        "graph",
        "fraud",
        "图神经网络",
    )):
        return "graph"

    if any(word in text for word in (
        "spectrogram",
        "waveform",
        "频谱",
    )):
        return "spectrogram"

    raise ValueError("Cannot determine a reliable retrieval query")

def build_retrieval_plan(
    question: str,
    *,
    max_documents: int = 3,
) -> list[RetrievalTask]:
    """为明确的多论文比较问题生成独立检索任务。"""

    if max_documents < 2:
        raise ValueError(
            "max_documents must be at least 2"
        )

    document_ids = extract_document_ids(question)

    if len(document_ids) < 2:
        raise ResearchPlanningError(
            "At least two explicit document IDs are required"
        )

    if len(document_ids) > max_documents:
        raise ResearchPlanningError(
            "Too many document IDs"
        )

    query = choose_retrieval_query(question)

    tasks: list[RetrievalTask] = []

    for index, document_id in enumerate(
        document_ids,
        start=1,
    ):
        tasks.append({
            "task_id": f"T{index}",
            "tool_name": "search_chunks",
            "arguments": {
                "query": query,
                "mode": "literal",
                "document_id": document_id,
                "limit": 5,
            },
            "purpose": (
                f"Collect stored evidence for document {document_id}"
            ),
        })

    return tasks