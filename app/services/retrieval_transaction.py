"""为只读检索操作提供 PostgreSQL SAVEPOINT 故障隔离。"""

from collections.abc import Callable
from typing import TypeVar

from sqlalchemy.orm import Session


T = TypeVar("T")


def run_with_savepoint(
    db: Session,
    operation: Callable[[], T],
) -> T:
    """在独立 SAVEPOINT 中执行检索，失败时仅回滚局部事务。"""

    if db.new or db.dirty or db.deleted:
        raise RuntimeError(
            "retrieval savepoint requires a clean session"
        )

    # begin_nested 会建立 SAVEPOINT。
    # 操作抛出异常时，上下文管理器只回滚该 SAVEPOINT。
    with db.begin_nested():
        return operation()