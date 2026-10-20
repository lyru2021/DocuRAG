"""使用 OpenAI Responses API 实现可替换的 Function Calling 适配器。"""

import json
from time import perf_counter

from openai import OpenAI

from app.agent.llm_adapter import (
    LLMMessage,
    LLMResponse,
    LLMUsage,
)
from app.agent.tool_schemas import ToolCall
from app.agent.llm_errors import (
    LLMIncompleteError,
    LLMProtocolError,
    LLMRefusalError,
)


class OpenAIAdapter:
    """将项目内部消息转换为 Responses API 请求与响应。"""

    provider = "openai"

    def __init__(
        self,
        *,
        model: str = "gpt-5-mini",
        api_key: str | None = None,
        timeout: float = 30.0,
        base_url: str | None = None,
        provider: str = "openai",
        client=None,
    ):
        """初始化兼容 Responses API 的模型客户端。"""

        self.provider = provider
        self.model = model

        if client is not None:
            self.client = client
        else:
            kwargs = {
                "api_key": api_key,
                "timeout": timeout,
                "max_retries": 0,
            }

            if base_url is not None:
                kwargs["base_url"] = base_url

            self.client = OpenAI(**kwargs)

    @staticmethod
    def _convert_messages(messages: list[LLMMessage]) -> list[dict]:
        """将内部工具请求与响应还原为 Provider 原生消息。"""

        converted = []

        for message in messages:
            if message.role == "tool":
                converted.append({
                    "type": "function_call_output",
                    "call_id": message.tool_call_id,
                    "output": message.content,
                })
                continue

            if message.role == "assistant":
                # 目前 ResearchAgent 将工具调用序列化为 JSON 数组。
                # 只在确认为内部工具调用结构时转换。
                try:
                    payload = json.loads(message.content)
                except (ValueError, TypeError):
                    payload = None

                if (
                    isinstance(payload, list)
                    and payload
                    and all(
                        isinstance(item, dict)
                        and {"call_id", "name", "arguments"} <= item.keys()
                        for item in payload
                    )
                ):
                    for item in payload:
                        converted.append({
                            "type": "function_call",
                            "call_id": item["call_id"],
                            "name": item["name"],
                            "arguments": json.dumps(
                                item["arguments"],
                                ensure_ascii=False,
                            ),
                        })
                    continue

            converted.append({
                "role": message.role,
                "content": message.content,
            })

        return converted

    def generate(
        self,
        messages: list[LLMMessage],
        tools: list[dict],
    ) -> LLMResponse:
        """调用真实模型并解析文本、工具请求及用量。"""

        start = perf_counter()

        response = self.client.responses.create(
            model=self.model,
            input=self._convert_messages(messages),
            tools=tools,
        )

        elapsed_ms = (perf_counter() - start) * 1000

                # 状态验证必须发生在解析工具调用之前。
        status = getattr(response, "status", None)

        if status == "incomplete":
            raise LLMIncompleteError(
                "provider response is incomplete"
            )

        if status in {"failed", "cancelled", "in_progress", "queued"}:
            raise LLMProtocolError(
                f"provider response is not completed: {status}"
            )

        if status not in {None, "completed"}:
            raise LLMProtocolError(
                f"unexpected provider response status: {status}"
            )

        # 拒绝回答可能位于 message.content 的结构化输出中。
        for item in response.output:
            if getattr(item, "type", None) != "message":
                continue

            for part in getattr(item, "content", []) or []:
                if getattr(part, "type", None) == "refusal":
                    raise LLMRefusalError(
                        "provider refused the request"
                    )

        calls = []

        for item in response.output:
            if item.type != "function_call":
                continue

            try:
                arguments = json.loads(item.arguments)
            except (TypeError, ValueError):
                # 保留非法参数为可验证的结构，交由后端拒绝。
                arguments = {"_invalid_json": item.arguments}

            if not isinstance(arguments, dict):
                arguments = {"_invalid_arguments": arguments}

            calls.append(
                ToolCall(
                    call_id=item.call_id,
                    name=item.name,
                    arguments=arguments,
                )
            )

        usage = response.usage

        normalized_usage = LLMUsage(
            input_tokens=usage.input_tokens if usage else 0,
            output_tokens=usage.output_tokens if usage else 0,
            total_tokens=usage.total_tokens if usage else 0,
        )

        if calls:
            return LLMResponse(
                response_type="tool_calls",
                tool_calls=calls,
                provider=self.provider,
                model=self.model,
                usage=normalized_usage,
                latency_ms=elapsed_ms,
            )

        return LLMResponse(
            response_type="final_answer",
            content=response.output_text or "",
            provider=self.provider,
            model=self.model,
            usage=normalized_usage,
            latency_ms=elapsed_ms,
        )