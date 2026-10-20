"""根据缺失研究字段公平分配补充检索任务。"""

from collections import deque

from app.agent.research_state import RetrievalTask


FIELD_QUERIES = {
    "method": "model",
    "experimental_conditions": "dataset",
    "conclusion": "results",
}


def plan_supplementary_tasks(
    missing_fields: dict[int, list[str]],
    *,
    max_tasks: int = 3,
) -> list[RetrievalTask]:
    """按论文轮流分配补检机会，避免第一篇论文占满预算。"""

    if max_tasks < 1:
        raise ValueError("max_tasks must be positive")

    # 只保留合法文档 ID 和可识别的缺失字段。
    # dict 保留输入顺序，保证测试结果可重复。
    queues: dict[int, deque[str]] = {}

    for document_id, fields in missing_fields.items():
        if type(document_id) is not int or document_id <= 0:
            continue

        valid_fields = list(dict.fromkeys(
            field
            for field in fields
            if field in FIELD_QUERIES
        ))

        if valid_fields:
            queues[document_id] = deque(valid_fields)

    tasks: list[RetrievalTask] = []

    # 每轮从每篇论文取出一个缺失字段。
    # 因此论文31不会在论文32之前连续占用三个名额。
    while queues and len(tasks) < max_tasks:
        for document_id in list(queues):
            if len(tasks) >= max_tasks:
                break

            fields = queues[document_id]

            if not fields:
                del queues[document_id]
                continue

            field = fields.popleft()
            query = FIELD_QUERIES[field]

            tasks.append({
                "task_id": f"S{len(tasks) + 1}",
                "tool_name": "search_chunks",
                "arguments": {
                    "query": query,
                    "mode": "literal",
                    "document_id": document_id,
                    "limit": 5,
                },
                "purpose": (
                    f"Supplement missing {field} evidence "
                    f"for document {document_id}"
                ),
            })

            if not fields:
                del queues[document_id]

    return tasks