"""验证科研 Agent 工具注册表的白名单与安全约束。"""

import pytest

from app.agent.tool_registry import (
    DuplicateToolError,
    RegisteredTool,
    ToolRegistry,
    UnknownToolError,
)
from app.agent.tool_schemas import (
    GetEvidenceArgs,
    SearchChunksArgs,
    SearchPapersArgs,
)


def make_tool(name: str, args_model=SearchChunksArgs):
    """构造不访问数据库的测试工具。"""

    return RegisteredTool(
        name=name,
        description=f"Test tool: {name}",
        args_model=args_model,
        handler=lambda args: [],
    )


def test_registry_registers_known_tool():
    """注册后的工具应可通过名称获取。"""

    registry = ToolRegistry()
    tool = make_tool("search_chunks")

    registry.register(tool)

    assert registry.get("search_chunks") is tool


def test_registry_rejects_unknown_tool():
    """不存在的工具名称不得执行。"""

    registry = ToolRegistry()

    with pytest.raises(
        UnknownToolError,
        match="unknown tool",
    ):
        registry.get("execute_python")


def test_registry_rejects_duplicate_name():
    """同名工具不能被第二次覆盖。"""

    registry = ToolRegistry()
    registry.register(make_tool("search_chunks"))

    with pytest.raises(DuplicateToolError):
        registry.register(make_tool("search_chunks"))


def test_registry_rejects_blank_name():
    """空工具名称不得注册。"""

    registry = ToolRegistry()

    with pytest.raises(ValueError):
        registry.register(make_tool("   "))


def test_registry_names_are_sorted():
    """工具列表顺序应稳定。"""

    registry = ToolRegistry()

    registry.register(make_tool("search_chunks"))
    registry.register(make_tool("get_evidence", GetEvidenceArgs))
    registry.register(make_tool("search_papers", SearchPapersArgs))

    assert registry.names() == [
        "get_evidence",
        "search_chunks",
        "search_papers",
    ]


def test_registry_definitions_include_json_schema():
    """Provider 工具描述应携带对应参数 Schema。"""

    registry = ToolRegistry()
    registry.register(make_tool("search_chunks"))

    definitions = registry.definitions()

    assert len(definitions) == 1

    definition = definitions[0]

    assert definition["type"] == "function"
    assert definition["name"] == "search_chunks"
    assert "parameters" in definition

    schema = definition["parameters"]

    assert "query" in schema["properties"]
    assert schema["additionalProperties"] is False


def test_registry_get_does_not_execute_handler():
    """仅查询工具注册信息时不得产生执行副作用。"""

    calls = []

    registry = ToolRegistry()
    registry.register(
        RegisteredTool(
            name="search_chunks",
            description="Search chunks",
            args_model=SearchChunksArgs,
            handler=lambda args: calls.append(args),
        )
    )

    registry.get("search_chunks")
    registry.definitions()

    assert calls == []