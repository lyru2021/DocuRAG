"""验证 Agent 数据库工具的短事务与测试隔离机制。"""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.agent.tool_db import (
    make_test_tool_session,
    production_tool_session,
)


def test_production_tool_session_is_read_only():
    """生产工具事务必须只读且设置语句超时。"""

    with production_tool_session(
        statement_timeout_ms=3000
    ) as db:
        read_only = db.scalar(
            text("SHOW transaction_read_only")
        )
        timeout = db.scalar(
            text("SHOW statement_timeout")
        )

        assert read_only == "on"
        assert timeout == "3s"


def test_production_tool_session_releases_transaction():
    """离开工具上下文后必须结束数据库事务。"""

    with production_tool_session() as db:
        connection = db.connection()
        assert connection.in_transaction()

    assert not db.in_transaction()


def test_production_tool_session_rejects_write():
    """只读事务不能修改数据库。"""

    with pytest.raises(DBAPIError):
        with production_tool_session() as db:
            db.execute(
                text(
                    "INSERT INTO documents "
                    "(title, filename) "
                    "VALUES ('Forbidden', 'forbidden.pdf')"
                )
            )


def test_test_tool_session_reads_fixture_data(db_session):
    """测试工具必须能读取当前 SAVEPOINT 内的数据。"""

    from app.models.document import Document

    document = Document(
        title="Agent Session Test",
        filename="agent_session_test.pdf",
    )
    db_session.add(document)
    db_session.flush()

    factory = make_test_tool_session(db_session)

    with factory() as db:
        title = db.scalar(
            text(
                "SELECT title FROM documents WHERE id = :id"
            ),
            {"id": document.id},
        )

    assert title == document.title


def test_test_tool_session_keeps_outer_transaction(db_session):
    """工具完成后不能结束 pytest 管理的测试事务。"""

    factory = make_test_tool_session(db_session)

    with factory() as db:
        assert db.scalar(text("SELECT 1")) == 1

    assert db_session.is_active
    assert db_session.scalar(text("SELECT 1")) == 1