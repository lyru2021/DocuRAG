"""验证检索 SAVEPOINT 能隔离真实 PostgreSQL SQL 错误。"""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.services.retrieval_transaction import run_with_savepoint


def test_savepoint_recovers_after_sql_error(db_session):
    """局部 SQL 错误不应破坏后续查询。"""

    with pytest.raises(DBAPIError):
        run_with_savepoint(
            db_session,
            lambda: db_session.execute(
                text(
                    "SELECT * FROM "
                    "docurag_missing_table_for_test"
                )
            ),
        )

    result = run_with_savepoint(
        db_session,
        lambda: db_session.scalar(text("SELECT 1")),
    )

    assert result == 1


def test_savepoint_does_not_rollback_outer_transaction(db_session):
    """检索失败不应取消外层事务中已执行的写入。"""

    db_session.execute(
        text(
            "CREATE TEMP TABLE IF NOT EXISTS "
            "docurag_savepoint_probe (value INTEGER) "
            "ON COMMIT DROP"
        )
    )

    db_session.execute(
        text(
            "INSERT INTO docurag_savepoint_probe "
            "(value) VALUES (42)"
        )
    )

    with pytest.raises(DBAPIError):
        run_with_savepoint(
            db_session,
            lambda: db_session.execute(
                text(
                    "SELECT * FROM "
                    "docurag_missing_table_for_test"
                )
            ),
        )

    value = db_session.scalar(
        text(
            "SELECT value FROM docurag_savepoint_probe "
            "LIMIT 1"
        )
    )

    assert value == 42


def test_savepoint_rejects_pending_orm_changes(db_session):
    """存在待写入 ORM 对象时，拒绝进入检索 SAVEPOINT。"""

    from app.models.document import Document

    db_session.add(
        Document(
            title="Pending",
            filename="pending.pdf",
        )
    )

    with pytest.raises(RuntimeError, match="clean session"):
        run_with_savepoint(
            db_session,
            lambda: db_session.scalar(text("SELECT 1")),
        )