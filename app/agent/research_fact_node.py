"""将结构化事实提取器接入 LangGraph，并隔离模型执行故障。"""

from app.agent.fact_extractor import FactExtractor
from app.agent.research_state import ResearchState


def make_fact_extraction_node(extractor: FactExtractor):
    """创建使用外部注入 FactExtractor 的工作流节点。"""

    def extract_facts_node(state: ResearchState) -> dict:
        """提取事实并记录引文校验结果，不声明语义支持。"""

        evidence = state["evidence"]

        if not evidence:
            return {
                "fact_verifications": [],
                "extraction_usage": {},
                "steps": state["steps"] + [
                    {
                        "step": "extract_facts",
                        "status": "skipped",
                        "detail": "No retrieved evidence",
                    }
                ],
            }

        try:
            result = extractor.extract(
                question=state["question"],
                evidence=evidence,
            )
        except Exception as exc:
            # 模型解析失败、超时等情况不影响已有数据库证据。
            # 不记录密钥、原始模型响应或敏感异常信息。
            return {
                "fact_verifications": [],
                "extraction_usage": {},
                "steps": state["steps"] + [
                    {
                        "step": "extract_facts",
                        "status": "failed",
                        "detail": type(exc).__name__,
                    }
                ],
            }

        verifications = [
            item.model_dump(mode="json")
            for item in result.verifications
        ]

        return {
            "fact_verifications": verifications,
            "extraction_usage": {
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
                "total_tokens": result.total_tokens,
                "latency_ms": result.latency_ms,
            },
            "steps": state["steps"] + [
                {
                    "step": "extract_facts",
                    "status": "success",
                    "detail": (
                        f"Extracted {len(verifications)} proposed facts; "
                        f"{sum(item['status'] == 'quote_verified' for item in verifications)} "
                        "quotes verified"
                    ),
                }
            ],
        }

    return extract_facts_node