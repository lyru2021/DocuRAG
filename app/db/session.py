"""数据库连接和 FastAPI Session 依赖。"""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()

engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    echo=False,
)

SessionLocal = sessionmaker(
    autoflush=False,
    bind=engine,
    expire_on_commit=False,
)


def get_db() -> Generator[Session, None, None]:
    """为 FastAPI 依赖注入提供数据库 Session。

    Yields:
        Session: 当前请求范围内使用的 SQLAlchemy Session。

    Notes:
        事务提交和回滚由仓储层显式处理，这里只负责关闭连接资源。
    """

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
