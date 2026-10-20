"""提供科研 Agent 单轮问答接口及可替换的模型依赖。"""


from fastapi import APIRouter, Depends

from app.agent.llm_adapter import (
    LLMAdapter,
    LLMResponse,
)
from app.agent.mock_llm import MockLLMAdapter
from app.agent.paper_tools import build_paper_tool_registry
from app.agent.research_agent import ResearchAgent
from app.agent.tool_executor import ToolExecutor
from app.schemas.agent import (
    AgentQueryRequest,
    AgentQueryResponse,
    AgentToolRecord,
)
from app.agent.tool_db import make_production_tool_session
from app.agent.evidence import collect_evidence
from app.core.config import get_settings
from app.agent.openai_adapter import OpenAIAdapter


router = APIRouter(prefix="/agent", tags=["agent"])


def get_llm_adapter() -> LLMAdapter:
    """根据显式配置选择模型，禁止故障时静默降级。"""

    settings = get_settings()

    if settings.LLM_PROVIDER == "mock":
        return MockLLMAdapter([
            LLMResponse(
                response_type="final_answer",
                content=(
                    "Mock LLM is configured. "
                    "No real model provider has been called."
                ),
                provider="mock",
                model="mock-function-calling",
            )
        ])

    if settings.LLM_PROVIDER == "openai":
        if settings.OPENAI_API_KEY is None:
            raise RuntimeError(
                "OPENAI_API_KEY is required when "
                "LLM_PROVIDER=openai"
            )

        api_key = (
            settings.OPENAI_API_KEY.get_secret_value()
        )

        if not api_key.strip():
            raise RuntimeError(
                "OPENAI_API_KEY must not be blank"
            )

        return OpenAIAdapter(
            model=settings.OPENAI_MODEL,
            api_key=api_key,
            timeout=settings.OPENAI_TIMEOUT_SECONDS,
        )
    if settings.LLM_PROVIDER == "deepseek":
        if settings.DEEPSEEK_API_KEY is None:
            raise RuntimeError(
                "DEEPSEEK_API_KEY is required when "
                "LLM_PROVIDER=deepseek"
            )

        api_key = (
            settings.DEEPSEEK_API_KEY.get_secret_value()
        )

        if not api_key.strip():
            raise RuntimeError(
                "DEEPSEEK_API_KEY must not be blank"
            )

        return OpenAIAdapter(
            provider="deepseek",
            model=settings.DEEPSEEK_MODEL,
            api_key=api_key,
            base_url="https://api.deepseek.com",
            timeout=settings.DEEPSEEK_TIMEOUT_SECONDS,
        )

    raise RuntimeError(
        "Unsupported LLM provider configuration"
    )

def get_tool_session_factory():
    """提供可在测试中替换的数据库工具事务工厂。"""

    return make_production_tool_session(
        statement_timeout_ms=3000
    )


def get_research_agent(
    session_factory=Depends(get_tool_session_factory),
    llm: LLMAdapter = Depends(get_llm_adapter),
) -> ResearchAgent:
    """创建请求独立的 Agent，数据库仅在工具执行期间使用。"""

    registry = build_paper_tool_registry(
        session_factory
    )

    return ResearchAgent(
        llm=llm,
        executor=ToolExecutor(
            registry,
            max_calls=5,
            max_output_chars=10000,
        ),
        max_llm_calls=6,
    )


@router.post("/query", response_model=AgentQueryResponse)
def query_agent(
    request: AgentQueryRequest,
    agent: ResearchAgent = Depends(get_research_agent),
) -> AgentQueryResponse:
    """执行一轮受控科研 Agent 问答。"""

    result = agent.run(request.question)

    return AgentQueryResponse(
        status=result.status,
        answer=result.answer,
        llm_calls=result.llm_calls,
        tool_calls=result.tool_calls,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        total_tokens=result.total_tokens,
        error_type=result.error_type,
        tools=[
            AgentToolRecord(
                call_id=item.call_id,
                name=item.name,
                status=item.status,
                elapsed_ms=item.elapsed_ms,
                error_type=item.error_type,
            )
            for item in result.tool_results
        ],
        evidence=collect_evidence(result.tool_results),
    )