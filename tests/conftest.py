"""pytest 公共夹具。

这里集中提供测试数据库 Session、FastAPI 测试客户端和基础测试文档。
"""
import os

import pytest
from dotenv import dotenv_values
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session


def get_test_database_url() -> str:
    """读取并验证独立测试数据库地址。"""

    values = dotenv_values(".env.test")

    url = (
        os.environ.get("TEST_DATABASE_URL")
        or values.get("TEST_DATABASE_URL")
    )

    if not url:
        raise RuntimeError("TEST_DATABASE_URL is required")

    if make_url(url).database != "docurag_test":
        raise RuntimeError("Tests must use docurag_test")

    return url


# 必须在导入应用模块之前完成测试环境初始化。
TEST_DATABASE_URL = get_test_database_url()

os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["ENV_FILE"] = ".env.test"


from app.db.session import get_db
from app.main import app
from app.models.document import Document


@pytest.fixture
def db_session():
    """提供带 SAVEPOINT 隔离的 SQLAlchemy Session。

    被测代码可以正常 commit；测试结束后外层事务统一 rollback，
    从而让每个测试都从干净数据库状态开始。
    """

    engine = create_engine(
        get_test_database_url(),
        pool_pre_ping=True,
    )

    connection = engine.connect()
    transaction = connection.begin()

    db = Session(
        bind=connection,
        join_transaction_mode="create_savepoint",
        expire_on_commit=False,
    )

    try:
        yield db
    finally:
        db.close()

        if transaction.is_active:
            transaction.rollback()

        connection.close()
        engine.dispose()


@pytest.fixture
def client(db_session):
    """返回绑定测试数据库 Session 的 FastAPI 测试客户端。"""

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def sample_document(db_session):
    """创建一个已 flush 的基础文档，供数据库测试复用。"""

    document = Document(
        title="Sample Document",
        filename="sample.pdf",
    )
    db_session.add(document)
    # flush 让数据库生成主键；外层事务仍由 fixture 统一回滚。
    db_session.flush()
    db_session.refresh(document)

    return document
