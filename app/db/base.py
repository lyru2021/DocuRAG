"""SQLAlchemy 声明式基类模块。"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """所有 SQLAlchemy ORM 模型的声明式基类。

    Alembic 会读取 `Base.metadata` 来发现模型对应的表结构。
    """

    pass
