"""从成功执行的论文工具结果中提取可追踪的结构化证据。"""

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.agent.tool_executor import ToolExecutionResult


class AgentEvidence(BaseModel):
    """记录工具返回的论文证据及其数据库定位信息。"""

    model_config = ConfigDict(extra="forbid", strict=True)

    document_id: int = Field(gt=0)
    chunk_id: int = Field(gt=0)
    title: str = Field(min_length=1)
    page_start: int = Field(ge=1)
    page_end: int = Field(ge=1)
    content: str = Field(min_length=1)


def collect_evidence(
    results: list[ToolExecutionResult],
    *,
    max_evidence: int = 10,
) -> list[AgentEvidence]:
    """只提取成功工具返回的完整证据，并按数据库 ID 去重。"""

    if max_evidence < 1:
        raise ValueError("max_evidence must be positive")

    evidence: list[AgentEvidence] = []
    seen: set[tuple[int, int]] = set()

    for result in results:
        if result.status != "success":
            continue

        if result.name not in {"search_chunks", "get_evidence"}:
            continue

        if result.name == "search_chunks":
            if not isinstance(result.output, list):
                continue
            candidates = result.output
        else:
            if not isinstance(result.output, dict):
                continue
            candidates = [result.output]

        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue

            try:
                item = AgentEvidence.model_validate({
                    key: candidate.get(key)
                    for key in AgentEvidence.model_fields
                })
            except ValidationError:
                continue

            if item.page_end < item.page_start:
                continue

            key = (item.document_id, item.chunk_id)

            if key in seen:
                continue

            seen.add(key)
            evidence.append(item)

            if len(evidence) >= max_evidence:
                return evidence

    return evidence