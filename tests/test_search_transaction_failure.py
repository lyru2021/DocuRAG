"""验证 PostgreSQL 查询错误对共享 Session 后续检索的影响。"""

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError


def test_failed_sql_blocks_following_query(db_session):
    """真实 SQL 错误后，同一事务中的后续查询可能失败。"""

    # 使用真实 PostgreSQL 查询，不使用 Mock。
    db_session.execute(text("SELECT 1"))

    # 故意访问不存在的表，触发 PostgreSQL SQL 错误。
    try:
        db_session.execute(
            text("SELECT * FROM docurag_missing_table_for_test")
        )
    except DBAPIError:
        pass
    else:
        raise AssertionError("Expected PostgreSQL error")

    # PostgreSQL 会拒绝同一失败事务中的后续 SQL。
    try:
        db_session.execute(text("SELECT 1"))
    except DBAPIError:
        blocked = True
    else:
        blocked = False

    assert blocked is True

    # 恢复 Session，避免影响测试夹具清理。
    db_session.rollback()

    assert db_session.scalar(text("SELECT 1")) == 1