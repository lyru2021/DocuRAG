"""管理 Agent 数据库工具的独立短事务与 SQL 执行限制。"""

from collections.abc import Callable, Iterator
from contextlib import contextmanager

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import SessionLocal


ToolSessionFactory = Callable[[], Iterator[Session]]


@contextmanager
def production_tool_session(
    statement_timeout_ms: int = 3000,
) -> Iterator[Session]:
    """为单次只读工具查询提供独立事务。"""

    if not 100 <= statement_timeout_ms <= 30000:
        raise ValueError(
            "statement_timeout_ms must be between 100 and 30000"
        )

    # 每次调用创建独立 Session；退出时自动提交或回滚，
    # 无论查询成功还是异常，都释放事务资源。
    with SessionLocal.begin() as db:
        # 必须在查询之前设置只读和事务局部超时。
        db.execute(text("SET TRANSACTION READ ONLY"))

        db.execute(
            text(
                "SELECT set_config("
                "'statement_timeout', :timeout_ms, true)"
            ),
            {"timeout_ms": str(statement_timeout_ms)},
        )

        yield db


def make_production_tool_session(
    statement_timeout_ms: int = 3000,
):
    """生成可注入 Registry 的工具 Session 工厂。"""

    @contextmanager
    def factory() -> Iterator[Session]:
        with production_tool_session(
            statement_timeout_ms
        ) as db:
            yield db

    return factory


def make_test_tool_session(db_session: Session):
    """复用 pytest 测试事务，并通过 SAVEPOINT 隔离工具查询。"""

    @contextmanager
    def factory() -> Iterator[Session]:
        # 测试数据可能尚未提交，必须使用同一测试 Session。
        # 此处不设置整个事务只读，否则会影响测试夹具。
        with db_session.begin_nested():
            yield db_session

    return factory